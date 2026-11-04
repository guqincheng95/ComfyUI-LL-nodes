"""Shared geometry for image and mask resizing. No model dependencies."""

from fractions import Fraction
from math import ceil, floor, sqrt
import re

RATIOS = ("original", "custom", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16")
FITS = ("crop", "letterbox", "fill")
METHODS = ("lanczos", "bicubic", "hamming", "bilinear", "box", "nearest")
SCALE_SIDES = ("longest", "shortest", "width", "height", "total_kpixels", "none")
ROUNDING = ("nearest", "up", "down")
MAX_SIDE = 16384
MAX_BATCH_PIXELS = 64_000_000


def _positive_int(value, name, limit):
    if type(value) is not int or not 1 <= value <= limit:
        raise ValueError(f"{name} 必须为 1～{limit} 的整数。")


def target_size(source, aspect_ratio, proportional_width, proportional_height,
                scale_to_side, scale_to_length, round_to_multiple, rounding, flip_ratio):
    if aspect_ratio not in RATIOS or scale_to_side not in SCALE_SIDES or rounding not in ROUNDING:
        raise ValueError("比例、尺寸依据或取整方式无效。")
    _positive_int(proportional_width, "比例宽", 10000)
    _positive_int(proportional_height, "比例高", 10000)
    _positive_int(scale_to_length, "目标值", 64000)
    _positive_int(round_to_multiple, "像素倍数", 512)
    if type(flip_ratio) is not bool:
        raise ValueError("反转宽高比例须为布尔值。")
    if aspect_ratio == "original":
        ratio = Fraction(*source)
    elif aspect_ratio == "custom":
        ratio = Fraction(proportional_width, proportional_height)
    else:
        ratio = Fraction(*map(int, aspect_ratio.split(":")))
    if flip_ratio:
        ratio = 1 / ratio
    side = scale_to_side
    length = scale_to_length
    if side == "total_kpixels":
        height = sqrt(length * 1000 / ratio)
        width = height * ratio
    else:
        if side == "none":
            length = max(source)
            side = "longest"
        if side == "longest":
            side = "width" if ratio >= 1 else "height"
        elif side == "shortest":
            side = "height" if ratio >= 1 else "width"
        width, height = (length, length / ratio) if side == "width" else (length * ratio, length)
    step = round_to_multiple
    if rounding == "nearest":
        quantize = lambda value: floor(value + Fraction(1, 2))
    else:
        quantize = ceil if rounding == "up" else floor
    result = tuple(max(1, quantize(d / step)) * step for d in (width, height))
    if max(result) > MAX_SIDE or result[0] * result[1] > MAX_BATCH_PIXELS:
        raise ValueError(f"输出尺寸 {result[0]}×{result[1]} 超出限制，请减小目标值或放宽比例。")
    return result


def fit_geometry(source, target, fit):
    """Return input sampling box, resized content size, and output offset."""
    sw, sh = source
    tw, th = target
    box = (0, 0, sw, sh)
    if fit == "fill":
        return box, target, (0, 0)
    if fit == "letterbox":
        factor = min(Fraction(tw, sw), Fraction(th, sh))
        rw, rh = max(1, round(sw * factor)), max(1, round(sh * factor))
        return box, (rw, rh), ((tw - rw) // 2, (th - rh) // 2)
    if fit != "crop":
        raise ValueError("适配方式无效。")
    if sw * th > sh * tw:
        x = (sw - Fraction(sh * tw, th)) / 2
        box = (float(x), 0, float(sw - x), sh)
    elif sw * th < sh * tw:
        y = (sh - Fraction(sw * th, tw)) / 2
        box = (0, float(y), sw, float(sh - y))
    return box, target, (0, 0)


def transform(image, mask, target, fit, method, mask_method, background_color):
    import numpy as np
    import torch
    from PIL import Image

    if method not in METHODS or mask_method not in ("same", "nearest", "bilinear"):
        raise ValueError("图像或遮罩插值方式无效。")
    if not isinstance(background_color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", background_color):
        raise ValueError("补边颜色须为 #RRGGBB，例如 #000000。")
    bg = tuple(int(background_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    if image is not None:
        if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[-1] not in (3, 4):
            raise ValueError("图像须为 [B,H,W,3或4] IMAGE。")
        batch, sh, sw, _ = image.shape
    if mask is not None:
        if not isinstance(mask, torch.Tensor) or mask.ndim not in (2, 3):
            raise ValueError("遮罩须为 [B,H,W] 或 [H,W] MASK。")
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)
        mb, mh, mw = mask.shape
        if not min(mask.shape):
            raise ValueError("遮罩不能为空。")
        if image is None:
            batch, sh, sw = mb, mh, mw
        elif mb not in (1, batch):
            raise ValueError(f"遮罩批次必须为 1 或与图像一致（{batch}）。")
        elif not sh or not sw or abs(mw * sh / (mh * sw) - 1) > .02:
            raise ValueError(f"图像 {sw}×{sh} 与遮罩 {mw}×{mh} 宽高比不同；请先对齐原始裁切范围。")
    tw, th = target
    if not batch or not sh or not sw:
        raise ValueError("输入图像不能为空。")
    if batch * tw * th > MAX_BATCH_PIXELS:
        raise ValueError("整批输出超过6400万像素，请降低尺寸或分批处理。")
    box, (rw, rh), (x, y) = fit_geometry((sw, sh), target, fit)
    image_filter = Image.Resampling[method.upper()]
    mask_filter = image_filter if mask_method == "same" else Image.Resampling[mask_method.upper()]

    def pixels(frame, label):
        if not frame.is_floating_point():
            raise ValueError(label + "须为 0～1 的浮点张量。")
        data = frame.detach().cpu().float().numpy()
        if not np.isfinite(data).all() or data.min() < 0 or data.max() > 1:
            raise ValueError(label + "须为 0～1 的有限数值。")
        return data

    def sample(data, size, resampling, bounds=None):
        # Float Pillow planes avoid a round-trip through 8-bit RGB or MASK.
        return np.asarray(Image.fromarray(data).resize(size, resampling, box=bounds)).clip(0, 1)

    images = np.empty((batch, th, tw, 3), dtype=np.float32)
    masks = np.zeros((batch, th, tw), dtype=np.float32)
    if image is not None:
        images[:] = bg
    if mask is not None and mb == 1:
        shared_mask = pixels(mask[0], "遮罩")
        if (mw, mh) != (sw, sh):
            shared_mask = sample(shared_mask, (sw, sh), mask_filter)
        shared_mask = sample(shared_mask, (rw, rh), mask_filter, box)
    else:
        shared_mask = None
    for i in range(batch):
        rgb = pixels(image[i], "图像") if image is not None else None
        if shared_mask is not None:
            matte = shared_mask
        elif mask is not None:
            matte = pixels(mask[i], "遮罩")
            if (mw, mh) != (sw, sh):
                matte = sample(matte, (sw, sh), mask_filter)
            matte = sample(matte, (rw, rh), mask_filter, box)
        elif rgb.shape[-1] == 4:
            matte = sample(rgb[..., 3], (rw, rh), mask_filter, box)
        else:
            matte = 1.0
        masks[i, y:y+rh, x:x+rw] = matte
        if rgb is None:
            images[i] = masks[i, ..., None]
        else:
            for c in range(3):
                images[i, y:y+rh, x:x+rw, c] = sample(rgb[..., c], (rw, rh), image_filter, box)
    device = image.device if image is not None else mask.device
    return torch.from_numpy(images).to(device), torch.from_numpy(masks).to(device)
