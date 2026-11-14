"""Standalone, idempotent Windows setup. Stdlib only until dependency repair.

User-invoked, Manager hook, or first-execution bootstrap. Import never installs.
The release and SHA256 are pinned to upstream's protocol-v4 compatible bundle.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'runtime' / 'dlss5'
RELEASE_URL = 'https://github.com/Merserk/dlss5-visual-enhancer/releases/download/v3.0/DLSS.5.Visual.Enhancer.v3.0.zip'
RELEASE_SHA256 = '6f0590d81677484f4ecdfaa5c44fc2a0e1a3835d33eefc59d656e6c3bcf35f6a'
REQUIRED = ('nvngx.dll', 'dxgi.dll', 'renodx-dlss5.addon64', 'nvngx_dlss.dll', 'nvngx_dlssnr.dll')
NOTICE = ('LL DLSS5 安装：使用 NVIDIA DLSS 神经渲染，非 LL 自训练模型。\n'
          '下载来自 Merserk 原项目的兼容 v3.0 发布包，约467MB；NVIDIA/ReShade/RenoDX组件各自授权。\n'
          '仅修复当前 Python 中缺失的 numpy/OpenCV 和本插件运行时；不安装或升级 Torch/CUDA/显卡驱动。')


def sha256(path, cancel_check=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if cancel_check:
                cancel_check()
            digest.update(chunk)
    return digest.hexdigest()


def _import_ok(name):
    try:
        module = importlib.import_module(name)
        return {'ready': True, 'version': getattr(module, '__version__', 'unknown')}
    except (ImportError, OSError, RuntimeError) as exc:
        return {'ready': False, 'reason': str(exc)}


def inspect_environment():
    report = {'python': sys.executable, 'python_version': platform.python_version(),
              'platform': platform.system(), 'bits': struct.calcsize('P') * 8,
              'dependencies': {name: _import_ok(name) for name in ('torch', 'numpy', 'cv2')},
              'hardware_ready': False, 'runtime_ready': False, 'warnings': []}
    if report['platform'] != 'Windows' or report['bits'] != 64:
        report['hardware_error'] = '原生 D3D12 运行时只支持 Windows 64位；其它 LL 节点不受影响。'
        return report
    if sys.version_info < (3, 10):
        report['hardware_error'] = '需要 Python 3.10 或更新版本。'
        return report
    try:
        ctypes.WinDLL('d3d12.dll')
        report['d3d12'] = True
    except OSError as exc:
        report['hardware_error'] = 'Windows D3D12 组件不可用：' + str(exc)
        return report
    # The native package is intentionally lazy-importable without torch/cv2.
    from .native.diagnostics import detect_gpu
    try:
        report['gpu'] = detect_gpu()
        report['hardware_ready'] = True
        if report['gpu']['generation'] != 50:
            report['warnings'].append('RTX30/40 为社区运行时路径；RTX30还需精确配套二进制。不等于 NVIDIA 官方支持。')
        report['warnings'].append('多显卡电脑仅能检测兼容候选；底层程序未提供 GPU 索引选择，实际使用设备需实测。')
    except (RuntimeError, ValueError) as exc:
        report['hardware_error'] = str(exc)
    from .native.paths import find_runtime
    try:
        layout = find_runtime()
        report['runtime_dir'] = str(layout.root)
        report['runtime_ready'] = all((layout.root / name).stat().st_size > 0 for name in REQUIRED)
        try:
            layout.require_ffmpeg()
            report['ffmpeg_ready'] = True
        except RuntimeError:
            report['ffmpeg_ready'] = False
    except RuntimeError as exc:
        report['runtime_error'] = str(exc)
    report['ready'] = report['hardware_ready'] and report['runtime_ready'] and all(
        item['ready'] for item in report['dependencies'].values())
    report['native_execution_verified'] = False
    return report


def run_checked(command, timeout=600, cancel_check=None):
    if cancel_check is None:
        return subprocess.run(command, check=True, timeout=timeout)
    process = subprocess.Popen(command)
    started = time.monotonic()
    try:
        while process.poll() is None:
            cancel_check()
            if time.monotonic() - started > timeout:
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(.15)
        cancel_check()
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        raise


def install_dependencies(index_url=None, wheel_dir=None, cancel_check=None, proxy=''):
    if not _import_ok('torch')['ready']:
        raise RuntimeError('当前 Python 无法导入 Torch。请选择运行 ComfyUI 的 Python；本脚本不擅自更换 Torch/CUDA。')
    for module, package in (('numpy', 'numpy>=1.24,<3'), ('cv2', 'opencv-python-headless==4.11.0.86')):
        if cancel_check:
            cancel_check()
        if _import_ok(module)['ready']:
            print(f'[已有] {module}，保留当前版本。', flush=True)
            continue
        # Don't replace a broken contrib/OpenCV distribution with a different flavour.
        if module == 'cv2':
            from importlib.metadata import distributions
            existing = [d.metadata['Name'] for d in distributions()
                        if d.metadata.get('Name', '').lower().replace('_', '-').startswith('opencv-')]
            if existing:
                raise RuntimeError('已安装 ' + ', '.join(existing) + ' 但 cv2 导入失败，请修复原 OpenCV 环境后重试。')
        command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', package]
        # Avoid changing an installed numpy for an OpenCV dependency resolution.
        if module == 'cv2':
            command += ['--no-deps']
        print('[安装缺失依赖] ' + package, flush=True)
        if proxy:
            command += ['--proxy', proxy]
        if wheel_dir:
            choices = [['--no-index', '--find-links', str(wheel_dir)]]
        else:
            configured = index_url or os.environ.get('PIP_INDEX_URL')
            choices = ([['--index-url', configured]] if configured else [
                ['--index-url', 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple'],
                ['--index-url', 'https://pypi.org/simple'],
            ])
        for number, source in enumerate(choices):
            try:
                run_checked(command + source + ['--timeout', '15', '--retries', '1'], timeout=600, cancel_check=cancel_check)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if number + 1 == len(choices):
                    raise
                print('[依赖源切换] 清华镜像未完成安装，尝试PyPI原始源。', flush=True)
        importlib.invalidate_caches()
        if not _import_ok(module)['ready']:
            raise RuntimeError(f'{module}安装后仍无法导入，请重启安装脚本并检查 Python 环境。')


def download_archive(url, target, *, cancel_check=None, progress_callback=None,
                     prefix='', proxy='', official_only=False):
    from .download import download
    return download(url, target, RELEASE_SHA256,
        466919995 if url == RELEASE_URL else None, prefix=prefix, mirrors=not official_only,
        proxy=proxy, cancel_check=cancel_check, progress_callback=progress_callback)


def extract_verified(archive_path, staging, expected_sha256=RELEASE_SHA256, cancel_check=None):
    """Authenticate first, then validate every selected member before any extraction."""
    if sha256(archive_path, cancel_check) != expected_sha256:
        raise RuntimeError('离线／缓存 ZIP 的 SHA-256 不匹配；要求兼容的原始 v3.0 发布包。')
    staging = Path(staging)
    selected, total, destinations = [], 0, set()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace('\\', '/')
            parts = PurePosixPath(name).parts
            if any(p in ('.', '..') or ':' in p for p in parts) or name.startswith('/'):
                raise ValueError('发布包包含不安全路径：' + info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('发布包不允许符号链接：' + info.filename)
            lowered = [p.lower() for p in parts]
            for marker, group in ((['bin', 'runtime'], 'runtime'), (['bin', 'ffmpeg', 'bin'], 'ffmpeg')):
                for start in range(len(parts) - len(marker)):
                    if lowered[start:start + len(marker)] == marker:
                        relative = Path(*parts[start + len(marker):])
                        key = (group, str(relative).lower())
                        if key in destinations:
                            raise ValueError('发布包包含重名文件。')
                        destinations.add(key)
                        total += info.file_size
                        if total > 2 * 1024 ** 3:
                            raise ValueError('解压内容超过2GiB限制。')
                        selected.append((info, staging / group / relative))
                        break
        for required in REQUIRED:
            if ('runtime', required) not in destinations:
                raise RuntimeError('发布包缺少 runtime/' + required)
        for required in ('ffmpeg.exe', 'ffprobe.exe'):
            if ('ffmpeg', required) not in destinations:
                raise RuntimeError('发布包缺少 ffmpeg/' + required)
        for info, path in selected:
            if cancel_check:
                cancel_check()
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, path.open('wb') as sink:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    if cancel_check:
                        cancel_check()
                    sink.write(block)
    verify_files(staging / 'runtime')
    return staging


def verify_files(runtime):
    runtime = Path(runtime)
    missing = [n for n in REQUIRED if not (runtime / n).is_file() or (runtime / n).stat().st_size < 2]
    if missing:
        raise RuntimeError('运行时文件不完整：' + ', '.join(missing))
    for name in REQUIRED:
        with (runtime / name).open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise RuntimeError('运行时不是有效的 Windows PE 文件：' + name)


def install_staged(staging, data, groups=('runtime', 'ffmpeg')):
    """Rollback both directories together if a locked DLL or rename fails."""
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    moved, backups = [], []
    try:
        for name in groups:
            destination = data / name
            backup = data / (name + '.previous')
            if backup.exists():
                raise RuntimeError(f'发现上次备份 {backup}，请先核对并移走，防止覆盖。')
            if destination.exists():
                destination.rename(backup)
                backups.append((backup, destination))
            (Path(staging) / name).rename(destination)
            moved.append(destination)
    except BaseException:
        for destination in reversed(moved):
            shutil.rmtree(destination)
        for backup, destination in reversed(backups):
            backup.rename(destination)
        raise
    for backup, _ in backups:
        shutil.rmtree(backup)


def resolve_ffmpeg_directory(runtime):
    from .native.paths import find_runtime
    try:
        layout = find_runtime(str(runtime)).require_ffmpeg()
        return layout.ffmpeg.parent
    except RuntimeError:
        return None


def smoke_test(runtime, timeout=120, cancel_check=None):
    """Tiny real worker roundtrip, protocol and signed feature-18 evidence required."""
    import numpy as np
    from .native.paths import RuntimeLayout
    from .native.session import DlssSession
    from .native.settings import DlssOptions
    layout = RuntimeLayout(Path(runtime)).validate()
    rgba = np.full((512, 512, 4), 128, np.uint8)
    rgba[..., 3] = 255
    with DlssSession(layout, DlssOptions.create(dlss_model_preset='Default'),
                     input_width=512, input_height=512, frame_count=1, timeout=timeout,
                     cancel_check=cancel_check) as session:
        from .native.imaging import fit_frame
        fitted = fit_frame(rgba, session.render_width, session.render_height)
        result, _ = session.submit(index=0, rgba=fitted,
            motion=np.zeros((session.render_height, session.render_width, 2), np.float16), reset=True, pts=0)
        if result.shape != (session.output_height, session.output_width, 4):
            raise RuntimeError('运行时自检输出尺寸错误。')
    return session.feature_report()


@contextlib.contextmanager
def setup_lock(data):
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    path = data / '.setup.lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError('另一个安装正在运行，或上次中断留下 .setup.lock；确认无安装进程后再删除锁文件。') from exc
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def main(argv=None, *, cancel_check=None, progress_callback=None):
    def progress(value, message):
        if cancel_check:
            cancel_check()
        if progress_callback:
            progress_callback(value, message)
    parser = argparse.ArgumentParser(description=NOTICE)
    parser.add_argument('--check', action='store_true', help='只检测，不写文件、不联网安装。')
    parser.add_argument('--archive', type=Path, help='原始 v3.0 离线 ZIP。')
    parser.add_argument('--runtime-dir', type=Path, help='复用已有兼容 runtime，不复制修改其文件。')
    parser.add_argument('--download-prefix', help='自选 HTTPS 下载代理前缀，拼接原始 GitHub 地址；仍需通过原包 SHA256。')
    parser.add_argument('--index-url', help='Python 包镜像地址。')
    parser.add_argument('--http-proxy', default='', help='显式HTTP/HTTPS代理地址；不填写使用系统／环境代理。')
    parser.add_argument('--official-only', action='store_true', help='仅使用GitHub原始下载地址，不测速公共加速入口。')
    parser.add_argument('--wheel-dir', type=Path, help='离线 wheel 文件夹。')
    parser.add_argument('--skip-self-test', action='store_true', help='仅部署，报告明确标记尚未验证原生执行。')
    parser.add_argument('--force', action='store_true', help='重新部署固定版本。')
    args = parser.parse_args(argv)
    progress(2, '检查运行环境')
    report = inspect_environment()
    if args.check:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get('ready') else 2
    print(NOTICE, flush=True)
    print('当前 Python：' + sys.executable, flush=True)
    if not report['hardware_ready']:
        print('[不满足运行条件] ' + report.get('hardware_error', '硬件不兼容'), flush=True)
        return 2
    try:
        with setup_lock(DATA):
            if args.official_only and args.download_prefix:
                raise ValueError('仅官方来源与自选下载前缀不能同时使用。')
            progress(8, '补齐缺失Python依赖')
            install_dependencies(args.index_url, args.wheel_dir, cancel_check=cancel_check, proxy=args.http_proxy)
            from .native.paths import write_config, find_runtime, RuntimeLayout
            from .native.diagnostics import ensure_supported
            runtime = args.runtime_dir.expanduser().resolve() if args.runtime_dir else None
            if runtime is None and not args.force and not args.archive:
                try:
                    layout = find_runtime()
                    verify_files(layout.root)
                    runtime = layout.root
                except RuntimeError:
                    # Also reuse the original author's sibling installation when available.
                    sibling = ROOT.parent / 'ComfyUI-DLSS5-Enhancer' / 'runtime'
                    try:
                        verify_files(sibling)
                        runtime = sibling
                    except RuntimeError:
                        pass
            ffmpeg_dir = resolve_ffmpeg_directory(runtime) if runtime is not None else None
            if runtime is None or ffmpeg_dir is None:
                cache = ROOT / '.cache' / 'dlss5'
                cache.mkdir(parents=True, exist_ok=True)
                archive = args.archive
                if archive is None:
                    archive = cache / 'DLSS.5.Visual.Enhancer.v3.0.zip'
                    if not archive.is_file() or sha256(archive, cancel_check) != RELEASE_SHA256:
                        download_archive(RELEASE_URL, archive, cancel_check=cancel_check,
                            progress_callback=progress_callback, prefix=args.download_prefix or '',
                            proxy=args.http_proxy, official_only=args.official_only)
                    else:
                        print('[复用] 已校验的本地下载缓存。', flush=True)
                with tempfile.TemporaryDirectory(prefix='.stage-', dir=DATA) as stage:
                    progress(80, '校验并解压兼容运行时')
                    extract_verified(archive, Path(stage), cancel_check=cancel_check)
                    install_staged(stage, DATA, ('runtime', 'ffmpeg') if runtime is None else ('ffmpeg',))
                if runtime is None:
                    runtime = DATA / 'runtime'
                ffmpeg_dir = DATA / 'ffmpeg'
            verify_files(runtime)
            ensure_supported(RuntimeLayout(runtime))
            # Verify before replacing the saved selection, so failed custom runtimes don't win.
            proof = {'verified': False, 'reason': '按参数跳过自检，尚未验证原生渲染。'}
            if not args.skip_self_test:
                print('[自检] 验证 D3D12、协议v4和真实 DLSS 神经渲染，请等待。', flush=True)
                progress(90, '验证真实DLSS神经渲染')
                proof = smoke_test(runtime, cancel_check=cancel_check)
            write_config(runtime, ffmpeg_dir)
            result = inspect_environment()
            result['native_execution_verified'] = proof.get('verified', False)
            result['neural_rendering'] = proof
            result['release_archive_sha256'] = RELEASE_SHA256 if runtime == DATA / 'runtime' else None
            (DATA / 'setup-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print('[完成] ' + ('原生神经渲染自检通过。' if proof.get('verified') else '依赖和文件就绪，原生渲染尚未验证。'), flush=True)
            progress(100, '环境已就绪')
            print('环境已就绪，继续当前增强任务。' if cancel_check else '重启 ComfyUI，搜索“LL DLSS5”。', flush=True)
        return 0
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print('[安装未完成] ' + str(exc), file=sys.stderr, flush=True)
        print('可使用 --archive 离线ZIP，或 --runtime-dir 已有运行时。详情见 docs/DLSS5.md。', file=sys.stderr)
        return 1
