import importlib.util
import json
from pathlib import Path
import sys
import unittest

import torch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ll_aspect_test", ROOT / "__init__.py")
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
node = package.NODE_CLASS_MAPPINGS["LLImageAspectScale"]()


class ImageAspectScaleTests(unittest.TestCase):
    def test_size_only_portrait_with_multiple(self):
        result = node.scale(aspect_ratio="9:16", round_to_multiple=16,
                            scale_to_side="longest", scale_to_length=1280)
        self.assertEqual(result, (None, None, None, 720, 1280))
        self.assertTrue(all(type(value) is int for value in result[-2:]))

    def test_size_only_matches_connected_custom_ratio_and_rounding(self):
        options = dict(aspect_ratio="custom", proportional_width=3, proportional_height=2,
                       flip_ratio=True, scale_to_length=100, round_to_multiple=16)
        for rounding, expected in (("nearest", (64, 96)), ("down", (64, 96)), ("up", (80, 112))):
            with self.subTest(rounding=rounding):
                size_only = node.scale(rounding=rounding, **options)
                with_mask = node.scale(mask=torch.ones((4, 8)), rounding=rounding, **options)
                self.assertEqual(size_only[-2:], expected)
                self.assertEqual(size_only[-2:], with_mask[-2:])

    def test_size_only_requires_explicit_ratio_and_length_basis(self):
        with self.assertRaisesRegex(ValueError, "画面比例"):
            node.scale(aspect_ratio="original")
        with self.assertRaisesRegex(ValueError, "保留原长边"):
            node.scale(aspect_ratio="9:16", scale_to_side="none")

    def test_source_ratio_and_custom_multiple(self):
        image = torch.zeros((1, 1392, 752, 3))
        result, mask, original, w, h = node.scale(image=image, method="bilinear")
        self.assertEqual((original, w, h), ([752, 1392], 688, 1280))
        self.assertEqual(tuple(result.shape), (1, 1280, 688, 3))
        self.assertEqual(tuple(mask.shape), (1, 1280, 688))
        _, _, _, w, h = node.scale(image=image, aspect_ratio="custom",
                                    proportional_width=2, proportional_height=3,
                                    scale_to_side="width", scale_to_length=100,
                                    round_to_multiple=7, rounding="up")
        self.assertEqual((w, h), (105, 154))

    def test_ratio_flip_does_not_rotate_source(self):
        image = torch.zeros((1, 2, 4, 3))
        image[:, :1, :, 0] = 1
        out, _, _, w, h = node.scale(image=image, aspect_ratio="3:2", flip_ratio=True,
                                      scale_to_length=6, round_to_multiple=1,
                                      fit="fill", method="nearest")
        self.assertEqual((w, h), (4, 6))
        self.assertTrue(torch.all(out[:, :3, :, 0] == 1))
        self.assertTrue(torch.all(out[:, 3:, :, 0] == 0))

    def test_letterbox_soft_mask_and_color(self):
        rgb = torch.full((2, 4, 8, 3), .412345)
        mask = torch.full((1, 2, 4), .634567)
        out, matte, original, w, h = node.scale(image=rgb, mask=mask, aspect_ratio="1:1",
            fit="letterbox", scale_to_length=8, round_to_multiple=1, background_color="#ff8000")
        self.assertEqual((original, w, h), ([8, 4], 8, 8))
        torch.testing.assert_close(out[:, 2:6], rgb, rtol=0, atol=0)
        torch.testing.assert_close(matte[:, 2:6], torch.full((2, 4, 8), .634567))
        self.assertTrue(torch.all(matte[:, :2] == 0) and torch.all(matte[:, 6:] == 0))
        torch.testing.assert_close(out[1, 0, 0], torch.tensor([1., 128/255, 0.]))

    def test_crop_uses_identical_geometry_for_image_and_mask(self):
        signal = torch.arange(32, dtype=torch.float32).reshape(1, 4, 8) / 31
        rgb = signal[..., None].expand(-1, -1, -1, 3)
        for method in node.INPUT_TYPES()["required"]["method"][0]:
            with self.subTest(method=method):
                out, matte, *_ = node.scale(image=rgb, mask=signal, aspect_ratio="1:1",
                    scale_to_length=4, round_to_multiple=1, method=method)
                torch.testing.assert_close(matte, signal[:, :, 2:6], rtol=0, atol=0)
                torch.testing.assert_close(out[..., 0], matte, rtol=0, atol=0)

    def test_alpha_and_explicit_mask(self):
        rgba = torch.rand((1, 3, 5, 4), generator=torch.Generator().manual_seed(54))
        options = dict(image=rgba, scale_to_side="none", round_to_multiple=1)
        out, matte, *_ = node.scale(**options)
        torch.testing.assert_close(out, rgba[..., :3], rtol=0, atol=0)
        torch.testing.assert_close(matte, rgba[..., 3], rtol=0, atol=0)
        out, matte, *_ = node.scale(mask=torch.zeros((3, 5)), **options)
        self.assertFalse(matte.any())
        torch.testing.assert_close(out, rgba[..., :3], rtol=0, atol=0)

    def test_mask_only_nearest_and_rgb_only_coverage(self):
        m = torch.tensor([[1., 0.], [0., 1.]])
        preview, mask, *_ = node.scale(mask=m, scale_to_length=4, round_to_multiple=1, mask_method="nearest")
        self.assertEqual(mask.unique().tolist(), [0., 1.])
        self.assertEqual(mask[0, 0].tolist(), [1., 1., 0., 0.])
        torch.testing.assert_close(preview[..., 2], mask)
        _, mask, *_ = node.scale(image=torch.zeros((1, 2, 4, 3)), aspect_ratio="1:1",
                                  fit="letterbox", scale_to_length=4, round_to_multiple=1)
        self.assertEqual(mask[0, :, 0].tolist(), [0., 1., 1., 0.])

    def test_scale_bases_and_rounding(self):
        options = dict(mask=torch.ones((4, 8)), aspect_ratio="2:3", scale_to_length=96, round_to_multiple=8)
        for side, expected in (("longest", (64, 96)), ("shortest", (96, 144)),
                               ("width", (96, 144)), ("height", (64, 96))):
            self.assertEqual(node.scale(scale_to_side=side, **options)[-2:], expected)
        self.assertEqual(node.scale(mask=options["mask"], aspect_ratio="1:1", scale_to_side="total_kpixels",
                                     scale_to_length=1000, round_to_multiple=8)[-2:], (1000, 1000))
        self.assertEqual(node.scale(mask=options["mask"], aspect_ratio="1:1", scale_to_length=100,
                                     round_to_multiple=8, rounding="down")[-2:], (96, 96))
        self.assertEqual(node.scale(mask=options["mask"], aspect_ratio="1:1", scale_to_length=100,
                                     round_to_multiple=8, rounding="nearest")[-2:], (104, 104))

    def test_mismatched_inputs_fail_with_actionable_error(self):
        image = torch.zeros((2, 4, 8, 3))
        for kwargs, reason in (({"image":image, "mask":torch.zeros(4, 4)}, "宽高比"),
                               ({"image":image, "mask":torch.zeros(3, 4, 8)}, "批次"),
                               ({"image":image, "round_to_multiple":0}, "像素倍数"),
                               ({"image":image, "scale_to_length":64000}, "超出限制"),
                               ({"image":image, "background_color":"transparent"}, "#RRGGBB")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                node.scale(**kwargs)

    def test_example_ui_and_api_agree_and_execute(self):
        path = ROOT / "examples" / "resolution"
        api = json.loads((path / "aspect_scale_api.json").read_text())
        workflow = json.loads((path / "aspect_scale_workflow.json").read_text())
        options = api["2"]["inputs"].copy()
        self.assertEqual(options.pop("image"), ["1", 0])
        self.assertEqual(workflow["nodes"][1]["widgets_values"], [options[k] for k in node.INPUT_TYPES()["required"]])
        self.assertEqual(workflow["links"], [[1, 1, 0, 2, 0, "IMAGE"], [2, 2, 0, 3, 0, "IMAGE"]])
        self.assertEqual(api["3"]["inputs"]["images"], ["2", 0])
        self.assertEqual(node.scale(image=torch.zeros((1, 4, 8, 3)), **options)[-2:], (1280, 720))
