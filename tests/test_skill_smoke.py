"""
Repo smoke tests for the skill's templates and docs. Standard library only --
no Docker, no third-party packages, and nothing written into the skill folder.

Run from the repo root:

    python3 -B -m unittest discover -s tests
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / "sagemaker-marketplace-onboarding"
TEMPLATES = SKILL_DIR / "templates"

# Words that mark a line as an explicit "custom dimensions are not supported"
# example rather than a suggestion to use one.
NEGATION = re.compile(r"\b(no|not|cannot|flag)\b", re.IGNORECASE)


def load_metering():
    # Keep the skill folder clean: no __pycache__ next to the templates.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("metering", TEMPLATES / "metering.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skill_text_files():
    for path in sorted(SKILL_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".py", ".sh", ".json", ".conf", ""}:
            yield path


class TemplateSyntaxTest(unittest.TestCase):
    def test_python_templates_compile(self):
        files = sorted(TEMPLATES.rglob("*.py"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.relative_to(SKILL_DIR)):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")


class MeteringTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_metering()

    def test_dimension_is_inference_count(self):
        self.assertEqual(self.m.DIMENSION, "inference.count")

    def test_header_shape(self):
        self.assertEqual(
            json.loads(self.m.inference_metering_header(3)),
            {"Dimension": "inference.count", "ConsumedUnits": 3},
        )

    def test_frame_shape(self):
        # 12 minutes of metered audio at 1 unit = 1 second.
        frame = self.m.make_metering_frame(720, client_token="t1")
        self.assertEqual(
            frame,
            {"Metering": {"Dimension": "inference.count", "ConsumedUnits": 720, "ClientToken": "t1"}},
        )
        self.assertLessEqual(len(json.dumps(frame).encode("utf-8")), 512)

    def test_zero_units_allowed(self):
        self.assertEqual(self.m.make_metering_frame(0)["Metering"]["ConsumedUnits"], 0)

    def test_negative_units_rejected(self):
        with self.assertRaises(ValueError):
            self.m.make_metering_frame(-1)

    def test_non_numeric_units_rejected(self):
        for bad in ("720", None, True):
            with self.subTest(value=bad), self.assertRaises(TypeError):
                self.m.make_metering_frame(bad)

    def test_accumulator_carries_remainder(self):
        acc = self.m.UnitAccumulator()  # 1 unit = 1 second
        for seconds in (0.4, 0.4, 0.4):
            acc.add(seconds)
        self.assertEqual(acc.take_units(), 1)  # 1.2s -> 1 unit, 0.2s carried
        acc.add(0.9)
        self.assertEqual(acc.take_units(), 1)  # 0.2 + 0.9 = 1.1s
        self.assertEqual(acc.take_units(), 0)

    def test_accumulator_scaled_unit(self):
        acc = self.m.UnitAccumulator(10)  # 1 unit = 10 seconds
        acc.add(25)
        self.assertEqual(acc.take_units(), 2)  # 5s carried
        acc.add(5)
        self.assertEqual(acc.take_units(), 1)


class DimensionDocsTest(unittest.TestCase):
    def test_every_dimension_literal_is_inference_count(self):
        pattern = re.compile(r'"Dimension"\s*:\s*"([^"]*)"')
        for path in skill_text_files():
            for value in pattern.findall(path.read_text(encoding="utf-8")):
                with self.subTest(path=path.relative_to(SKILL_DIR)):
                    self.assertEqual(value, "inference.count")

    def test_audio_seconds_only_as_not_supported_example(self):
        for path in skill_text_files():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "audio_seconds" in line:
                    with self.subTest(path=f"{path.relative_to(SKILL_DIR)}:{lineno}"):
                        self.assertRegex(line, NEGATION)


if __name__ == "__main__":
    unittest.main()
