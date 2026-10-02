"""Editable, non-scientific starters for the existing recipe catalog.

These are ordinary SlideSpecs, not another layout system. The picker
preview, the atomic creation endpoint and agent authoring (``presentation.py
new``) all use this factory. Agent authoring may also start evidence recipes
whose data a human cannot enter in the picker, such as charts.
"""
from slidekit import ContractError, validate_slide_spec


STARTERS = {
    "section-divider": ("Section break", "One centered title on a blank slide."),
    "evidence-table": ("Table", "Editable headers and cells; add rows and columns in the toolbar."),
    "evidence-figure": ("Image / plot", "Drop an image or exported plot into the large image region."),
    "mechanism-pipeline": ("Process diagram", "Edit, move and resize the three nodes and their connectors."),
    "hierarchical-gallery": ("Image gallery", "Replace images and edit labels in an aligned three-image gallery."),
    "hero-equation": ("Equation", "Edit native LaTeX and its local definition."),
}
# Starters for agent authoring only: their evidence comes from source data.
AUTHOR_STARTERS = {
    "chart-panels": ("Chart", "One named chart with a labelled trace and a named annotation."),
}


def make_starter(recipe, slide_id, created_at, after=None, *, authoring=False, footer=False):
    if recipe not in STARTERS and not (authoring and recipe in AUTHOR_STARTERS):
        raise ContractError("unknown layout starter")
    components = {}

    def text(key, value, **options):
        components[key] = {"kind": "text", "text": value, **options}
        return key

    def image(key):
        components[key] = {"kind": "image", "src": "placeholder.svg", "alt": "Replace this image"}
        return key

    spec = {"schema": "online-slide/slide@1", "id": slide_id,
            "createdAt": created_at, "placement": {"after": after},
            "recipe": recipe, "headline": text("headline", "Section title" if recipe == "section-divider" else "Your slide title"),
            "components": components, "data": {}}
    data = spec["data"]
    if footer:
        spec["footer"] = text("protocol", "Run name · date · run code (where the evidence comes from)", role="protocol")
    if recipe == "section-divider":
        data["centered"] = True
    elif recipe == "evidence-table":
        data.update(heatmap={"label":text("heatmap-label","Value · low → high")},
                    columns=[text("column-name", "Comparison"), text("column-first", "First"), text("column-second", "Second")],
                    rows=[{"label": text(f"row-{name}", f"{name.title()} item"),
                           "cells": [text(f"{name}-first", "—"), text(f"{name}-second", "—")]}
                          for name in ("first", "second", "third")])
    elif recipe == "evidence-figure":
        data.update(image=image("figure"), caption=text("caption", "Your image caption"))
    elif recipe == "mechanism-pipeline":
        data.update(nodes=[{"id": key, "label": text(key+"-label", label)} for key, label in
                           (("input", "Input"), ("process", "Process"), ("output", "Output"))],
                    edges=[{"id": "input-to-process", "from": "input", "to": "process"},
                           {"id": "process-to-output", "from": "process", "to": "output"}])
    elif recipe == "hierarchical-gallery":
        data.update(columns=[text("column-"+key, key.title()) for key in ("first", "second", "third")],
                    selectors=[], views=[{"selection": {}, "metric": text("metric", "Your metric"),
                                         "classLabel": text("class-label", "Image group"), "pageSet": "images"}],
                    pageSets={"images": [{"label": text("page-label", "1"), "rows": [
                        {"label": text("row-label", "Examples"), "images": [image("image-"+key) for key in ("first", "second", "third")]}]}]})
    elif recipe == "hero-equation":
        data.update(equation=text("equation", r"y = f(x)", render="latex"),
                    definitions=[text("definition", "Define the symbols here")])
    elif recipe == "chart-panels":
        size = {"size": 28}
        components["chart"] = {"kind": "chart", "figure": {
            "data": [{"type": "scatter", "mode": "lines+markers", "uid": "series", "name": "Series name",
                      "x": [0, 1, 2, 3], "y": [1.0, 0.8, 0.5, 0.4], "line": {"width": 4}}],
            "layout": {"xaxis": {"title": {"text": "x quantity (unit)", "font": size}, "tickfont": size},
                       "yaxis": {"title": {"text": "y quantity (unit)", "font": size}, "tickfont": size},
                       "annotations": [{"name": "key-point", "x": 3, "y": 0.4, "xref": "x", "yref": "y",
                                        "text": "Label the point that carries the claim",
                                        "showarrow": True, "ax": -120, "ay": -80, "font": size}],
                       "legend": {"font": {"size": 24}},
                       "margin": {"l": 130, "r": 30, "t": 30, "b": 105}}}}
        data.update(panels=[{"chart": "chart"}])
    validate_slide_spec(spec)
    return spec


def starter_catalog():
    return [{"id": recipe, "name": name, "description": description,
             "slide": make_starter(recipe, "layout-preview", "2000-01-01T00:00:00Z")}
            for recipe, (name, description) in STARTERS.items()]
