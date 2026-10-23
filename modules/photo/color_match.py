"""Reference color matching without resampling the output image.

Same-scene: robust spatial linear-RGB fit. Look transfer: monotone luminance
quantile matching + Reinhard-style chroma statistics in three tonal regions.
Oklab matrices are adapted from Bjorn Ottosson's public-domain implementation:
https://bottosson.github.io/posts/oklab/ (2021 matrix update).
No GPL color-matcher source is copied or required.
"""
import math
import torch
import torch.nn.functional as F
from .processing import srgb_to_linear, linear_to_srgb, gamut_at_luminance, luminance, region_weights

AUTO_MODES = ('off', 'original', 'reference')


def linear_to_oklab(rgb):
    m1 = rgb.new_tensor(((.4122214708,.5363325363,.0514459929),(.2119034982,.6806995451,.1073969566),(.0883024619,.2817188376,.6299787005)))
    m2 = rgb.new_tensor(((.2104542553,.7936177850,-.0040720468),(1.9779984951,-2.4285922050,.4505937099),(.0259040371,.7827717662,-.8086757660)))
    lms = rgb @ m1.T
    roots = lms.sign() * lms.abs().pow(1 / 3)
    return roots @ m2.T


def oklab_to_linear(lab):
    m1 = lab.new_tensor(((1,.3963377774,.2158037573),(1,-.1055613458,-.0638541728),(1,-.0894841775,-1.2914855480)))
    m2 = lab.new_tensor(((4.0767416621,-3.3077115913,.2309699292),(-1.2684380046,2.6097574011,-.3413193965),(-.0041960863,-.7034186147,1.7076147010)))
    return (lab @ m1.T).pow(3) @ m2.T


def _validate_image(image, label):
    if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[-1] not in (3, 4):
        raise ValueError(f'{label} 必须是 [B,H,W,3或4] IMAGE。')
    if not image.is_floating_point() or any(v == 0 for v in image.shape):
        raise ValueError(f'{label} 必须是非空浮点图像。')
    if not torch.isfinite(image).all().item() or image.min().item() < 0 or image.max().item() > 1:
        raise ValueError(f'{label} 必须为 0～1 的有限 sRGB 图像。')


def _sample(image, size=None):
    h, w = image.shape[:2]
    if size is None:
        scale = min(1, 256 / max(h, w))
        size = (max(1, round(h * scale)), max(1, round(w * scale)))
    data = image.detach().float().permute(2, 0, 1)[None].cpu()
    if tuple(data.shape[-2:]) != tuple(size):
        # Hidden RGB in PNG cutouts must not bleed into visible statistics.
        if data.shape[1] == 4:
            data = torch.cat((data[:, :3] * data[:, 3:], data[:, 3:]), dim=1)
        data = F.interpolate(data, size=size, mode='bilinear', align_corners=False, antialias=True)
        if data.shape[1] == 4:
            data = torch.cat((data[:, :3] / data[:, 3:].clamp_min(1e-8), data[:, 3:]), dim=1)
    return data[0].permute(1, 2, 0)


def _visible(sample):
    return torch.ones(sample.shape[:2], dtype=torch.bool) if sample.shape[-1] == 3 else sample[..., 3] > .01


