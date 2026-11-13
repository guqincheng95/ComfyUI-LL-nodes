"""Single-pass spatial mixing. All image arithmetic is linear-light float32.

The low/high frequency split is an approximation, not access to model layers.
Masks select enhancement strength; they never remove a subject from the input.
"""
from __future__ import annotations

import numpy as np


def cv():
    try:
        import cv2
        return cv2
    except ImportError as exc:
        raise RuntimeError('缺少 OpenCV，请运行 setup_dlss5.bat 补齐环境。') from exc


def linear(rgb):
    rgb = np.asarray(rgb, dtype=np.float32).clip(0, 1)
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)


def srgb(rgb):
    rgb = np.asarray(rgb, dtype=np.float32).clip(0, 1)
    return np.where(rgb <= .0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - .055).clip(0, 1)


def luminance(rgb):
    return np.sum(rgb * np.array([.2126, .7152, .0722], np.float32), axis=-1, keepdims=True)


def blur(array, sigma):
    return cv().GaussianBlur(array, (0, 0), max(.1, float(sigma)), borderType=cv().BORDER_REFLECT_101)


def resize_image(frame, width, height):
    """Normalized-coordinate scaling; straight alpha uses premultiplied colour."""
    frame = np.asarray(frame, dtype=np.float32)
    if frame.ndim != 3 or frame.shape[-1] not in (3, 4) or not np.isfinite(frame).all():
        raise ValueError('图像必须是有限的 H×W×3/4 RGB/RGBA 数据。')
    if frame.shape[:2] == (height, width):
        return frame.clip(0, 1).copy()
    method = cv().INTER_AREA if width < frame.shape[1] or height < frame.shape[0] else cv().INTER_LINEAR
    colour = linear(frame[..., :3])
    if frame.shape[-1] == 4:
        alpha = frame[..., 3:4].clip(0, 1)
        packed = np.concatenate([colour * alpha, alpha], axis=-1)
        packed = cv().resize(packed, (width, height), interpolation=method)
        alpha = packed[..., 3:4].clip(0, 1)
        colour = np.divide(packed[..., :3], alpha, out=np.zeros_like(packed[..., :3]), where=alpha > 1e-7)
        return np.concatenate([srgb(colour), alpha], axis=-1)
    return srgb(cv().resize(colour, (width, height), interpolation=method))


def mask_batch(mask, count, source_hw, target_hw, name='遮罩'):
    """Accept Comfy MASK [H,W], [B,H,W] or [B,H,W,1]; never cycle batches."""
    if mask is None:
        return None
    if hasattr(mask, 'detach'):
        mask = mask.detach().float().cpu().numpy()
    mask = np.asarray(mask, dtype=np.float32)
    if mask.ndim == 2:
        mask = mask[None]
    if mask.ndim == 4 and mask.shape[-1] == 1:
        mask = mask[..., 0]
    if mask.ndim != 3 or min(mask.shape) < 1 or not np.isfinite(mask).all():
        raise ValueError(f'{name}需为有限的 [H,W] 或 [B,H,W]，白色表示选中。')
    if mask.shape[0] not in (1, count):
        raise ValueError(f'{name}有 {mask.shape[0]} 帧，图像有 {count} 帧；只支持单张广播或逐帧一一对应。')
    sh, sw = source_hw
    mh, mw = mask.shape[1:]
    # Allow differently sized masks, but don't silently distort another aspect ratio.
    if abs(mw / mh - sw / sh) > max(2 / sh, 2 / mh):
        raise ValueError(f'{name}宽高比与图像不同，请先使用同一次裁切／补边对齐，不能只强制拉伸。')
    th, tw = target_hw
    # Retain one broadcast mask, do not allocate count copies for a video.
    return np.stack([cv().resize(m, (tw, th), interpolation=cv().INTER_LINEAR)
                     if m.shape != target_hw else m.copy() for m in mask]).clip(0, 1)


