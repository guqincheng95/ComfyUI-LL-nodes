import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from modules.dlss import processing as p
from modules.dlss.nodes import DLSS5Settings, DLSS5Compare
from modules.dlss import runner


class MixingTests(unittest.TestCase):
    def setUp(self):
        self.source = np.full((64, 96, 3), .25, np.float32)
        self.enhanced = np.full_like(self.source, .75)
        self.mask = np.zeros((64, 96), np.float32)
        self.mask[:, :48] = 1
        self.plain = dict(mode='regional_all', neutral_protection=0., skin_protection=0., feather=0., edge_guard=0.)

    def test_linear_light_blending_not_gamma_average(self):
        output, _, _ = p.compose(np.zeros_like(self.source), np.ones_like(self.source),
            background_strength=.5, **self.plain)
        self.assertAlmostEqual(float(output[0, 0, 0]), .73535698, places=6)

    def test_zero_strength_preserves_original_and_alpha(self):
        source = np.concatenate([self.source, np.full((64, 96, 1), .314159, np.float32)], -1)
        output, _, _ = p.compose(source, self.enhanced, background_strength=0., **self.plain)
        np.testing.assert_allclose(output, source, atol=1e-7)
        np.testing.assert_array_equal(output[..., 3], source[..., 3])

    def test_person_and_background_are_separate(self):
        output, _, _ = p.compose(self.source, self.enhanced, self.mask,
            person_strength=0., background_strength=1., **self.plain)
        np.testing.assert_allclose(output[:, :48], self.source[:, :48], atol=1e-7)
        np.testing.assert_allclose(output[:, 48:], self.enhanced[:, 48:], atol=1e-7)

    def test_unified_lighting_keeps_person_illumination_at_zero_detail(self):
        output, _, report = p.compose(self.source, self.enhanced, self.mask,
            person_strength=0., background_strength=1., lighting_strength=.5,
            mode='unified_lighting', neutral_protection=0., skin_protection=0., feather=0., edge_guard=0.)
        np.testing.assert_allclose(output[:, 10], output[:, 80], atol=1e-6)
        self.assertGreater(float(output[:, 10].mean()), .25)

    def test_edge_guard_limits_transition_enhancement(self):
        base, _, _ = p.compose(self.source, self.enhanced, self.mask, person_strength=.2, **self.plain)
        guarded, _, _ = p.compose(self.source, self.enhanced, self.mask,
            person_strength=.2, **{**self.plain, 'edge_guard': 1.})
        self.assertLess(float(guarded[:, 48].mean()), float(base[:, 48].mean()))
        np.testing.assert_allclose(guarded[:, 80], base[:, 80], atol=1e-7)

    def test_soft_mask_and_scale_are_retained(self):
        mask = np.linspace(0, 1, 24, dtype=np.float32)[None].repeat(16, 0)
        result = p.mask_batch(torch.tensor(mask), 8, (64, 96), (64, 96))
        self.assertEqual(result.shape, (1, 64, 96))
        self.assertTrue(np.any((result > .1) & (result < .9)))
        with self.assertRaisesRegex(ValueError, '宽高比'):
            p.mask_batch(np.ones((32, 32)), 1, (64, 96), (64, 96))
        with self.assertRaisesRegex(ValueError, '一一对应'):
            p.mask_batch(np.ones((3, 64, 96)), 2, (64, 96), (64, 96))

    def test_transparent_colour_does_not_bleed_on_rescale(self):
        image = np.zeros((4, 8, 4), np.float32)
        image[:, :4] = [1, 0, 0, 1]
        image[:, 4:] = [0, 1, 0, 0]
        out = p.resize_image(image, 16, 8)
        active = out[..., 3] > .01
        np.testing.assert_allclose(out[active, 1:3], 0., atol=1e-7)

    def test_skin_protection_keeps_luminance_and_only_selected_area(self):
        source = self.source.copy(); source[:] = [.65, .42, .31]
        enhanced = self.enhanced.copy(); enhanced[:] = [.85, .38, .28]
        before, _, _ = p.compose(source, enhanced, self.mask, **self.plain)
        after, _, report = p.compose(source, enhanced, self.mask, self.mask,
            **{**self.plain, 'skin_protection': 1.})
        np.testing.assert_allclose(p.luminance(p.linear(after)), p.luminance(p.linear(before)), atol=2e-6)
        np.testing.assert_allclose(after[:, 48:], before[:, 48:], atol=1e-6)
        self.assertLess(float(after[:, 10, 0].mean()), float(before[:, 10, 0].mean()))
        self.assertGreater(report['skin_samples'], 0)

    def test_no_skin_mask_does_not_treat_person_as_skin(self):
        _, _, report = p.compose(self.source, self.enhanced, self.mask)
        self.assertIn('skin_skipped', report)

    def test_no_neutral_samples_skip_instead_of_palette_transfer(self):
        source = self.source.copy(); source[:] = [.8, .03, .01]
        _, _, report = p.compose(source, self.enhanced)
        self.assertEqual(report['neutral_samples'], 0)
        self.assertIn('neutral_skipped', report)

    def test_neutral_colour_gains_are_smoothed_and_reset_on_cut(self):
        state = {}
        neutral_source = np.full_like(self.source, .5)
        red = self.enhanced.copy(); red[..., 0] += .08
        blue = self.enhanced.copy(); blue[..., 2] += .08
        args = dict(neutral_protection=1., skin_protection=0., mode='regional_all', colour_state=state)
        _, _, first = p.compose(neutral_source, red, reset=True, **args)
        _, _, next_frame = p.compose(neutral_source, blue, reset=False, **args)
        _, _, cut = p.compose(neutral_source, blue, reset=True, **args)
        first_gain = np.log(first['neutral_rgb_gain'])
        next_gain = np.log(next_frame['neutral_rgb_gain'])
        cut_gain = np.log(cut['neutral_rgb_gain'])
        np.testing.assert_allclose(next_gain, first_gain * .7 + cut_gain * .3, atol=1e-6)

    def test_transparent_pixels_are_not_neutral_anchors(self):
        source = np.concatenate([self.source, np.zeros((64, 96, 1), np.float32)], -1)
        _, _, report = p.compose(source, self.enhanced)
        self.assertEqual(report['neutral_samples'], 0)

    def test_invalid_numbers_and_wrong_size_fail(self):
        with self.assertRaises(ValueError):
            p.compose(self.source, self.enhanced, person_strength=float('nan'))
        with self.assertRaises(ValueError):
            p.compose(self.source, self.enhanced[:32])

    def test_temporal_flow_tracks_translation_and_cut_resets(self):
        before = np.zeros((64, 96), np.float32); before[16:40, 20:40] = 1
        after = np.roll(before, 6, axis=1)
        flow = np.zeros((64, 96, 2), np.float16); flow[..., 0] = -6
        temporal = p.TemporalMask(.8)
        temporal.process(before, flow, True)
        np.testing.assert_allclose(temporal.process(after, flow, False), after, atol=1e-7)
        np.testing.assert_array_equal(temporal.process(before, flow, True), before)

    def test_roi_is_post_crop_and_uses_mask(self):
        image = torch.from_numpy(self.source[None])
        enhanced = torch.from_numpy(self.enhanced[None])
        result, report = DLSS5Compare().compare(image, enhanced, roi_mask=torch.from_numpy(self.mask[None]))
        report = json.loads(report)
        self.assertEqual(result.shape[2], report['width'] * 2)
        self.assertLess(report['width'], 96)


