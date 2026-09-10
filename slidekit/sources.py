"""Validation of independent declarative slide sources."""
from __future__ import annotations
import json
import itertools
import math
from typing import Any
from .common import (_validate_text_region, ContractError, _require, _component_ids, _recipe_visual_objects, _finite_number, SLIDE_SCHEMA, RECIPES, COMPONENT_ID, SLIDE_ID, HEX_COLOR)
from .overlays import (validate_objects, validate_text_marks)

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


