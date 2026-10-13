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
