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

TOOLKIT = Path(__file__).resolve().parent


def build(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if output == source or source.is_relative_to(output):
        raise ValueError("output must be a separate generated directory")
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
        shutil.copytree(TOOLKIT / "public", staging / "public")
        for directory in (staging / "public", *(staging / "public").rglob("*")):
            if directory.is_dir():
                directory.chmod(0o755)
        if assets.is_dir():
            shutil.copytree(assets, staging / "public" / "assets", dirs_exist_ok=True)
        shutil.copytree(source / "slides", staging / "slides")
        for name in ("server.py", "slidekit.py"):
            shutil.copy2(TOOLKIT / name, staging / name)
        (staging / "data").mkdir()
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
