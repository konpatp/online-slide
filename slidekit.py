"""Contracts for independent scientific slide sources and mutable deck state.

Slide source files are immutable author contributions.  Ordering, visibility,
and human edits live in a separate revision-checked state file.  Keeping those
surfaces separate lets several contributors add slides without rewriting a
shared deck source or overwriting live human decisions.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


SLIDE_SCHEMA = "online-slide/slide@1"
STATE_SCHEMA = "online-slide/state@2"
RECIPES = {"hero-plot", "evidence-table", "mechanism-diagram", "matched-gallery"}
COMPONENT_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SLIDE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_OVERLAY_KEYS = {"text", "color", "fontScale", "src", "imageScale"}


class ContractError(ValueError):
    """Raised when source or state would make an edit ambiguous."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _component_ids(spec: dict[str, Any]) -> set[str]:
    return set(spec["components"])


def validate_slide_spec(spec: Any, *, source: str = "<memory>") -> dict[str, Any]:
    _require(isinstance(spec, dict), f"{source}: slide must be an object")
    _require(spec.get("schema") == SLIDE_SCHEMA, f"{source}: unsupported slide schema")
    slide_id = spec.get("id")
    _require(isinstance(slide_id, str) and SLIDE_ID.fullmatch(slide_id) is not None,
             f"{source}: invalid permanent slide id")
    _require(spec.get("recipe") in RECIPES, f"{source}: unknown recipe")
    _require(isinstance(spec.get("createdAt"), str) and spec["createdAt"],
             f"{source}: createdAt is required for deterministic insertion")

    placement = spec.get("placement", {})
    _require(isinstance(placement, dict), f"{source}: placement must be an object")
    after = placement.get("after")
    _require(after is None or (isinstance(after, str) and SLIDE_ID.fullmatch(after)),
             f"{source}: placement.after must be a slide id or null")

    theme = spec.get("theme", {})
    _require(isinstance(theme, dict), f"{source}: theme must be an object")
    accent = theme.get("accent", "#2f6fed")
    _require(isinstance(accent, str) and HEX_COLOR.fullmatch(accent) is not None,
             f"{source}: theme accent must be #RRGGBB")

    components = spec.get("components")
    _require(isinstance(components, dict) and components,
             f"{source}: components must be a non-empty object")
    for component_id, component in components.items():
        _require(COMPONENT_ID.fullmatch(component_id) is not None,
                 f"{source}: invalid component id {component_id!r}")
        _require(isinstance(component, dict),
                 f"{source}: component {component_id!r} must be an object")
        kind = component.get("kind")
        _require(kind in {"text", "image"},
                 f"{source}: component {component_id!r} has invalid kind")
        if kind == "text":
            _require(isinstance(component.get("text"), str),
                     f"{source}: text component {component_id!r} needs text")
        else:
            _require(isinstance(component.get("src"), str) and component["src"],
                     f"{source}: image component {component_id!r} needs src")
            _require(isinstance(component.get("alt"), str) and component["alt"],
                     f"{source}: image component {component_id!r} needs alt text")

    referenced: list[str] = []

    def ref(value: Any, label: str) -> None:
        _require(isinstance(value, str), f"{source}: {label} must name a component")
        referenced.append(value)

    ref(spec.get("headline"), "headline")
    if spec.get("eyebrow") is not None:
        ref(spec["eyebrow"], "eyebrow")
    if spec.get("footer") is not None:
        ref(spec["footer"], "footer")

    data = spec.get("data")
    _require(isinstance(data, dict), f"{source}: data must be an object")
    recipe = spec["recipe"]
    if recipe == "hero-plot":
        for axis in ("xAxis", "yAxis"):
            axis_spec = data.get(axis)
            _require(isinstance(axis_spec, dict), f"{source}: {axis} is required")
            ref(axis_spec.get("label"), f"{axis}.label")
            domain = axis_spec.get("domain")
            _require(isinstance(domain, list) and len(domain) == 2 and
                     all(isinstance(v, (int, float)) for v in domain) and domain[0] < domain[1],
                     f"{source}: {axis}.domain must be two increasing numbers")
        series = data.get("series")
        _require(isinstance(series, list) and series, f"{source}: plot needs series")
        for index, item in enumerate(series):
            _require(isinstance(item, dict), f"{source}: series {index} must be an object")
            ref(item.get("label"), f"series[{index}].label")
            _require(HEX_COLOR.fullmatch(str(item.get("color", ""))) is not None,
                     f"{source}: series {index} needs a hex color")
            points = item.get("points")
            _require(isinstance(points, list) and len(points) >= 2,
                     f"{source}: series {index} needs at least two points")
            _require(all(isinstance(point, list) and len(point) == 2 and
                         all(isinstance(v, (int, float)) for v in point) for point in points),
                     f"{source}: series {index} points must be [x,y]")
    elif recipe == "evidence-table":
        columns = data.get("columns")
        rows = data.get("rows")
        _require(isinstance(columns, list) and columns, f"{source}: table needs columns")
        _require(isinstance(rows, list) and rows, f"{source}: table needs rows")
        for index, component_id in enumerate(columns):
            ref(component_id, f"columns[{index}]")
        for row_index, row in enumerate(rows):
            _require(isinstance(row, dict), f"{source}: row {row_index} must be an object")
            ref(row.get("label"), f"rows[{row_index}].label")
            cells = row.get("cells")
            _require(isinstance(cells, list) and len(cells) == len(columns) - 1,
                     f"{source}: row {row_index} cell count must match numeric columns")
            for cell_index, component_id in enumerate(cells):
                ref(component_id, f"rows[{row_index}].cells[{cell_index}]")
            best = row.get("best")
            _require(isinstance(best, int) and 0 <= best < len(cells),
                     f"{source}: row {row_index} needs a valid best index")
    elif recipe == "mechanism-diagram":
        nodes = data.get("nodes")
        edges = data.get("edges")
        _require(isinstance(nodes, list) and len(nodes) >= 2,
                 f"{source}: diagram needs at least two nodes")
        _require(isinstance(edges, list) and edges, f"{source}: diagram needs edges")
        node_ids: set[str] = set()
        node_roles: set[str] = set()
        valid_roles = {"origin", "raw", "base", "tangent", "result"}
        for index, node in enumerate(nodes):
            _require(isinstance(node, dict), f"{source}: node {index} must be an object")
            node_id = node.get("id")
            _require(isinstance(node_id, str) and COMPONENT_ID.fullmatch(node_id),
                     f"{source}: node {index} needs a semantic id")
            _require(node_id not in node_ids, f"{source}: duplicate node id {node_id}")
            node_ids.add(node_id)
            role = node.get("role")
            _require(role in valid_roles, f"{source}: node {node_id} needs a supported semantic role")
            _require(role not in node_roles, f"{source}: duplicate diagram role {role}")
            node_roles.add(role)
            ref(node.get("label"), f"nodes[{index}].label")
        _require(node_roles == valid_roles,
                 f"{source}: mechanism diagram requires origin/raw/base/tangent/result roles")
        for index, edge in enumerate(edges):
            _require(isinstance(edge, dict), f"{source}: edge {index} must be an object")
            _require(edge.get("from") in node_ids and edge.get("to") in node_ids,
                     f"{source}: edge {index} must reference nodes")
            if edge.get("label") is not None:
                ref(edge["label"], f"edges[{index}].label")
    else:
        columns = data.get("columns")
        rows = data.get("rows")
        _require(isinstance(columns, list) and columns, f"{source}: gallery needs columns")
        _require(isinstance(rows, list) and rows, f"{source}: gallery needs rows")
        for index, component_id in enumerate(columns):
            ref(component_id, f"columns[{index}]")
        for row_index, row in enumerate(rows):
            ref(row.get("label"), f"rows[{row_index}].label")
            images = row.get("images")
            _require(isinstance(images, list) and len(images) == len(columns),
                     f"{source}: gallery row {row_index} must fill every column")
            for cell_index, component_id in enumerate(images):
                ref(component_id, f"rows[{row_index}].images[{cell_index}]")

    known = _component_ids(spec)
    unknown = sorted(set(referenced) - known)
    _require(not unknown, f"{source}: unknown component references: {', '.join(unknown)}")
    _require(spec["components"][spec["headline"]]["kind"] == "text",
             f"{source}: headline must reference text")
    return spec


