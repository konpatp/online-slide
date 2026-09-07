# test-tier: every-time
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import build_deck

ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def test_independent_sources_build_deterministically_without_live_state(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            shutil.copytree(ROOT / "slides", source / "slides")
            shutil.copytree(ROOT / "public/assets", source / "assets")
            output = Path(temp) / "built"
            def digest():
                return {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in output.rglob("*") if p.is_file()}
            first = build_deck.build(source, output)
            before = digest()
            second = build_deck.build(source, output)
            self.assertEqual(first, second)
            self.assertEqual(before, digest())
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
