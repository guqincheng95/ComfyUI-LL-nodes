import hashlib
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from modules.dlss import download as dl


class Cancelled(Exception): pass


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None, fail_after=None, tick=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {'Content-Length': str(len(data))}
        self.fail_after, self.tick = fail_after, tick
    def read1(self, size):
        if self.tick: self.tick()
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise OSError('connection lost')
        limit = size if self.fail_after is None else min(size, self.fail_after - self.tell())
        return super().read(limit)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.data = b'PK\x03\x04' + bytes(range(256)) * 1024
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'release.zip'
        self.sources = [dl.Source('fast', 'https://fast.invalid/file'), dl.Source('fallback', 'https://fallback.invalid/file')]
        self.calls = []

    def ranked(self, sources, size, opener, cancel):
        return [{'source': s, 'speed': 1024 * 1024} for s in self.sources]

    def open(self, source, headers, timeout):
        self.calls.append((source.label, dict(headers)))
        if 'Range' in headers:
            start = int(re.search(r'bytes=(\d+)-', headers['Range']).group(1))
            return Response(self.data[start:], 206, {'Content-Range': f'bytes {start}-{len(self.data)-1}/{len(self.data)}'})
        return Response(self.data)

    def run_download(self, opener=None, cancel=None):
        return dl.download('https://example.invalid/file', self.target, self.digest, len(self.data),
                           _open=opener or self.open, _rank=self.ranked, cancel_check=cancel)

    def test_existing_verified_archive_skips_all_network(self):
        self.target.write_bytes(self.data)
        self.run_download()
        self.assertEqual(self.calls, [])

    def test_complete_partial_is_verified_and_promoted(self):
        self.target.with_suffix('.part').write_bytes(self.data)
        self.run_download()
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(self.calls, [])

    def test_resume_checks_overlap_and_never_duplicates_data(self):
        self.target.with_suffix('.part').write_bytes(self.data[:100_000])
        self.run_download()
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(self.calls[0][1]['Range'], f'bytes={100_000-32*1024}-')

    def test_network_failure_keeps_partial_then_next_source_resumes(self):
        def opener(source, headers, timeout):
            if source.label == 'fast': return Response(self.data, fail_after=65536)
            return self.open(source, headers, timeout)
        self.run_download(opener)
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertIn('Range', self.calls[0][1])

    def test_all_network_failures_keep_data_for_next_run(self):
        self.sources = self.sources[:1]
        with self.assertRaisesRegex(RuntimeError, '保留分片'):
            self.run_download(lambda *args: Response(self.data, fail_after=65536))
        self.assertEqual(self.target.with_suffix('.part').stat().st_size, 65536)
        self.run_download()
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_wrong_content_range_does_not_append(self):
        self.sources = self.sources[:1]
        part = self.target.with_suffix('.part'); part.write_bytes(self.data[:100_000])
        def opener(*args): return Response(self.data, 206, {'Content-Range': f'bytes 17-{len(self.data)-1}/{len(self.data)}'})
        with self.assertRaisesRegex(RuntimeError, '范围'):
            self.run_download(opener)
        self.assertEqual(part.read_bytes(), self.data[:100_000])

    def test_html_response_is_rejected_before_writing(self):
        with self.assertRaisesRegex(RuntimeError, 'HTML'):
            self.run_download(lambda *args: Response(b'<html>blocked</html>', headers={'Content-Type': 'text/html'}))
        self.assertFalse(self.target.exists() or self.target.with_suffix('.part').exists())

    def test_server_ignoring_range_gets_verified_full_fallback(self):
        self.sources = self.sources[:1]
        self.target.with_suffix('.part').write_bytes(self.data[:100_000])
        self.run_download(lambda *args: Response(self.data))
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertFalse(self.target.with_suffix('.part').exists())

    def test_hash_mismatch_never_creates_final_archive(self):
        corrupted = b'X' + self.data[1:]
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            self.run_download(lambda *args: Response(corrupted))
        self.assertFalse(self.target.exists() or self.target.with_suffix('.part').exists())

    def test_corrupt_old_prefix_is_replaced_after_full_hash_failure(self):
        self.sources = self.sources[:1]
        self.target.with_suffix('.part').write_bytes(b'bad!' + self.data[4:100_000])
        self.run_download()
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn('Range', self.calls[1][1])

    def test_slow_source_switches_with_resume(self):
        clock = [0.]
        def tick(): clock[0] += 4.5
        def opener(source, headers, timeout):
            if source.label == 'fast': return Response(self.data, tick=tick)
            return self.open(source, headers, timeout)
        with patch.object(dl.time, 'monotonic', side_effect=lambda: clock[0]):
            self.run_download(opener)
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(self.calls[0][0], 'fallback')
        self.assertIn('Range', self.calls[0][1])

    def test_cancellation_preserves_exception_and_partial(self):
        def cancel():
            part = self.target.with_suffix('.part')
            if part.exists() and part.stat().st_size:
                raise Cancelled()
        with self.assertRaises(Cancelled): self.run_download(cancel=cancel)
        self.assertTrue(self.target.with_suffix('.part').exists())

    def test_candidates_include_public_accelerators_and_do_not_leak_private_urls(self):
        result = dl.candidates('https://github.com/owner/repo/releases/download/v1/file.zip', has_proxy=True)
        self.assertTrue(any('ghfast.top' in s.url for s in result))
        self.assertTrue(any(s.direct for s in result))
        self.assertEqual(len(dl.candidates('https://private.invalid/file', has_proxy=True)), 1)

    def test_fastest_measured_source_wins(self):
        def probe(source, size, opener, stopped):
            return {'source': source, 'speed': 100 if source.label == 'fast' else 400}
        with patch.object(dl, '_probe', side_effect=probe):
            ranked = dl.rank_sources(self.sources, len(self.data), self.open)
        self.assertEqual(ranked[0]['source'].label, 'fallback')

    def test_failed_probe_does_not_prevent_trying_actual_download(self):
        with patch.object(dl, '_probe', side_effect=OSError('range probe failed')):
            ranked = dl.rank_sources(self.sources, len(self.data), self.open)
        self.assertEqual({r['source'] for r in ranked}, set(self.sources))


if __name__ == '__main__': unittest.main()
