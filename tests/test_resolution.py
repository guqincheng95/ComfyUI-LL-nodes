import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resolution_test_package", ROOT / "__init__.py")
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from resolution_test_package.presets import PRESETS, validate_presets


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.node = package.NODE_CLASS_MAPPINGS["ResolutionPreset"]()

    def test_required_five_cases(self):
        cases = [
            ("Z-Image", "9:16", "Quality", "Portrait", (864, 1536)),
            ("Z-Image", "16:9", "Quality", "Landscape", (1536, 864)),
            ("Z-Image", "3:4", "Max", "Portrait", (1536, 2048)),
            ("Z-Image", "4:3", "Fast", "Landscape", (1024, 768)),
            ("Custom", "9:16", "Quality", "Portrait", (1376, 768)),
        ]
        for family, ratio, tier, orientation, expected in cases:
            with self.subTest(family=family, ratio=ratio, tier=tier):
                self.assertEqual(self.node.resolve(family, ratio, tier, orientation), expected)

    def test_all_162_builtin_combinations(self):
        # Independent specification oracle, not a copy of the implementation table.
        for family in ("Z-Image", "SCAIL-2 / WAN", "FLUX"):
            for ratio in ("1:1", "3:4", "4:3", "9:16", "16:9", "2:3"):
                a, b = map(int, ratio.split(":"))
                for tier, long_side in (("Fast", 1024), ("Quality", 1536), ("Max", 2048)):
                    unit = round(long_side / (max(a, b) * 32)) * 32
                    expected = (unit * a, unit * b)
                    for orientation in ("Auto", "Portrait", "Landscape"):
                        pair = expected if orientation == "Auto" else tuple(sorted(expected, reverse=orientation == "Landscape"))
                        with self.subTest(family=family, ratio=ratio, tier=tier, orientation=orientation):
                            actual = self.node.resolve(family, ratio, tier, orientation)
                            self.assertEqual(actual, pair)
                            self.assertTrue(all(type(v) is int and v % 32 == 0 for v in actual))

    def test_two_three_and_krea_alignment(self):
        for family in ("Z-Image", "SCAIL-2 / WAN", "FLUX"):
            for tier, expected in (("Fast", (704, 1056)), ("Quality", (1024, 1536)), ("Max", (1344, 2016))):
                self.assertEqual(self.node.resolve(family, "2:3", tier, "Auto"), expected)
                self.assertEqual(self.node.resolve(family, "2:3", tier, "Landscape"), expected[::-1])
                self.assertEqual(expected[0] * 3, expected[1] * 2)
                self.assertTrue(all(v % 16 == 0 for v in expected))

    def test_custom_unchanged(self):
        for orientation in ("Auto", "Portrait", "Landscape"):
            for width, height in ((1376, 768), (1377, 769), (1, 1), (20000, 17)):
                self.assertEqual(self.node.resolve("Custom", "1:1", "Max", orientation, width, height), (width, height))

    def test_invalid_inputs(self):
        args = ["Z-Image", "9:16", "Quality", "Auto"]
        for index in range(4):
            invalid = args.copy()
            invalid[index] = "invalid"
            with self.assertRaises(ValueError):
                self.node.resolve(*invalid)
        for value in (0, -1, True, 1.5, "768", 2147483648):
            with self.assertRaises(ValueError):
                self.node.resolve("Custom", "1:1", "Fast", "Auto", value, 768)

    def test_preset_validation(self):
        validate_presets()
        for bad in ((513, 1024), (0, 1024), (32.0, 1024), (32,), None):
            data = copy.deepcopy(PRESETS)
            data["FLUX"]["1:1"]["Fast"] = bad
            with self.assertRaises(ValueError):
                validate_presets(data)
        data = copy.deepcopy(PRESETS)
        del data["FLUX"]["9:16"]
        with self.assertRaises(ValueError):
            validate_presets(data)

    def test_family_tables_independent(self):
        self.assertIsNot(PRESETS["Z-Image"]["1:1"], PRESETS["FLUX"]["1:1"])

    def test_registration_and_defaults(self):
        self.assertEqual(self.node.RETURN_TYPES, ("INT", "INT"))
        self.assertEqual(self.node.RETURN_NAMES, ("width", "height"))
        self.assertEqual(package.NODE_DISPLAY_NAME_MAPPINGS["ResolutionPreset"], '比例预设 · Resolution Preset')
        schema = self.node.INPUT_TYPES()["required"]
        defaults = {name: definition[1]["default"] for name, definition in schema.items()}
        self.assertEqual(getattr(self.node, self.node.FUNCTION)(**defaults), (864, 1536))

    def test_workflow_links(self):
        flow = json.loads((ROOT / "examples/minimal_workflow.json").read_text())
        self.assertEqual(flow["links"][:2], [[1, 1, 0, 2, 0, "INT"], [2, 1, 1, 2, 1, "INT"]])
        prompt = json.loads((ROOT / "examples/minimal_api.json").read_text())
        self.assertEqual(prompt["2"]["inputs"]["width"], ["1", 0])
        self.assertEqual(prompt["2"]["inputs"]["height"], ["1", 1])
        self.assertEqual(prompt["3"]["class_type"], "SaveImage")


if __name__ == "__main__":
    unittest.main(verbosity=2)
