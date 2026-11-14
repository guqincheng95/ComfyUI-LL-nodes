"""One native render per frame; no downloads or implicit dependency changes."""
from __future__ import annotations

from dataclasses import replace
import json
import platform
import threading

import numpy as np
import torch

from .native.paths import find_runtime
from .native.session import DlssSession
from .native.motion import TemporalGuide
from .native.imaging import tensor_to_rgba, rgba_to_tensor
from .native.settings import resolve_output_size
from .processing import resize_image, mask_batch, compose, TemporalMask

_RENDER_LOCK = threading.Lock()


def _comfy_callbacks(release):
    try:
        from comfy import model_management
        from comfy.utils import ProgressBar
    except ImportError as exc:
        raise RuntimeError('请在 ComfyUI 中执行增强节点。环境检查请运行 setup_dlss5.py --check。') from exc
    if release:
        model_management.unload_all_models()
        model_management.soft_empty_cache()
    return model_management.throw_exception_if_processing_interrupted, ProgressBar


def enhance(images, settings=None, batch_mode='independent_images', preview_mode=False,
            preview_long_edge=1024, person_mask=None, skin_mask=None,
            *, processing_mode='auto', _session_factory=None, _callbacks=None, _platform=None):
    """Injected backend/callbacks are test seams, never an exposed fallback renderer."""
    if (_platform or platform.system()) != 'Windows':
        raise RuntimeError('DLSS5 原生渲染需要 Windows 64位＋受支持的 NVIDIA RTX 显卡；其它 LL 节点仍可使用。')
    if batch_mode not in ('independent_images', 'video_sequence'):
        raise ValueError('批次类型必须是独立图片或视频序列。')
    if images.ndim != 4 or min(images.shape) < 1 or images.shape[-1] not in (3, 4):
        raise ValueError('输入需要非空 [B,H,W,3/4] IMAGE。')
    if processing_mode not in ('auto', 'native', 'regional'):
        raise ValueError('处理方式需为自动、原生直出或分区增强。')
    regional = processing_mode == 'regional' or (processing_mode == 'auto' and
        (settings is not None or person_mask is not None or skin_mask is not None))
    if settings is None:
        from .nodes import DLSS5Settings
        from .native.settings import DlssOptions
        settings, = DLSS5Settings().build()
        if not regional:
            # Match upstream's actual defaults, not the LL portrait preset.
            settings['options'] = DlssOptions()
            settings['preset'] = '原生默认'
    options = settings['options']
    count, source_h, source_w, channels = images.shape
    in_w, in_h = source_w, source_h
    if preview_mode:
        scale = min(1., int(preview_long_edge) / (max(in_w, in_h) * options.upscaling_factor))
        in_w, in_h = max(1, round(in_w * scale)), max(1, round(in_h * scale))
    if min(in_w, in_h) < 64:
        raise ValueError('DLSS5 输入短边至少64像素，请调整输入或预览尺寸。')
    out_w, out_h = resolve_output_size(in_w, in_h, options.upscaling_factor)
    output_bytes = count * out_h * out_w * (channels + 1) * 4
    if output_bytes > 2 * 1024 ** 3:
        raise ValueError('本批输出图像＋遮罩超过2GiB，请拆分视频帧批次或使用预览模式。')
    # Fail on misaligned masks before unloading models or starting native rendering.
    people = mask_batch(person_mask, count, (source_h, source_w), (out_h, out_w), '人物遮罩') if regional else None
    skins = mask_batch(skin_mask, count, (source_h, source_w), (out_h, out_w), '皮肤遮罩') if regional else None
    sequence = batch_mode == 'video_sequence'
    warnings = []
    if regional and people is None:
        warnings.append('未接人物遮罩，区域细节强度全图采用环境值。原生自动皮肤结构仍由设置控制。')
    if not regional and (person_mask is not None or skin_mask is not None):
        warnings.append('原生直出模式忽略外接遮罩，不执行LL分区／色彩保护。')
    if sequence and count > 1:
        if people is not None and len(people) == 1:
            warnings.append('视频只有一张人物遮罩，将广播到每帧；运动主体建议使用逐帧分割遮罩。')
        if skins is not None and len(skins) == 1:
            warnings.append('视频只有一张皮肤遮罩，将广播到每帧；可能与运动皮肤错位。')
    if preview_mode:
        warnings.append('当前为低分辨率整图预览，输出尺寸不是正式尺寸。')
    if not _RENDER_LOCK.acquire(blocking=False):
        raise RuntimeError('另一个 LL DLSS5 任务正在运行，请完成或取消后重试。')
    try:
        layout = find_runtime(settings.get('runtime_dir') or None)
        interrupt, progress_cls = (_callbacks or _comfy_callbacks)(settings.get('release_comfy_models', True))
        interrupt()
        factory = _session_factory or DlssSession
        # Disconnected stills always reset history, regardless of visual similarity.
        options = replace(options, motion_mode='optical_flow' if sequence else 'none')
        frame_reports = []
        with factory(layout, options, input_width=in_w, input_height=in_h, frame_count=count,
                     timeout=settings.get('worker_timeout', 120), cancel_check=interrupt) as session:
            guide = TemporalGuide(session.render_width, session.render_height,
                flow_width=options.flow_width, scene_change_threshold=options.scene_change_threshold,
                enabled=sequence and count > 1)
            results = torch.empty((count, out_h, out_w, channels), dtype=torch.float32)
            masks = torch.empty((count, out_h, out_w), dtype=torch.float32)
            progress = progress_cls(count)
            temporal_person = TemporalMask(settings.get('temporal_mask_strength', .4))
            temporal_skin = TemporalMask(settings.get('temporal_mask_strength', .4))
            colour_state = {} if sequence else None
            for index in range(count):
                interrupt()
                raw = images[index].detach().float().cpu().numpy()
                # Exactly the same normalized coordinate grid for colour, masks, and alpha.
                rgba = tensor_to_rgba(torch.from_numpy(resize_image(raw, session.render_width, session.render_height)))
                motion = guide.process(rgba)
                reset = motion.reset if sequence else True
                enhanced, _ = session.submit(index=index, rgba=rgba, motion=motion.motion, reset=reset, pts=index)
                p = None if people is None else people[0 if len(people) == 1 else index]
                s = None if skins is None else skins[0 if len(skins) == 1 else index]
                if sequence:
                    p = temporal_person.process(p, motion.motion, reset)
                    s = temporal_skin.process(s, motion.motion, reset)
                native = rgba_to_tensor(enhanced, keep_alpha=False).numpy()
                if regional:
                    source = resize_image(raw, out_w, out_h)
                    mix = dict(settings['mix'])
                    factor = out_w / source_w
                    mix['feather'] *= factor
                    mix['expand'] *= factor
                    result, mask, report = compose(source, native, p, s,
                                                   colour_state=colour_state, reset=reset, **mix)
                else:
                    result = native
                    if channels == 4:
                        alpha = resize_image(raw, out_w, out_h)[..., 3:4]
                        result = np.concatenate([native, alpha], axis=-1)
                    mask = np.zeros((out_h, out_w), np.float32)
                    report = {'mode': 'native', 'll_postprocessing': False}
                results[index] = torch.from_numpy(result)
                masks[index] = torch.from_numpy(mask)
                report.update(frame=index, reset_history=reset, scene_score=motion.scene_score)
                frame_reports.append(report)
                progress.update(1)
        # Never report success merely because the worker returned an upscaled frame.
        proof = session.feature_report()
        report = {'version': '0.12.1', 'preset': settings['preset'], 'native_passes_per_frame': 1,
                  'processing_mode': 'regional' if regional else 'native',
                  'input_size': [source_w, source_h], 'output_size': [out_w, out_h],
                  'preview': bool(preview_mode), 'batch_mode': batch_mode,
                  'native_settings': options.native(), 'regional_settings': settings['mix'] if regional else None,
                  'warnings': warnings, 'neural_rendering': proof, 'frames': frame_reports}
        return results, masks, json.dumps(report, ensure_ascii=False, indent=2)
    except RuntimeError as exc:
        # Preserve ComfyUI's cancellation exception type after killing a blocked worker.
        if 'interrupt' in locals():
            interrupt()
        raise RuntimeError('LL DLSS5 增强失败。环境缺失时主节点会自动部署，详情请查看控制台；若是 NGX 初始化错误，'
            '请关闭其它 GPU 任务并检查显卡驱动和运行时配套版本。原始错误：\n' + str(exc)) from exc
    finally:
        _RENDER_LOCK.release()
