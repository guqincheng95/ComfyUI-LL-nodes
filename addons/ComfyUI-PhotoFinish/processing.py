"""Float32 display-referred sRGB photo adjustment. No PIL/uint8 round trips.

Exposure uses the standard linear-light 2**EV relationship (also used by
GPUImage2). Tone-region and gamut algorithms here are independent implementations.
See docs/ALGORITHMS.md for source research, assumptions and limitations.
"""
import math
import torch

PARAMETERS = (
    'exposure', 'contrast', 'highlights', 'shadows', 'whites', 'blacks',
    'temperature', 'tint', 'vibrance', 'saturation',
    'shadow_cyan_red', 'shadow_magenta_green', 'shadow_yellow_blue',
    'midtone_cyan_red', 'midtone_magenta_green', 'midtone_yellow_blue',
    'highlight_cyan_red', 'highlight_magenta_green', 'highlight_yellow_blue',
)
WEIGHTS = (0.2126, 0.7152, 0.0722)


def validate_parameters(values):
    unknown = set(values) - set(PARAMETERS)
    if unknown:
        raise ValueError(f'Unknown parameters: {sorted(unknown)}')
    result = dict.fromkeys(PARAMETERS, 0.0)
    for name, value in values.items():
        limit = 5.0 if name == 'exposure' else 100.0
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
            raise ValueError(f'{name} must be finite and between {-limit} and {limit}')
        result[name] = float(value)
    return result


def srgb_to_linear(x):
    return torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055).clamp_min(0).pow(2.4))


def linear_to_srgb(x):
    return torch.where(x <= 0.0031308, x * 12.92, 1.055 * x.clamp_min(0).pow(1 / 2.4) - 0.055)


def luminance(rgb):
    return (rgb * rgb.new_tensor(WEIGHTS)).sum(dim=-1, keepdim=True)


def smoothstep(x):
    x = x.clamp(0, 1)
    return x * x * (3 - 2 * x)


def gamut_at_luminance(rgb, target):
    """Compress chroma towards neutral to fit [0,1], keeping linear Y exactly."""
    target = target.clamp(0, 1)
    chroma = rgb - luminance(rgb)
    upper = (1 - target) / chroma.clamp_min(1e-8)
    lower = target / (-chroma).clamp_min(1e-8)
    limits = torch.where(chroma > 0, upper, torch.where(chroma < 0, lower, torch.ones_like(chroma)))
    scale = limits.amin(dim=-1, keepdim=True).clamp(0, 1)
    return (target + scale * chroma).clamp(0, 1)


def tone_curve(x, p):
    """Continuous monotone tone transforms. Shadows/highlights preserve endpoints;
    black/white controls move endpoints. No spatial masks or halo-producing blur.
    """
    if p['contrast']:
        power = 2 ** (p['contrast'] / 100)
        lo, hi = x.pow(power), (1 - x).pow(power)
        x = lo / (lo + hi).clamp_min(1e-8)
    if p['shadows']:
        u = (x / 0.55).clamp(0, 1)
        x = x + 0.55 * 0.9 * (p['shadows'] / 100) * u * (1 - u).square()
    if p['highlights']:
        u = ((x - 0.45) / 0.55).clamp(0, 1)
        x = x + 0.55 * 0.9 * (p['highlights'] / 100) * u.square() * (1 - u)
    if p['blacks']:
        x = x + 0.12 * (p['blacks'] / 100) * (1 - smoothstep(x / 0.25))
    if p['whites']:
        x = x + 0.12 * (p['whites'] / 100) * smoothstep((x - 0.75) / 0.25)
    return x.clamp(0, 1)


def region_weights(perceptual_y):
    shadow = 1 - smoothstep((perceptual_y - 0.15) / 0.40)
    highlight = smoothstep((perceptual_y - 0.45) / 0.40)
    midtone = 1 - shadow - highlight
    return shadow, midtone, highlight


