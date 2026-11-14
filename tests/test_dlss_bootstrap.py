from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock

from modules.dlss import bootstrap as boot
from modules.dlss import runtime_setup as setup


class Cancelled(Exception):
    pass


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.check = Mock()
        self.progress = Mock()
        self.hooks = Mock(return_value=(self.check, self.progress))
        self.refresh = patch.object(boot, '_refresh_optional_imports')
        self.refresh.start(); self.addCleanup(self.refresh.stop)

    def run_bootstrap(self, settings=None):
        return boot.ensure_environment(settings or {}, _platform='Windows', _hooks=self.hooks)

    def test_existing_install_never_invokes_setup(self):
        with patch.object(boot, '_ready', return_value=True), patch.object(setup, 'main') as main:
            self.run_bootstrap()
        self.hooks.assert_not_called(); main.assert_not_called()

    def test_missing_environment_installs_then_continues(self):
        with patch.object(boot, '_ready', side_effect=[False, False, True]), patch.object(setup, 'main', return_value=0) as main:
            self.run_bootstrap()
        main.assert_called_once_with([], cancel_check=self.check, progress_callback=self.progress)
        self.assertFalse(boot._LOCK.locked())

    def test_offline_mirror_proxy_and_runtime_options_forwarded(self):
        config = dict(runtime_dir='D:/runtime', setup_archive='D:/release.zip', setup_wheel_dir='D:/wheels',
                      setup_index_url='https://index.invalid/simple', setup_http_proxy='http://127.0.0.1:1234',
                      setup_official_only=True, release_comfy_models=False)
        with patch.object(boot, '_ready', side_effect=[False, False, True]), patch.object(setup, 'main', return_value=0) as main:
            self.run_bootstrap(config)
        args = main.call_args.args[0]
        self.assertIn('--archive', args); self.assertIn('--official-only', args)
        self.assertIn('http://127.0.0.1:1234', args)
        self.hooks.assert_called_once_with(False)

    def test_user_can_disable_automatic_deployment(self):
        with patch.object(boot, '_ready', return_value=False), patch.object(setup, 'main') as main:
            with self.assertRaisesRegex(RuntimeError, '自动部署已关闭'):
                self.run_bootstrap({'auto_setup': False})
        main.assert_not_called()

    def test_unsupported_os_never_installs(self):
        with patch.object(setup, 'main') as main:
            with self.assertRaisesRegex(RuntimeError, 'Windows'):
                boot.ensure_environment({}, _platform='Linux')
        main.assert_not_called()

    def test_failure_does_not_report_ready_or_keep_lock(self):
        with patch.object(boot, '_ready', return_value=False), patch.object(setup, 'main', return_value=1):
            with self.assertRaisesRegex(RuntimeError, '自动部署未完成'):
                self.run_bootstrap()
        self.assertFalse(boot._LOCK.locked())

    def test_cancelled_install_preserves_exception_and_releases_lock(self):
        with patch.object(boot, '_ready', return_value=False), patch.object(setup, 'main', side_effect=Cancelled()):
            with self.assertRaises(Cancelled):
                self.run_bootstrap()
        self.assertFalse(boot._LOCK.locked())

    def test_concurrent_first_use_installs_only_once(self):
        ready = threading.Event()
        def install(*args, **kwargs):
            time.sleep(.05); ready.set(); return 0
        with patch.object(boot, '_ready', side_effect=lambda runtime: ready.is_set()), \
             patch.object(setup, 'main', side_effect=install) as main:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.run_bootstrap) for _ in range(2)]
                for future in futures:
                    future.result(timeout=3)
            self.assertEqual(main.call_count, 1)

    def test_installed_but_unavailable_in_process_requests_restart(self):
        with patch.object(boot, '_ready', return_value=False), patch.object(setup, 'main', return_value=0):
            with self.assertRaisesRegex(RuntimeError, '重启ComfyUI'):
                self.run_bootstrap()

    def test_cancelled_package_install_terminates_child(self):
        process = Mock(); process.poll.return_value = None
        def cancel(): raise Cancelled()
        with patch.object(setup.subprocess, 'Popen', return_value=process):
            with self.assertRaises(Cancelled):
                setup.run_checked(['python', '-m', 'pip'], cancel_check=cancel)
        process.terminate.assert_called_once(); process.wait.assert_called_once()

    def test_missing_dependency_uses_tuna_then_pypi_without_changing_torch(self):
        installed = {'cv2': False}
        def available(name): return {'ready': installed['cv2'] if name == 'cv2' else True}
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if len(commands) == 1: raise subprocess.CalledProcessError(1, command)
            installed['cv2'] = True
        with patch.object(setup, '_import_ok', side_effect=available), \
             patch('importlib.metadata.distributions', return_value=[]), \
             patch.object(setup, 'run_checked', side_effect=run), patch.dict('os.environ', {'PIP_INDEX_URL': ''}):
            setup.install_dependencies()
        self.assertIn('https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple', commands[0])
        self.assertIn('https://pypi.org/simple', commands[1])
        self.assertTrue(all('torch' not in command for command in commands))


if __name__ == '__main__': unittest.main()
