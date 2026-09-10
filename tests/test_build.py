# test-tier: every-time
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import build_deck

ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def test_immutable_toolkit_package_can_be_built_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            toolkit = root / "toolkit"
            toolkit.mkdir()
            package = toolkit / "slidekit"
            shutil.copytree(ROOT / "slidekit", package,
                            ignore=shutil.ignore_patterns('__pycache__'))
            package.chmod(0o555)
            for name in ('public', 'server.py', 'slide_templates.py', 'display_media.py'):
                (toolkit / name).symlink_to(ROOT / name)
            source = root / 'source'
            shutil.copytree(ROOT / 'slides', source / 'slides')
            shutil.copytree(ROOT / 'public/assets', source / 'assets')
            try:
                with patch.object(build_deck, 'TOOLKIT', toolkit):
                    first = build_deck.build(source, root / 'output')
                    self.assertTrue((root / 'output/slidekit').stat().st_mode & 0o200)
                    self.assertEqual(first, build_deck.build(source, root / 'output'))
                    self.assertEqual(package.stat().st_mode & 0o777, 0o555)
            finally:
                package.chmod(0o755)

    def test_independent_sources_build_deterministically_without_live_state(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            shutil.copytree(ROOT / "slides", source / "slides")
            shutil.copytree(ROOT / "public/assets", source / "assets")
            from PIL import Image
            raster = source / "assets" / "test.png"
            Image.new("RGB", (16, 16), "blue").save(raster)
            original = raster.read_bytes()
            output = Path(temp) / "built"
            def digest():
                return {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in output.rglob("*") if p.is_file()}
            first = build_deck.build(source, output)
            before = digest()
            second = build_deck.build(source, output)
            self.assertEqual(first, second)
            self.assertEqual(before, digest())
            display_map = json.loads((output / "data/display-media.json").read_text())
            self.assertTrue(display_map["assets/test.png"].endswith(".webp"))
            self.assertTrue((output / "public" / display_map["assets/test.png"]).exists())
            self.assertFalse((output / "public/assets/test.png").exists())
            self.assertEqual(raster.read_bytes(), original)
            from tools.validate_deck import validate
            self.assertTrue(validate(output)["ok"])
            self.assertFalse((output / "data/live-state.json").exists())
            # Adding one file alone is sufficient. Existing source bytes stay unchanged.
            spec = json.loads((source / "slides/01-hero-plot.json").read_text())
            spec["id"] = "independent-new-slide"
            spec["placement"] = {"after": "mock-growth-trajectories"}
            (source / "slides/new-slide.json").write_text(json.dumps(spec))
            self.assertEqual(build_deck.build(source, output)["slides"], 7)
            protected = output / "data/live-state.json"
            protected.write_text('{"human":"must survive"}')
            with self.assertRaisesRegex(ValueError, "live authoring state"):
                build_deck.build(source, output)
            self.assertEqual(protected.read_text(), '{"human":"must survive"}')


if __name__ == "__main__":
    unittest.main()
