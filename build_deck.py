#!/usr/bin/env python3
"""Package independent sources with a pinned renderer; never copy live state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from slidekit import catalog_receipt, empty_state, load_catalog, reconcile_state
from display_media import RASTERS, publish_image

TOOLKIT = Path(__file__).resolve().parent


def copy_build_tree(source: Path, destination: Path, **options) -> None:
    """Copy immutable inputs into a replaceable, build-owned artifact tree."""
    shutil.copytree(source, destination, **options)
    for directory in (destination, *destination.rglob("*")):
        if directory.is_dir():
            directory.chmod(0o755)


def build(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if output == source or source.is_relative_to(output):
        raise ValueError("output must be a separate generated directory")
    if (output / "data" / "live-state.json").exists():
        raise ValueError("refusing to rebuild over live authoring state")
    catalog = load_catalog(source / "slides")
    seed_path = source / "seed-state.json"
    seed = json.loads(seed_path.read_text()) if seed_path.exists() else empty_state()
    seed, _ = reconcile_state(seed, catalog)
    # Assets are owned by the contribution, not recovered by a central builder.
    assets = source / "assets"
    for spec in catalog.values():
        for component in spec["components"].values():
            if component["kind"] != "image":
                continue
            path = (source / component["src"]).resolve()
            if not path.is_relative_to(assets.resolve()) or not path.is_file():
                raise ValueError(f"missing or out-of-bound source asset: {component['src']}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".slide-build-", dir=output.parent) as temp:
        staging = Path(temp) / "site"
        staging.mkdir()
        copy_build_tree(TOOLKIT / "public", staging / "public")
        if assets.is_dir():
            copy_build_tree(assets, staging / "public" / "assets", dirs_exist_ok=True,
                            ignore=lambda directory, names: [
                                name for name in names if Path(name).suffix.lower() in RASTERS
                                and (Path(directory) / name).is_file()
                            ])
        display_map = {}
        # Reuse the previous generated release as the cache; the new release
        # retains only derivatives reachable from the current source assets.
        for image in sorted(assets.rglob("*")) if assets.is_dir() else ():
            if not image.is_file() or image.suffix.lower() not in RASTERS:
                continue
            target = publish_image(image, output / "public" / "display")
            relative = target.relative_to(output / "public")
            (staging / "public" / "display").mkdir(exist_ok=True)
            shutil.copy2(target, staging / "public" / relative)
            display_map[image.relative_to(source).as_posix()] = relative.as_posix()
        copy_build_tree(source / "slides", staging / "slides")
        copy_build_tree(TOOLKIT / "slidekit", staging / "slidekit",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in ("server.py", "slide_templates.py", "display_media.py"):
            shutil.copy2(TOOLKIT / name, staging / name)
        (staging / "data").mkdir()
        (staging / "data" / "display-media.json").write_text(
            json.dumps(display_map, sort_keys=True) + "\n")
        (staging / "data" / "seed-state.json").write_text(
            json.dumps(seed, indent=2, sort_keys=True) + "\n")
        receipt = catalog_receipt(catalog)
        receipt["sourceFiles"] = {
            path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source / "slides").glob("*.json"))
        }
        receipt["assets"] = {
            path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(assets.rglob("*")) if path.is_file()
        } if assets.is_dir() else {}
        (staging / "data" / "build.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        # This is a local generated artifact, never an active serving root.
        # Refuse a directory carrying authoring state rather than erasing it.
        if (output / "data" / "live-state.json").exists():
            raise ValueError("refusing to rebuild over live authoring state")
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(staging), output)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))
