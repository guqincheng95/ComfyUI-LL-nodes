"""Two-stage portrait matching. Fits the existing temperature/tint/EV controls."""
import math
import torch
import torch.nn.functional as F

from .color_match import _validate_image, linear_to_oklab
from .processing import (TEMPERATURE_GAIN, TINT_GAIN, gamut_at_luminance, linear_to_srgb,
                         luminance, process_rgb, smoothstep, srgb_to_linear, validate_parameters)

REGIONS = ('neutral', 'face', 'body')
SOURCES = ('external_masks', 'atr_onnx', 'white_balance_only')


def _validate_mask(mask, image, name):
    if mask is None:
        return None
    if isinstance(mask, torch.Tensor) and mask.ndim == 2:
        mask = mask.unsqueeze(0)
    if (not isinstance(mask, torch.Tensor) or mask.ndim != 3
            or mask.shape[1:] != image.shape[1:3] or mask.shape[0] not in (1, image.shape[0])):
        raise ValueError(f'{name} MASK 须与对应图片尺寸一致，批次为 1 或与图片一致。')
    if not mask.is_floating_point() or not torch.isfinite(mask).all().item() or mask.min().item() < 0 or mask.max().item() > 1:
        raise ValueError(f'{name} MASK 须为 0～1 的浮点遮罩。')
    return mask


def _frame_mask(mask, index):
    return None if mask is None else mask[0 if len(mask) == 1 else index]


def _semantic_masks(frame, session):
    from ..subject.parsing import probabilities

    h, w = frame.shape[:2]
    scale = min(1, 512 / max(h, w))
    size = (max(1, round(h * scale)), max(1, round(w * scale)))
    data = frame.detach().float().permute(2, 0, 1)[None].cpu()
    if data.shape[1] == 4:
        data = torch.cat((data[:, :3] * data[:, 3:], data[:, 3:]), dim=1)
    small = F.interpolate(data, size=size, mode='bilinear', align_corners=False, antialias=True)[0].permute(1, 2, 0)
    rgb = small[..., :3]
    if small.shape[-1] == 4:
        rgb = rgb / small[..., 3:].clamp_min(1e-6)
    rgb = rgb.clamp(0, 1)
    probs = torch.from_numpy(probabilities(session, rgb.numpy()))
    labels = probs.argmax(0)
    l, a, b = linear_to_oklab(srgb_to_linear(rgb)).unbind(-1)
    # Arm/leg classes are not skin guarantees (e.g. sleeves, tights or gloves).
    # Require visible, plausibly skin-colored pixels as well as semantic evidence.
    color = (l > .20) & (l < .98) & (a > .006) & (b > .006) & (a < .21) & (b < .17)
    if small.shape[-1] == 4:
        color &= small[..., 3] > .05
    face = (labels == 11) & color
    body = ((labels >= 12) & (labels <= 15)) & color
    face = face * smoothstep((probs[11] - .55) / .25)
    body = body * smoothstep((probs[12:16].sum(0) - .65) / .23)
    masks = F.interpolate(torch.stack((face, body))[None], size=(h, w), mode='bilinear', align_corners=False)[0]
    return masks[0], masks[1]


def _sample(frame, masks):
    step = max(1, math.ceil(max(frame.shape[:2]) / 384))
    pixels = frame[::step, ::step].detach().float().cpu()
    sample_masks = {key: None if mask is None else mask[::step, ::step].detach().float().cpu()
                    for key, mask in masks.items()}
    return pixels, sample_masks


def _samples(pixels, masks, region):
    rgb = pixels[..., :3]
    valid = (rgb.amin(-1) > .035) & (rgb.amax(-1) < .985)
    if pixels.shape[-1] == 4:
        valid &= pixels[..., 3] >= .5
    mask = masks[region]
    if region == 'neutral':
        lab = linear_to_oklab(srgb_to_linear(rgb))
        valid &= (lab[..., 0] > .30) & (lab[..., 0] < .96)
        if mask is None:
            valid &= torch.linalg.vector_norm(lab[..., 1:], dim=-1) <= .055
        for key in ('face', 'body'):
            if masks[key] is not None:
                valid &= masks[key] < .2
    elif mask is None:
        return rgb.new_empty((0, 3))
    elif region == 'body' and masks['face'] is not None:
        valid &= masks['face'] < .2
    if mask is not None:
        valid &= mask >= .65
    return rgb[valid]


