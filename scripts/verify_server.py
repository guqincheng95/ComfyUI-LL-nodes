"""Exercise a running ComfyUI server and record actual output PNG dimensions.

Standard library only. This opt-in development tool is not imported by the node.
Saves 11 small test images in the server output directory (no model required).
"""
import argparse
import copy
import json
from pathlib import Path
import struct
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request(base, path, payload=None, binary=False):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read()
    except HTTPError as error:
        raise RuntimeError(f'HTTP {error.code}: {error.read().decode(errors="replace")}') from error
    return raw if binary else json.loads(raw)


def run(base, output, timeout):
    output.mkdir(parents=True, exist_ok=True)
    report = {'server': base, 'status': 'running', 'cases': []}
    try:
        info = request(base, '/object_info/ResolutionPreset')
        (output / 'object_info.json').write_text(json.dumps(info, indent=2))
        node = info.get('ResolutionPreset', {})
        if node.get('output') != ['INT', 'INT']:
            raise RuntimeError('ResolutionPreset not registered with two INT outputs')
        report['registered'] = True
        stats = request(base, '/system_stats')
        (output / 'system_stats.json').write_text(json.dumps(stats, indent=2))
        template = json.loads((Path(__file__).resolve().parents[1] / 'examples/minimal_api.json').read_text())
        cases = [
            ('Z-Image', '9:16', 'Quality', 'Portrait', (864, 1536)),
            ('Z-Image', '16:9', 'Quality', 'Landscape', (1536, 864)),
            ('Z-Image', '3:4', 'Max', 'Portrait', (1536, 2048)),
            ('Z-Image', '4:3', 'Fast', 'Landscape', (1024, 768)),
            ('Custom', '9:16', 'Quality', 'Portrait', (1376, 768)),
            ('Z-Image', '1:1', 'Fast', 'Auto', (1024, 1024)),
            ('SCAIL-2 / WAN', '9:16', 'Fast', 'Auto', (576, 1024)),
            ('FLUX', '16:9', 'Fast', 'Auto', (1024, 576)),
            ('Z-Image', '9:16', 'Quality', 'Landscape', (1536, 864)),
            ('Custom', '1:1', 'Fast', 'Landscape', (1377, 769)),
            ('Z-Image', '2:3', 'Quality', 'Auto', (1024, 1536)),
        ]
        for index, (family, ratio, tier, orientation, expected) in enumerate(cases, 1):
            prompt = copy.deepcopy(template)
            prompt['1']['inputs'].update(model_family=family, ratio=ratio, quality_tier=tier, orientation=orientation)
            if family == 'Custom':
                prompt['1']['inputs'].update(custom_width=expected[0], custom_height=expected[1])
            prompt['3']['inputs']['filename_prefix'] = f'ResolutionPreset_acceptance/case_{index:02}'
            queued = request(base, '/prompt', {'prompt': prompt})
            if queued.get('node_errors'):
                raise RuntimeError(str(queued['node_errors']))
            prompt_id = queued['prompt_id']
            deadline = time.monotonic() + timeout
            while True:
                history = request(base, '/history/' + prompt_id).get(prompt_id)
                if history:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(f'case {index}: prompt {prompt_id} not complete after {timeout}s')
                time.sleep(0.5)
            (output / f'history_{index:02}.json').write_text(json.dumps(history, indent=2))
            if history.get('status', {}).get('status_str') == 'error':
                raise RuntimeError(f'Execution error: {history.get("status")}')
            images = history.get('outputs', {}).get('3', {}).get('images', [])
            if not images:
                raise RuntimeError(f'case {index}: SaveImage returned no image')
            item = images[0]
            png = request(base, '/view?' + urlencode({k: item[k] for k in ('filename', 'subfolder', 'type')}), binary=True)
            if png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR':
                raise RuntimeError('Expected PNG output')
            actual = struct.unpack('>II', png[16:24])
            if actual != expected:
                raise AssertionError(f'case {index}: {actual} != {expected}')
            (output / f'case_{index:02}.png').write_bytes(png)
            report['cases'].append({'case':index,'family':family,'ratio':ratio,'tier':tier,'orientation':orientation,'expected':expected,'actual':actual,'status':'passed'})
            print(f'PASS {index}: {family} {ratio} {tier} {orientation} -> {actual}', flush=True)
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:6006')
    parser.add_argument('--output', type=Path, default=Path('acceptance-output'))
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    run(args.url.rstrip('/'), args.output, args.timeout)
