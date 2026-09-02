#!/usr/bin/env python3
"""Fast source gate for independent ScientificSlideKit contributions."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from slidekit import ContractError, catalog_receipt, load_catalog  # noqa: E402


def validate(root: Path) -> dict:
    started = time.perf_counter()
    catalog = load_catalog(root / "slides")
    findings = []
    for slide_id, spec in catalog.items():
        if spec["recipe"] == "matched-gallery":
            for component_id, component in spec["components"].items():
                if component["kind"] != "image":
                    continue
                path = root / "public" / component["src"]
                if not path.is_file():
                    findings.append(f"{slide_id}@{component_id}: missing asset {component['src']}")
        for required in ("headline", "footer"):
            if not spec.get(required):
                findings.append(f"{slide_id}: {required} is required by the pilot")
    css = (root / "public" / "styles.css").read_text(encoding="utf-8")
    if ".gallery-cell img" not in css or "object-fit: contain" not in css:
        findings.append("gallery renderer must enforce object-fit: contain")
    receipt = catalog_receipt(catalog)
    receipt.update({
        "elapsedMs": round((time.perf_counter() - started) * 1000, 2),
        "findings": findings,
        "ok": not findings,
    })
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        receipt = validate(args.root.resolve())
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        receipt = {"schema": "online-slide/catalog-receipt@1", "ok": False, "findings": [str(exc)]}
    text = json.dumps(receipt, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
