import base64
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import zlib

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_test_pkg', ROOT / '__init__.py')
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from preview_test_pkg.modules.photo.processing import adjust_image


def decode(payload):
    return np.frombuffer(zlib.decompress(base64.b64decode(payload['pixels'])), dtype='<u2').reshape(
        payload['height'], payload['width'], 4)


class PhotoPreviewTests(unittest.TestCase):
    def test_legacy_preview_is_auto_base_and_output_is_unchanged(self):
        node = pkg.NODE_CLASS_MAPPINGS['AIVisualPhotoFinish']()
        source = torch.rand((1, 18, 24, 3), generator=torch.Generator().manual_seed(14)) * .7 + .1
        reference = source * torch.tensor([.8, 1., .95])
        opts = dict(auto_mode='original', reference_image=reference)
        (base,) = node.apply(source, **opts)
        (normal,) = node.apply(source, exposure=.8, **opts)
        result = node.apply(source, exposure=.8, live_preview=True, **opts)
        payload, = result['ui']['ll_photo_preview']
        torch.testing.assert_close(result['result'][0], normal, rtol=0, atol=0)
        np.testing.assert_array_equal(decode(payload)[..., :3], (base[0].numpy() * 65535).round())
        self.assertTrue((decode(payload)[..., 3] == 65535).all())
        self.assertEqual(payload['manual']['exposure'], .8)
        self.assertEqual(payload['automatic']['auto_mode'], 'original')

    def test_portrait_preview_keeps_report_and_bounds_first_frame(self):
        node = pkg.NODE_CLASS_MAPPINGS['LLPortraitColorAlign']()
        source = torch.full((2, 800, 60, 4), .5)
        source[0, ..., 3] = .25
        source[1, ..., 3] = .75
        opts = dict(skin_source='white_balance_only', temperature=10)
        normal = node.apply(source, source[:1], **opts)
        result = node.apply(source, source[:1], live_preview=True, **opts)
        payload, = result['ui']['ll_photo_preview']
        self.assertEqual((payload['batch'], payload['width'], payload['height']), (2, 48, 640))
        self.assertTrue((decode(payload)[..., 3] == 16384).all())
        torch.testing.assert_close(normal[0], result['result'][0], rtol=0, atol=0)
        self.assertEqual(normal[1], result['result'][1])

    def test_browser_fixture_matches_python_formal_output(self):
        fixture = json.loads((ROOT / 'tests' / 'photo_preview_fixture.json').read_text())
        image = torch.tensor(fixture['rgba16'], dtype=torch.float32).reshape(
            1, fixture['height'], fixture['width'], 4) / 65535
        for case in fixture['cases']:
            with self.subTest(case=case['name']):
                result = adjust_image(image, **case['params']).mul(255).round().to(torch.int).flatten()
                self.assertEqual(result.tolist(), case['rgba8'])