def prepare_mask(mask, feather=6., expand=0.):
    result = mask.copy()
    radius = int(round(abs(expand)))
    if radius:
        kernel = cv().getStructuringElement(cv().MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        result = (cv().dilate if expand > 0 else cv().erode)(result, kernel)
    if feather > 0:
        result = blur(result, max(.1, feather / 3))
    return result.clip(0, 1)


def boundary_band(mask, radius=6.):
    binary = (mask >= .5).astype(np.uint8)
    if not binary.any() or binary.all():
        return np.zeros_like(mask)
    inside = cv().distanceTransform(binary, cv().DIST_L2, 3)
    outside = cv().distanceTransform(1 - binary, cv().DIST_L2, 3)
    return (1 - (inside + outside) / max(1., radius)).clip(0, 1)


def _gamut_with_luminance(rgb, target_y):
    """Compress colour towards equal-luminance grey instead of clipping channels."""
    y = target_y.clip(0, 1)
    rgb = rgb * y / np.maximum(luminance(rgb), 1e-7)
    offset = rgb - y
    positive = np.where(offset > 1e-7, (1 - y) / np.maximum(offset, 1e-7), np.inf)
    negative = np.where(offset < -1e-7, y / np.maximum(-offset, 1e-7), np.inf)
    amount = np.minimum(1., np.minimum(positive, negative).min(axis=-1, keepdims=True))
    return (y + offset * amount).clip(0, 1)


def protect_colour(source, result, neutral_strength, skin_mask, skin_strength, sigma, colour_state=None, reset=True, visible=None):
    """Same-scene neutral anchors and visible skin masks; never a global palette match."""
    report = {'neutral_samples': 0, 'skin_samples': 0}
    if neutral_strength > 0:
        source_srgb = srgb(source)
        maximum = source_srgb.max(axis=-1)
        saturation = (maximum - source_srgb.min(axis=-1)) / np.maximum(maximum, 1e-6)
        y = luminance(source)[..., 0]
        anchors = (saturation < .12) & (y > .06) & (y < .8)
        if visible is not None:
            anchors &= visible
        report['neutral_samples'] = int(anchors.sum())
        if anchors.sum() >= 32:
            a = source[anchors] / np.maximum(luminance(source)[anchors], 1e-5)
            b = result[anchors] / np.maximum(luminance(result)[anchors], 1e-5)
            # Bounded chromatic correction, retaining the new luminance field.
            log_gain = np.median(np.log(np.maximum(a, 1e-5) / np.maximum(b, 1e-5)), axis=0).clip(-.12, .12) * neutral_strength
            if colour_state is not None:
                if not reset and 'log_gain' in colour_state:
                    log_gain = colour_state['log_gain'] * .7 + log_gain * .3
                colour_state['log_gain'] = log_gain.copy()
            gain = np.exp(log_gain)
            result = _gamut_with_luminance(result * gain, luminance(result))
            report['neutral_rgb_gain'] = gain.tolist()
        else:
            report['neutral_skipped'] = '缺少可靠中性色样本，未套用全图统计仿色。'
            if colour_state is not None:
                colour_state.pop('log_gain', None)
    if skin_mask is not None and skin_strength > 0:
        active = skin_mask > .05
        report['skin_samples'] = int(active.sum())
        if active.any():
            # Mask-normalized smoothing avoids bleeding clothing colours into skin.
            w = blur(skin_mask, sigma)[..., None]
            sampled = blur(source * skin_mask[..., None], sigma) / np.maximum(w, 1e-6)
            target = _gamut_with_luminance(sampled, luminance(result))
            weight = (skin_mask * skin_strength)[..., None]
            result = result * (1 - weight) + target * weight
    elif skin_strength > 0:
        report['skin_skipped'] = '未接可见皮肤遮罩；不会把整人遮罩当作皮肤。'
    return result, report


def compose(source, enhanced, person_mask=None, skin_mask=None, *, mode='unified_lighting',
            person_strength=.35, background_strength=1., lighting_strength=.7,
            neutral_protection=.35, skin_protection=.6, feather=6., expand=0., edge_guard=.7,
            colour_state=None, reset=True):
    if source.shape[:2] != enhanced.shape[:2]:
        raise ValueError('内部原图与增强图尺寸不一致，已停止融合。')
    if mode not in ('unified_lighting', 'regional_all'):
        raise ValueError('未知区域融合模式。')
    values = (person_strength, background_strength, lighting_strength,
              neutral_protection, skin_protection, edge_guard)
    if any(not np.isfinite(x) or not 0 <= x <= 1 for x in values):
        raise ValueError('增强／保护强度必须在 0～1 内。')
    if not np.isfinite(feather) or not 0 <= feather <= 512 or not np.isfinite(expand) or abs(expand) > 512:
        raise ValueError('遮罩羽化／扩缩范围超出限制。')
    a, b = linear(source[..., :3]), linear(enhanced[..., :3])
    sigma = max(1., min(source.shape[:2]) * .006)
    mask = prepare_mask(person_mask, feather, expand) if person_mask is not None else np.zeros(a.shape[:2], np.float32)
    weight = background_strength + (person_strength - background_strength) * mask
    band = boundary_band(mask, max(2., feather + 2.)) if person_mask is not None else np.zeros_like(mask)
    conservative = min(person_strength, background_strength)
    weight = weight * (1 - band * edge_guard) + conservative * band * edge_guard
    delta = b - a
    if mode == 'unified_lighting':
        broad = blur(delta, sigma)
        mixed = a + broad * lighting_strength + (delta - broad) * weight[..., None]
    else:
        mixed = a + delta * weight[..., None]
    mixed = mixed.clip(0, 1)
    visible = source[..., 3] > .5 if source.shape[-1] == 4 else None
    if skin_mask is not None and visible is not None:
        skin_mask = skin_mask * source[..., 3]
    mixed, report = protect_colour(a, mixed, neutral_protection, skin_mask, skin_protection, sigma,
                                   colour_state, reset, visible)
    result = srgb(mixed)
    if source.shape[-1] == 4:
        result = np.concatenate([result, source[..., 3:4]], axis=-1)
    report.update(mode=mode, person_mask_connected=person_mask is not None,
                  mean_detail_strength=float(weight.mean()), boundary_pixels=int((band > 0).sum()),
                  lighting_separation='低／高频近似分离，不是模型内部光照缓冲')
    return result.astype(np.float32), mask.astype(np.float32), report


class TemporalMask:
    """Backward-flow propagation constrained by current masks, reset on cuts.

    No static-coordinate averaging, so a moving hand doesn't leave a mask trail.
    """
    def __init__(self, strength=.4):
        self.strength = strength
        self.previous = None

    def process(self, mask, motion, reset):
        if mask is None:
            self.previous = None
            return None
        if self.previous is None or reset or self.strength <= 0:
            self.previous = mask.copy()
            return mask
        h, w = mask.shape
        flow = cv().resize(motion.astype(np.float32), (w, h), interpolation=cv().INTER_LINEAR)
        flow[..., 0] *= w / motion.shape[1]
        flow[..., 1] *= h / motion.shape[0]
        yy, xx = np.mgrid[:h, :w].astype(np.float32)
        warped = cv().remap(self.previous, xx + flow[..., 0], yy + flow[..., 1],
                           cv().INTER_LINEAR, borderMode=cv().BORDER_CONSTANT, borderValue=0)
        confidence = (1 - np.abs(warped - mask) / .3).clip(0, 1) * self.strength
        result = mask * (1 - confidence) + warped * confidence
        self.previous = result.copy()
        return result


def comparison(source, enhanced, roi_mask=None, x=0., y=0., width=1., height=1.):
    """Crop *after* full-context processing, source and result side by side."""
    h, w = enhanced.shape[:2]
    source = resize_image(source, w, h)
    if roi_mask is not None and np.any(roi_mask > .1):
        yy, xx = np.where(roi_mask > .1)
        x0, x1, y0, y1 = max(0, xx.min() - 8), min(w, xx.max() + 9), max(0, yy.min() - 8), min(h, yy.max() + 9)
    else:
        x0, y0 = min(w - 1, int(x * w)), min(h - 1, int(y * h))
        x1, y1 = min(w, x0 + max(1, int(width * w))), min(h, y0 + max(1, int(height * h)))
    left, right = source[y0:y1, x0:x1, :3], enhanced[y0:y1, x0:x1, :3]
    return np.concatenate([left, right], axis=1), {'x': int(x0), 'y': int(y0), 'width': int(x1 - x0), 'height': int(y1 - y0)}
