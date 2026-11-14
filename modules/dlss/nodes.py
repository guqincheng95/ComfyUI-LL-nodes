"""Stable V1 ComfyUI schemas; heavy/native imports happen only on execution."""

PRESETS = ['人像保真', '均衡增强', '环境增强', '自定义']
DLSS_CATEGORY = 'LL 节点库/图像后期/DLSS5 神经增强'
COMPAT_CATEGORY = 'LL 节点库/兼容节点/DLSS5 旧版'


def unit(default, tip=''):
    return ('FLOAT', {'default': default, 'min': 0., 'max': 1., 'step': .05, 'tooltip': tip})


class DLSS5Settings:
    DEPRECATED = True
    CATEGORY = COMPAT_CATEGORY
    FUNCTION = 'build'
    RETURN_TYPES = ('LL_DLSS5_SETTINGS',)
    RETURN_NAMES = ('settings',)
    DESCRIPTION = '旧工作流兼容节点，已弃用。新工作流请直接使用LL DLSS5图像增强，参数已合并到主节点。'

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
            'auto_setup': ('BOOLEAN', {'default': True, 'tooltip': '首次运行自动检查，缺失时下载兼容运行时并补齐依赖，完成后继续增强。不会安装驱动或更换Torch/CUDA。'}),
            'setup_archive': ('STRING', {'default': '', 'tooltip': '可选：固定v3.0原始离线ZIP完整路径。留空在线下载或复用缓存。'}),
            'setup_index_url': ('STRING', {'default': '', 'tooltip': '可选：缺失Python依赖的镜像源simple地址。'}),
            'setup_download_prefix': ('STRING', {'default': '', 'tooltip': '可选：HTTPS下载代理前缀；仍校验原始发布包SHA256。'}),
            'setup_wheel_dir': ('STRING', {'default': '', 'tooltip': '可选：匹配当前Python和Windows的离线wheel文件夹。'}),
            'setup_http_proxy': ('STRING', {'default': '', 'tooltip': '可选HTTP/HTTPS代理地址。留空检测系统／环境代理；PAC和浏览器代理不保证被Python使用。'}),
            'setup_official_only': ('BOOLEAN', {'default': False, 'tooltip': '关闭时测速GitHub与公共加速入口，择优并回退；开启只使用GitHub原始地址。'}),
        }}

    def build(self, preset='人像保真', upscaling='1x', model='M', style='自然', tone=1., structure=1.2,
              skin_structure=.6, automatic_skin_mask=True, region_mode='unified_lighting',
              person_strength=.35, background_strength=1., lighting_strength=.7,
              neutral_protection=.35, skin_protection=.6, edge_guard=.7, feather=6., mask_expand=0.,
              temporal_mask_strength=.4, runtime_dir='', release_comfy_models=True,
              worker_timeout=120, scene_change_threshold=.24, auto_setup=True,
              setup_archive='', setup_index_url='', setup_download_prefix='', setup_wheel_dir='',
              setup_http_proxy='', setup_official_only=False):
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
                 'temporal_mask_strength': temporal_mask_strength, 'auto_setup': auto_setup,
                 'setup_archive': setup_archive, 'setup_index_url': setup_index_url,
                 'setup_download_prefix': setup_download_prefix, 'setup_wheel_dir': setup_wheel_dir,
                 'setup_http_proxy': setup_http_proxy, 'setup_official_only': setup_official_only},)