def load_catalog(slides_dir: Path) -> dict[str, dict[str, Any]]:
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
    for slide_id, spec in catalog.items():
        after = spec.get("placement", {}).get("after")
        _require(after is None or after in catalog,
                 f"{slide_id}: placement anchor {after!r} is not published")
        _require(after != slide_id, f"{slide_id}: slide cannot follow itself")
    return catalog


def catalog_revision(catalog: dict[str, dict[str, Any]]) -> str:
    raw = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def empty_state() -> dict[str, Any]:
    return {"schema": STATE_SCHEMA, "revision": 0, "order": [], "hidden": [], "overlays": {}}


def _insert_new_slide(order: list[str], slide_id: str, catalog: dict[str, dict[str, Any]]) -> None:
    after = catalog[slide_id].get("placement", {}).get("after")
    if after is None or after not in order:
        order.append(slide_id)
        return
    insert_at = order.index(after) + 1
    while insert_at < len(order):
        neighbor = order[insert_at]
        neighbor_after = catalog.get(neighbor, {}).get("placement", {}).get("after")
        if neighbor_after != after:
            break
        insert_at += 1
    order.insert(insert_at, slide_id)


def reconcile_state(state: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    """Add new independent sources without disturbing human ordering.

    Source removal fails closed because silently dropping a slide could discard
    accepted order, visibility, or component overlays.
    """

    _require(isinstance(state, dict) and state.get("schema") == STATE_SCHEMA,
             "state has an unsupported schema")
    order = list(state.get("order", []))
    existing = set(order)
    source_ids = set(catalog)
    removed = sorted(existing - source_ids)
    _require(not removed, "published slide source disappeared: " + ", ".join(removed))
    _require(len(order) == len(existing), "state order contains duplicate ids")
    changed = False
    pending = set(source_ids - existing)
    while pending:
        ready = [slide_id for slide_id in pending
                 if catalog[slide_id].get("placement", {}).get("after") is None or
                 catalog[slide_id].get("placement", {}).get("after") in order]
        _require(ready, "placement graph contains a cycle")
        for slide_id in sorted(ready, key=lambda item: (catalog[item]["createdAt"], item)):
            _insert_new_slide(order, slide_id, catalog)
            pending.remove(slide_id)
            changed = True

    hidden = list(state.get("hidden", []))
    _require(set(hidden) <= source_ids, "hidden state contains an unknown slide")
    overlays = state.get("overlays", {})
    _require(isinstance(overlays, dict), "overlays must be an object")
    validate_overlays(overlays, catalog)
    reconciled = {
        "schema": STATE_SCHEMA,
        "revision": int(state.get("revision", 0)) + (1 if changed else 0),
        "order": order,
        "hidden": [slide_id for slide_id in order if slide_id in set(hidden)],
        "overlays": overlays,
    }
    return reconciled, changed


def validate_overlays(overlays: Any, catalog: dict[str, dict[str, Any]]) -> None:
    _require(isinstance(overlays, dict), "overlays must be an object")
    for slide_id, slide_overlays in overlays.items():
        _require(slide_id in catalog, f"overlay targets unknown slide {slide_id}")
        _require(isinstance(slide_overlays, dict), f"overlay for {slide_id} must be an object")
        known_components = _component_ids(catalog[slide_id])
        for component_id, overlay in slide_overlays.items():
            _require(component_id in known_components,
                     f"overlay target disappeared: {slide_id}@{component_id}")
            _require(isinstance(overlay, dict), "component overlay must be an object")
            _require(set(overlay) <= ALLOWED_OVERLAY_KEYS,
                     f"unsupported overlay fields on {slide_id}@{component_id}")
            component = catalog[slide_id]["components"][component_id]
            if "text" in overlay:
                _require(component["kind"] == "text", "text overlay must target text")
                _require(isinstance(overlay["text"], str) and len(overlay["text"]) <= 800,
                         "text overlay is invalid")
            if "src" in overlay:
                _require(component["kind"] == "image", "src overlay must target image")
                _require(isinstance(overlay["src"], str) and
                         (overlay["src"].startswith("uploads/") or overlay["src"].startswith("assets/")),
                         "image overlay must reference a published asset")
            if "color" in overlay:
                _require(isinstance(overlay["color"], str) and HEX_COLOR.fullmatch(overlay["color"]),
                         "overlay color must be #RRGGBB")
            if "fontScale" in overlay:
                _require(isinstance(overlay["fontScale"], (int, float)) and
                         0.7 <= overlay["fontScale"] <= 1.5,
                         "fontScale must be between 0.7 and 1.5")
            if "imageScale" in overlay:
                _require(component["kind"] == "image" and
                         isinstance(overlay["imageScale"], (int, float)) and
                         0.65 <= overlay["imageScale"] <= 1.35,
                         "imageScale must be between 0.65 and 1.35")


def validate_state_snapshot(candidate: Any, current: dict[str, Any],
                            catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _require(isinstance(candidate, dict), "snapshot must be an object")
    _require(candidate.get("schema") == STATE_SCHEMA, "unsupported state schema")
    order = candidate.get("order")
    hidden = candidate.get("hidden")
    overlays = candidate.get("overlays")
    known = set(catalog)
    _require(isinstance(order, list) and len(order) == len(known) and set(order) == known,
             "order must contain every published slide exactly once")
    _require(all(isinstance(item, str) for item in order), "slide ids must be strings")
    _require(isinstance(hidden, list) and set(hidden) <= known,
             "hidden must contain only published slide ids")
    validate_overlays(overlays, catalog)
    return {
        "schema": STATE_SCHEMA,
        "revision": int(current["revision"]) + 1,
        "order": list(order),
        "hidden": [slide_id for slide_id in order if slide_id in set(hidden)],
        "overlays": overlays,
    }


def catalog_receipt(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    recipe_counts = {recipe: 0 for recipe in sorted(RECIPES)}
    component_counts = {"text": 0, "image": 0}
    for spec in catalog.values():
        recipe_counts[spec["recipe"]] += 1
        for component in spec["components"].values():
            component_counts[component["kind"]] += 1
    return {
        "schema": "online-slide/catalog-receipt@1",
        "sourceRevision": catalog_revision(catalog),
        "slides": len(catalog),
        "slideIds": list(catalog),
        "recipes": recipe_counts,
        "components": component_counts,
        "semanticComponentIds": sum(component_counts.values()),
        "positionalComponentIds": 0,
    }
