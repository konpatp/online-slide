# test-tier: every-time
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from display_media import display_bytes, display_references, publish_image


class DisplayMediaTests(unittest.TestCase):
    def test_webp_preserves_dimensions_alpha_and_sources_and_caches(self):
        image = Image.new("RGBA", (24, 16), (180, 80, 40, 111))
        source_bytes = io.BytesIO()
        image.save(source_bytes, format="PNG")
        raw = source_bytes.getvalue()
        encoded, suffix = display_bytes(raw, ".png")
        decoded = Image.open(io.BytesIO(encoded))
        self.assertEqual(suffix, ".webp")
        self.assertEqual(decoded.size, image.size)
        self.assertEqual(decoded.getchannel("A").tobytes(), image.getchannel("A").tobytes())
        self.assertEqual(display_bytes(encoded, ".webp"), (encoded, ".webp"))
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "image.png"
            source.write_bytes(raw)
            target = publish_image(source, Path(temp) / "display")
            with patch("display_media.display_bytes", side_effect=AssertionError("re-encode")):
                self.assertEqual(publish_image(source, target.parent), target)
            self.assertEqual(source.read_bytes(), raw)

    def test_projection_does_not_mutate_human_state(self):
        state = {"components": [{"src": "uploads/original.png", "caption": "original.png"}]}
        result = display_references(state, {"uploads/original.png": "uploads/display.webp"})
        self.assertEqual(result["components"][0]["src"], "uploads/display.webp")
        self.assertEqual(state["components"][0]["src"], "uploads/original.png")
