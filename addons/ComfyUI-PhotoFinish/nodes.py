from .processing import PARAMETERS, adjust_image

LABELS = {
    'exposure': '曝光 EV', 'contrast': '对比度', 'highlights': '高光',
    'shadows': '阴影', 'whites': '白色', 'blacks': '黑色',
    'temperature': '色温：负冷 / 正暖（相对偏移，不是 Kelvin）',
    'tint': '色调：负绿 / 正洋红', 'vibrance': '自然饱和度', 'saturation': '饱和度',
}
for region, label in (('shadow', '阴影'), ('midtone', '中间调'), ('highlight', '高光')):
    for axis, text in (('cyan_red', '负青 / 正红'), ('magenta_green', '负洋红 / 正绿'), ('yellow_blue', '负黄 / 正蓝')):
        LABELS[f'{region}_{axis}'] = f'{label}色彩平衡：{text}'


class PhotoFinish:
    @classmethod
    def INPUT_TYPES(cls):
        required = {'image': ('IMAGE',)}
        for name in PARAMETERS:
            limit = 5.0 if name == 'exposure' else 100.0
            required[name] = ('FLOAT', {'default': 0.0, 'min': -limit, 'max': limit,
                                      'step': 0.05 if name == 'exposure' else 1.0,
                                      'tooltip': LABELS[name]})
        required['preserve_luminosity'] = ('BOOLEAN', {'default': True,
            'tooltip': '保持色彩平衡前的线性亮度；不撤销曝光和光影调整。'})
        return {'required': required}

    RETURN_TYPES = ('IMAGE',)
    RETURN_NAMES = ('image',)
    FUNCTION = 'apply'
    CATEGORY = 'AI 视觉/后期修图'
    DESCRIPTION = '基础后期：光影六项、白平衡、自然饱和度与饱和度、三明度区域色彩平衡。'

    def apply(self, image, preserve_luminosity=True, **values):
        return (adjust_image(image, preserve_luminosity=preserve_luminosity, **values),)
