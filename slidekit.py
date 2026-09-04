"""Contracts for independent scientific slide sources and mutable deck state.

Slide source files are immutable author contributions. Ordering, visibility,
human overlays, and semantic table structure live in a separate revision-checked state file. Keeping those
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
STATE_SCHEMA = "online-slide/state@4"
LEGACY_STATE_SCHEMAS = {"online-slide/state@2", "online-slide/state@3"}
RECIPES = {
    "hero-plot", "evidence-table", "mechanism-pipeline",
    "vector-geometry", "hierarchical-gallery", "target-accessibility",
}
COMPONENT_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SLIDE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_OVERLAY_KEYS = {
    "text", "color", "fontScale", "src", "imageScale", "region",
}


def _validate_text_region(value: Any, message: str) -> None:
    """Validate a region in canonical 1920x1080 slide coordinates.

    ``x`` and ``y`` are displacements from the recipe-authored anchor.  Width
    and height are explicit content bounds.  Keeping the durable values in
    slide coordinates makes an edit invariant to editor zoom and fullscreen.
    """

    _require(isinstance(value, dict) and set(value) == {"x", "y", "width", "height"},
             message)
    _require(all(isinstance(value[key], (int, float)) and not isinstance(value[key], bool)
                 for key in ("x", "y", "width", "height")), message)
    _require(-1920 <= value["x"] <= 1920 and -1080 <= value["y"] <= 1080,
             message)
    _require(24 <= value["width"] <= 1920 and 18 <= value["height"] <= 1080,
             message)


class ContractError(ValueError):
    """Raised when source or state would make an edit ambiguous."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _component_ids(spec: dict[str, Any]) -> set[str]:
    return set(spec["components"])


