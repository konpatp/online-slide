"""Source discovery and deterministic fingerprints."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from .common import (ContractError, _require, _visual_objects, RECIPES)
from .sources import (validate_slide_spec)

def load_catalog(slides_dir: Path, created_slides=None) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    paths = sorted(slides_dir.glob("*.json"))
    _require(paths, f"{slides_dir}: no slide sources found")
    for path in paths:
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"{path}: invalid JSON: {exc}") from exc
        validate_slide_spec(spec, source=str(path))
        slide_id = spec["id"]
        _require(slide_id not in catalog, f"duplicate permanent slide id: {slide_id}")
        catalog[slide_id] = spec
    _require(created_slides is None or isinstance(created_slides, dict), "createdSlides must be an object")
    for slide_id, spec in (created_slides or {}).items():
        validate_slide_spec(spec, source=f"createdSlides.{slide_id}")
        _require(slide_id == spec['id'] and slide_id not in catalog,
                 f"created slide identity collides with authored source: {slide_id}")
        catalog[slide_id] = spec
    route_ids=set(catalog)
    for spec in catalog.values():
        if spec['recipe']=='slide-index':
            for section in spec['data']['sections']:
                for item in section['items']:
                    _require(item['slide'] in catalog,f"index destination disappeared: {item['slide']}")
    for slide_id,spec in catalog.items():
        routes=spec.get('routes',[])
        _require(isinstance(routes,list),f'{slide_id}: routes must be a list')
        for route in routes:
            _require(isinstance(route,dict) and set(route)=={'id','selection'},f'{slide_id}: malformed view route')
            route_id=route['id']
            _require(isinstance(route_id,str) and re.fullmatch(r'[a-z0-9][a-z0-9:-]*',route_id) and route_id not in route_ids,
                     f'{slide_id}: invalid or duplicate route {route_id}')
            _require(spec['recipe']=='chart-panels' and any(view.get('selection')==route['selection'] for view in spec['data'].get('views',[])),
                     f'{slide_id}: route selection does not resolve')
            route_ids.add(route_id)
    for slide_id, spec in catalog.items():
        after = spec.get("placement", {}).get("after")
        _require(after is None or after in catalog,
                 f"{slide_id}: placement anchor {after!r} is not published")
        _require(after != slide_id, f"{slide_id}: slide cannot follow itself")
    return catalog


def catalog_revision(catalog: dict[str, dict[str, Any]]) -> str:
    raw = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def source_revisions(catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {key: catalog_revision({key: spec}) for key, spec in catalog.items()}


def catalog_receipt(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    recipe_counts = {recipe: 0 for recipe in sorted(RECIPES)}
    component_counts = {"text": 0, "image": 0, "chart": 0}
    visual_object_counts = {
        "diagram-node": 0, "diagram-edge": 0, "vector": 0, "segment": 0,
        "accessibility-target": 0, "accessibility-reach": 0,
        "annotation-rect": 0, "annotation-line": 0,
        "recipe-frame": 0,
    }
    for spec in catalog.values():
        recipe_counts[spec["recipe"]] += 1
        for component in spec["components"].values():
            component_counts[component["kind"]] += 1
        for kind in _visual_objects(spec).values():
            visual_object_counts[kind] += 1
    return {
        "schema": "online-slide/catalog-receipt@1",
        "sourceRevision": catalog_revision(catalog),
        "slides": len(catalog),
        "slideIds": list(catalog),
        "recipes": recipe_counts,
        "components": component_counts,
        "semanticComponentIds": sum(component_counts.values()),
        "positionalComponentIds": 0,
        "visualObjects": visual_object_counts,
        "semanticVisualObjectIds": sum(visual_object_counts.values()),
        "positionalVisualObjectIds": 0,
    }
