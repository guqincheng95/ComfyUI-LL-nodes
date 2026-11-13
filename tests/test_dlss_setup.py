"""Offline setup/rollback/security checks; no GPU or binary downloads."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from modules.dlss import runtime_setup as setup


class SetupTests(unittest.TestCase):
    def make_archive(self, root, extra=None, missing=None):
        archive = root / 'release.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for name in setup.REQUIRED:
                if name != missing:
                    z.writestr('app/bin/runtime/' + name, b'MZfixture')
            z.writestr('app/bin/ffmpeg/bin/ffmpeg.exe', b'MZffmpeg')
            z.writestr('app/bin/ffmpeg/bin/ffprobe.exe', b'MZffprobe')
            if extra:
                z.writestr(extra, b'bad')
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_compatible_tag_and_hash_are_pinned(self):
        self.assertIn('/download/v3.0/', setup.RELEASE_URL)
        self.assertEqual(setup.RELEASE_SHA256, '6f0590d81677484f4ecdfaa5c44fc2a0e1a3835d33eefc59d656e6c3bcf35f6a')

    def test_bad_hash_does_not_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, _ = self.make_archive(root)
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                setup.extract_verified(archive, root / 'stage')
            self.assertFalse((root / 'stage').exists())

    def test_verified_bundle_installs_both_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = self.make_archive(root)
            setup.extract_verified(archive, root / 'stage', digest)
            setup.install_staged(root / 'stage', root / 'data')
            setup.verify_files(root / 'data/runtime')
            self.assertTrue((root / 'data/ffmpeg/ffprobe.exe').is_file())

    def test_missing_required_member_does_not_partly_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = self.make_archive(root, missing='nvngx.dll')
            with self.assertRaisesRegex(RuntimeError, 'nvngx.dll'):
                setup.extract_verified(archive, root / 'stage', digest)
            self.assertFalse((root / 'stage').exists())

    def test_traversal_and_windows_drive_rejected(self):
        for name in ['app/bin/runtime/../../escape.exe', 'app/bin/runtime/C:/escape.exe', '/bin/runtime/escape.exe']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive, digest = self.make_archive(root, extra=name)
                with self.assertRaises(ValueError):
                    setup.extract_verified(archive, root / 'stage', digest)
                self.assertFalse((root / 'stage').exists())

    def test_failed_directory_swap_restores_old_runtime_and_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage, data = root / 'stage', root / 'data'
            for folder in [stage / 'runtime', data / 'runtime', data / 'ffmpeg']:
                folder.mkdir(parents=True)
                (folder / 'keep.txt').write_text(str(folder))
            old_runtime = (data / 'runtime/keep.txt').read_text()
            old_ffmpeg = (data / 'ffmpeg/keep.txt').read_text()
            # No staged ffmpeg: failure occurs after the runtime was swapped.
            with self.assertRaises(OSError):
                setup.install_staged(stage, data)
            self.assertEqual((data / 'runtime/keep.txt').read_text(), old_runtime)
            self.assertEqual((data / 'ffmpeg/keep.txt').read_text(), old_ffmpeg)

    def test_ffmpeg_only_repair_preserves_existing_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = self.make_archive(root)
            setup.extract_verified(archive, root / 'stage', digest)
            runtime = root / 'data/runtime'; runtime.mkdir(parents=True)
            (runtime / 'custom.dll').write_bytes(b'MZexisting')
            setup.install_staged(root / 'stage', root / 'data', ('ffmpeg',))
            self.assertEqual((runtime / 'custom.dll').read_bytes(), b'MZexisting')
            self.assertFalse((runtime / 'nvngx.dll').exists())
            self.assertTrue((root / 'data/ffmpeg/ffmpeg.exe').exists())

    def test_setup_lock_rejects_concurrent_install_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            with setup.setup_lock(tmp):
                with self.assertRaises(RuntimeError):
                    with setup.setup_lock(tmp):
                        pass
            self.assertFalse((Path(tmp) / '.setup.lock').exists())

    def test_existing_dependencies_not_reinstalled(self):
        with patch.object(setup, '_import_ok', return_value={'ready': True}), patch.object(setup.subprocess, 'run') as run:
            setup.install_dependencies()
        run.assert_not_called()

    def test_missing_torch_never_installs_or_changes_cuda(self):
        with patch.object(setup, '_import_ok', return_value={'ready': False}), patch.object(setup.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Torch'):
                setup.install_dependencies()
        run.assert_not_called()

    def test_check_mode_does_not_write_download_or_install(self):
        with patch.object(setup, 'inspect_environment', return_value={'ready': False}), \
             patch.object(setup, 'download_archive') as download, patch.object(setup, 'install_dependencies') as deps, \
             patch.object(setup, 'setup_lock') as lock, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(setup.main(['--check']), 2)
        download.assert_not_called(); deps.assert_not_called(); lock.assert_not_called()

    def test_unsupported_hardware_stops_before_install(self):
        with patch.object(setup, 'inspect_environment', return_value={'hardware_ready': False}), \
             patch.object(setup, 'install_dependencies') as deps, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(setup.main([]), 2)
        deps.assert_not_called()

    def test_download_hash_failure_removes_partial_archive(self):
        class Response(io.BytesIO):
            headers = {'Content-Length': '3'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup.urllib.request, 'urlopen', return_value=Response(b'bad')):
            path = Path(tmp) / 'release.zip'
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                setup.download_archive('https://example.invalid/release.zip', path)
            self.assertFalse(path.exists() or path.with_suffix('.part').exists())

    def test_gpu_detection_skips_unsupported_card_and_accepts_professional_ada(self):
        from modules.dlss.native.diagnostics import detect_gpu
        detect_gpu.cache_clear()
        output = 'NVIDIA GeForce RTX 2080, 600.0, 8192, 7.5\nNVIDIA RTX 6000 Ada Generation, 600.0, 49152, 8.9\n'
        with patch('modules.dlss.native.diagnostics.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output)):
            report = detect_gpu()
            self.assertEqual(report['generation'], 40)
        detect_gpu.cache_clear()

    def test_launcher_supports_aki_portable_and_override(self):
        launcher = (setup.ROOT / 'setup_dlss5.bat').read_text()
        self.assertIn('LL_COMFY_PYTHON', launcher)
        self.assertIn('python_embeded', launcher)
        self.assertIn('\\python\\python.exe', launcher)
        self.assertNotIn('pip install torch', launcher)

    def test_skip_smoke_is_explicitly_recorded_as_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runtime = root / 'existing'; runtime.mkdir()
            for name in setup.REQUIRED:
                (runtime / name).write_bytes(b'MZfixture')
            with patch.object(setup, 'DATA', root / 'data'), \
                 patch.object(setup, 'inspect_environment', return_value={'hardware_ready': True, 'ready': True}), \
                 patch.object(setup, 'install_dependencies'), \
                 patch.object(setup, 'resolve_ffmpeg_directory', return_value=root / 'ffmpeg'), \
                 patch('modules.dlss.native.diagnostics.ensure_supported'), \
                 patch('modules.dlss.native.paths.write_config'), patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(setup.main(['--runtime-dir', str(runtime), '--skip-self-test']), 0)
            report = json.loads((root / 'data/setup-report.json').read_text())
            self.assertFalse(report['native_execution_verified'])

    def test_failed_smoke_does_not_replace_saved_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runtime = root / 'existing'; runtime.mkdir()
            for name in setup.REQUIRED:
                (runtime / name).write_bytes(b'MZfixture')
            with patch.object(setup, 'DATA', root / 'data'), \
                 patch.object(setup, 'inspect_environment', return_value={'hardware_ready': True}), \
                 patch.object(setup, 'install_dependencies'), \
                 patch.object(setup, 'resolve_ffmpeg_directory', return_value=root / 'ffmpeg'), \
                 patch('modules.dlss.native.diagnostics.ensure_supported'), \
                 patch('modules.dlss.native.paths.write_config') as write, \
                 patch.object(setup, 'smoke_test', side_effect=RuntimeError('bad NGX')), \
                 patch('sys.stdout', new_callable=io.StringIO), patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(setup.main(['--runtime-dir', str(runtime)]), 1)
                write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