class DLSS5RegionEnhance:
    CATEGORY = DLSS_CATEGORY
    FUNCTION = 'enhance'
    RETURN_TYPES = ('IMAGE', 'MASK', 'STRING')
    RETURN_NAMES = ('image', 'person_mask', 'report')
    DESCRIPTION = '一个节点完成原生整图增强、参数设置、人物分区和内嵌局部对比。只接图片即可运行；展开高级设置可细调。旧settings输入仅用于兼容。'

    @classmethod
    def INPUT_TYPES(cls):
        inline = DLSS5Settings.INPUT_TYPES()
        controls = {**inline['required'], **inline['optional']}
        controls.update({
            'preset': (['原生默认', *PRESETS], {'default': '原生默认', 'tooltip': '原生默认保留原版参数；人像／均衡／环境预设包含LL分区处理；自定义按处理方式生效。'}),
            'style': (['默认', '自然', '电影'], {'default': '默认'}),
            'structure': ('FLOAT', {'default': 1.5, 'min': 0., 'max': 2., 'step': .05}),
            'skin_structure': ('FLOAT', {'default': 2., 'min': -1., 'max': 2., 'step': .05}),
        })
        # Append setup widgets after every v0.12.0 widget, so old positional
        # workflow values don't get reinterpreted as proxy/archive settings.
        setup_names = ('auto_setup', 'setup_archive', 'setup_index_url', 'setup_download_prefix',
                       'setup_wheel_dir', 'setup_http_proxy', 'setup_official_only')
        setup_controls = {name: controls.pop(name) for name in setup_names}
        return {'required': {
            'image': ('IMAGE',),
            'batch_mode': (['independent_images', 'video_sequence'], {'default': 'independent_images', 'tooltip': '独立图片逐张重置历史；视频必须按帧顺序输入，并建议提供逐帧 MASK。'}),
            'preview_mode': ('BOOLEAN', {'default': False, 'tooltip': '缩小完整画面后增强，保留上下文。输出也是预览尺寸，不能当作原尺寸成片。'}),
            'preview_long_edge': ('INT', {'default': 1024, 'min': 256, 'max': 2048, 'step': 64}),
        }, 'optional': {
            'settings': ('LL_DLSS5_SETTINGS', {'tooltip': '旧工作流兼容输入，可不接。接入后以外部设置为准，忽略主节点内置参数。'}),
            'person_mask': ('MASK', {'tooltip': '白色人物、黑色环境。推荐使用分割模型的完整人物 MASK，勿用删除头发／裙摆后的轮廓修剪结果。'}),
            'skin_mask': ('MASK', {'tooltip': '可见皮肤：脸／身体／手，可合并；排除眼唇、衣服和遮挡。缺省不执行外部肤色保护。'}),
            'processing_mode': (['auto', 'native', 'regional'], {'default': 'auto', 'tooltip': '自动：原生默认且无遮罩时整图直出；接遮罩或选人像／均衡／环境预设时分区。可明确指定原生或分区。'}),
            **controls,
            'show_advanced': ('BOOLEAN', {'default': False, 'tooltip': '只控制参数展开显示，不改变已保存的参数值。'}),
            'compare_preview': ('BOOLEAN', {'default': False, 'tooltip': '在本节点内显示左原图／右结果；正式图像输出不受影响。'}),
            'roi_mask': ('MASK', {'tooltip': '可选：仅用于对比预览的范围；不参与人物分区或渲染。'}),
            'roi_x': unit(0.), 'roi_y': unit(0.), 'roi_width': unit(1.), 'roi_height': unit(1.),
            **setup_controls,
        }, 'hidden': {'prompt': 'PROMPT', 'extra_pnginfo': 'EXTRA_PNGINFO'}}

    def enhance(self, image, settings=None, batch_mode='independent_images', preview_mode=False,
                preview_long_edge=1024, person_mask=None, skin_mask=None, processing_mode='auto',
                preset='原生默认', compare_preview=False, roi_mask=None, roi_x=0., roi_y=0.,
                roi_width=1., roi_height=1., show_advanced=False, prompt=None, extra_pnginfo=None, **values):
        if settings is None:
            settings = inline_settings(preset, values)
            if processing_mode == 'auto':
                processing_mode = 'regional' if person_mask is not None or skin_mask is not None or preset in PRESETS[:3] else 'native'
        # Bootstrap before importing runner: numpy/cv2 can be missing initially.
        from .bootstrap import ensure_environment
        ensure_environment(settings)
        from .runner import enhance
        result = enhance(image, settings, batch_mode, preview_mode, preview_long_edge, person_mask, skin_mask,
                         processing_mode=processing_mode)
        if compare_preview:
            from .preview import comparison_preview
            return comparison_preview(image, result, roi_mask, roi_x, roi_y, roi_width, roi_height, prompt, extra_pnginfo)
        return result


def inline_settings(preset='原生默认', values=None):
    """Shared settings implementation; the old node is never required by the graph."""
    values = dict(values or {})
    defaults = {'style': '默认', 'structure': 1.5, 'skin_structure': 2.}
    defaults.update(values)
    result, = DLSS5Settings().build(preset='自定义' if preset == '原生默认' else preset, **defaults)
    result['preset'] = preset
    return result


class DLSS5Compare:
    DEPRECATED = True
    CATEGORY = COMPAT_CATEGORY
    FUNCTION = 'compare'
    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('comparison', 'report')
    DESCRIPTION = '旧工作流兼容节点，已弃用。新工作流直接开启LL DLSS5图像增强节点内的对比预览。'

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