def _fit(source, reference, strength, light_strength=0):
    counts = [len(source), len(reference)]
    if min(counts) < 12 or not strength:
        return None, {'samples': counts, 'status': '样本不足，跳过' if strength else '强度为 0，跳过'}
    x, y = srgb_to_linear(source), srgb_to_linear(reference)

    def ratios(linear):
        r, g, b = linear.log2().unbind(-1)
        return torch.stack((r - b, (r + b) / 2 - g), -1).median(dim=0).values

    temp, tint = (ratios(y) - ratios(x)).tolist()
    # Inverse of the manual RGB gain equations in processing.process_rgb.
    temperature = min(35., max(-35., temp / (2 * TEMPERATURE_GAIN) * 100)) * strength
    tint = min(35., max(-35., tint / (2 * TINT_GAIN) * 100)) * strength
    ev = float(luminance(y).median().log2() - luminance(x).median().log2())
    exposure = min(.35, max(-.35, ev)) * strength * light_strength
    params = validate_parameters({'temperature': temperature, 'tint': tint})
    return (params, exposure), {'samples': counts, 'status': '已估算',
                                'temperature': round(temperature, 3), 'tint': round(tint, 3),
                                'exposure': round(exposure, 3)}


def _colored(rgb, fit, preserve_light=False):
    if fit is None:
        return rgb
    params, exposure = fit
    if params['temperature'] or params['tint']:
        adjusted = process_rgb(rgb, params, True)
    else:
        adjusted = rgb
    if not preserve_light or (adjusted is rgb and not exposure):
        return adjusted
    linear = srgb_to_linear(adjusted)
    target = (luminance(srgb_to_linear(rgb)) * (2 ** exposure)).clamp(0, 1)
    return linear_to_srgb(gamut_at_luminance(linear * (target / luminance(linear).clamp_min(1e-8)), target)).clamp(0, 1)


@torch.no_grad()
def align_portrait(image, reference, skin_source, white_balance_strength, face_strength,
                   body_strength, skin_luminance, source_masks, reference_masks):
    _validate_image(image, '待调图')
    _validate_image(reference, '参考图')
    if len(reference) not in (1, len(image)):
        raise ValueError('参考图批次须为 1 或与待调图一致。')
    if skin_source not in SOURCES:
        raise ValueError('肤色遮罩来源无效。')
    for value in (white_balance_strength, face_strength, body_strength, skin_luminance):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('校正强度须为 0～1。')
    src_masks = {key: _validate_mask(source_masks.get(key), image, key) for key in REGIONS}
    ref_masks = {key: _validate_mask(reference_masks.get(key), reference, '参考' + key) for key in REGIONS}
    if skin_source == 'white_balance_only':
        face_strength = body_strength = 0
    session = None
    if skin_source == 'atr_onnx' and (face_strength or body_strength):
        need_parser = any(group[key] is None and strength
                          for group in (src_masks, ref_masks)
                          for key, strength in (('face', face_strength), ('body', body_strength)))
        if need_parser:
            from ..subject.parsing import load_parser
            session = load_parser()

    def get_masks(frame, group, index):
        masks = {key: _frame_mask(group[key], index) for key in REGIONS}
        if session is not None and ((masks['face'] is None and face_strength)
                                    or (masks['body'] is None and body_strength)):
            found = _semantic_masks(frame, session)
            for key, value in zip(('face', 'body'), found):
                if masks[key] is None:
                    masks[key] = value
        return masks

    output = torch.empty_like(image, dtype=torch.float32)
    reports = []
    ref_cache = {}
    for i, frame in enumerate(image):
        ri = 0 if len(reference) == 1 else i
        if ri not in ref_cache:
            ref = reference[ri]
            rp, rm = _sample(ref, get_masks(ref, ref_masks, ri))
            ref_samples = {key: _samples(rp, rm, key) for key in REGIONS}
            if len(reference) == 1:
                ref_cache[ri] = ref_samples
        else:
            ref_samples = ref_cache[ri]
        masks = get_masks(frame, src_masks, i)
        pixels, sample_masks = _sample(frame, masks)
        wb, wb_report = _fit(_samples(pixels, sample_masks, 'neutral'),
                             ref_samples['neutral'], white_balance_strength)
        fits = {}
        report = {'frame': i + 1, 'white_balance': wb_report}
        for key, strength in (('face', face_strength), ('body', body_strength)):
            skin = _colored(_samples(pixels, sample_masks, key), wb)
            fits[key], report[key] = _fit(skin, ref_samples[key], strength, skin_luminance)
        reports.append(report)
        for row in range(0, frame.shape[0], 128):
            sl = slice(row, row + 128)
            tile = frame[sl].float()
            rgb = _colored(tile[..., :3], wb)
            face_mask = masks['face']
            if face_mask is not None:
                face_mask = face_mask[sl, :, None].to(tile)
            result = rgb
            for key in ('face', 'body'):
                if fits[key] is None:
                    continue
                weight = masks[key][sl, :, None].to(tile)
                if key == 'body' and face_mask is not None:
                    weight = weight * (1 - face_mask)
                result = result + weight * (_colored(rgb, fits[key], preserve_light=True) - rgb)
            if tile.shape[-1] == 4:
                result = torch.where(tile[..., 3:] > .01, result, tile[..., :3])
                output[i, sl, :, 3:] = tile[..., 3:]
            output[i, sl, :, :3] = result.clamp(0, 1)
    return output, reports
