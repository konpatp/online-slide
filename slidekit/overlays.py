"""Validation of semantic human edits, tables and visual objects."""
from __future__ import annotations
import math
from typing import Any
from .common import (_validate_text_region, _require, _component_ids, _visual_objects, _finite_number, _validate_point, COMPONENT_ID, HEX_COLOR, ALLOWED_OVERLAY_KEYS)

def validate_tables(tables: Any, catalog: dict[str, dict[str, Any]]) -> None:
    """Validate human-authored table structure by semantic identity.

    A table override is a complete logical table, not a set of DOM positions.
    Rows, columns, and cells keep stable ids when their visual order changes.
    Components introduced by a curator live with that logical table so no
    positional selector or hidden source rewrite is needed.
    """

    _require(isinstance(tables, dict), "tables must be an object")
    owned_insertions={}
    for table_key, table in tables.items():
        slide_id, separator, table_id=table_key.partition('::table::')
        _require(slide_id in catalog, f"table targets unknown slide {slide_id}")
        slide = catalog[slide_id]
        _require(slide["recipe"] == "evidence-table",
                 f"table structure may only target an evidence-table: {slide_id}")
        panels=slide['data'].get('tables')
        if panels is not None:
            _require(separator and table_id in {p['id'] for p in panels},f'table source disappeared: {table_key}')
            panel=next(p for p in panels if p['id']==table_id)
            permitted=set(panel['columns'])|{r['label'] for r in panel['rows']}|{c for r in panel['rows'] for c in r['cells']}
        else:
            _require(not separator,f'unknown independent table: {table_key}')
            permitted=_component_ids(slide)
        _require(isinstance(table, dict) and set(table) == {"columns", "rows", "components"},
                 f"table override for {slide_id} has an invalid shape")
        inserted = table["components"]
        _require(isinstance(inserted, dict), f"table components for {slide_id} must be an object")
        source_ids = _component_ids(slide)
        for component_id, component in inserted.items():
            owner=(slide_id,component_id)
            _require(owner not in owned_insertions,f'ambiguous inserted table component: {slide_id}@{component_id}')
            owned_insertions[owner]=table_key
            _require(COMPONENT_ID.fullmatch(component_id) is not None,
                     f"table component has invalid id: {slide_id}@{component_id}")
            _require(component_id not in source_ids,
                     f"table component collides with source: {slide_id}@{component_id}")
            _require(isinstance(component, dict) and component.get("kind") == "text" and
                     isinstance(component.get("text"), str) and len(component["text"]) <= 800,
                     f"inserted table component must be text: {slide_id}@{component_id}")
            _require(set(component) <= {
                "kind", "text", "role", "render", "display", "color", "fontScale", "region", "hidden", "marks",
            }, f"unsupported inserted table component fields: {slide_id}@{component_id}")
            if 'marks' in component:
                validate_text_marks(component['marks'], component)
            if 'hidden' in component:
                _require(isinstance(component['hidden'],bool), 'inserted component hidden state must be boolean')
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
        known_components = permitted | set(inserted)
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
            if kind in {"diagram-node", "accessibility-target", "annotation-rect", "recipe-frame"}:
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
                _require(kind in {"accessibility-reach","annotation-line"} and
                         set(geometry) == {"kind", "from", "to"},
                         f"{kind} geometry is invalid: {slide_id}@{object_id}")
                for endpoint in ("from", "to"):
                    _validate_point(geometry[endpoint],
                                    f"{kind} endpoint is invalid: {slide_id}@{object_id}")
                    _require(all(0 <= coordinate <= 1 for coordinate in geometry[endpoint]),
                             f"{kind} endpoint leaves its bounded panel: {slide_id}@{object_id}")


