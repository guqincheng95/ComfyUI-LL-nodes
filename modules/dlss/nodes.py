"""Stable V1 ComfyUI schemas; heavy/native imports happen only on execution."""

PRESETS = ['人像保真', '均衡增强', '环境增强', '自定义']


def unit(default, tip=''):
    return ('FLOAT', {'default': default, 'min': 0., 'max': 1., 'step': .05, 'tooltip': tip})


class DLSS5Settings:
    CATEGORY = 'LL 节点库/图像后期/DLSS5 神经增强'
    FUNCTION = 'build'
    RETURN_TYPES = ('LL_DLSS5_SETTINGS',)
    RETURN_NAMES = ('settings',)
    DESCRIPTION = '整图仅渲染一次；预设决定原生参数和区域强度。自定义可逐项调整。首次使用先运行 setup_dlss5.bat。'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'preset': (PRESETS, {'default': '人像保真', 'tooltip': '预设会覆盖下方光影、结构、区域和保护参数；选择自定义才使用这些数值。'}),
            'upscaling': (['1x', '1.5x', '1.724x', '2x', '3x'], {'default': '1x'}),
            'model': (['Default', 'J', 'K', 'L', 'M'], {'default': 'M'}),
            'style': (['自然', '默认', '电影'], {'default': '自然'}),
            'tone': ('FLOAT', {'default': 1., 'min': 0., 'max': 2., 'step': .05, 'tooltip': '原生光影／色调参数，不是区域混合强度。'}),
            'structure': ('FLOAT', {'default': 1.2, 'min': 0., 'max': 2., 'step': .05}),
            'skin_structure': ('FLOAT', {'default': .6, 'min': -1., 'max': 2., 'step': .05}),
            'automatic_skin_mask': ('BOOLEAN', {'default': True, 'tooltip': '原生皮肤识别，只控制皮肤结构；不替代外接人物 MASK。'}),
            'region_mode': (['unified_lighting', 'regional_all'], {'default': 'unified_lighting', 'tooltip': '统一光影：低频光影共享，细节分区；全部分区：所有变化都按区域混合。'}),
            'person_strength': unit(.35, '统一光影模式下主要控制人物细节；设为0仍保留统一光影。'),
            'background_strength': unit(1.),
            'lighting_strength': unit(.7, '统一光影模式的全图低频变化强度；全部分区模式忽略。'),
            'neutral_protection': unit(.35, '用原图中性区域限制色偏，保留新的亮度变化；无可靠样本则跳过。'),
            'skin_protection': unit(.6, '须接可见皮肤 MASK。限制肤色色度变化，保留增强亮度，不把衣服当皮肤。'),
            'edge_guard': unit(.7, '在人物边界降低细节混合差异；无法保证消除模型引起的位移。'),
            'feather': ('FLOAT', {'default': 6., 'min': 0., 'max': 64., 'step': 1., 'tooltip': '按原图像素设置，放大时同比换算。'}),
            'mask_expand': ('FLOAT', {'default': 0., 'min': -64., 'max': 64., 'step': 1.}),
            'temporal_mask_strength': unit(.4, '仅视频序列：按光流传播遮罩并与当前遮罩核对，切镜重置。'),
        }, 'optional': {
            'runtime_dir': ('STRING', {'default': '', 'tooltip': '留空使用安装脚本记录的目录；可复用原作者节点的兼容 v3.0 runtime。'}),
            'release_comfy_models': ('BOOLEAN', {'default': True, 'tooltip': '渲染前卸载 ComfyUI 已加载模型，释放显存；后续节点可能需要重新加载。'}),
            'worker_timeout': ('INT', {'default': 120, 'min': 30, 'max': 600, 'step': 10}),
            'scene_change_threshold': ('FLOAT', {'default': .24, 'min': .01, 'max': 1., 'step': .01}),
        }}

    def build(self, preset='人像保真', upscaling='1x', model='M', style='自然', tone=1., structure=1.2,
              skin_structure=.6, automatic_skin_mask=True, region_mode='unified_lighting',
              person_strength=.35, background_strength=1., lighting_strength=.7,
              neutral_protection=.35, skin_protection=.6, edge_guard=.7, feather=6., mask_expand=0.,
              temporal_mask_strength=.4, runtime_dir='', release_comfy_models=True,
              worker_timeout=120, scene_change_threshold=.24):
        from .native.settings import DlssOptions
        if preset not in PRESETS:
            raise ValueError('未知 DLSS5 预设。')
        mix = dict(mode=region_mode, person_strength=person_strength, background_strength=background_strength,
                   lighting_strength=lighting_strength, neutral_protection=neutral_protection,
                   skin_protection=skin_protection, edge_guard=edge_guard, feather=feather, expand=mask_expand)
        if preset != '自定义':
            tone, structure, skin_structure, person_strength, background_strength, lighting_strength = {
                '人像保真': (1., 1.2, .6, .35, .9, .65),
                '均衡增强': (1., 1.3, .8, .55, .85, .75),
                '环境增强': (1.2, 1.6, .6, .3, 1., .85),
            }[preset]
            mix.update(mode='unified_lighting', person_strength=person_strength,
                       background_strength=background_strength, lighting_strength=lighting_strength,
                       neutral_protection=.35, skin_protection=.6, edge_guard=.7)
        options = DlssOptions.create(upscaling_factor=float(upscaling.removesuffix('x')),
            nr_style={'自然': 'Natural', '默认': 'Default', '电影': 'Cinematic'}[style],
            dlss_model_preset=model, local_tone_strength=tone, local_structure_strength=structure,
            skin_structure_strength=skin_structure, automatic_mask=bool(automatic_skin_mask),
            scene_change_threshold=scene_change_threshold)
        return ({'options': options, 'mix': mix, 'preset': preset, 'runtime_dir': runtime_dir,
                 'release_comfy_models': release_comfy_models, 'worker_timeout': worker_timeout,
                 'temporal_mask_strength': temporal_mask_strength},)


