"""Editable, non-scientific starters for the existing recipe catalog.

These are ordinary SlideSpecs, not another layout system. Both the picker
preview and the atomic creation endpoint use this factory.
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


def make_starter(recipe, slide_id, created_at, after=None):
    if recipe not in STARTERS:
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
    if recipe == "section-divider":
        data["centered"] = True
    elif recipe == "evidence-table":
        data.update(columns=[text("column-name", "Comparison"), text("column-first", "First"), text("column-second", "Second")],
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
    validate_slide_spec(spec)
    return spec


def starter_catalog():
    return [{"id": recipe, "name": name, "description": description,
             "slide": make_starter(recipe, "layout-preview", "2000-01-01T00:00:00Z")}
            for recipe, (name, description) in STARTERS.items()]
