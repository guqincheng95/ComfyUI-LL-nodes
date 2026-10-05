"""Production presets; edit this file to tune each model independently."""
from copy import deepcopy

RATIOS = ("1:1", "3:4", "4:3", "9:16", "16:9")
QUALITY_TIERS = ("Fast", "Quality", "Max")
ORIENTATIONS = ("Auto", "Portrait", "Landscape")
_BASE = {
    "1:1": {"Fast": (1024, 1024), "Quality": (1536, 1536), "Max": (2048, 2048)},
    "3:4": {"Fast": (768, 1024), "Quality": (1152, 1536), "Max": (1536, 2048)},
    "4:3": {"Fast": (1024, 768), "Quality": (1536, 1152), "Max": (2048, 1536)},
    "9:16": {"Fast": (576, 1024), "Quality": (864, 1536), "Max": (1152, 2048)},
    "16:9": {"Fast": (1024, 576), "Quality": (1536, 864), "Max": (2048, 1152)},
}
PRESETS = {name: deepcopy(_BASE) for name in ("Z-Image", "SCAIL-2 / WAN", "FLUX")}
MODEL_FAMILIES = (*PRESETS, "Custom")


def validate_presets(presets=PRESETS):
    """Fail clearly on missing choices, non-integers or non-aligned built-ins."""
    for family in MODEL_FAMILIES[:-1]:
        if family not in presets or set(presets[family]) != set(RATIOS):
            raise ValueError(f"Invalid ratio table: {family}")
        for ratio, tiers in presets[family].items():
            if set(tiers) != set(QUALITY_TIERS):
                raise ValueError(f"Invalid quality table: {family}/{ratio}")
            for tier, size in tiers.items():
                if not isinstance(size, (tuple, list)) or len(size) != 2:
                    raise ValueError(f"Invalid size: {family}/{ratio}/{tier}")
                if any(type(v) is not int or v <= 0 or v % 32 for v in size):
                    raise ValueError(f"Size must be positive integers aligned to 32: {family}/{ratio}/{tier}: {size}")


validate_presets()
