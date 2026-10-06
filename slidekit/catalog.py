"""Source discovery and deterministic fingerprints."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from .common import (ContractError, _require, _visual_objects, RECIPES)
from .sources import (validate_slide_spec)

def _read_source(path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path}: invalid JSON: {exc}") from exc
    validate_slide_spec(spec, source=str(path))
    return spec


def _assemble(files: list[dict[str, Any]], created_slides) -> dict[str, dict[str, Any]]:
    """Order and identity rules for already-validated specs (files, then created)."""
    catalog: dict[str, dict[str, Any]] = {}
    for spec in files:
        slide_id = spec["id"]
        _require(slide_id not in catalog, f"duplicate permanent slide id: {slide_id}")
        catalog[slide_id] = spec
    for slide_id, spec in (created_slides or {}).items():
        _require(slide_id == spec['id'] and slide_id not in catalog,
                 f"created slide identity collides with authored source: {slide_id}")
        catalog[slide_id] = spec
    return catalog


def link_catalog(catalog: dict[str, dict[str, Any]]) -> None:
    """Rules that span slides: index destinations, view routes, placement anchors."""
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


def load_catalog(slides_dir: Path, created_slides=None) -> dict[str, dict[str, Any]]:
    paths = sorted(slides_dir.glob("*.json"))
    _require(paths, f"{slides_dir}: no slide sources found")
    _require(created_slides is None or isinstance(created_slides, dict), "createdSlides must be an object")
    for slide_id, spec in (created_slides or {}).items():
        validate_slide_spec(spec, source=f"createdSlides.{slide_id}")
    catalog = _assemble([_read_source(path) for path in paths], created_slides)
    link_catalog(catalog)
    return catalog


def catalog_revision(catalog: dict[str, dict[str, Any]]) -> str:
    raw = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def source_revisions(catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {key: catalog_revision({key: spec}) for key, spec in catalog.items()}


# Plotly's official "basic" partial bundle registers exactly these trace
# types; every other trace needs the full distribution.
BASIC_PLOTLY_TRACES = frozenset({"scatter", "bar", "pie"})


def chart_runtime(catalog: dict[str, dict[str, Any]]) -> str:
    """Smallest pinned Plotly bundle able to draw every chart in the catalog."""
    for spec in catalog.values():
        for component in spec["components"].values():
            if component["kind"] == "chart" and any(
                    trace.get("type", "scatter") not in BASIC_PLOTLY_TRACES
                    for trace in component["figure"]["data"]):
                return "plotly.min.js"
    return "plotly-basic.min.js"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SourceCatalog:
    """Validated slide sources, re-derived only where their inputs change.

    A request path must not pay for the whole deck when one slide changes:
    creating a slide used to re-read, re-validate and re-serialize all ~140
    sources (~2 s under load). Each source file is re-read only when its stat
    identity changes, each created slide is validated only when its content
    changes, and revisions are assembled from cached per-slide serializations,
    so they equal ``catalog_revision``/``source_revisions`` exactly.
    """

    def __init__(self, slides_dir: Path, created_slides=None):
        self.slides_dir = Path(slides_dir)
        self._files: dict[str, tuple[tuple, dict[str, Any]]] = {}
        self._created: dict[str, tuple[str, dict[str, Any]]] = {}
        self._serialized: dict[int, tuple[dict[str, Any], str]] = {}
        self._signature: tuple | None = None
        self.refresh(created_slides)

    def _file_specs(self) -> list[dict[str, Any]]:
        paths = sorted(self.slides_dir.glob("*.json"))
        _require(paths, f"{self.slides_dir}: no slide sources found")
        files = {}
        for path in paths:
            stat = path.stat()
            key = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            prior = self._files.get(path.name)
            files[path.name] = prior if prior and prior[0] == key else (key, _read_source(path))
        self._files = files
        return [spec for _, spec in files.values()]

    def _created_specs(self, created_slides) -> dict[str, dict[str, Any]]:
        _require(created_slides is None or isinstance(created_slides, dict), "createdSlides must be an object")
        created = {}
        for slide_id, spec in (created_slides or {}).items():
            text = _canonical(spec)
            prior = self._created.get(slide_id)
            if not prior or prior[0] != text:
                validate_slide_spec(spec, source=f"createdSlides.{slide_id}")
                prior = (text, json.loads(text))
            created[slide_id] = prior
        self._created = created
        return {slide_id: spec for slide_id, (_, spec) in created.items()}

    def _text(self, spec: dict[str, Any]) -> str:
        cached = self._serialized.get(id(spec))
        if cached is None or cached[0] is not spec:
            cached = (spec, _canonical(spec))
        return cached[1]

    def _signature_for(self, created_slides) -> tuple:
        files = []
        for path in sorted(self.slides_dir.glob("*.json")):
            stat = path.stat()
            files.append((path.name, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        return tuple(files), _canonical(created_slides)

    def refresh(self, created_slides=None) -> bool:
        """Adopt changed sources; return whether the catalog revision changed."""
        signature = self._signature_for(created_slides)
        if signature == self._signature:
            return False
        catalog = _assemble(self._file_specs(), self._created_specs(created_slides))
        link_catalog(catalog)
        texts = {key: self._text(spec) for key, spec in catalog.items()}
        self._serialized = {id(spec): (spec, texts[key]) for key, spec in catalog.items()}
        entry = {key: _canonical(key) + ":" + text for key, text in texts.items()}
        revisions = {key: hashlib.sha256(("{" + item + "}").encode()).hexdigest()
                     for key, item in entry.items()}
        revision = hashlib.sha256(("{" + ",".join(entry[key] for key in sorted(entry)) + "}").encode()).hexdigest()
        changed = self._signature is None or revision != self.revision
        self.catalog, self.revisions, self.revision = catalog, revisions, revision
        self.chart_runtime = chart_runtime(catalog)
        self._signature = signature
        return changed


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
