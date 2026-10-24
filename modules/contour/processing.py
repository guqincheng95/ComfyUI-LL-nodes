"""Batch-safe mask construction; all temporal state is local to one execution."""
import math
import numpy as np
from PIL import Image
from .geometry import parse_frames, parse_person, render_person, refine_mask
from .extremities import extremity_regions, extremity_support

DEFAULTS = dict(head_scale=1.0, torso_scale=1.0, arm_scale=1.0, leg_scale=1.0,
                padding_px=4, feather_px=2, confidence=0.3, temporal_smoothing=0.0,
                person_index=0, background_value=0.0, coordinate_mode='auto', missing_pose='keep',
                foot_protection=True, foot_scale=1.2, hand_protection=True, hand_scale=1.15)


def validate_options(options):
    unknown = set(options) - set(DEFAULTS)
    if unknown:
        raise ValueError(f'未知参数：{sorted(unknown)}')
    values = {**DEFAULTS, **options}
    for key, (lo, hi) in {
        'head_scale': (0.4, 2.0), 'torso_scale': (0.4, 2.0), 'arm_scale': (0.4, 2.0),
        'leg_scale': (0.4, 2.0), 'confidence': (0.0, 1.0), 'temporal_smoothing': (0.0, 0.9),
        'background_value': (0.0, 1.0),
        'foot_scale': (0.5, 3.0), 'hand_scale': (0.5, 3.0),
    }.items():
        v = values[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f'{key} 必须在 {lo}～{hi} 之间。')
    for key, lo, hi in [('padding_px', 0, 64), ('feather_px', 0, 32), ('person_index', -1, 99)]:
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(f'{key} 必须为 {lo}～{hi} 的整数。')
    for key in ('foot_protection', 'hand_protection'):
        if type(values[key]) is not bool:
            raise ValueError(f'{key} 必须为布尔值。')
    if values['coordinate_mode'] not in ('auto', 'pixels', 'normalized'):
        raise ValueError('coordinate_mode 只能为 auto / pixels / normalized。')
    if values['missing_pose'] not in ('keep', 'error'):
        raise ValueError('missing_pose 只能为 keep / error。')
    return values


def _mask_input(mask, batch, height, width, label):
    if mask is None:
        return None
    value = np.asarray(mask, dtype=np.float32)
    if value.ndim == 2:
        value = value[None]
    if value.ndim != 3 or min(value.shape) <= 0 or value.shape[0] not in (1, batch):
        raise ValueError(f'{label} 必须为 [1或{batch}, H, W]，且与深度图使用同一裁切/画布。')
    if not np.isfinite(value).all() or value.min() < 0 or value.max() > 1:
        raise ValueError(f'{label} 必须是 0～1 的有限 MASK。')
    if value.shape[1:] != (height, width):
        if abs((value.shape[2] / value.shape[1]) / (width / height) - 1) > 0.02:
            raise ValueError(f'{label} 与深度图的宽高比不一致；请先对齐裁切范围，不能直接拉伸。')
        value = np.stack([np.asarray(Image.fromarray(frame).resize((width, height), Image.Resampling.BILINEAR)) for frame in value])
    return value


def _smooth(current, previous, amount):
    if previous is None or not amount:
        return current
    b, old = current['body'], previous['body']
    if b.shape != old.shape or len(b) != 18:
        return current
    core = [2, 5, 8, 11]
    if not np.isfinite(b[core]).all() or not np.isfinite(old[core]).all():
        return current
    scale = np.linalg.norm((b[8, :2] + b[11, :2] - b[2, :2] - b[5, :2]) / 2)
    if np.linalg.norm(np.mean(b[core, :2] - old[core, :2], axis=0)) > max(4, scale * 0.6):
        return current  # scene cut / discontinuity: never trail a distant previous person
    result = {}
    for key, points in current.items():
        result[key] = points.copy()
        prev = previous.get(key)
        if prev is not None and prev.shape == points.shape:
            valid = np.isfinite(points).all(axis=1) & np.isfinite(prev).all(axis=1)
            result[key][valid, :2] = points[valid, :2] * (1 - amount) + prev[valid, :2] * amount
    return result