def _fit_original(source, reference):
    """Huber IRLS with identity regularization; no high-resolution texture copying."""
    x = srgb_to_linear(source[..., :3]).reshape(-1, 3).double()
    y = srgb_to_linear(reference[..., :3]).reshape(-1, 3).double()
    valid = (_visible(source) & _visible(reference)).flatten()
    valid &= (source[..., :3].amin(-1).flatten() > .005) & (source[..., :3].amax(-1).flatten() < .995)
    valid &= (reference[..., :3].amin(-1).flatten() > .005) & (reference[..., :3].amax(-1).flatten() < .995)
    if valid.sum() < 16:
        valid = (_visible(source) & _visible(reference)).flatten()
    if not valid.any():
        raise ValueError('原图与待调图没有共同的有效可见像素。')
    x, y = x[valid], y[valid]
    design = torch.cat((x, torch.ones((len(x), 1), dtype=x.dtype)), dim=-1)
    prior = torch.cat((torch.eye(3, dtype=x.dtype), torch.zeros((1, 3), dtype=x.dtype)))
    regularizer = max(len(x) * 1e-5, 1e-6) * torch.eye(4, dtype=x.dtype)
    weights = torch.ones(len(x), dtype=x.dtype)
    transform = prior
    for _ in range(5):
        weighted = design * weights[:, None]
        transform = torch.linalg.solve(design.T @ weighted + regularizer,
                                       weighted.T @ y + regularizer @ prior)
        error = (design @ transform - y).square().mean(-1).sqrt()
        scale = error.median().clamp_min(1e-5) * 1.5
        weights = (scale / error.clamp_min(1e-8)).clamp(max=1)
    # Prevent underdetermined/different-content fits from generating extreme transforms.
    transform[:3] = transform[:3].clamp(-2, 4)
    transform[3] = transform[3].clamp(-.25, .25)
    return transform.float()


def _usable_lab(sample):
    lab = linear_to_oklab(srgb_to_linear(sample[..., :3])).reshape(-1, 3)
    visible = _visible(sample).flatten()
    if not visible.any():
        raise ValueError('参考图没有有效可见像素。')
    valid = visible & (lab[:, 0] > .02) & (lab[:, 0] < .98)
    return lab[valid] if valid.sum() >= 16 else lab[visible]


def _tone_curve(source_l, reference_l):
    quantiles = torch.linspace(.005, .995, 129)
    x = torch.quantile(source_l, quantiles)
    y = torch.quantile(reference_l, quantiles)
    # Merge source plateaus. A clipped constant cannot acquire missing detail.
    x, inverse = torch.unique_consecutive(x, return_inverse=True)
    sums = torch.zeros_like(x).scatter_add_(0, inverse, y)
    counts = torch.zeros_like(x).scatter_add_(0, inverse, torch.ones_like(y))
    y = sums / counts
    valid = (x > 1e-5) & (x < 1 - 1e-5)
    return torch.cat((torch.zeros(1), x[valid], torch.ones(1))), torch.cat((torch.zeros(1), y[valid], torch.ones(1)))


def _interpolate(values, x, y):
    indexes = torch.searchsorted(x, values.contiguous()).clamp(1, len(x) - 1)
    low, high = x[indexes - 1], x[indexes]
    fraction = ((values - low) / (high - low).clamp_min(1e-8)).clamp(0, 1)
    return y[indexes - 1] + fraction * (y[indexes] - y[indexes - 1])


def _moments(lab):
    moments = []
    for weights in region_weights(lab[:, :1]):
        total = weights.sum()
        if total < max(4, len(lab) * .002):
            weights = torch.ones_like(weights)
            total = weights.sum()
        mean = (lab[:, 1:] * weights).sum(0) / total
        variance = ((lab[:, 1:] - mean).square() * weights).sum(0) / total
        moments.append((mean, variance.sqrt()))
    return moments


def _reference_mapping(source, reference):
    source_lab, reference_lab = _usable_lab(source), _usable_lab(reference)
    x, y = _tone_curve(source_lab[:, 0], reference_lab[:, 0])
    chroma = []
    for (sm, ss), (rm, rs) in zip(_moments(source_lab), _moments(reference_lab)):
        # A nearly neutral source has no meaningful color variance to amplify.
        gain = torch.where(ss > .003, (rs / ss.clamp_min(.003)).clamp(.5, 2), torch.ones_like(ss))
        chroma.append((gain, (rm - sm * gain).clamp(-.25, .25)))
    return x, y, chroma