def _visual_objects(spec: dict[str, Any]) -> dict[str, str]:
    """Return source-authored editable geometry identities for one slide."""

    data = spec["data"]
    if spec["recipe"] == "mechanism-pipeline":
        return {
            **{item["id"]: "diagram-node" for item in data.get("nodes", [])},
            **{item["id"]: "diagram-edge" for item in data.get("edges", [])},
        }
    if spec["recipe"] == "vector-geometry":
        return {
            **{item["id"]: "vector" for item in data.get("vectors", []) if item.get("editable") is True},
            **{item["id"]: "segment" for item in data.get("segments", []) if item.get("editable") is True},
        }
    if spec["recipe"] == "target-accessibility":
        return {
            object_id: kind
            for panel in data.get("panels", [])
            for object_id, kind in (
                (f"{panel['id']}-target", "accessibility-target"),
                (f"{panel['id']}-b4-reach", "accessibility-reach"),
                (f"{panel['id']}-r3-reach", "accessibility-reach"),
            )
        }
    return {}


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
            render = component.get("render", "plain")
            _require(render in {"plain", "latex"},
                     f"{source}: text component {component_id!r} has invalid renderer")
            if component.get("role") in {"math", "formula", "equation"}:
                _require(render == "latex",
                         f"{source}: mathematical component {component_id!r} must use LaTeX")
            if "region" in component:
                _validate_text_region(
                    component["region"],
                    f"{source}: text component {component_id!r} has an invalid region",
                )
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
    elif recipe == "mechanism-pipeline":
        nodes = data.get("nodes")
        edges = data.get("edges")
        _require(isinstance(nodes, list) and len(nodes) >= 2,
                 f"{source}: diagram needs at least two nodes")
        _require(isinstance(edges, list) and edges, f"{source}: diagram needs edges")
        node_ids: set[str] = set()
        lane_layout = data.get("layout", "directed")
        _require(lane_layout in {"directed", "lanes"},
                 f"{source}: diagram layout must be directed or lanes")
        for index, node in enumerate(nodes):
            _require(isinstance(node, dict), f"{source}: node {index} must be an object")
            node_id = node.get("id")
            _require(isinstance(node_id, str) and COMPONENT_ID.fullmatch(node_id),
                     f"{source}: node {index} needs a semantic id")
            _require(node_id not in node_ids, f"{source}: duplicate node id {node_id}")
            node_ids.add(node_id)
            ref(node.get("label"), f"nodes[{index}].label")
            if node.get("detail") is not None:
                ref(node["detail"], f"nodes[{index}].detail")
            sizing = node.get("sizing", "content")
            _require(sizing in {"content", "fixed"},
                     f"{source}: node {index} sizing must be content or fixed")
            if sizing == "fixed":
                _require(all(isinstance(node.get(key), (int, float)) and node[key] > 0
                             for key in ("width", "height")),
                         f"{source}: fixed node {index} needs positive width and height")
            else:
                _require("width" not in node and "height" not in node,
                         f"{source}: node {index} dimensions require sizing=fixed; content sizing is the default")
            if lane_layout == "lanes":
                _require(all(isinstance(node.get(key), (int, float)) and not isinstance(node.get(key), bool)
                             for key in ("lane", "step")),
                         f"{source}: lane layout node {index} needs numeric lane and step")
        edge_ids: set[str] = set()
        for index, edge in enumerate(edges):
            _require(isinstance(edge, dict), f"{source}: edge {index} must be an object")
            edge_id = edge.get("id")
            _require(isinstance(edge_id, str) and COMPONENT_ID.fullmatch(edge_id),
                     f"{source}: edge {index} needs a semantic id")
            _require(edge_id not in edge_ids, f"{source}: duplicate edge id {edge_id}")
            _require(edge_id not in node_ids, f"{source}: visual object id is reused {edge_id}")
            edge_ids.add(edge_id)
            _require(edge.get("from") in node_ids and edge.get("to") in node_ids,
                     f"{source}: edge {index} must reference nodes")
            if edge.get("label") is not None:
                ref(edge["label"], f"edges[{index}].label")
    elif recipe == "vector-geometry":
        bounds = data.get("bounds")
        _require(isinstance(bounds, list) and len(bounds) == 4 and
                 all(isinstance(value, (int, float)) for value in bounds) and
                 bounds[0] < bounds[2] and bounds[3] < bounds[1],
                 f"{source}: vector geometry needs [left, top, right, bottom] bounds")
        vectors = data.get("vectors")
        _require(isinstance(vectors, list) and vectors,
                 f"{source}: vector geometry needs vectors")
        object_ids: set[str] = set()
        for collection_name in ("vectors", "segments"):
            for index, item in enumerate(data.get(collection_name, [])):
                _require(isinstance(item, dict),
                         f"{source}: {collection_name}[{index}] must be an object")
                object_id = item.get("id")
                _require(isinstance(object_id, str) and COMPONENT_ID.fullmatch(object_id),
                         f"{source}: {collection_name}[{index}] needs a semantic id")
                _require(object_id not in object_ids,
                         f"{source}: duplicate visual object id {object_id}")
                object_ids.add(object_id)
                _require(item.get("editable", False) in {True, False},
                         f"{source}: {collection_name}[{index}].editable must be boolean")
                for endpoint in ("from", "to"):
                    point = item.get(endpoint)
                    _require(isinstance(point, list) and len(point) == 2 and
                             all(isinstance(value, (int, float)) for value in point),
                             f"{source}: {collection_name}[{index}].{endpoint} must be [x,y]")
                _require(HEX_COLOR.fullmatch(str(item.get("color", ""))) is not None,
                         f"{source}: {collection_name}[{index}] needs a hex color")
        for index, arc in enumerate(data.get("arcs", [])):
            _require(isinstance(arc, dict) and
                     isinstance(arc.get("center"), list) and len(arc["center"]) == 2 and
                     isinstance(arc.get("radius"), (int, float)) and arc["radius"] > 0 and
                     isinstance(arc.get("startDeg"), (int, float)) and
                     isinstance(arc.get("endDeg"), (int, float)),
                     f"{source}: arcs[{index}] is invalid")
        for index, label in enumerate(data.get("labels", [])):
            box = label.get("box") if isinstance(label, dict) else None
            _require(isinstance(box, dict) and
                     all(isinstance(box.get(key), (int, float)) for key in ("x", "y", "width", "height")) and
                     0 <= box["x"] < 100 and 0 <= box["y"] < 100 and
                     box["width"] > 0 and box["height"] > 0 and
                     box["x"] + box["width"] <= 100 and box["y"] + box["height"] <= 100,
                     f"{source}: labels[{index}] needs a bounded percentage box")
            _require(box.get("align", "center") in {"flex-start", "center", "flex-end"} and
                     box.get("valign", "center") in {"flex-start", "center", "flex-end"},
                     f"{source}: labels[{index}] has invalid box alignment")
            ref(label.get("component"), f"labels[{index}].component")
        equations = data.get("equations", [])
        _require(isinstance(equations, list), f"{source}: equations must be a list")
        for index, component_id in enumerate(equations):
            ref(component_id, f"equations[{index}]")
            component = components.get(component_id, {})
            _require(component.get("kind") == "text" and component.get("render") == "latex",
                     f"{source}: equations[{index}] must reference a LaTeX text component")
    elif recipe == "target-accessibility":
        panels = data.get("panels")
        _require(isinstance(panels, list) and len(panels) == 2,
                 f"{source}: target accessibility needs exactly two panels")
        panel_ids: set[str] = set()
        for index, panel in enumerate(panels):
            _require(isinstance(panel, dict), f"{source}: panels[{index}] must be an object")
            panel_id = panel.get("id")
            _require(isinstance(panel_id, str) and COMPONENT_ID.fullmatch(panel_id),
                     f"{source}: panels[{index}] needs a semantic id")
            _require(panel_id not in panel_ids, f"{source}: duplicate panel id {panel_id}")
            panel_ids.add(panel_id)
            for key in ("title", "summary", "target", "b4Fit", "r3Fit"):
                ref(panel.get(key), f"panels[{index}].{key}")
            shares = panel.get("shares")
            _require(isinstance(shares, list) and len(shares) == 3 and
                     all(isinstance(value, (int, float)) and value > 0 for value in shares),
                     f"{source}: panels[{index}].shares needs three positive qualitative weights")
        legend = data.get("legend")
        _require(isinstance(legend, list) and len(legend) == 3,
                 f"{source}: target accessibility needs three legend labels")
        for index, component_id in enumerate(legend):
            ref(component_id, f"legend[{index}]")
        equation = data.get("equation")
        ref(equation, "equation")
        component = components.get(equation, {})
        _require(component.get("kind") == "text" and component.get("render") == "latex",
                 f"{source}: target accessibility equation must use LaTeX")
    else:
        columns = data.get("columns")
        selectors = data.get("selectors")
        views = data.get("views")
        page_sets = data.get("pageSets")
        _require(isinstance(columns, list) and columns, f"{source}: gallery needs columns")
        _require(isinstance(selectors, list) and selectors, f"{source}: gallery needs selectors")
        _require(isinstance(views, list) and views, f"{source}: gallery needs views")
        _require(isinstance(page_sets, dict) and page_sets, f"{source}: gallery needs pageSets")
        for index, component_id in enumerate(columns):
            ref(component_id, f"columns[{index}]")
        selector_ids: set[str] = set()
        selector_values: dict[str, set[str]] = {}
        for selector_index, selector in enumerate(selectors):
            selector_id = selector.get("id")
            _require(isinstance(selector_id, str) and COMPONENT_ID.fullmatch(selector_id),
                     f"{source}: selector {selector_index} needs a semantic id")
            _require(selector_id not in selector_ids, f"{source}: duplicate selector {selector_id}")
            selector_ids.add(selector_id)
            ref(selector.get("label"), f"selectors[{selector_index}].label")
            options = selector.get("options")
            _require(isinstance(options, list) and len(options) >= 2,
                     f"{source}: selector {selector_id} needs options")
            values: set[str] = set()
            for option_index, option in enumerate(options):
                value = option.get("value")
                _require(isinstance(value, str) and COMPONENT_ID.fullmatch(value),
                         f"{source}: selector {selector_id} option {option_index} needs a value")
                _require(value not in values, f"{source}: duplicate option {selector_id}={value}")
                values.add(value)
                ref(option.get("label"), f"selectors[{selector_index}].options[{option_index}].label")
            selector_values[selector_id] = values
        for page_set_id, pages in page_sets.items():
            _require(COMPONENT_ID.fullmatch(page_set_id) is not None,
                     f"{source}: invalid page set id {page_set_id!r}")
            _require(isinstance(pages, list) and pages,
                     f"{source}: page set {page_set_id} needs pages")
            for page_index, page in enumerate(pages):
                ref(page.get("label"), f"pageSets.{page_set_id}[{page_index}].label")
                rows = page.get("rows")
                _require(isinstance(rows, list) and rows,
                         f"{source}: gallery page {page_set_id}[{page_index}] needs rows")
                for row_index, row in enumerate(rows):
                    ref(row.get("label"),
                        f"pageSets.{page_set_id}[{page_index}].rows[{row_index}].label")
                    images = row.get("images")
                    _require(isinstance(images, list) and 0 < len(images) <= len(columns),
                             f"{source}: gallery row {row_index} must fit the declared columns")
                    _require(len(images) == len(columns) or row_index == len(rows) - 1,
                             f"{source}: only the final gallery row may be partial")
                    for cell_index, component_id in enumerate(images):
                        ref(component_id,
                            f"pageSets.{page_set_id}[{page_index}].rows[{row_index}].images[{cell_index}]")
                        image_component = components.get(component_id, {})
                        caption = image_component.get("caption")
                        if caption is not None:
                            ref(caption,
                                f"components.{component_id}.caption")
        seen_selections: set[tuple[tuple[str, str], ...]] = set()
        for view_index, view in enumerate(views):
            selection = view.get("selection")
            _require(isinstance(selection, dict) and set(selection) == selector_ids,
                     f"{source}: view {view_index} must select every gallery facet")
            for selector_id, value in selection.items():
                _require(value in selector_values[selector_id],
                         f"{source}: view {view_index} has unknown {selector_id}={value}")
            key = tuple(sorted(selection.items()))
            _require(key not in seen_selections, f"{source}: duplicate gallery selection {dict(key)}")
            seen_selections.add(key)
            ref(view.get("metric"), f"views[{view_index}].metric")
            ref(view.get("classLabel"), f"views[{view_index}].classLabel")
            _require(view.get("pageSet") in page_sets,
                     f"{source}: view {view_index} references an unknown pageSet")

    known = _component_ids(spec)
    unknown = sorted(set(referenced) - known)
    _require(not unknown, f"{source}: unknown component references: {', '.join(unknown)}")
    _require(spec["components"][spec["headline"]]["kind"] == "text",
             f"{source}: headline must reference text")
    for component_id, component in components.items():
        caption = component.get("caption")
        if caption is not None:
            _require(component["kind"] == "image",
                     f"{source}: only images may reference captions")
            _require(components[caption]["kind"] == "text",
                     f"{source}: image caption {caption!r} must reference text")
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
    return {
        "schema": STATE_SCHEMA,
        "revision": 0,
        "order": [],
        "hidden": [],
        "overlays": {},
        "tables": {},
        "objects": {},
    }


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


