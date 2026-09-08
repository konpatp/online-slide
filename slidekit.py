"""Contracts for independent scientific slide sources and mutable deck state.

Slide source files are immutable author contributions. Ordering, visibility,
human overlays, and semantic table structure live in a separate revision-checked state file. Keeping those
surfaces separate lets several contributors add slides without rewriting a
shared deck source or overwriting live human decisions.
"""

from __future__ import annotations

import hashlib
import copy
import json
import itertools
import math
import re
from pathlib import Path
from typing import Any, Iterable


SLIDE_SCHEMA = "online-slide/slide@1"
STATE_SCHEMA = "online-slide/state@4"
LEGACY_STATE_SCHEMAS = {"online-slide/state@2", "online-slide/state@3"}
RECIPES = {
    "hero-plot", "evidence-table", "mechanism-pipeline",
    "vector-geometry", "hierarchical-gallery", "target-accessibility", "chart-panels", "section-divider", "hero-equation", "evidence-figure", "slide-index",
}
COMPONENT_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SLIDE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_OVERLAY_KEYS = {
    "text", "color", "fontScale", "src", "imageScale", "region", "chartLayout", "hidden", "marks",
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

    return {**_recipe_visual_objects(spec), **({spec['frame']['id']:'recipe-frame'} if spec.get('frame') else {}), **{
        item['id']: 'annotation-rect' if item['kind']=='rect' else 'annotation-line'
        for item in spec.get('annotations',[]) if item['kind']!='text'}}


def _recipe_visual_objects(spec: dict[str, Any]) -> dict[str, str]:
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
        _require(kind in {"text", "image", "chart"},
                 f"{source}: component {component_id!r} has invalid kind")
        if kind == "text":
            _require(isinstance(component.get("text"), str),
                     f"{source}: text component {component_id!r} needs text")
            if 'marks' in component:
                validate_text_marks(component['marks'], component)
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
        elif kind == "chart":
            if 'region' in component:_validate_text_region(component['region'],f'{source}: chart region is invalid')
            figure = component.get("figure")
            _require(isinstance(figure, dict) and isinstance(figure.get("data"), list)
                     and figure["data"] and isinstance(figure.get("layout"), dict),
                     f"{source}: chart needs source-native data and layout")
            try:
                json.dumps(figure, allow_nan=False)
            except (ValueError, TypeError):
                raise ContractError(f"{source}: chart contains non-finite or non-JSON evidence")
            _require(all(isinstance(trace, dict) for trace in figure["data"]),
                     f"{source}: chart traces must be objects")
            identities = [trace.get("uid") for trace in figure["data"]]
            _require(all(isinstance(key, str) and key for key in identities)
                     and len(set(identities)) == len(identities),
                     f"{source}: chart traces need unique authored uids")
            annotations = figure["layout"].get("annotations", [])
            _require(isinstance(annotations, list) and all(isinstance(item, dict) for item in annotations),
                     f"{source}: chart annotations must be objects")
            names = [item.get("name") for item in annotations]
            _require(all(isinstance(key, str) and key for key in names)
                     and len(set(names)) == len(names),
                     f"{source}: chart annotations need unique authored names")
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
    annotations=spec.get('annotations',[])
    frame=spec.get('frame')
    if frame is not None:
        _require(isinstance(frame,dict) and set(frame)=={'id','geometry'},f'{source}: invalid recipe frame')
        _require(isinstance(frame['id'],str) and COMPONENT_ID.fullmatch(frame['id']) and frame['id'] not in components and frame['id'] not in _recipe_visual_objects(spec),f'{source}: frame needs unique semantic identity')
        validate_objects({spec['id']:{frame['id']:{'kind':'recipe-frame',**frame['geometry']}}},{spec['id']:spec})
    _require(isinstance(annotations,list),f'{source}: annotations must be a list')
    annotation_ids=set();annotation_objects={}
    for item in annotations:
        _require(isinstance(item,dict) and item.get('kind') in {'text','rect','line','arrow'},f'{source}: invalid annotation kind')
        if item['kind']=='text':
            ref(item.get('component'),'annotation text')
            _require(components[item['component']].get('kind')=='text' and 'region' in components[item['component']],f'{source}: annotation text requires a bounded region')
            continue
        key=item.get('id')
        _require(isinstance(key,str) and COMPONENT_ID.fullmatch(key) and key not in annotation_ids and key not in components and key not in _recipe_visual_objects(spec) and key!=(frame or {}).get('id'),f'{source}: annotation identity must be unique')
        annotation_ids.add(key)
        _require(HEX_COLOR.fullmatch(str(item.get('color',''))) is not None,f'{source}: annotation requires hex color')
        _require(_finite_number(item.get('strokeWidth',3)) and 1<=item.get('strokeWidth',3)<=20,f'{source}: invalid annotation stroke width')
        _require(_finite_number(item.get('cornerRadius',0)) and 0<=item.get('cornerRadius',0)<=40,f'{source}: invalid annotation corner radius')
        _require(isinstance(item.get('geometry'),dict),f'{source}: annotation geometry required')
        annotation_objects[key]={**item['geometry'],'kind':'annotation-rect' if item['kind']=='rect' else 'annotation-line'}
    if annotation_objects:validate_objects({spec['id']:annotation_objects},{spec['id']:spec})
    recipe = spec["recipe"]
    if recipe == 'slide-index':
        sections=data.get('sections')
        _require(isinstance(sections,list) and sections,f'{source}: index sections required')
        destinations=set()
        for section in sections:
            ref(section.get('heading'),'index heading')
            _require(isinstance(section.get('items'),list) and section['items'],f'{source}: index items required')
            for item in section['items']:
                ref(item.get('label'),'index label')
                destination=item.get('slide')
                _require(isinstance(destination,str) and SLIDE_ID.fullmatch(destination) and destination not in destinations,f'{source}: invalid or duplicate index destination')
                destinations.add(destination)
    elif recipe == "section-divider":
        _require(set(data) <= {"centered"} and isinstance(data.get("centered", False), bool),
                 f"{source}: section dividers support only the centered option")
    elif recipe == "evidence-figure":
        image_id=data.get('image')
        _require(isinstance(image_id,str) and components.get(image_id,{}).get('kind')=='image',
                 f'{source}: evidence figure needs one image component')
        labels=data.get('labels',[])
        _require(isinstance(labels,list) and len(labels)<=4,f'{source}: at most four figure labels')
        for label in labels:
            ref(label,'figure label')
        if data.get('caption'):
            ref(data['caption'],'figure caption')
    elif recipe == "hero-equation":
        ref(data.get('equation'), 'equation')
        _require(components.get(data.get('equation'),{}).get('render')=='latex',
                 f'{source}: hero equation must be native LaTeX')
        definitions=data.get('definitions',[])
        _require(isinstance(definitions,list) and 1 <= len(definitions) <= 4,
                 f'{source}: hero equation needs one to four local definitions')
        for label in definitions:
            ref(label,'definition')
        if data.get('question'):
            ref(data['question'],'question')
    elif recipe == "chart-panels":
        if 'smoothing' in data:
            smoothing=data['smoothing']
            _require(isinstance(smoothing,dict) and set(smoothing)=={'radius','max','step','unit'} and
                     all(isinstance(smoothing[k],(int,float)) and not isinstance(smoothing[k],bool) and math.isfinite(smoothing[k]) for k in ('radius','max','step')) and
                     0<=smoothing['radius']<=smoothing['max'] and 0<smoothing['step']<=smoothing['max'] and
                     isinstance(smoothing['unit'],str),f'{source}: invalid centered smoothing control')
        def chart_composition(composition):
            panels = composition.get("panels")
            _require(isinstance(panels, list) and 1 <= len(panels) <= 3,
                     f"{source}: chart-panels needs one to three panels")
            _require(composition.get('layout','row') in {'row','main-with-diagnostics'},f'{source}: unknown chart composition')
            if composition.get('layout')=='main-with-diagnostics':
                _require(len(panels)==3,f'{source}: main-with-diagnostics needs exactly three panels')
            for panel in panels:
                _require(isinstance(panel, dict), f"{source}: panel must be an object")
                ref(panel.get("chart"), "panel.chart")
                _require(components.get(panel.get("chart"), {}).get("kind") == "chart",
                         f"{source}: panel must reference a chart")
                for key in ("heading", "subheading", "caption"):
                    if panel.get(key):
                        ref(panel[key], "panel."+key)
                for endpoint in panel.get('endpoints',[]):
                    for key in ('label','value','horizon'):
                        ref(endpoint.get(key),'endpoint.'+key)
            _require(len({panel["chart"] for panel in panels}) == len(panels),
                     f"{source}: the same chart cannot occupy two panels")
            for item in composition.get("legend", []):
                ref(item.get("label"), "legend.label")
            for label in composition.get("decoders", []):
                ref(label, "decoder")
            for key in ("xLabel", "yLabel"):
                if composition.get(key):
                    ref(composition[key], key)

        if "views" in data:
            selectors, views = data.get("selectors"), data["views"]
            _require(isinstance(selectors, list) and selectors and isinstance(views, list) and views,
                     f"{source}: faceted charts need selectors and views")
            allowed = {}
            for selector in selectors:
                key = selector.get("id")
                _require(isinstance(key,str) and COMPONENT_ID.fullmatch(key) and key not in allowed,
                         f"{source}: selectors need unique semantic ids")
                ref(selector.get("label"), "selector.label")
                options = selector.get("options")
                _require(isinstance(options,list) and options, f"{source}: selector options missing")
                values = [option.get("value") for option in options]
                _require(all(isinstance(value,str) and value for value in values) and len(set(values)) == len(values),
                         f"{source}: selector options must be unique")
                allowed[key] = values
                for option in options:
                    ref(option.get("label"), "option.label")
            keys = list(allowed)
            combinations = set()
            for view in views:
                selection = view.get("selection", {})
                _require(set(selection) == set(keys) and all(selection[key] in allowed[key] for key in keys),
                         f"{source}: invalid view selection")
                combination = tuple(selection[key] for key in keys)
                _require(combination not in combinations, f"{source}: ambiguous chart view")
                combinations.add(combination)
                # Scientific arrays were already checked once above. A view
                # validates only its references, not the whole matrix again.
                chart_composition({**data, **view})
            _require(combinations == set(itertools.product(*(allowed[key] for key in keys))),
                     f"{source}: chart facet combinations are incomplete")
        chart_composition(data)
    elif recipe == "hero-plot":
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
        if 'tables' in data:
            panels=data['tables']
            _require(isinstance(panels,list) and 1<=len(panels)<=3,f'{source}: one to three independent tables required')
            ids=set();leaves=set()
            for panel in panels:
                key=panel.get('id')
                _require(isinstance(key,str) and COMPONENT_ID.fullmatch(key) and key not in ids,f'{source}: tables need unique semantic ids')
                ids.add(key)
                _require('tables' not in panel,f'{source}: nested tables are not supported')
                validate_slide_spec({**spec,'data':panel},source=source+'::table::'+key)
                used=set(panel['columns'])|{row['label'] for row in panel['rows']}|{cell for row in panel['rows'] for cell in row['cells']}
                _require(not used & leaves,f'{source}: independent tables cannot share editable cells')
                leaves.update(used)
                for field in ('heading','visibility'):
                    if panel.get(field):ref(panel[field],'table.'+field)
            if 'tableSelector' in data:
                selector=data['tableSelector']
                _require(isinstance(selector,dict),f'{source}: tableSelector must be an object')
                ref(selector.get('label'),'tableSelector.label')
                options=selector.get('options')
                _require(isinstance(options,list) and len(options)==len(ids),f'{source}: table selector must cover every table')
                values=[option.get('value') for option in options]
                _require(all(isinstance(value,str) for value in values) and set(values)==ids and len(set(values))==len(values),f'{source}: table selector must name each table once')
                for option in options:ref(option.get('label'),'tableSelector.option.label')
                _require(data.get('initialTable',panels[0]['id']) in ids,f'{source}: initialTable must name a table')
            unknown=set(referenced)-set(components)
            _require(not unknown,f'{source}: unknown table control components: {sorted(unknown)}')
            return spec
        columns = data.get("columns")
        rows = data.get("rows")
        _require(isinstance(columns, list) and columns, f"{source}: table needs columns")
        _require(isinstance(rows, list) and rows, f"{source}: table needs rows")
        if "columnWeights" in data:
            weights = data["columnWeights"]
            _require(isinstance(weights, list) and len(weights) == len(columns) and
                     all(isinstance(value, (int, float)) and not isinstance(value, bool) and
                         0.35 <= value <= 4 for value in weights),
                     f"{source}: table columnWeights must match columns and lie in [0.35,4]")
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
            _require(best is None or isinstance(best, int) and not isinstance(best, bool) and 0 <= best < len(cells),
                     f"{source}: row {row_index} needs a valid best index or no emphasis")
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
        for point in data.get('points',[]):
            _require(isinstance(point,dict) and isinstance(point.get('at'),list) and len(point['at'])==2 and
                     all(_finite_number(v) for v in point['at']),f'{source}: point needs finite coordinates')
            for field in ('color','fillColor'):
                if field in point:_require(HEX_COLOR.fullmatch(str(point[field])) is not None,f'{source}: invalid point {field}')
        for index, arc in enumerate(data.get("arcs", [])):
            _require(isinstance(arc, dict) and
                     isinstance(arc.get("center"), list) and len(arc["center"]) == 2 and
                     isinstance(arc.get("radius"), (int, float)) and arc["radius"] > 0 and
                     isinstance(arc.get("startDeg"), (int, float)) and
                     isinstance(arc.get("endDeg"), (int, float)),
                     f"{source}: arcs[{index}] is invalid")
        for index, label in enumerate(data.get("labels", [])):
            box = label.get("box") if isinstance(label, dict) else None
            space=label.get('space','percent') if isinstance(label,dict) else None
            _require(space in {'percent','world'},f'{source}: unknown geometry label coordinate space')
            _require(isinstance(box, dict) and
                     all(isinstance(box.get(key), (int, float)) and math.isfinite(box[key]) for key in ("x", "y", "width", "height")) and
                     box["width"] > 0 and box["height"] > 0,
                     f"{source}: labels[{index}] needs a finite bounded box")
            if space=='world':
                _require(bounds[0]<=box['x'] and box['x']+box['width']<=bounds[2] and
                         box['y']<=bounds[1] and box['y']-box['height']>=bounds[3],
                         f'{source}: world label outside geometry bounds')
            else:
                _require(0<=box['x'] and 0<=box['y'] and box['x']+box['width']<=100 and box['y']+box['height']<=100,
                         f'{source}: percentage label outside geometry bounds')
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
        _require(isinstance(selectors, list), f"{source}: gallery selectors must be a list")
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
                    if row.get("detail"):
                        ref(row["detail"], "gallery row detail")
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
            if "columns" in view:
                _require(isinstance(view["columns"],list) and len(view["columns"]) == len(columns),
                         f"{source}: gallery view columns must preserve matrix width")
                for component_id in view["columns"]:
                    ref(component_id, "view.columns")
            _require(view.get("pageSet") in page_sets,
                     f"{source}: view {view_index} references an unknown pageSet")
        if "initialSelection" in data:
            _require(isinstance(data["initialSelection"],dict) and
                     tuple(sorted(data["initialSelection"].items())) in seen_selections,
                     f"{source}: initial gallery selection must identify a view")

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


class EditConflict(ContractError):
    """An edited target changed since the caller observed it."""


def merge_state_snapshot(base: Any, candidate: Any, current: dict[str, Any],
                         catalog: dict[str, dict[str, Any]],
                         base_sources: Any) -> dict[str, Any]:
    """Three-way merge by semantic edit target, never last-writer-wins.

    Ordering is one conflict domain; visibility is per slide, overlays per
    attribute, geometry per object, and table structure per table. Source-only
    additions do not conflict with edits to an unchanged existing slide.
    Preconditions travel with the request, so retries remain idempotent without
    an unbounded server revision history.
    """
    _require(isinstance(base, dict) and isinstance(candidate, dict),
             "baseSnapshot and snapshot must be objects")
    _require(isinstance(base_sources, dict), "baseSlideRevisions must be an object")
    ids = base.get("order")
    _require(isinstance(ids, list) and all(isinstance(key, str) for key in ids),
             "baseSnapshot needs slide identities")
    _require(set(ids) <= set(catalog), "baseSnapshot contains removed slide identities")
    subset = {key: catalog[key] for key in ids}
    validate_state_snapshot(base, current, subset)
    validate_state_snapshot(candidate, current, subset)
    result = copy.deepcopy(current)
    revisions = source_revisions(catalog)
    missing = object()

    def choose(old: Any, new: Any, remote: Any, path: tuple[str, ...]) -> Any:
        if old == new:
            return remote
        if len(path) > 1 and path[0] in {"overlays", "objects", "tables", "textBoxes"}:
            key = path[1]
            if path[0]=='tables':key=key.partition('::table::')[0]
            if base_sources.get(key) != revisions[key]:
                raise EditConflict("source changed for edited slide: " + key)
        if remote != old and remote != new:
            raise EditConflict("edit conflict: " + "/".join(path))
        return new

    def merge_map(old: dict, new: dict, remote: dict, depth: int,
                  path: tuple[str, ...]) -> dict:
        merged = copy.deepcopy(remote)
        keys = old.keys() | new.keys()
        if depth == 1 and path[0] == 'overlays' and any('marks' in value for value in (old,new,remote)):
            # Ranges and the text they index form one conflict domain. A
            # concurrent wording edit must not move bold onto other words.
            group = lambda value: {key:value[key] for key in ('text','marks') if key in value}
            chosen = choose(group(old),group(new),group(remote),(*path,'text'))
            for key in ('text','marks'):
                merged.pop(key,None)
            merged.update(copy.deepcopy(chosen))
            keys -= {'text','marks'}
        for key in keys:
            before, after = old.get(key, missing), new.get(key, missing)
            actual = remote.get(key, missing)
            if before == after:
                continue
            if depth > 1:
                value = merge_map(
                    {} if before is missing else before,
                    {} if after is missing else after,
                    {} if actual is missing else actual, depth - 1, (*path, key))
                if value:
                    merged[key] = value
                else:
                    merged.pop(key, None)
            else:
                value = choose(before, after, actual, (*path, key))
                if value is missing:
                    merged.pop(key, None)
                else:
                    merged[key] = copy.deepcopy(value)
        return merged

    base_order, new_order = base["order"], candidate["order"]
    if base_order != new_order:
        old_ids = set(base_order)
        remote_order = [key for key in current["order"] if key in old_ids]
        chosen = choose(base_order, new_order, remote_order, ("order",))
        replacements = iter(chosen)
        result["order"] = [
            next(replacements) if key in old_ids else key for key in current["order"]]
    hidden = set(current["hidden"])
    for key in ids:
        value = choose(key in base["hidden"], key in candidate["hidden"],
                       key in hidden, ("hidden", key))
        if value:
            hidden.add(key)
        else:
            hidden.discard(key)
    result["hidden"] = [key for key in result["order"] if key in hidden]
    for field, depth in (("overlays", 3), ("objects", 2), ("tables", 1), ("textBoxes", 2)):
        result[field] = merge_map(base.get(field, {}), candidate.get(field, {}),
                                  current.get(field, {}), depth, (field,))
    return validate_state_snapshot(result, current, catalog)


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
    text_boxes = state.get("textBoxes", {})
    validate_text_boxes(text_boxes, catalog)
    reconciled = {
        "schema": STATE_SCHEMA,
        "revision": int(state.get("revision", 0)) + (1 if changed else 0),
        "order": order,
        "hidden": [slide_id for slide_id in order if slide_id in set(hidden)],
        "overlays": overlays,
        "tables": tables,
        "objects": objects,
        "textBoxes": text_boxes,
    }
    if state.get("createdSlides"):
        reconciled["createdSlides"] = copy.deepcopy(state["createdSlides"])
    return reconciled, changed


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


def validate_state_snapshot(candidate: Any, current: dict[str, Any],
                            catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _require(isinstance(candidate, dict), "snapshot must be an object")
    _require(candidate.get("schema") == STATE_SCHEMA, "unsupported state schema")
    order = candidate.get("order")
    hidden = candidate.get("hidden")
    overlays = candidate.get("overlays")
    tables = candidate.get("tables", {})
    objects = candidate.get("objects", {})
    text_boxes = candidate.get("textBoxes", {})
    known = set(catalog)
    _require(isinstance(order, list) and len(order) == len(known) and set(order) == known,
             "order must contain every published slide exactly once")
    _require(all(isinstance(item, str) for item in order), "slide ids must be strings")
    _require(isinstance(hidden, list) and set(hidden) <= known,
             "hidden must contain only published slide ids")
    validate_overlays(overlays, catalog)
    validate_tables(tables, catalog)
    validate_objects(objects, catalog)
    validate_text_boxes(text_boxes, catalog)
    result = {
        "schema": STATE_SCHEMA,
        "revision": int(current["revision"]) + 1,
        "order": list(order),
        "hidden": [slide_id for slide_id in order if slide_id in set(hidden)],
        "overlays": overlays,
        "tables": tables,
        "objects": objects,
        "textBoxes": text_boxes,
    }
    # Created sources are service-owned. A stale or malicious snapshot cannot
    # replace them; only the atomic creation endpoint can add a source.
    if current.get("createdSlides"):
        result["createdSlides"] = copy.deepcopy(current["createdSlides"])
    return result


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
