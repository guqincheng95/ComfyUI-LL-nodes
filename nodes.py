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
                                     "tooltip": "Custom only. Passed through unchanged; orientation is ignored."}),
            "custom_height": ("INT", {"default": 768, "min": 1, "max": 2147483647, "step": 1,
                                      "tooltip": "Custom only. No rounding or alignment."}),
        }}

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "resolve"
    CATEGORY = "AI Visual / Utilities"
    DESCRIPTION = "Model, ratio and quality presets. Custom preserves both dimensions exactly."

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
