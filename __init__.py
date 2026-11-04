"""comfyui-LL-nodes: one installation, shared frontend and categorized nodes."""
from .modules.resolution.nodes import ResolutionPreset, ImageAspectScale
from .modules.photo.nodes import PhotoFinish
from .modules.contour.nodes import PersonContourTrim
from .modules.subject.nodes import PersonSubjectClean

__version__ = "0.8.0"
WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {
    "ResolutionPreset": ResolutionPreset,
    "LLImageAspectScale": ImageAspectScale,
    "AIVisualPhotoFinish": PhotoFinish,
    "LLPersonContourTrim": PersonContourTrim,
    "LLPersonSubjectClean": PersonSubjectClean,
}
NODE_DISPLAY_NAME_MAPPINGS = {'LLImageAspectScale': 'LL 图像比例控制 · Image Aspect Scale', 'LLPersonSubjectClean': 'LL 人物主体提取·深度·肤色净化 · Subject Clean', 'LLPersonContourTrim': 'LL 人物轮廓修剪 · Person Contour Trim', 'ResolutionPreset': 'LL 比例预设 · Resolution Preset', 'AIVisualPhotoFinish': 'LL 后期修图·自动仿色·曝光·白平衡 · Photo Finish'}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
