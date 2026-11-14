"""Use ComfyUI's standard temporary-image preview inside the single main node."""


def comparison_preview(original, result, roi_mask=None, x=0., y=0., width=1., height=1.,
                       prompt=None, extra_pnginfo=None, *, _save_images=None):
    from .nodes import DLSS5Compare
    image, _ = DLSS5Compare().compare(original, result[0], x, y, width, height, roi_mask)
    if _save_images is None:
        from nodes import PreviewImage
        _save_images = PreviewImage().save_images
    saved = _save_images(image, filename_prefix='LL_DLSS5_compare', prompt=prompt, extra_pnginfo=extra_pnginfo)
    return {'ui': saved['ui'], 'result': result}