def build_masks(keypoints, batch, height, width, *, foreground_mask=None, protect_mask=None,
                exclude_mask=None, **options):
    opts = validate_options(options)
    if min(batch, height, width) <= 0 or height * width > 64_000_000:
        raise ValueError('图像批量/尺寸无效或单帧超过 6400 万像素。')
    frames = parse_frames(keypoints)
    if len(frames) not in (1, batch):
        raise ValueError(f'深度图有 {batch} 帧，骨架有 {len(frames)} 帧；必须逐帧对应，或单帧骨架用于静态批量。')
    fg = _mask_input(foreground_mask, batch, height, width, 'foreground_mask')
    protect = _mask_input(protect_mask, batch, height, width, 'protect_mask')
    exclude = _mask_input(exclude_mask, batch, height, width, 'exclude_mask')
    # Work on a bounded mask canvas, never rescale the source IMAGE.
    ratio = min(1.0, 1024 / max(height, width))
    ww, hh = max(1, round(width * ratio)), max(1, round(height * ratio))
    output, reports, previous, part_counts = [], [], {}, {'foot':0, 'hand':0, 'fallback':0}
    for frame_index in range(batch):
        cw, ch, people = frames[0 if len(frames) == 1 else frame_index]
        observed = None if fg is None else fg[0 if len(fg) == 1 else frame_index]
        small_fg = None if observed is None else np.asarray(Image.fromarray(observed).resize((ww, hh), Image.Resampling.BILINEAR))
        indexes = list(range(len(people))) if opts['person_index'] == -1 else [opts['person_index']]
        combined = np.zeros((hh, ww), dtype=np.float32)
        automatic = np.zeros_like(combined)
        reasons = []
        if not people or any(index >= len(people) for index in indexes):
            reasons.append('未检测到指定人物')
        else:
            for index in indexes:
                parsed = parse_person(people[index], (cw, ch), (ww, hh), opts['confidence'], opts['coordinate_mode'])
                # No identity tracker: disable smoothing for multiple detections to avoid person-order mixing.
                smoothed = _smooth(parsed, previous.get(index), opts['temporal_smoothing'] if len(people) == 1 else 0)
                mask, reason = render_person(smoothed, ww, hh, foreground=small_fg,
                                            **{k: opts[k] for k in ('head_scale', 'torso_scale', 'arm_scale', 'leg_scale')})
                if mask is None:
                    previous.pop(index, None)
                    reasons.append(f'人物 {index}：{reason}')
                else:
                    previous[index] = smoothed
                    combined = np.maximum(combined, mask)
                    parts = extremity_regions(smoothed, ww, hh, foreground=small_fg,
                        **{k:opts[k] for k in ('foot_protection','foot_scale','hand_protection','hand_scale')})
                    automatic = np.maximum(automatic, extremity_support(parts, combined.shape))
                    for part in parts:
                        part_counts[part['kind']] += 1
                        part_counts['fallback'] += part['source'] != 'wholebody_landmarks'
        if reasons:
            if opts['missing_pose'] == 'error':
                raise ValueError(f'第 {frame_index + 1} 帧：' + '；'.join(reasons))
            # Safe fallback: never silently delete an undetected arm/person.
            combined.fill(1)
            reports.append(f'第 {frame_index + 1} 帧未修剪：' + '；'.join(reasons))
            previous.clear()
        else:
            combined = refine_mask(combined, round(opts['padding_px'] * ratio), round(opts['feather_px'] * ratio))
            combined = np.maximum(combined, automatic)
        if (ww, hh) != (width, height):
            combined = np.asarray(Image.fromarray(combined).resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32)
        if protect is not None:
            combined = np.maximum(combined, protect[0 if len(protect) == 1 else frame_index])
        if observed is not None:
            # Intersection: original background holes remain holes; no hidden surface is invented.
            combined = np.minimum(combined, observed)
        if exclude is not None:
            combined *= 1 - exclude[0 if len(exclude) == 1 else frame_index]
        output.append(np.clip(combined, 0, 1))
    report = f'{batch} 帧；{batch - len(reports)} 帧完成轮廓修剪；{len(reports)} 帧安全保留。'
    report += ' 已使用原图前景轮廓观测部位宽度。' if fg is not None else ' 建议连接原图背景移除的 MASK，提高边界贴合度。'
    report += f" 手脚保护：脚掌{part_counts['foot']}处，手掌{part_counts['hand']}处，局部估计{part_counts['fallback']}处；脚掌范围{opts['foot_scale']}，手掌范围{opts['hand_scale']}。"
    if fg is None and (opts['foot_protection'] or opts['hand_protection']):
        report += ' 未接前景MASK：手脚保护使用有界几何范围，可能保留附近背景。'
    if batch > 1 and len(frames) == 1:
        report += ' 注意：单帧骨架已重复用于全部图像；运动视频应逐帧提供骨架。'
    resized_count = sum(value is not None and np.asarray(value).shape[-2:] != (height, width) for value in (foreground_mask, protect_mask, exclude_mask))
    if resized_count:
        report += f' 已将 {resized_count} 路等比例遮罩对齐到深度图尺寸。'
    if reports:
        report += '\n' + '\n'.join(reports[:10]) + ('\n其余提示省略。' if len(reports) > 10 else '')
    return np.stack(output), report