class DLSS5RegionEnhance:
    CATEGORY = DLSS5Settings.CATEGORY
    FUNCTION = 'enhance'
    RETURN_TYPES = ('IMAGE', 'MASK', 'STRING')
    RETURN_NAMES = ('image', 'person_mask', 'report')
    DESCRIPTION = '全画面单次 DLSS5 渲染，再按外接人物／皮肤 MASK 控制增强。无需新分割模型。预览模式输出低分辨率，正式导出请关闭。'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'image': ('IMAGE',), 'settings': ('LL_DLSS5_SETTINGS',),
            'batch_mode': (['independent_images', 'video_sequence'], {'default': 'independent_images', 'tooltip': '独立图片逐张重置历史；视频必须按帧顺序输入，并建议提供逐帧 MASK。'}),
            'preview_mode': ('BOOLEAN', {'default': False, 'tooltip': '缩小完整画面后增强，保留上下文。输出也是预览尺寸，不能当作原尺寸成片。'}),
            'preview_long_edge': ('INT', {'default': 1024, 'min': 256, 'max': 2048, 'step': 64}),
        }, 'optional': {
            'person_mask': ('MASK', {'tooltip': '白色人物、黑色环境。推荐使用分割模型的完整人物 MASK，勿用删除头发／裙摆后的轮廓修剪结果。'}),
            'skin_mask': ('MASK', {'tooltip': '可见皮肤：脸／身体／手，可合并；排除眼唇、衣服和遮挡。缺省不执行外部肤色保护。'}),
        }}

    def enhance(self, image, settings, batch_mode='independent_images', preview_mode=False,
                preview_long_edge=1024, person_mask=None, skin_mask=None):
        from .runner import enhance
        return enhance(image, settings, batch_mode, preview_mode, preview_long_edge, person_mask, skin_mask)


class DLSS5Compare:
    CATEGORY = DLSS5Settings.CATEGORY
    FUNCTION = 'compare'
    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('comparison', 'report')
    DESCRIPTION = '左原图、右增强；先完整渲染再裁出 ROI，不改变光照上下文。仅首帧检查，可接预览图像节点。'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'original': ('IMAGE',), 'enhanced': ('IMAGE',),
            'x': unit(0.), 'y': unit(0.), 'width': unit(1.), 'height': unit(1.),
        }, 'optional': {'roi_mask': ('MASK', {'tooltip': '优先用白色区域的包围框作为检查范围；未接时使用上方0～1坐标。'})}}

    def compare(self, original, enhanced, x=0., y=0., width=1., height=1., roi_mask=None):
        import json
        import torch
        from .processing import comparison, mask_batch
        if original.ndim != 4 or enhanced.ndim != 4 or min(original.shape) < 1 or min(enhanced.shape) < 1:
            raise ValueError('对比输入需为非空 IMAGE。')
        if any(not 0 <= v <= 1 for v in (x, y, width, height)):
            raise ValueError('局部坐标需在0～1内。')
        masks = mask_batch(roi_mask, len(enhanced), original.shape[1:3], enhanced.shape[1:3], '局部预览遮罩')
        result, report = comparison(original[0].detach().float().cpu().numpy(),
            enhanced[0].detach().float().cpu().numpy(), None if masks is None else masks[0], x, y, width, height)
        return torch.from_numpy(result[None]), json.dumps(report, ensure_ascii=False)
