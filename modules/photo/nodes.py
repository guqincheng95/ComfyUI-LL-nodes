from .parameters import PARAMETERS

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
        # Append controls after all v1 widgets: old workflows keep their positional values.
        auto_controls = {
            'auto_mode': (['off', 'original', 'reference'], {'default': 'off', 'tooltip': '原图对齐修正同画面放大/二次采样色差；参考仿色匹配其他图片的色调统计。'}),
            'match_strength': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'tooltip': '自动匹配总强度，0为原样；不影响手动调色。'}),
            'match_luminance': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'tooltip': '明暗与色阶匹配强度。'}),
            'match_color': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'tooltip': '颜色匹配强度，0只匹配明暗。'}),
        }
        return {'required': required, 'optional': {
            'reference_image': ('IMAGE', {'tooltip': '接原图或需要仿色的参考图。原图对齐要求同构图；参考仿色允许不同内容、尺寸和画幅。'}),
            **auto_controls,
        }}

    RETURN_TYPES = ('IMAGE',)
    RETURN_NAMES = ('image',)
    FUNCTION = 'apply'
    CATEGORY = 'LL 节点库/图像后期/基础调色'
    DESCRIPTION = '自动原图对齐／参考仿色后进行手动调色。曝光、色温、色调三个可折叠区域。'

    def apply(self, image, preserve_luminosity=True, reference_image=None, auto_mode='off',
              match_strength=1.0, match_luminance=1.0, match_color=1.0, **values):
        from .processing import adjust_image
        from .color_match import match_image
        image = match_image(image, reference_image, auto_mode, match_strength, match_luminance, match_color)
        return (adjust_image(image, preserve_luminosity=preserve_luminosity, **values),)
