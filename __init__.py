"""ComfyUI-ResolutionPreset v0.1.0."""
from .nodes import ResolutionPreset

__version__ = "0.1.0"
NODE_CLASS_MAPPINGS = {"ResolutionPreset": ResolutionPreset}
NODE_DISPLAY_NAME_MAPPINGS = {"ResolutionPreset": "Resolution Preset"}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
