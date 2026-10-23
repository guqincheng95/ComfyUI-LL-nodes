"""OpenPose envelopes fitted to observed foreground boundaries.

Uses Pillow's mature polygon/ellipse rasterization, Gaussian filtering and
morphological filters. Input contract is ComfyUI SDPose's OpenPose frame format.
No pose estimation, segmentation model, body reconstruction or inpainting here.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BODY25_TO_18 = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)
CORE = (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)


def parse_frames(keypoints):
    if isinstance(keypoints, dict):
        keypoints = [keypoints]
    if not isinstance(keypoints, (list, tuple)) or not keypoints:
        raise ValueError('keypoints 必须连接 SDPose / DWPose 的 POSE_KEYPOINT 输出，不是彩色骨架图片。')
    frames = []
    for i, frame in enumerate(keypoints):
        if not isinstance(frame, dict) or 'people' not in frame:
            raise ValueError(f'第 {i + 1} 帧不是 OpenPose frame 字典。')
        try:
            w, h = float(frame['canvas_width']), float(frame['canvas_height'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('骨架数据缺少有效的 canvas_width / canvas_height。') from exc
        if not math.isfinite(w + h) or w <= 0 or h <= 0:
            raise ValueError('骨架画布尺寸必须为有限正数。')
        if not isinstance(frame['people'], list):
            raise ValueError('people 必须为人物字典列表。')
        frames.append((w, h, frame['people']))
    return frames


def _points(flat, sx, sy, cw, ch, threshold, normalized):
    try:
        points = np.asarray(flat, dtype=np.float64)
    except (ValueError, TypeError) as exc:
        raise ValueError('关键点必须为 [x,y,score,...] 数值数组。') from exc
    if points.size == 0:
        return np.empty((0, 3), dtype=np.float64)
    if points.size % 3:
        raise ValueError('关键点数组长度必须为 3 的倍数。')
    points = points.reshape(-1, 3).copy()
    if normalized:
        points[:, 0] *= cw
        points[:, 1] *= ch
    good = np.isfinite(points).all(axis=1) & (points[:, 2] >= threshold) & (points[:, 2] > 0)
    good &= (points[:, 0] >= -cw * 0.25) & (points[:, 0] <= cw * 1.25)
    good &= (points[:, 1] >= -ch * 0.25) & (points[:, 1] <= ch * 1.25)
    points[:, 0] *= sx
    points[:, 1] *= sy
    points[~good] = np.nan
    return points


def parse_person(person, frame_size, target_size, threshold=0.3, coordinate_mode='auto'):
    if not isinstance(person, dict):
        raise ValueError('每个人物必须是 OpenPose 字典。')
    cw, ch = frame_size
    tw, th = target_size
    raw = person.get('pose_keypoints_2d', [])
    a = np.asarray(raw, dtype=np.float64)
    if a.size % 3:
        raise ValueError('pose_keypoints_2d 长度必须为 3 的倍数。')
    a = a.reshape(-1, 3)
    confident = a[np.isfinite(a).all(axis=1) & (a[:, 2] > 0)]
    normalized = coordinate_mode == 'normalized'
    if coordinate_mode == 'auto':
        normalized = bool(len(confident) and np.min(confident[:, :2]) >= 0 and np.max(confident[:, :2]) <= 1)
    values = {name: _points(person.get(name, []), tw / cw, th / ch, cw, ch, threshold, normalized)
              for name in ('pose_keypoints_2d', 'face_keypoints_2d', 'hand_left_keypoints_2d',
                           'hand_right_keypoints_2d', 'foot_keypoints_2d')}
    body = values['pose_keypoints_2d']
    if len(body) == 25:
        if not len(values['foot_keypoints_2d']):
            values['foot_keypoints_2d'] = body[[19, 20, 21, 22, 23, 24]].copy()
        body = body[list(BODY25_TO_18)]
    elif len(body) not in (0, 18):
        raise ValueError(f'支持 OpenPose BODY_18 / BODY_25，当前为 {len(body)} 点。请勿直接输入 COCO 数组。')
    values['body'] = body
    return values


def _valid(p):
    return len(p) and np.isfinite(p[:2]).all()


def _unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-6)


def _perp(v):
    return np.array([-v[1], v[0]])


def _disk(draw, point, radius):
    x, y = point
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)


def _capsule(draw, a, b, ra, rb=None):
    rb = ra if rb is None else rb
    n = _perp(_unit(b - a))
    draw.polygon([tuple(a + n * ra), tuple(b + n * rb), tuple(b - n * rb), tuple(a - n * ra)], fill=255)
    _disk(draw, a, ra)
    _disk(draw, b, rb)


def _ellipse(draw, center, axis, rx, ry):
    normal = _perp(axis)
    polygon = [tuple(center + normal * rx * math.cos(t) + axis * ry * math.sin(t))
               for t in np.linspace(0, 2 * math.pi, 64, endpoint=False)]
    draw.polygon(polygon, fill=255)


def observed_width(foreground, centers, normal, base):
    """Fit only nearby, continuous foreground boundaries; reject wide garment spans.

    A skirt or cape extending beyond the bounded search range cannot inflate the
    estimate. This is observed clothed-surface width, not hidden anatomy recovery.
    """
    if foreground is None:
        return base
    h, w = foreground.shape
    distances = np.linspace(0, base * 1.6, max(8, int(base * 2)))
    estimates = []
    for center in centers:
        sides = []
        for sign in (-1, 1):
            points = center[None, :] + sign * distances[:, None] * normal
            xs, ys = np.rint(points[:, 0]).astype(int), np.rint(points[:, 1]).astype(int)
            inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
            samples = np.zeros(len(points), dtype=bool)
            samples[inside] = foreground[ys[inside], xs[inside]] >= 0.5
            # An off-center/missing foreground observation is not trustworthy.
            if not samples[0]:
                break
            edge = np.flatnonzero(~samples)
            if not len(edge):
                break
            sides.append(distances[edge[0]])
        if len(sides) == 2:
            estimates.append(sum(sides) / 2)
    if not estimates:
        return base
    return float(np.clip(np.median(estimates), base * 0.65, base * 1.15))


def render_person(parsed, width, height, *, foreground=None, head_scale=1.0,
                  torso_scale=1.0, arm_scale=1.0, leg_scale=1.0):
    body = parsed['body']
    if len(body) != 18 or not all(_valid(body[i]) for i in CORE):
        return None, '身体主关键点缺失或置信度不足，保留原帧'
    p = body[:, :2]
    shoulders = (p[2] + p[5]) / 2
    hips = (p[8] + p[11]) / 2
    length = float(np.linalg.norm(hips - shoulders))
    if length < 6:
        return None, '躯干尺度过小，保留原帧'
    axis = _unit(hips - shoulders)
    normal = _perp(axis)
    shoulder_half = max(abs(float(np.dot(p[5] - p[2], normal))) / 2, length * 0.22)
    hip_half = max(abs(float(np.dot(p[11] - p[8], normal))) / 2, length * 0.20)
    # Shoulder/hip landmarks can collapse in profile; torso length supplies a bounded prior.
    sh = observed_width(foreground, [shoulders], normal, shoulder_half * 1.10) * torso_scale
    hh = observed_width(foreground, [hips], normal, hip_half * 1.22) * torso_scale
    waist = shoulders * 0.42 + hips * 0.58
    wh = observed_width(foreground, [waist], normal, min(shoulder_half, hip_half) * 0.96) * torso_scale
    image = Image.new('L', (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.polygon([tuple(shoulders - normal * sh), tuple(waist - normal * wh), tuple(hips - normal * hh),
                  tuple(hips + axis * length * 0.10 - normal * hh * 0.8),
                  tuple(hips + axis * length * 0.10 + normal * hh * 0.8),
                  tuple(hips + normal * hh), tuple(waist + normal * wh), tuple(shoulders + normal * sh)], fill=255)
    head_axis = _unit(p[0] - shoulders)
    face = parsed['face_keypoints_2d']
    face = face[np.isfinite(face).all(axis=1), :2] if len(face) else np.empty((0, 2))
    center = p[0] + head_axis * length * 0.04
    rx, ry = length * 0.23, length * 0.31
    if len(face) >= 10:
        face_center = np.mean(face, axis=0)
        coords = face - face_center
        rx = max(length * 0.15, float(np.ptp(coords @ _perp(head_axis))) * 0.66)
        ry = max(length * 0.23, float(np.ptp(coords @ head_axis)) * 0.80)
        center = face_center + head_axis * ry * 0.18
    _capsule(draw, shoulders, center, length * 0.10)
    _ellipse(draw, center, head_axis, rx * head_scale, ry * head_scale)
    # Bounded per-part fitting avoids taking a dress's maximum width as body width.
    for a, b, c in ((2, 3, 4), (5, 6, 7)):
        for u, v, r1, r2 in ((a, b, 0.12, 0.095), (b, c, 0.095, 0.065)):
            n = _perp(_unit(p[v] - p[u]))
            centers = [p[u] * (1 - t) + p[v] * t for t in (0.3, 0.55, 0.8)]
            fit = observed_width(foreground, centers, n, length * (r1 + r2) / 2)
            factor = fit / (length * (r1 + r2) / 2) * arm_scale
            _capsule(draw, p[u], p[v], length * r1 * factor, length * r2 * factor)
    for a, b, c in ((8, 9, 10), (11, 12, 13)):
        for u, v, r1, r2 in ((a, b, 0.18, 0.13), (b, c, 0.13, 0.075)):
            n = _perp(_unit(p[v] - p[u]))
            centers = [p[u] * (1 - t) + p[v] * t for t in (0.3, 0.55, 0.8)]
            fit = observed_width(foreground, centers, n, length * (r1 + r2) / 2)
            factor = fit / (length * (r1 + r2) / 2) * leg_scale
            _capsule(draw, p[u], p[v], length * r1 * factor, length * r2 * factor)
    # Wholebody landmarks preserve the observed hands/feet without globally widening limbs.
    for name, wrist, elbow in (('hand_right_keypoints_2d', 4, 3), ('hand_left_keypoints_2d', 7, 6)):
        hand = parsed[name]
        good = hand[np.isfinite(hand).all(axis=1), :2] if len(hand) else np.empty((0, 2))
        if len(good) >= 3:
            # Rasterize each finger chain, NOT a hand bounding rectangle that could bridge to headwear.
            for start in (1, 5, 9, 13, 17):
                previous = p[wrist]
                for index in range(start, min(start + 4, len(hand))):
                    if _valid(hand[index]):
                        point = hand[index, :2]
                        _capsule(draw, previous, point, length * 0.025)
                        previous = point
            for point in good:
                _disk(draw, point, length * 0.025)
            _disk(draw, p[wrist], length * 0.07)
        else:
            end = p[wrist] + _unit(p[wrist] - p[elbow]) * length * 0.12
            _capsule(draw, p[wrist], end, length * 0.075)
    foot = parsed['foot_keypoints_2d']
    for ankle, indices in ((13, range(0, 3)), (10, range(3, 6))):
        good = [foot[i, :2] for i in indices if i < len(foot) and _valid(foot[i])]
        if good:
            for point in good:
                _capsule(draw, p[ankle], point, length * 0.06)
        else:
            _disk(draw, p[ankle], length * 0.10)
    return np.asarray(image, dtype=np.float32) / 255, ''


def refine_mask(mask, padding_px=0, feather_px=0):
    """Standard morphology + inward Gaussian feather; no new foreground is painted."""
    image = Image.fromarray(np.rint(mask * 255).astype(np.uint8))
    if padding_px:
        image = image.filter(ImageFilter.MaxFilter(2 * padding_px + 1))
    binary = np.asarray(image, dtype=np.float32) / 255
    if feather_px:
        blurred = np.asarray(image.filter(ImageFilter.GaussianBlur(feather_px)), dtype=np.float32) / 255
        binary = np.minimum(binary, blurred)
    return binary