class FakeSession:
    submitted = []
    created = 0
    proof_error = False

    def __init__(self, layout, options, input_width, input_height, frame_count, **kwargs):
        type(self).created += 1
        self.render_width, self.render_height = input_width, input_height
        self.output_width, self.output_height = runner.resolve_output_size(input_width, input_height, options.upscaling_factor)
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def submit(self, **kwargs):
        type(self).submitted.append(kwargs['reset'])
        import cv2
        return cv2.resize(kwargs['rgba'], (self.output_width, self.output_height)), kwargs['pts']
    def feature_report(self):
        if self.proof_error:
            raise RuntimeError('signed DLSSNR missing')
        return {'verified': True, 'test_double': True}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.image = torch.full((2, 64, 96, 4), .4)
        self.image[..., 3] = .123456
        self.settings, = DLSS5Settings().build()
        self.settings['release_comfy_models'] = False
        FakeSession.created = 0; FakeSession.submitted = []; FakeSession.proof_error = False
        self.layout = patch.object(runner, 'find_runtime', return_value=object())
        self.layout.start()
        self.addCleanup(self.layout.stop)
    def run_node(self, **kwargs):
        class Progress:
            def __init__(self, count): pass
            def update(self, count): pass
        return runner.enhance(self.image, self.settings,
            kwargs.pop('mode', 'independent_images'), kwargs.pop('preview', False), kwargs.pop('long_edge', 1024),
            kwargs.pop('person_mask', None), None, _session_factory=FakeSession,
            _callbacks=lambda release: (lambda: None, Progress), _platform='Windows', **kwargs)

    def test_independent_images_reset_every_frame_and_alpha_is_exact(self):
        output, mask, report = self.run_node()
        self.assertEqual(FakeSession.submitted, [True, True])
        self.assertEqual(FakeSession.created, 1)
        self.assertEqual(json.loads(report)['native_passes_per_frame'], 1)
        torch.testing.assert_close(output[..., 3], self.image[..., 3], rtol=0, atol=0)

    def test_video_uses_temporal_history_and_warns_static_mask(self):
        _, _, report = self.run_node(mode='video_sequence', person_mask=torch.ones((1, 64, 96)))
        self.assertEqual(FakeSession.submitted, [True, False])
        self.assertTrue(any('一张人物' in w for w in json.loads(report)['warnings']))

    def test_preview_limits_output_and_marks_it(self):
        self.image = torch.full((1, 800, 1200, 3), .4)
        _, mask, report = self.run_node(preview=True, long_edge=384)
        self.assertLessEqual(max(mask.shape[1:]), 384)
        self.assertTrue(json.loads(report)['preview'])

    def test_missing_signed_proof_is_not_success_and_lock_is_released(self):
        FakeSession.proof_error = True
        with self.assertRaisesRegex(RuntimeError, 'signed DLSSNR'):
            self.run_node()
        self.assertFalse(runner._RENDER_LOCK.locked())

    def test_wrong_mask_batch_rejected_before_worker_start(self):
        with self.assertRaises(ValueError):
            self.run_node(person_mask=torch.ones((3, 64, 96)))
        self.assertEqual(FakeSession.created, 0)

    def test_output_budget_fails_before_allocation(self):
        self.image = torch.tensor(.4).expand(1000, 768, 1024, 3)
        with self.assertRaisesRegex(ValueError, '2GiB'):
            self.run_node()
        self.assertEqual(FakeSession.created, 0)

    def test_custom_settings_and_presets_are_reportable(self):
        custom, = DLSS5Settings().build(preset='自定义', person_strength=.17, tone=.8)
        self.assertEqual(custom['mix']['person_strength'], .17)
        self.assertEqual(custom['options'].local_tone_strength, .8)
        preset, = DLSS5Settings().build(preset='环境增强', person_strength=.17, tone=.8)
        self.assertEqual(preset['mix']['person_strength'], .3)
        self.assertEqual(preset['options'].local_tone_strength, 1.2)


