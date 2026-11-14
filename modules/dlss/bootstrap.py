"""Prepare DLSS5 on first execution; importing this module has no side effects.

Keep stdlib-only so missing optional packages can be installed before runner import.
"""
from __future__ import annotations

import importlib
import platform
import sys
import threading

from . import runtime_setup
from .native.paths import find_runtime

_LOCK = threading.Lock()


def _ready(runtime_dir):
    if not all(runtime_setup._import_ok(name)['ready'] for name in ('torch', 'numpy', 'cv2')):
        return False
    try:
        importlib.import_module('torch').zeros(1).numpy()
        layout = find_runtime(runtime_dir or None)
        runtime_setup.verify_files(layout.root)
        layout.require_ffmpeg()
        return True
    except (RuntimeError, OSError):
        return False


def _comfy_hooks(release):
    try:
        from comfy import model_management
        from comfy.utils import ProgressBar
    except ImportError as exc:
        raise RuntimeError('请在ComfyUI中运行节点；独立环境请使用setup_dlss5.py。') from exc
    if release:
        model_management.unload_all_models()
        model_management.soft_empty_cache()
    bar = ProgressBar(100)
    return model_management.throw_exception_if_processing_interrupted, lambda value, message: bar.update_absolute(value, 100)


def _refresh_optional_imports():
    importlib.invalidate_caches()
    cv2 = importlib.import_module('cv2')
    # An earlier direct import may have cached optional cv2=None in these modules.
    for name in ('native.imaging', 'native.motion'):
        module = sys.modules.get(__package__ + '.' + name)
        if module is not None:
            module.cv2 = cv2


def ensure_environment(settings, *, _platform=None, _hooks=None):
    if (_platform or platform.system()) != 'Windows':
        raise RuntimeError('DLSS5需要Windows 64位＋兼容NVIDIA RTX显卡；不会在不支持的系统自动安装。')
    runtime_dir = settings.get('runtime_dir', '').strip()
    if _ready(runtime_dir):
        _refresh_optional_imports()
        return
    if not settings.get('auto_setup', True):
        raise RuntimeError('DLSS5环境缺失且自动部署已关闭。请开启高级设置中的自动部署，或运行setup_dlss5.bat。')
    cancel_check, progress = (_hooks or _comfy_hooks)(settings.get('release_comfy_models', True))
    cancel_check()
    while not _LOCK.acquire(timeout=.25):
        cancel_check()
    try:
        # Another node in this process may have completed deployment while we waited.
        if _ready(runtime_dir):
            _refresh_optional_imports()
            return
        args = []
        for key, flag in (('runtime_dir', '--runtime-dir'), ('setup_archive', '--archive'),
                          ('setup_index_url', '--index-url'), ('setup_download_prefix', '--download-prefix'),
                          ('setup_wheel_dir', '--wheel-dir'), ('setup_http_proxy', '--http-proxy')):
            value = str(settings.get(key, '') or '').strip()
            if value:
                args += [flag, value]
        if settings.get('setup_official_only', False):
            args.append('--official-only')
        print('[LL DLSS5] 首次运行正在准备环境；完成后继续当前增强任务。', flush=True)
        result = runtime_setup.main(args, cancel_check=cancel_check, progress_callback=progress)
        if result:
            raise RuntimeError('DLSS5自动部署未完成，具体原因见ComfyUI控制台。可在高级设置中填写离线ZIP或镜像；驱动／硬件条件需手动处理。')
        _refresh_optional_imports()
        if not _ready(runtime_dir):
            raise RuntimeError('部署后当前进程仍无法使用依赖，请查看控制台并重启ComfyUI；不会重复覆盖现有Torch/CUDA。')
        cancel_check()
    finally:
        _LOCK.release()
