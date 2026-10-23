import importlib.util
from pathlib import Path
import sys
import unittest
import torch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('photo_test', ROOT / '__init__.py')
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from photo_test.modules.photo.processing import (PARAMETERS, adjust_image, srgb_to_linear,
    linear_to_srgb, luminance, tone_curve, validate_parameters, region_weights)

torch.set_num_threads(2)


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.ramp = torch.linspace(0, 1, 4097).view(1, 1, -1, 1).repeat(1, 1, 1, 3)
        self.random = torch.rand((2, 13, 17, 3), generator=torch.Generator().manual_seed(19))

    def test_registration_and_19_defaults(self):
        cls = pkg.NODE_CLASS_MAPPINGS['AIVisualPhotoFinish']
        schema = cls.INPUT_TYPES()['required']
        self.assertEqual(len([schema[k] for k in PARAMETERS if schema[k][0] == 'FLOAT']), 19)
        values = {k: v[1]['default'] for k, v in schema.items() if k != 'image'}
        result = cls().apply(self.random, **values)[0]
        self.assertTrue(torch.equal(result, self.random))

    def test_transfer_roundtrip(self):
        self.assertTrue(torch.allclose(linear_to_srgb(srgb_to_linear(self.ramp)), self.ramp, atol=2e-7))

    def test_exposure_is_linear_ev(self):
        x = torch.full((1, 3, 4, 3), 0.25)
        y = srgb_to_linear(adjust_image(x, exposure=1))
        self.assertTrue(torch.allclose(y, srgb_to_linear(x) * 2, atol=2e-7))

    def test_all_controls_effect_and_bounds(self):
        for name in PARAMETERS:
            for value in (-5, 5) if name == 'exposure' else (-100, 100):
                with self.subTest(name=name, value=value):
                    y = adjust_image(self.random, **{name: value})
                    self.assertTrue(torch.isfinite(y).all())
                    self.assertTrue((y >= 0).all() and (y <= 1).all())
                    self.assertFalse(torch.allclose(y, self.random))
                    self.assertEqual(y.shape, self.random.shape)

    def test_tone_monotone_extremes(self):
        import itertools
        x = self.ramp[..., :1]
        names = ('contrast', 'shadows', 'highlights', 'blacks', 'whites')
        for signs in itertools.product((-100, 100), repeat=5):
            p = validate_parameters(dict(zip(names, signs)))
            y = tone_curve(x, p).flatten()
            self.assertGreaterEqual(torch.diff(y).min().item(), -2e-7)

    def test_tone_regions_distinct(self):
        x = torch.tensor([0.02, 0.2, 0.5, 0.8, 0.98]).view(1, 1, 5, 1).repeat(1, 1, 1, 3)
        sh = adjust_image(x, shadows=60) - x
        hi = adjust_image(x, highlights=-60) - x
        self.assertGreater(sh[0, 0, 1, 0].item(), 0.02)
        self.assertAlmostEqual(sh[0, 0, 3, 0].item(), 0, places=6)
        self.assertLess(hi[0, 0, 3, 0].item(), -0.02)
        self.assertAlmostEqual(hi[0, 0, 1, 0].item(), 0, places=6)
        self.assertFalse(torch.allclose(adjust_image(x, whites=-60), adjust_image(x, highlights=-60)))
        self.assertFalse(torch.allclose(adjust_image(x, blacks=60), adjust_image(x, shadows=60)))

    def test_black_white_endpoints(self):
        black, white = torch.zeros(1, 1, 1, 3), torch.ones(1, 1, 1, 3)
        self.assertGreater(adjust_image(black, blacks=50).mean().item(), 0)
        self.assertLess(adjust_image(white, whites=-50).mean().item(), 1)
        self.assertTrue(torch.equal(adjust_image(black, shadows=100), black))
        self.assertTrue(torch.allclose(adjust_image(white, highlights=-100), white, atol=1e-6))

    def test_white_balance_signs(self):
        x = torch.full((1, 1, 1, 3), 0.5)
        warm = adjust_image(x, temperature=50).flatten()
        cool = adjust_image(x, temperature=-50).flatten()
        magenta = adjust_image(x, tint=50).flatten()
        self.assertGreater(warm[0], warm[2])
        self.assertLess(cool[0], cool[2])
        self.assertGreater(magenta[0], magenta[1])
        self.assertGreater(magenta[2], magenta[1])

    def test_region_weights_and_isolation(self):
        weights = region_weights(self.ramp[..., :1])
        self.assertTrue(torch.allclose(sum(weights), torch.ones_like(weights[0])))
        self.assertTrue(all((w >= -1e-7).all() for w in weights))
        x = torch.tensor([0.1, 0.9]).view(1, 1, 2, 1).repeat(1, 1, 1, 3)
        y = adjust_image(x, shadow_cyan_red=60)
        self.assertGreater(y[0, 0, 0, 0], x[0, 0, 0, 0])
        self.assertTrue(torch.allclose(y[..., 1, :], x[..., 1, :], atol=2e-7))

    def test_preserve_luminance_after_gamut_mapping(self):
        values = {name: 100 if i % 2 else -100 for i, name in enumerate(PARAMETERS[10:])}
        before = luminance(srgb_to_linear(self.random))
        preserved = adjust_image(self.random, **values)
        self.assertLess((luminance(srgb_to_linear(preserved)) - before).abs().max().item(), 5e-7)
        changed = adjust_image(self.random, preserve_luminosity=False, **values)
        self.assertGreater((luminance(srgb_to_linear(changed)) - before).abs().mean().item(), 1e-3)

    def test_saturation_and_vibrance(self):
        gray = adjust_image(self.random, saturation=-100)
        self.assertTrue(torch.allclose(gray[..., 0], gray[..., 1]))
        self.assertTrue(torch.allclose(gray[..., 1], gray[..., 2]))
        # Less-saturated patch gets a stronger relative chroma boost.
        x = linear_to_srgb(torch.tensor([[[[0.3, 0.25, 0.25], [0.7, 0.04, 0.04]]]]))
        result = srgb_to_linear(adjust_image(x, vibrance=100))
        before = srgb_to_linear(x)
        boost = (result.amax(-1)-result.amin(-1))/(before.amax(-1)-before.amin(-1))
        self.assertGreater(boost[0, 0, 0], boost[0, 0, 1])

    def test_batch_tile_alpha_nonmutation(self):
        rgba = torch.cat([self.random, torch.rand(2, 13, 17, 1)], -1)
        saved = rgba.clone()
        one = adjust_image(rgba, exposure=0.3, temperature=20, tile_rows=1)
        full = adjust_image(rgba, exposure=0.3, temperature=20, tile_rows=128)
        self.assertTrue(torch.allclose(one, full, atol=5e-7, rtol=0))
        self.assertTrue(torch.equal(rgba, saved))
        self.assertTrue(torch.equal(one[..., 3], rgba[..., 3]))
        for i in range(2):
            self.assertTrue(torch.allclose(one[i:i+1], adjust_image(rgba[i:i+1], exposure=0.3, temperature=20), atol=5e-7, rtol=0))

    def test_float_precision_no_uint8_quantization(self):
        x = torch.linspace(0.1, 0.9, 4097).reshape(1, 1, -1, 1).repeat(1, 1, 1, 3)
        y = adjust_image(x, exposure=0.1)
        self.assertGreater(torch.unique(y[..., 0]).numel(), 4000)

    def test_invalid_inputs(self):
        for image in (torch.zeros(3, 4, 3), torch.zeros(1, 2, 2, 1), torch.zeros(1, 2, 2, 3, dtype=torch.uint8), torch.full((1, 1, 1, 3), float('nan')), torch.ones(1, 1, 1, 3)*2):
            with self.assertRaises(ValueError):
                adjust_image(image)
        for values in ({'exposure':6}, {'contrast':float('inf')}, {'bad':0}, {'tint':True}):
            with self.assertRaises(ValueError):
                adjust_image(self.random, **values)

    def test_combined_extremes_and_half_input(self):
        for value in (-100, 100):
            p = {name: value for name in PARAMETERS if name != 'exposure'}
            y = adjust_image(self.random.half(), exposure=value/20, **p)
            self.assertEqual(y.dtype, torch.float32)
            self.assertTrue(torch.isfinite(y).all())
            self.assertTrue((y >= 0).all() and (y <= 1).all())


if __name__ == '__main__':
    unittest.main(verbosity=2)