def validate_tables(tables: Any, catalog: dict[str, dict[str, Any]]) -> None:
    """Validate human-authored table structure by semantic identity.

    A table override is a complete logical table, not a set of DOM positions.
    Rows, columns, and cells keep stable ids when their visual order changes.
    Components introduced by a curator live with that logical table so no
    positional selector or hidden source rewrite is needed.
    """

    _require(isinstance(tables, dict), "tables must be an object")
    for slide_id, table in tables.items():
        _require(slide_id in catalog, f"table targets unknown slide {slide_id}")
        slide = catalog[slide_id]
        _require(slide["recipe"] == "evidence-table",
                 f"table structure may only target an evidence-table: {slide_id}")
        _require(isinstance(table, dict) and set(table) == {"columns", "rows", "components"},
                 f"table override for {slide_id} has an invalid shape")
        inserted = table["components"]
        _require(isinstance(inserted, dict), f"table components for {slide_id} must be an object")
        source_ids = _component_ids(slide)
        for component_id, component in inserted.items():
            _require(COMPONENT_ID.fullmatch(component_id) is not None,
                     f"table component has invalid id: {slide_id}@{component_id}")
            _require(component_id not in source_ids,
                     f"table component collides with source: {slide_id}@{component_id}")
            _require(isinstance(component, dict) and component.get("kind") == "text" and
                     isinstance(component.get("text"), str) and len(component["text"]) <= 800,
                     f"inserted table component must be text: {slide_id}@{component_id}")
            _require(set(component) <= {
                "kind", "text", "role", "render", "display", "color", "fontScale", "region",
            }, f"unsupported inserted table component fields: {slide_id}@{component_id}")
            _require(isinstance(component.get("role", "table-value"), str),
                     f"inserted table component role is invalid: {slide_id}@{component_id}")
            _require(component.get("render", "plain") in {"plain", "latex"},
                     f"inserted table component renderer is invalid: {slide_id}@{component_id}")
            _require(component.get("display", "inline") in {"inline", "block"},
                     f"inserted table component display is invalid: {slide_id}@{component_id}")
            if "color" in component:
                _require(isinstance(component["color"], str) and HEX_COLOR.fullmatch(component["color"]),
                         f"inserted table component color is invalid: {slide_id}@{component_id}")
            if "fontScale" in component:
                _require(isinstance(component["fontScale"], (int, float)) and
                         0.7 <= component["fontScale"] <= 1.5,
                         f"inserted table component fontScale is invalid: {slide_id}@{component_id}")
            if "region" in component:
                _validate_text_region(
                    component["region"],
                    f"inserted table component region is invalid: {slide_id}@{component_id}",
                )
        known_components = source_ids | set(inserted)
        referenced_inserted: set[str] = set()
        columns = table["columns"]
        rows = table["rows"]
        _require(isinstance(columns, list) and len(columns) >= 2,
                 f"table override for {slide_id} needs at least two columns")
        _require(isinstance(rows, list) and rows,
                 f"table override for {slide_id} needs at least one row")
        column_ids: list[str] = []
        for index, column in enumerate(columns):
            _require(isinstance(column, dict) and set(column) == {"id", "label", "width"},
                     f"table column {slide_id}[{index}] has an invalid shape")
            column_id = column.get("id")
            label = column.get("label")
            _require(isinstance(column_id, str) and COMPONENT_ID.fullmatch(column_id),
                     f"table column {slide_id}[{index}] needs a semantic id")
            _require(column_id not in column_ids,
                     f"duplicate table column id: {slide_id}@{column_id}")
            column_ids.append(column_id)
            _require(label in known_components,
                     f"table column label disappeared: {slide_id}@{label}")
            if label in inserted:
                referenced_inserted.add(label)
            _require(isinstance(column["width"], (int, float)) and
                     0.35 <= column["width"] <= 4,
                     f"table column width is invalid: {slide_id}@{column_id}")
        row_ids: set[str] = set()
        used_cells: set[str] = set()
        for index, row in enumerate(rows):
            _require(isinstance(row, dict) and set(row) == {
                "id", "label", "cells", "best", "globalBest",
            }, f"table row {slide_id}[{index}] has an invalid shape")
            row_id = row.get("id")
            _require(isinstance(row_id, str) and COMPONENT_ID.fullmatch(row_id),
                     f"table row {slide_id}[{index}] needs a semantic id")
            _require(row_id not in row_ids, f"duplicate table row id: {slide_id}@{row_id}")
            row_ids.add(row_id)
            _require(row.get("label") in known_components,
                     f"table row label disappeared: {slide_id}@{row.get('label')}")
            if row.get("label") in inserted:
                referenced_inserted.add(row["label"])
            cells = row.get("cells")
            _require(isinstance(cells, list) and len(cells) == len(columns) - 1,
                     f"table row {slide_id}@{row_id} does not match its columns")
            for component_id in cells:
                _require(component_id in known_components,
                         f"table cell disappeared: {slide_id}@{component_id}")
                _require(component_id not in used_cells,
                         f"table cell is reused: {slide_id}@{component_id}")
                used_cells.add(component_id)
                if component_id in inserted:
                    referenced_inserted.add(component_id)
            for key in ("best", "globalBest"):
                value = row.get(key)
                _require(value is None or value in cells,
                         f"table row {slide_id}@{row_id} has an invalid {key} target")
        retired = sorted(set(inserted) - referenced_inserted)
        _require(not retired,
                 f"table-owned components are unreferenced: {slide_id}@{', '.join(retired)}")


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < 1_000_000


