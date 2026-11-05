import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portrait_test_pkg', ROOT / '__init__.py')
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from portrait_test_pkg.modules.photo.processing import adjust_image, luminance, srgb_to_linear
from portrait_test_pkg.modules.photo.portrait_match import _semantic_masks
from portrait_test_pkg.modules.subject import parsing

torch.set_num_threads(2)


class PortraitMatchTests(unittest.TestCase):
    def setUp(self):
        self.node = pkg.NODE_CLASS_MAPPINGS['LLPortraitColorAlign']()
        self.ref = torch.empty((1, 72, 56, 3))
        self.ref[:] = torch.tensor([.65, .65, .65])
        self.face = torch.zeros(self.ref.shape[1:3])
        self.body = torch.zeros_like(self.face)
        self.face[9:26, 18:38] = 1
        self.body[40:68, 5:13] = 1
        self.ref[:, self.face.bool()] = torch.tensor([.73, .55, .49])
        self.ref[:, self.body.bool()] = torch.tensor([.66, .52, .42])
        self.ref[:, 32:69, 16:41] = torch.tensor([.14, .21, .31])
        self.image = adjust_image(self.ref, temperature=18, tint=12)
        self.image[:, self.face.bool()] = torch.tensor([.78, .45, .43])
        self.image[:, self.body.bool()] = torch.tensor([.63, .53, .44])
        self.masks = dict(face_mask=self.face, body_mask=self.body,
                          reference_face_mask=self.face, reference_body_mask=self.body)

    def test_white_balance_estimates_manual_values(self):
        out, report = self.node.apply(self.image, self.ref, skin_source='white_balance_only', white_balance_strength=1)
        frame = json.loads(report)['frames'][0]
        self.assertAlmostEqual(frame['white_balance']['temperature'], -18., places=2)
        self.assertAlmostEqual(frame['white_balance']['tint'], -12., places=2)
        torch.testing.assert_close(out[:, :7], self.ref[:, :7], atol=.004, rtol=0)
        self.assertIn('跳过', frame['face']['status'])

    def test_face_body_are_independent_and_preserve_skin_shading(self):
        wb, _ = self.node.apply(self.image, self.ref, **self.masks, face_strength=0, body_strength=0)
        out, report = self.node.apply(self.image, self.ref, **self.masks, face_strength=1, body_strength=1)
        report = json.loads(report)['frames'][0]
        self.assertNotEqual(report['face']['tint'], report['body']['tint'])
        for mask in (self.face, self.body):
            region = mask.bool()
            linear = lambda a: srgb_to_linear(a[:, region])
            normalized = lambda a: linear(a) / luminance(linear(a))
            self.assertLess((normalized(out) - normalized(self.ref)).abs().mean(),
                            (normalized(wb) - normalized(self.ref)).abs().mean() * .40)
            torch.testing.assert_close(luminance(linear(out)), luminance(linear(wb)), atol=1e-6, rtol=0)
        non_skin = ~(self.face.bool() | self.body.bool())
        torch.testing.assert_close(out[:, non_skin], wb[:, non_skin], atol=0, rtol=0)

    def test_covered_body_skips_even_when_reference_body_is_visible(self):
        masks = dict(self.masks, body_mask=torch.zeros_like(self.body))
        out, report = self.node.apply(self.image, self.ref, **masks)
        frame = json.loads(report)['frames'][0]
        self.assertEqual(frame['body']['samples'][0], 0)
        self.assertIn('跳过', frame['body']['status'])
        self.assertEqual(frame['face']['status'], '已估算')
        base, _ = self.node.apply(self.image, self.ref, **masks, body_strength=0)
        torch.testing.assert_close(out, base, atol=0, rtol=0)

    def test_local_exposure_is_optional_and_bounded(self):
        without, _ = self.node.apply(self.image, self.ref, **self.masks, face_strength=1)
        with_ev, report = self.node.apply(self.image, self.ref, **self.masks, face_strength=1, skin_luminance=1)
        ev = json.loads(report)['frames'][0]['face']['exposure']
        self.assertGreater(ev, .05)
        self.assertLessEqual(ev, .35)
        region = self.face.bool()
        before = luminance(srgb_to_linear(without[:, region]))
        after = luminance(srgb_to_linear(with_ev[:, region]))
        torch.testing.assert_close(after, before * 2 ** ev, atol=2e-4, rtol=0)
        torch.testing.assert_close(with_ev[:, :5], without[:, :5], atol=0, rtol=0)

    def test_manual_values_run_last_and_report_is_unchanged(self):
        base, report = self.node.apply(self.image, self.ref, **self.masks)
        out, report2 = self.node.apply(self.image, self.ref, **self.masks, exposure=.1, temperature=-3)
        torch.testing.assert_close(out, adjust_image(base, exposure=.1, temperature=-3))
        self.assertEqual(report, report2)

    def test_batch_broadcast_alpha_and_wrong_mask_size(self):
        alpha = torch.ones_like(self.image[..., :1])
        alpha[:, :6] = 0
        rgba = torch.cat((self.image, alpha), dim=-1).repeat(2, 1, 1, 1)
        out, report = self.node.apply(rgba, self.ref, **self.masks)
        self.assertEqual(len(json.loads(report)['frames']), 2)
        torch.testing.assert_close(out[0], out[1])
        torch.testing.assert_close(out[..., 3:], rgba[..., 3:], atol=0, rtol=0)
        torch.testing.assert_close(out[:, :6], rgba[:, :6], atol=0, rtol=0)
        with self.assertRaisesRegex(ValueError, '尺寸一致'):
            self.node.apply(rgba, self.ref, face_mask=torch.ones(4, 4))

    def test_semantic_candidate_guard_rejects_dark_covered_limbs(self):
        rgb = torch.empty((20, 28, 3))
        rgb[:, :10] = torch.tensor([.75, .54, .46])
        rgb[:, 10:19] = torch.tensor([.15, .16, .18])
        rgb[:, 19:] = torch.tensor([.68, .49, .43])
        p = np.zeros((18, *rgb.shape[:2]), dtype=np.float32)
        p[11, :, :10] = 1
        p[14, :, 10:] = 1
        with patch.object(parsing, 'probabilities', return_value=p):
            face, body = _semantic_masks(rgb, object())
        self.assertTrue((face[:, :10] == 1).all())
        self.assertFalse(body[:, :19].any())
        self.assertTrue((body[:, 19:] == 1).all())

    def test_atr_mode_uses_provided_masks_without_loading_model(self):
        with patch.object(parsing, 'load_parser', side_effect=AssertionError('should not load')):
            out, _ = self.node.apply(self.image, self.ref, skin_source='atr_onnx', **self.masks)
        explicit, _ = self.node.apply(self.image, self.ref, **self.masks)
        torch.testing.assert_close(out, explicit, atol=0, rtol=0)