def process_rgb(rgb, p, preserve_luminosity):
    rgb = srgb_to_linear(rgb)
    if p['temperature'] or p['tint']:
        temp, tint = p['temperature'] / 100, p['tint'] / 100
        gains = rgb.new_tensor([2 ** (0.7 * temp + 0.35 * tint), 2 ** (-0.35 * tint), 2 ** (-0.7 * temp + 0.35 * tint)])
        gains = gains / (gains * rgb.new_tensor(WEIGHTS)).sum()
        rgb = rgb * gains
    if p['exposure']:
        rgb = rgb * (2 ** p['exposure'])
    y = luminance(rgb)
    if any(p[key] for key in ('contrast', 'highlights', 'shadows', 'whites', 'blacks')):
        target = srgb_to_linear(tone_curve(linear_to_srgb(y).clamp(0, 1), p))
        scaled = rgb * (target / y.clamp_min(1e-8))
        rgb = torch.where(y > 1e-8, scaled, target.expand_as(rgb))
        rgb = gamut_at_luminance(rgb, target)
    else:
        rgb = gamut_at_luminance(rgb, y)
    if any(p[key] for key in PARAMETERS[10:]):
        y = luminance(rgb)
        weights = region_weights(linear_to_srgb(y))
        delta = torch.zeros_like(rgb)
        for region, weight in zip(('shadow', 'midtone', 'highlight'), weights):
            vector = rgb.new_tensor([p[f'{region}_{axis}'] / 100 for axis in ('cyan_red', 'magenta_green', 'yellow_blue')])
            delta = delta + weight * vector
        # Vanishes at black/white; no undefined divisions in neutral endpoints.
        delta = delta * 0.35 * (y * (1 - y)).clamp_min(0).sqrt()
        candidate = rgb + delta
        rgb = gamut_at_luminance(candidate, y) if preserve_luminosity else candidate.clamp(0, 1)
    if p['vibrance'] or p['saturation']:
        y = luminance(rgb)
        maximum = rgb.amax(dim=-1, keepdim=True)
        minimum = rgb.amin(dim=-1, keepdim=True)
        sat = (maximum - minimum) / maximum.clamp_min(1e-8)
        vib = p['vibrance'] / 100
        factor = (1 + vib * (1 - sat).square()) if vib >= 0 else (1 + vib)
        factor = factor * (1 + p['saturation'] / 100)
        rgb = gamut_at_luminance(y + (rgb - y) * factor, y)
    return linear_to_srgb(rgb).clamp(0, 1)


def adjust_image(image, preserve_luminosity=True, tile_rows=128, **values):
    """ComfyUI BHWC IMAGE -> BHWC float32 IMAGE, same device and shape.

    Pointwise row tiles bound temporary memory. Finite float input in [0,1]
    only; RGBA is supported with alpha untouched. Neutral settings are exact.
    """
    p = validate_parameters(values)
    if not isinstance(preserve_luminosity, bool):
        raise ValueError('preserve_luminosity must be boolean')
    if not isinstance(tile_rows, int) or isinstance(tile_rows, bool) or tile_rows < 1:
        raise ValueError('tile_rows must be a positive integer')
    if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[-1] not in (3, 4):
        raise ValueError('Expected IMAGE tensor [batch, height, width, 3 or 4]')
    if not image.is_floating_point() or any(size == 0 for size in image.shape):
        raise ValueError('Expected a nonempty floating-point IMAGE')
    if not torch.isfinite(image).all().item() or image.amin().item() < 0 or image.amax().item() > 1:
        raise ValueError('IMAGE must contain finite display-referred sRGB values in [0,1]')
    if not any(p.values()):
        return image
    with torch.no_grad():
        output = torch.empty(image.shape, dtype=torch.float32, device=image.device)
        for batch in range(image.shape[0]):
            for row in range(0, image.shape[1], tile_rows):
                tile = image[batch:batch+1, row:row+tile_rows].float()
                output[batch:batch+1, row:row+tile_rows, :, :3] = process_rgb(tile[..., :3], p, preserve_luminosity)
                if image.shape[-1] == 4:
                    output[batch:batch+1, row:row+tile_rows, :, 3:] = tile[..., 3:]
        return output
