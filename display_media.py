"""CPU-side display packaging; scientific/source images are never overwritten."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import tempfile

POLICY = "webp-q88-m4-v1"
RASTERS = {".png", ".jpg", ".jpeg"}


def atomic_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".image-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def display_bytes(raw: bytes, suffix: str) -> tuple[bytes, str]:
    """Use WebP for still raster displays; SVG/GIF/WebP stay unchanged."""
    if suffix.lower() not in RASTERS:
        return raw, suffix.lower()
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("animated PNG requires an explicit animation publication path")
        image.load()
        oriented = ImageOps.exif_transpose(image)
        alpha = "A" in oriented.getbands() or "transparency" in oriented.info
        oriented = oriented.convert("RGBA" if alpha else "RGB")
        result = io.BytesIO()
        options = {"icc_profile": image.info["icc_profile"]} if image.info.get("icc_profile") else {}
        oriented.save(result, format="WEBP", quality=88, method=4, exact=True,
                      alpha_quality=100, **options)
        return result.getvalue(), ".webp"


def publish_image(source: Path, destination: Path) -> Path:
    """Content-keyed derivative cache: repeated builds do not re-encode."""
    raw = source.read_bytes()
    from PIL import __version__, features
    encoder = f"{POLICY}/{__version__}/{features.version('webp')}"
    key = hashlib.sha256(encoder.encode() + raw).hexdigest()
    suffix = ".webp" if source.suffix.lower() in RASTERS else source.suffix.lower()
    target = destination / (key + suffix)
    if not target.is_file():
        encoded, extension = display_bytes(raw, source.suffix)
        if extension != suffix:
            raise ValueError("unexpected display format")
        atomic_bytes(target, encoded)
    return target


def display_references(value, mapping):
    """Projection only: source and human edit documents keep their identities."""
    if isinstance(value, list):
        return [display_references(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: mapping.get(item, item) if key == "src" and isinstance(item, str)
                else display_references(item, mapping) for key, item in value.items()}
    return value