def validate_text_boxes(boxes: Any, catalog: dict[str, dict[str, Any]]) -> None:
    """Curator-owned text uses the same safe text/marks/region contract.

    Each UUID identity is an atomic conflict domain, independent of other
    insertions and author-owned source components. No raw HTML is accepted.
    """
    _require(isinstance(boxes, dict), "textBoxes must be an object")
    for sid, components in boxes.items():
        _require(sid in catalog, "text box targets unknown slide")
        _require(isinstance(components, dict) and len(components) <= 200,
                 "text boxes must be a bounded component map")
        for key, value in components.items():
            _require(isinstance(key, str) and COMPONENT_ID.fullmatch(key) and
                     key.startswith('text-box-') and key not in catalog[sid]['components'] and
                     key not in _visual_objects(catalog[sid]), "text box identity collides or is invalid")
            _require(isinstance(value, dict) and {'text', 'region'} <= set(value) and
                     set(value) <= {'text', 'region', 'marks', 'color', 'fontScale', 'hidden'},
                     "text box needs bounded text and supported formatting")
            validate_overlays({sid:{key:value}}, {sid:{'components':{key:{'kind':'text','text':''}}}})


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
            if 'marks' in overlay:
                _require('text' in overlay, 'text marks must bind their exact text')
                validate_text_marks(overlay['marks'], {**component, **overlay})
            elif 'text' in overlay and 'marks' in component:
                _require(False, 'replacement text must explicitly replace its authored marks')
            if 'hidden' in overlay:
                _require(isinstance(overlay['hidden'],bool), 'component hidden state must be boolean')
            if "chartLayout" in overlay:
                _require(component["kind"] == "chart", "chartLayout must target a chart")
                validate_chart_layout(overlay["chartLayout"], component)
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
                _require(component["kind"] in {"text","chart"},
                         "region overlay must target text or chart")
                _validate_text_region(
                    overlay["region"],
                    f"region overlay is invalid on {slide_id}@{component_id}",
                )


def validate_text_marks(marks: Any, component: dict) -> None:
    """Plain-text formatting ranges, never executable HTML; offsets use DOM UTF-16."""
    _require(component.get('kind') == 'text' and component.get('render', 'plain') == 'plain',
             'text marks require plain text (use LaTeX commands for math)')
    _require(isinstance(marks, list) and len(marks) <= 200, 'invalid text marks')
    _require(isinstance(component.get('text'), str), 'marked text must be a string')
    length = len(component['text'].encode('utf-16-le')) // 2
    previous = 0
    for mark in marks:
        _require(isinstance(mark, dict) and set(mark) == {'start', 'end', 'bold'}, 'invalid text mark fields')
        start, end = mark['start'], mark['end']
        _require(type(start) is int and type(end) is int and previous <= start < end <= length,
                 'text marks overlap or exceed the text')
        _require(type(mark['bold']) is bool, 'bold mark must be boolean')
        previous = end


def validate_chart_layout(value: Any, component: dict) -> None:
    """Only presentation edits; never permit an overlay to replace scientific data.

    Names, not annotation indices, are durable targets. Removing an edited
    annotation is refused even if a different annotation occupies its old slot.
    """
    _require(isinstance(value, dict) and set(value) <= {"legend", "annotations"},
             "unsupported chart edit")
    if "legend" in value:
        legend = value["legend"]
        _require(isinstance(legend, dict) and set(legend) <= {"x", "y"}, "invalid legend edit")
        _require(all(isinstance(v, (int, float)) and -10 <= v <= 10 for v in legend.values()),
                 "legend position out of bounds")
    names = {item["name"] for item in component["figure"]["layout"].get("annotations", [])}
    annotations = value.get("annotations", {})
    _require(isinstance(annotations, dict) and set(annotations) <= names,
             "edited chart annotation disappeared")
    for changes in annotations.values():
        _require(isinstance(changes, dict) and set(changes) <= {"x", "y", "ax", "ay", "text"},
                 "invalid annotation edit")
        for key, item in changes.items():
            if key == "text":
                _require(isinstance(item, str) and len(item) <= 2000, "invalid annotation text")
            else:
                _require(isinstance(item, (int, float)) and abs(item) < 1e12,
                         "invalid annotation position")


