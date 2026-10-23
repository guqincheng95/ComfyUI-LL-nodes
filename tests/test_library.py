import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ll_library_test', ROOT / '__init__.py')
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from ll_library_test.scripts.migrate_legacy import migrate


class LibraryTests(unittest.TestCase):
    def test_unified_registration_and_assets(self):
        self.assertEqual(set(pkg.NODE_CLASS_MAPPINGS), {'ResolutionPreset', 'AIVisualPhotoFinish', 'LLPersonContourTrim'})
        self.assertTrue((ROOT / pkg.WEB_DIRECTORY / 'photo_finish.js').is_file())
        translations = json.loads((ROOT / 'locales/zh/nodeDefs.json').read_text())
        for key, node in pkg.NODE_CLASS_MAPPINGS.items():
            self.assertEqual(set(translations[key]['inputs']), set(node.INPUT_TYPES()['required']) | set(node.INPUT_TYPES().get('optional', {})))
            self.assertTrue(node.CATEGORY.startswith('LL 节点库/'))
        self.assertFalse((ROOT / 'addons').exists())

    def test_existing_api_workflows_resolve(self):
        for folder in ['resolution', 'photo']:
            prompt = json.loads((ROOT / 'examples' / folder / 'minimal_api.json').read_text())
            for data in prompt.values():
                if data['class_type'] not in pkg.NODE_CLASS_MAPPINGS:
                    continue
                schema = pkg.NODE_CLASS_MAPPINGS[data['class_type']].INPUT_TYPES()['required']
                self.assertTrue(set(data['inputs']) <= set(schema))

    def test_migration_preview_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            custom = Path(temp) / 'ComfyUI/custom_nodes'
            root = custom / 'comfyui-LL-nodes'
            root.mkdir(parents=True)
            old = custom / 'ComfyUI-PhotoFinish'
            old.mkdir(); (old / '__init__.py').write_text('AIVisualPhotoFinish')
            (old / 'user.txt').write_text('preserve me')
            self.assertEqual(migrate(root), [str(old)])
            self.assertTrue(old.exists())
            destinations = migrate(root, True)
            self.assertFalse(old.exists())
            self.assertEqual((Path(destinations[0]) / 'user.txt').read_text(), 'preserve me')
            self.assertFalse(Path(destinations[0]).is_relative_to(custom))
            self.assertEqual(migrate(root, True), [])

    def test_migration_rejects_unrecognized_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'custom_nodes/comfyui-LL-nodes'; root.mkdir(parents=True)
            old = root.parent / 'ComfyUI-PhotoFinish'; old.mkdir()
            with self.assertRaises(ValueError): migrate(root, True)
            self.assertTrue(old.exists())


if __name__ == '__main__': unittest.main()
