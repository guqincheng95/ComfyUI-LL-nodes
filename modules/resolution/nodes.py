"""Native ComfyUI controls and integer outputs; no runtime dependencies."""
from .presets import MODEL_FAMILIES, ORIENTATIONS, PRESETS, QUALITY_TIERS, RATIOS


class ResolutionPreset:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model_family": (list(MODEL_FAMILIES), {"default": "Z-Image"}),
            "ratio": (list(RATIOS), {"default": "9:16"}),
            "quality_tier": (list(QUALITY_TIERS), {"default": "Quality"}),
            "orientation": (list(ORIENTATIONS), {"default": "Auto"}),
            "custom_width": ("INT", {"default": 1376, "min": 1, "max": 2147483647, "step": 1,
                                     "tooltip": "仅在模型预设选择“自定义”时生效；数值原样输出，不随比例和方向变化。"}),
            "custom_height": ("INT", {"default": 768, "min": 1, "max": 2147483647, "step": 1,
                                      "tooltip": "仅自定义模式生效；不自动取整或对齐。这不是预设模式的实际输出高度。"}),
        }}

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "resolve"
    CATEGORY = "LL 节点库/图像工具/尺寸与比例"
    DESCRIPTION = "按模型预设、画面比例、尺寸档位和方向输出宽高。自定义宽高仅在自定义模式生效，不显示预设输出值。"

    def resolve(self, model_family, ratio, quality_tier, orientation,
                custom_width=1376, custom_height=768):
        if model_family not in MODEL_FAMILIES:
            raise ValueError(f"Unknown model family: {model_family}")
        if model_family == "Custom":
            for label, value in (("custom_width", custom_width), ("custom_height", custom_height)):
                if type(value) is not int or not 1 <= value <= 2147483647:
                    raise ValueError(f"{label} must be a positive INT (1..2147483647)")
            return (custom_width, custom_height)
        if ratio not in RATIOS:
            raise ValueError(f"Unknown ratio: {ratio}")
        if quality_tier not in QUALITY_TIERS:
            raise ValueError(f"Unknown quality tier: {quality_tier}")
        if orientation not in ORIENTATIONS:
            raise ValueError(f"Unknown orientation: {orientation}")
        width, height = PRESETS[model_family][ratio][quality_tier]
        if orientation == "Portrait":
            width, height = min(width, height), max(width, height)
        elif orientation == "Landscape":
            width, height = max(width, height), min(width, height)
        return (width, height)


class ImageAspectScale:
    @classmethod
    def INPUT_TYPES(cls):
        from .scale import RATIOS, FITS, METHODS, SCALE_SIDES, ROUNDING
        return {"required": {
            "aspect_ratio": (list(RATIOS), {"default": "original", "tooltip": "不接图像或遮罩时，选择固定比例或自定义比例即可单独计算宽高。"}),
            "proportional_width": ("INT", {"default": 1, "min": 1, "max": 10000}),
            "proportional_height": ("INT", {"default": 1, "min": 1, "max": 10000}),
            "fit": (list(FITS), {"default": "crop"}),
            "method": (list(METHODS), {"default": "lanczos"}),
            "round_to_multiple": ("INT", {"default": 8, "min": 1, "max": 512, "tooltip": "1=不限制倍数。可输入 8、16、32 或任意自定义倍数。"}),
            "scale_to_side": (list(SCALE_SIDES), {"default": "longest"}),
            "scale_to_length": ("INT", {"default": 1280, "min": 1, "max": 64000}),
            "background_color": ("STRING", {"default": "#000000"}),
            "flip_ratio": ("BOOLEAN", {"default": False, "tooltip": "交换目标宽高比例，不旋转输入图像。"}),
            "rounding": (list(ROUNDING), {"default": "nearest"}),
            "mask_method": (["same", "nearest", "bilinear"], {"default": "same"}),
        }, "optional": {"image": ("IMAGE",), "mask": ("MASK",)}}

    RETURN_TYPES = ("IMAGE", "MASK", "BOX", "INT", "INT")
    RETURN_NAMES = ("image", "mask", "original_size", "width", "height")
    FUNCTION = "scale"
    CATEGORY = ResolutionPreset.CATEGORY
    DESCRIPTION = "不接图像或遮罩也可按比例、目标值与像素倍数输出宽高。接入图像或遮罩后，可同步裁切、补边或拉伸。"

    def scale(self, aspect_ratio="original", proportional_width=1, proportional_height=1,
              fit="crop", method="lanczos", round_to_multiple=8, scale_to_side="longest",
              scale_to_length=1280, background_color="#000000", flip_ratio=False,
              rounding="nearest", mask_method="same", image=None, mask=None):
        from .scale import target_size, transform
        source_size = None
        if image is not None or mask is not None:
            source = image if image is not None else mask
            shape = getattr(source, "shape", ())
            if image is not None and len(shape) == 4:
                h, w = shape[1:3]
            elif image is None and len(shape) in (2, 3):
                h, w = shape[-2:]
            else:
                raise ValueError("图像须为 [B,H,W,C]；遮罩须为 [B,H,W] 或 [H,W]。")
            if not h or not w:
                raise ValueError("输入尺寸不能为空。")
            source_size = (w, h)

        width, height = target_size(source_size, aspect_ratio, proportional_width, proportional_height,
                                    scale_to_side, scale_to_length, round_to_multiple, rounding, flip_ratio)
        if source_size is None:
            return None, None, None, width, height
        out, matte = transform(image, mask, (width, height), fit, method, mask_method, background_color)
        return out, matte, list(source_size), width, height
