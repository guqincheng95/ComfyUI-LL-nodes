"""Pinned-release transport: bounded probes, source fallback and verified resume.

No authentication headers, global proxy changes, TLS bypass, or remote scripts.
Every successful download must match the caller's trusted SHA256.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import threading
import time
import urllib.request
from urllib.parse import urlsplit

MIRROR_PREFIXES = ('https://ghfast.top/', 'https://gh-proxy.org/')
PROBE_BYTES = 256 * 1024
_NETWORK_ERRORS = (OSError, HTTPException, ValueError)


@dataclass(frozen=True)
class Source:
    label: str
    url: str
    direct: bool = False


class SlowSource(OSError):
    pass


class ResumeMismatch(OSError):
    pass


def candidates(url, prefix='', mirrors=True, has_proxy=None):
    if not url.startswith('https://'):
        raise ValueError('下载地址必须使用HTTPS。')
    public = urlsplit(url).hostname == 'github.com' and not urlsplit(url).username
    proxies = urllib.request.getproxies()
    has_proxy = bool(proxies.get('https') or proxies.get('http')) if has_proxy is None else has_proxy
    result = []
    prefixes = ([prefix] if prefix else []) + (list(MIRROR_PREFIXES) if mirrors and public else [])
    for item in dict.fromkeys(prefixes):
        if not item.startswith('https://') or urlsplit(item).username:
            raise ValueError('下载加速前缀必须为不含凭据的HTTPS地址。')
        mirror = item.rstrip('/') + '/' + url
        name = urlsplit(item).hostname
        # Test direct transport only for public acceleration services, never
        # alter the process environment or bypass a GitHub authentication route.
        if has_proxy:
            result.append(Source(f'{name}（不经HTTP代理）', mirror, True))
        result.append(Source(f'{name}（系统路由）', mirror))
    result.append(Source('GitHub原始源（系统路由）', url))
    return result


def http_open(source, headers, timeout, proxy=''):
    request = urllib.request.Request(source.url, headers={
        'User-Agent': 'LL-nodes-DLSS5/0.12.1', 'Accept-Encoding': 'identity', **headers})
    if source.direct:
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout)
    if proxy:
        if urlsplit(proxy).scheme not in ('http', 'https'):
            raise ValueError('显式代理需为HTTP/HTTPS代理地址；SOCKS端口不能直接用于urllib。')
        return urllib.request.build_opener(urllib.request.ProxyHandler({'http': proxy, 'https': proxy})).open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _range(value):
    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', (value or '').strip())
    if not match:
        return None
    start, end, total = map(int, match.groups())
    return (start, end, total) if 0 <= start <= end < total else None


def _read(response, size):
    # read1 returns available bytes rather than hiding a slow trickle inside a
    # large blocking read, so the throughput window can trigger source switching.
    return getattr(response, 'read1', response.read)(size)


def _reject_html(response, data):
    content_type = response.headers.get('Content-Type', '').lower()
    if 'text/html' in content_type or data.lstrip().lower().startswith((b'<!doctype', b'<html')):
        raise ValueError('来源返回了HTML／验证页面，不是发布文件。')


def _probe(source, expected_size, opener, stopped):
    started = time.monotonic()
    data = bytearray()
    with opener(source, {'Range': f'bytes=0-{PROBE_BYTES-1}'}, 8) as response:
        status = getattr(response, 'status', 200)
        span = _range(response.headers.get('Content-Range'))
        if status not in (200, 206) or (status == 206 and (span is None or span[0] != 0)):
            raise ValueError('测速响应的状态或Content-Range不正确。')
        total = span[2] if span else int(response.headers.get('Content-Length') or 0)
        if expected_size and total and total != expected_size:
            raise ValueError('来源文件大小与固定发布资产不符。')
        while len(data) < PROBE_BYTES and time.monotonic() - started < 8:
            if stopped.is_set():
                raise OSError('测速已停止。')
            chunk = _read(response, min(64 * 1024, PROBE_BYTES - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        _reject_html(response, bytes(data))
    if not data:
        raise OSError('来源没有返回测试数据。')
    return {'source': source, 'speed': len(data) / max(.001, time.monotonic() - started),
            'range': span is not None, 'size': total, 'prefix': bytes(data)}


def rank_sources(sources, expected_size, opener, cancel_check=None):
    pool = ThreadPoolExecutor(max_workers=min(6, len(sources)), thread_name_prefix='ll-dlss-source')
    stopped = threading.Event()
    pending = {pool.submit(_probe, source, expected_size, opener, stopped): source for source in sources}
    results, failures = [], []
    try:
        while pending:
            if cancel_check:
                cancel_check()
            done, _ = wait(pending, timeout=.15, return_when=FIRST_COMPLETED)
            for future in done:
                source = pending.pop(future)
                try:
                    result = future.result()
                    results.append(result)
                    print(f'[测速] {source.label}: {result["speed"] / 1024:.0f} KB/s', flush=True)
                except _NETWORK_ERRORS as exc:
                    failures.append(source)
                    print(f'[测速不可用] {source.label}: {type(exc).__name__}', flush=True)
    finally:
        stopped.set()
        pool.shutdown(wait=False, cancel_futures=True)
    if not results:
        print('[测速] 未取得有效测速结果，仍将依次尝试候选下载来源。', flush=True)
    return sorted(results, key=lambda item: item['speed'], reverse=True) + [
        {'source': source, 'speed': 0., 'range': False, 'size': expected_size, 'prefix': b''}
        for source in failures]


def file_hash(path, cancel_check=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if cancel_check:
                cancel_check()
            digest.update(chunk)
    return digest.hexdigest()


def _transfer(source, part, expected_size, opener, cancel_check, progress_callback, allow_switch, reference_speed):
    offset = part.stat().st_size if part.exists() else 0
    overlap = min(offset, 32 * 1024)
    start = offset - overlap
    headers = {'Range': f'bytes={start}-'} if offset else {}
    with opener(source, headers, 12) as response:
        status = getattr(response, 'status', 200)
        span = _range(response.headers.get('Content-Range'))
        if status not in (200, 206):
            raise OSError(f'HTTP {status}')
        if offset and (status != 206 or span is None or span[0] != start):
            raise ResumeMismatch('此来源未正确支持断点范围，保留已有下载并尝试其它来源。')
        if status == 206 and (span is None or span[0] != start):
            raise ResumeMismatch('来源返回的Content-Range起点错误。')
        total = span[2] if span else int(response.headers.get('Content-Length') or 0)
        if expected_size and total and total != expected_size:
            raise ValueError('来源文件大小与固定发布包不符。')
        total = expected_size or total
        if 'text/html' in response.headers.get('Content-Type', '').lower():
            raise ValueError('来源返回HTML页面。')
        if overlap:
            previous = bytearray()
            while len(previous) < overlap:
                if cancel_check:
                    cancel_check()
                block = _read(response, overlap - len(previous))
                if not block:
                    raise ResumeMismatch('续传重叠段不完整。')
                previous.extend(block)
            with part.open('rb') as existing:
                existing.seek(start)
                if existing.read(overlap) != previous:
                    raise ResumeMismatch('续传重叠段与本地文件不同，拒绝拼接。')
        received = offset
        started = window_started = shown = time.monotonic()
        window_bytes = 0
        with part.open('ab' if offset else 'wb') as sink:
            while True:
                if cancel_check:
                    cancel_check()
                block = _read(response, 64 * 1024)
                if not block:
                    break
                if received == 0:
                    _reject_html(response, block)
                if received + len(block) > (total or 1024 ** 3):
                    raise ValueError('来源传输超过预期文件大小。')
                sink.write(block)
                received += len(block)
                window_bytes += len(block)
                now = time.monotonic()
                rate = (received - offset) / max(.001, now - started)
                if now - shown >= .5 or (total and received == total):
                    percent = received * 100 / total if total else 0
                    eta = (total - received) / max(1., rate) if total else 0
                    print(f'[下载] {source.label} | {received/1e6:.1f}/{total/1e6:.1f} MB '
                          f'({percent:.1f}%) | {rate/1e6:.2f} MB/s | 剩余约{eta:.0f}秒', flush=True)
                    if progress_callback:
                        progress_callback(20 + min(55, int(percent * .55)), source.label)
                    shown = now
                if now - window_started >= 8:
                    recent_speed = window_bytes / (now - window_started)
                    if allow_switch and recent_speed < max(64 * 1024, reference_speed * .2):
                        raise SlowSource('持续低速，保留已下载部分并切换来源。')
                    window_started, window_bytes = now, 0
        if total and received != total:
            raise OSError(f'传输中断：已有{received}字节，预期{total}字节。')


def download(url, target, expected_sha256, expected_size=None, *, prefix='', mirrors=True, proxy='',
             cancel_check=None, progress_callback=None, _open=None, _rank=None):
    target = Path(target)
    part = target.with_suffix('.part')
    metadata = target.with_suffix('.download.json')
    if target.is_file() and file_hash(target, cancel_check) == expected_sha256:
        return target
    if part.is_file() and file_hash(part, cancel_check) == expected_sha256:
        part.replace(target)
        metadata.unlink(missing_ok=True)
        return target
    if expected_size and part.is_file() and part.stat().st_size > expected_size:
        part.unlink()
    print('[网络] 系统／环境HTTP代理' if proxy or any(urllib.request.getproxies().get(k) for k in ('https', 'http'))
          else '[网络] 未发现HTTP代理；TUN由系统路由处理，PAC不等于Python代理。', flush=True)
    opener = _open or (lambda source, headers, timeout: http_open(source, headers, timeout, proxy))
    sources = candidates(url, prefix, mirrors, has_proxy=True if proxy else None)
    if progress_callback:
        progress_callback(15, '测速并选择下载来源')
    ranked = (_rank or rank_sources)(sources, expected_size, opener, cancel_check)
    print(f'[优选] {ranked[0]["source"].label}；续传{part.stat().st_size/1e6:.1f} MB' if part.exists()
          else f'[优选] {ranked[0]["source"].label}', flush=True)
    errors, non_resuming = [], []
    for index, item in enumerate(ranked):
        source = item['source']
        retry_fresh = bool(part.exists() and part.stat().st_size)
        for attempt in range(2 if retry_fresh else 1):
            if cancel_check:
                cancel_check()
            try:
                metadata.write_text(json.dumps({'sha256': expected_sha256, 'source': source.label}, ensure_ascii=False), encoding='utf-8')
                _transfer(source, part, expected_size, opener, cancel_check, progress_callback,
                          index < len(ranked) - 1, item['speed'])
                if file_hash(part, cancel_check) != expected_sha256:
                    part.unlink(missing_ok=True)
                    if retry_fresh and attempt == 0:
                        print('[校验] 旧分片SHA-256不匹配，重新完整下载。', flush=True)
                        continue
                    raise ValueError('发布包SHA-256不匹配，拒绝安装。')
                part.replace(target)
                metadata.unlink(missing_ok=True)
                return target
            except _NETWORK_ERRORS as exc:
                if isinstance(exc, ResumeMismatch):
                    non_resuming.append(item)
                errors.append(f'{source.label}: {type(exc).__name__}: {str(exc)[:240]}')
                print(f'[切换来源] {source.label}: {str(exc)}', flush=True)
                break
    # Some accelerators return HTTP200 for every Range. Preserve the old partial
    # until a full fresh transfer has passed SHA256 rather than concatenating it.
    if non_resuming and part.exists():
        fresh = target.with_suffix('.fresh.part')
        for item in non_resuming:
            source = item['source']
            if cancel_check:
                cancel_check()
            fresh.unlink(missing_ok=True)
            try:
                print(f'[完整回退] {source.label}不能安全续传，保留旧分片并尝试完整下载。', flush=True)
                _transfer(source, fresh, expected_size, opener, cancel_check, progress_callback, False, item['speed'])
                if file_hash(fresh, cancel_check) != expected_sha256:
                    fresh.unlink(missing_ok=True)
                    raise ValueError('发布包SHA-256不匹配，拒绝安装。')
                fresh.replace(target)
                part.unlink(missing_ok=True)
                metadata.unlink(missing_ok=True)
                return target
            except _NETWORK_ERRORS as exc:
                errors.append(f'{source.label}: {type(exc).__name__}: {str(exc)[:240]}')
    # Never discard a useful partial file on network failure or cancellation.
    raise RuntimeError('下载未完成，已保留分片以便下次续传。' + '; '.join(errors))
