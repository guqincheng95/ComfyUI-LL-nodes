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
            'auto_mode': (['off', 'original', 'reference', 'reference_palette'], {'default': 'off', 'tooltip': '原图对齐用于同一构图；参考仿色优先依据低饱和区域校正色偏；整图调色板沿用旧版统计仿色。'}),
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


class PortraitColorAlign(PhotoFinish):
    @classmethod
    def INPUT_TYPES(cls):
        required = super().INPUT_TYPES()['required']
        required['reference_image'] = ('IMAGE', {'tooltip': '提供希望匹配的白平衡、脸部及裸露身体肤色。'})
        required['skin_source'] = (['external_masks', 'atr_onnx', 'white_balance_only'], {'default': 'external_masks'})
        for key, default, tip in (
            ('white_balance_strength', .85, '优先用两张图的低饱和区域估计全图色温／色调。'),
            ('face_strength', .8, '只匹配脸部，缺少任意一侧的有效脸部样本就跳过。'),
            ('body_strength', .8, '只匹配可见身体皮肤，缺少任意一侧的有效样本就跳过。'),
            ('skin_luminance', 0., '0 保留皮肤亮度与光影；调高可有限地向参考图的对应区域补偿曝光。'),
        ):
            required[key] = ('FLOAT', {'default': default, 'min': 0., 'max': 1., 'step': .05, 'tooltip': tip})
        optional = {}
        for prefix in ('', 'reference_'):
            for region, tip in (
                ('neutral', '可选的中性取样区（白墙、灰卡等）；只取样，白平衡应用于全图。'),
                ('face', '可见面部皮肤 MASK，建议排除眼睛、嘴唇、头发及遮挡。'),
                ('body', '可见身体皮肤 MASK，排除衣物、手套、饰品。不要接整人 MASK。'),
            ):
                optional[f'{prefix}{region}_mask'] = ('MASK', {'tooltip': tip})
        return {'required': required, 'optional': optional}

    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('image', 'report')
    DESCRIPTION = '中性色对齐白平衡 → 分区匹配脸部和可见身体皮肤 → 手动微调。报告列出实际自动数值与跳过原因。'

    def apply(self, image, reference_image, preserve_luminosity=True,
              skin_source='external_masks', white_balance_strength=.85, face_strength=.8,
              body_strength=.8, skin_luminance=0., neutral_mask=None, face_mask=None, body_mask=None,
              reference_neutral_mask=None, reference_face_mask=None, reference_body_mask=None, **values):
        import json
        from .portrait_match import align_portrait
        from .processing import adjust_image

        corrected, report = align_portrait(
            image, reference_image, skin_source, white_balance_strength, face_strength, body_strength,
            skin_luminance, {'neutral': neutral_mask, 'face': face_mask, 'body': body_mask},
            {'neutral': reference_neutral_mask, 'face': reference_face_mask, 'body': reference_body_mask})
        return (adjust_image(corrected, preserve_luminosity=preserve_luminosity, **values),
                json.dumps({'skin_source': skin_source, 'frames': report}, ensure_ascii=False, indent=2))
