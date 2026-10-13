"""comfyui-LL-nodes: one installation, shared frontend and categorized nodes."""
from .modules.resolution.nodes import ResolutionPreset
from .modules.photo.nodes import PhotoFinish

__version__ = "0.3.0"
WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {
    "ResolutionPreset": ResolutionPreset,
    "AIVisualPhotoFinish": PhotoFinish,
}
NODE_DISPLAY_NAME_MAPPINGS = {'ResolutionPreset': 'LL 比例预设 · Resolution Preset', 'AIVisualPhotoFinish': 'LL 后期修图·曝光·白平衡·色彩平衡 · Photo Finish'}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
