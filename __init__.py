"""comfyui-LL-nodes: one installation, shared frontend and categorized nodes."""
from .modules.resolution.nodes import ResolutionPreset
from .modules.photo.nodes import PhotoFinish
from .modules.contour.nodes import PersonContourTrim

__version__ = "0.5.0"
WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {
    "ResolutionPreset": ResolutionPreset,
    "AIVisualPhotoFinish": PhotoFinish,
    "LLPersonContourTrim": PersonContourTrim,
}
NODE_DISPLAY_NAME_MAPPINGS = {'LLPersonContourTrim': 'LL 人物轮廓修剪 · Person Contour Trim', 'ResolutionPreset': 'LL 比例预设 · Resolution Preset', 'AIVisualPhotoFinish': 'LL 后期修图·自动仿色·曝光·白平衡 · Photo Finish'}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