def _validate_point(value: Any, message: str) -> None:
    _require(isinstance(value, list) and len(value) == 2 and all(_finite_number(item) for item in value),
             message)


def validate_objects(objects: Any, catalog: dict[str, dict[str, Any]]) -> None:
    """Validate geometry overlays against source-authored semantic object ids.

    Diagram positions use normalized recipe-plane coordinates. Vector and
    segment endpoints stay in the source coordinate plane. A missing or
    type-changed object fails closed, so an accepted edit cannot silently move
    to a sibling after a source insertion or reorder.
    """

    _require(isinstance(objects, dict), "objects must be an object")
    for slide_id, slide_objects in objects.items():
        _require(slide_id in catalog, f"visual object targets unknown slide {slide_id}")
        _require(isinstance(slide_objects, dict), f"visual objects for {slide_id} must be an object")
        known = _visual_objects(catalog[slide_id])
        for object_id, geometry in slide_objects.items():
            _require(object_id in known,
                     f"visual object target disappeared: {slide_id}@{object_id}")
            _require(isinstance(geometry, dict),
                     f"visual object geometry must be an object: {slide_id}@{object_id}")
            kind = known[object_id]
            _require(geometry.get("kind") == kind,
                     f"visual object kind changed: {slide_id}@{object_id}")
            if kind in {"diagram-node", "accessibility-target"}:
                _require(set(geometry) == {"kind", "x", "y", "width", "height"},
                         f"{kind} geometry is invalid: {slide_id}@{object_id}")
                _require(all(_finite_number(geometry[key]) for key in ("x", "y", "width", "height")),
                         f"{kind} geometry is invalid: {slide_id}@{object_id}")
                min_width, min_height = ((.03, .03) if kind == "diagram-node" else (.02, .005))
                _require(0 <= geometry["x"] <= 1 and 0 <= geometry["y"] <= 1 and
                         min_width <= geometry["width"] <= 1 and
                         min_height <= geometry["height"] <= 1 and
                         geometry["x"] + geometry["width"] <= 1.001 and
                         geometry["y"] + geometry["height"] <= 1.001,
                         f"{kind} geometry is outside its bounded plane: {slide_id}@{object_id}")
            elif kind == "diagram-edge":
                _require(set(geometry) == {"kind", "vertices"} and
                         isinstance(geometry["vertices"], list) and len(geometry["vertices"]) <= 16,
                         f"diagram edge geometry is invalid: {slide_id}@{object_id}")
                for point in geometry["vertices"]:
                    _validate_point(point, f"diagram edge vertex is invalid: {slide_id}@{object_id}")
                    _require(all(0 <= coordinate <= 1 for coordinate in point),
                             f"diagram edge vertex leaves its bounded plane: {slide_id}@{object_id}")
            elif kind in {"vector", "segment"}:
                _require(set(geometry) == {"kind", "from", "to"},
                         f"{kind} geometry is invalid: {slide_id}@{object_id}")
                _validate_point(geometry["from"], f"{kind} start is invalid: {slide_id}@{object_id}")
                _validate_point(geometry["to"], f"{kind} end is invalid: {slide_id}@{object_id}")
                left, top, right, bottom = catalog[slide_id]["data"]["bounds"]
                for point in (geometry["from"], geometry["to"]):
                    _require(left <= point[0] <= right and bottom <= point[1] <= top,
                             f"{kind} endpoint leaves its bounded plane: {slide_id}@{object_id}")
            else:
                _require(kind == "accessibility-reach" and
                         set(geometry) == {"kind", "from", "to"},
                         f"{kind} geometry is invalid: {slide_id}@{object_id}")
                for endpoint in ("from", "to"):
                    _validate_point(geometry[endpoint],
                                    f"{kind} endpoint is invalid: {slide_id}@{object_id}")
                    _require(all(0 <= coordinate <= 1 for coordinate in geometry[endpoint]),
                             f"{kind} endpoint leaves its bounded panel: {slide_id}@{object_id}")


