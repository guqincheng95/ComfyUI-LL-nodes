from .nodes import PhotoFinish

__version__ = '0.1.1'
NODE_CLASS_MAPPINGS = {'AIVisualPhotoFinish': PhotoFinish}
NODE_DISPLAY_NAME_MAPPINGS = {'AIVisualPhotoFinish': '后期修图·曝光·白平衡·色彩平衡 · Photo Finish'}
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