def match_image(image, reference_image=None, auto_mode='off', match_strength=1.0,
                match_luminance=1.0, match_color=1.0, tile_rows=128):
    """Match first, then call existing manual adjustments in the node adapter.

    A one-image reference broadcasts to the target batch; otherwise batches must
    match. Only small statistics samples are resized, never the result image.
    """
    if auto_mode not in AUTO_MODES:
        raise ValueError('自动匹配模式无效。')
    for name, value in [('match_strength', match_strength), ('match_luminance', match_luminance), ('match_color', match_color)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{name} 必须为 0～1。')
    if type(tile_rows) is not int or tile_rows < 1:
        raise ValueError('tile_rows 必须为正整数。')
    _validate_image(image, '待调色图')
    if auto_mode == 'off' or match_strength == 0 or (match_luminance == 0 and match_color == 0):
        return image
    if reference_image is None:
        raise ValueError('请连接“原图／仿色参考图”，或将自动对齐模式设为关闭。')
    _validate_image(reference_image, '参考图')
    if reference_image.shape[0] not in (1, image.shape[0]):
        raise ValueError('参考图批量须为 1 或与待调图数量一致。')
    if auto_mode == 'original':
        aspect_s = image.shape[2] / image.shape[1]
        aspect_r = reference_image.shape[2] / reference_image.shape[1]
        if abs(aspect_r / aspect_s - 1) > .02:
            raise ValueError('原图对齐需要相同构图/裁切；宽高比不一致时请使用“参考仿色”。')
    if image.shape == reference_image.shape and torch.equal(image, reference_image.to(image.device)):
        return image
    with torch.no_grad():
        output = torch.empty(image.shape, dtype=torch.float32, device=image.device)
        for batch in range(image.shape[0]):
            sample = _sample(image[batch])
            if not _visible(sample).any():
                output[batch] = image[batch].float()
                continue
            ref = reference_image[0 if len(reference_image) == 1 else batch]
            if auto_mode == 'original':
                reference = _sample(ref, sample.shape[:2])
                matrix = _fit_original(sample, reference).to(image.device)
            else:
                reference = _sample(ref)
                x, y, chroma = _reference_mapping(sample, reference)
                x, y = x.to(image.device), y.to(image.device)
                chroma = [(gain.to(image.device), bias.to(image.device)) for gain, bias in chroma]
            for row in range(0, image.shape[1], tile_rows):
                source = image[batch, row:row+tile_rows].float()
                linear = srgb_to_linear(source[..., :3])
                original_lab = linear_to_oklab(linear)
                if auto_mode == 'original':
                    candidate = linear @ matrix[:3] + matrix[3]
                    desired = linear_to_oklab(candidate)
                else:
                    desired = original_lab.clone()
                    desired[..., 0] = _interpolate(original_lab[..., 0], x, y)
                    adjusted_ab = torch.zeros_like(original_lab[..., 1:])
                    for weight, (gain, bias) in zip(region_weights(original_lab[..., :1]), chroma):
                        adjusted_ab += weight * (original_lab[..., 1:] * gain + bias)
                    # Preserve irrecoverable black/white endpoints; avoid tinting clipped whites.
                    envelope = torch.minimum(original_lab[..., :1] / .05, (1 - original_lab[..., :1]) / .05).clamp(0, 1)
                    desired[..., 1:] = original_lab[..., 1:] + envelope * (adjusted_ab - original_lab[..., 1:])
                factor = source.new_tensor([match_luminance, match_color, match_color]) * match_strength
                lab = original_lab + (desired - original_lab) * factor
                rgb = oklab_to_linear(lab)
                rgb = gamut_at_luminance(rgb, luminance(rgb))
                output[batch, row:row+tile_rows, :, :3] = linear_to_srgb(rgb).clamp(0, 1)
                if image.shape[-1] == 4:
                    output[batch, row:row+tile_rows, :, 3:] = source[..., 3:]
        return output