def reconcile_state(state: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    """Add new independent sources without disturbing human ordering.

    Source removal fails closed because silently dropping a slide could discard
    accepted order, visibility, or component overlays.
    """

    _require(isinstance(state, dict) and state.get("schema") in {STATE_SCHEMA, *LEGACY_STATE_SCHEMAS},
             "state has an unsupported schema")
    order = list(state.get("order", []))
    existing = set(order)
    source_ids = set(catalog)
    removed = sorted(existing - source_ids)
    _require(not removed, "published slide source disappeared: " + ", ".join(removed))
    _require(len(order) == len(existing), "state order contains duplicate ids")
    changed = state.get("schema") != STATE_SCHEMA
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
    tables = state.get("tables", {})
    validate_tables(tables, catalog)
    objects = state.get("objects", {})
    validate_objects(objects, catalog)
    reconciled = {
        "schema": STATE_SCHEMA,
        "revision": int(state.get("revision", 0)) + (1 if changed else 0),
        "order": order,
        "hidden": [slide_id for slide_id in order if slide_id in set(hidden)],
        "overlays": overlays,
        "tables": tables,
        "objects": objects,
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
            if "region" in overlay:
                _require(component["kind"] == "text",
                         "region overlay must target text")
                _validate_text_region(
                    overlay["region"],
                    f"region overlay is invalid on {slide_id}@{component_id}",
                )


def validate_state_snapshot(candidate: Any, current: dict[str, Any],
                            catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _require(isinstance(candidate, dict), "snapshot must be an object")
    _require(candidate.get("schema") == STATE_SCHEMA, "unsupported state schema")
    order = candidate.get("order")
    hidden = candidate.get("hidden")
    overlays = candidate.get("overlays")
    tables = candidate.get("tables", {})
    objects = candidate.get("objects", {})
    known = set(catalog)
    _require(isinstance(order, list) and len(order) == len(known) and set(order) == known,
             "order must contain every published slide exactly once")
    _require(all(isinstance(item, str) for item in order), "slide ids must be strings")
    _require(isinstance(hidden, list) and set(hidden) <= known,
             "hidden must contain only published slide ids")
    validate_overlays(overlays, catalog)
    validate_tables(tables, catalog)
    validate_objects(objects, catalog)
    return {
        "schema": STATE_SCHEMA,
        "revision": int(current["revision"]) + 1,
        "order": list(order),
        "hidden": [slide_id for slide_id in order if slide_id in set(hidden)],
        "overlays": overlays,
        "tables": tables,
        "objects": objects,
    }


def catalog_receipt(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    recipe_counts = {recipe: 0 for recipe in sorted(RECIPES)}
    component_counts = {"text": 0, "image": 0}
    visual_object_counts = {
        "diagram-node": 0, "diagram-edge": 0, "vector": 0, "segment": 0,
        "accessibility-target": 0, "accessibility-reach": 0,
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
