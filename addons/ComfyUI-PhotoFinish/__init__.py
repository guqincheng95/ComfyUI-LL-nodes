from .nodes import PhotoFinish

__version__ = '0.1.0'
NODE_CLASS_MAPPINGS = {'AIVisualPhotoFinish': PhotoFinish}
NODE_DISPLAY_NAME_MAPPINGS = {'AIVisualPhotoFinish': 'Photo Finish · 基础后期'}
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
