"""User paths through the unified node; no native GPU inference is simulated as proof."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import torch

from modules.dlss.nodes import DLSS5RegionEnhance, DLSS5Settings, inline_settings
from modules.dlss.native.settings import DlssOptions
from modules.dlss.preview import comparison_preview


class SingleNodeTests(unittest.TestCase):
    def setUp(self):
        self.image = torch.full((1, 64, 96, 3), .3)
        self.output = (self.image + .2, torch.zeros((1, 64, 96)), 'report')

    def test_default_image_only_uses_upstream_defaults_without_settings_node(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            result = DLSS5RegionEnhance().enhance(self.image)
        self.assertIs(result, self.output)
        self.assertEqual(run.call_args.args[1]['options'].native(), DlssOptions().native())
        self.assertEqual(run.call_args.kwargs['processing_mode'], 'native')

    def test_inline_native_controls_do_not_require_separate_settings(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            DLSS5RegionEnhance().enhance(self.image, upscaling='2x', tone=.75, structure=.8)
        options = run.call_args.args[1]['options']
        self.assertEqual(options.upscaling_factor, 2.)
        self.assertEqual(options.local_tone_strength, .75)
        self.assertEqual(options.local_structure_strength, .8)
        self.assertEqual(run.call_args.kwargs['processing_mode'], 'native')

    def test_inline_portrait_preset_automatically_enables_region_pipeline(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            DLSS5RegionEnhance().enhance(self.image, preset='人像保真')
        self.assertEqual(run.call_args.kwargs['processing_mode'], 'regional')
        self.assertEqual(run.call_args.args[1]['mix']['background_strength'], .9)

    def test_inline_mask_activates_region_even_with_native_preset(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            DLSS5RegionEnhance().enhance(self.image, person_mask=torch.ones((1, 64, 96)))
        self.assertEqual(run.call_args.kwargs['processing_mode'], 'regional')

    def test_custom_region_parameters_apply_in_same_node(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            DLSS5RegionEnhance().enhance(self.image, preset='自定义', processing_mode='regional',
                                        person_strength=.1, background_strength=.8, neutral_protection=0.)
        mix = run.call_args.args[1]['mix']
        self.assertEqual((mix['person_strength'], mix['background_strength'], mix['neutral_protection']), (.1, .8, 0.))

    def test_external_legacy_settings_keep_priority(self):
        settings, = DLSS5Settings().build(preset='环境增强')
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            DLSS5RegionEnhance().enhance(self.image, settings=settings, preset='人像保真', tone=.1)
        self.assertIs(run.call_args.args[1], settings)
        self.assertEqual(run.call_args.kwargs['processing_mode'], 'auto')

    def test_compare_preview_does_not_replace_downstream_image(self):
        calls = []
        def save_images(image, **kwargs):
            calls.append((image, kwargs))
            return {'ui': {'images': [{'filename': 'test.png', 'type': 'temp', 'subfolder': ''}]}}
        result = comparison_preview(self.image, self.output, x=.25, y=.25, width=.5, height=.5,
                                    prompt={'test': True}, _save_images=save_images)
        self.assertIs(result['result'], self.output)
        self.assertEqual(calls[0][0].shape, (1, 32, 96, 3))
        torch.testing.assert_close(calls[0][0][:, :, :48], self.image[:, 16:48, 24:72])
        self.assertEqual(calls[0][1]['prompt'], {'test': True})
        self.assertEqual(result['ui']['images'][0]['type'], 'temp')

    def test_node_preview_returns_standard_comfy_ui_payload(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output), \
             patch('modules.dlss.preview.comparison_preview', return_value={'ui': {}, 'result': self.output}) as preview:
            result = DLSS5RegionEnhance().enhance(self.image, compare_preview=True)
        preview.assert_called_once()
        self.assertIs(result['result'], self.output)

    def test_only_main_dlss_node_is_active_and_legacy_ids_still_registered(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('ll_single_node_registry', root / '__init__.py')
        pkg = importlib.util.module_from_spec(spec); sys.modules[spec.name] = pkg
        spec.loader.exec_module(pkg)
        active = [key for key, node in pkg.NODE_CLASS_MAPPINGS.items()
                  if key.startswith('LLDLSS5') and not getattr(node, 'DEPRECATED', False)]
        self.assertEqual(active, ['LLDLSS5RegionEnhance'])
        self.assertIn('LLDLSS5Compare', pkg.NODE_CLASS_MAPPINGS)
        self.assertIn('LLDLSS5Settings', pkg.NODE_CLASS_MAPPINGS)

    def test_advanced_visibility_does_not_change_processing_parameters(self):
        with patch('modules.dlss.runner.enhance', return_value=self.output) as run:
            DLSS5RegionEnhance().enhance(self.image, show_advanced=False, structure=.8)
            hidden = run.call_args.args[1]['options']
            DLSS5RegionEnhance().enhance(self.image, show_advanced=True, structure=.8)
            shown = run.call_args.args[1]['options']
        self.assertEqual(hidden, shown)


if __name__ == '__main__':
    unittest.main()