@unittest.skipIf(os.name == 'nt', 'POSIX fake worker exercises pipe lifecycle without Windows/GPU')
class WorkerLifecycleTests(unittest.TestCase):
    def test_blocked_handshake_is_killed_by_timeout(self):
        from modules.dlss.native.session import DlssSession
        from modules.dlss.native.paths import RuntimeLayout
        from modules.dlss.native.settings import DlssOptions
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / 'nvngx.dll'
            worker.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(15)\n')
            worker.chmod(0o755)
            with patch('modules.dlss.native.session.ensure_supported', return_value=({}, {})):
                with self.assertRaisesRegex(RuntimeError, '超过'):
                    DlssSession(RuntimeLayout(Path(tmp)), DlssOptions(), input_width=64,
                                input_height=64, frame_count=1, timeout=.1)

    def test_blocked_handshake_can_be_cancelled(self):
        from modules.dlss.native.session import DlssSession
        from modules.dlss.native.paths import RuntimeLayout
        from modules.dlss.native.settings import DlssOptions
        class Cancelled(Exception):
            pass
        def cancelled():
            raise Cancelled('test cancellation')
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / 'nvngx.dll'
            worker.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(15)\n')
            worker.chmod(0o755)
            with patch('modules.dlss.native.session.ensure_supported', return_value=({}, {})):
                with self.assertRaises(Cancelled):
                    DlssSession(RuntimeLayout(Path(tmp)), DlssOptions(), input_width=64,
                                input_height=64, frame_count=1, timeout=10., cancel_check=cancelled)


if __name__ == '__main__':
    unittest.main()
