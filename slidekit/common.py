"""Shared source/state primitives; no catalog or transport dependencies."""
from __future__ import annotations
import re
from typing import Any

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


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < 1_000_000


def _validate_point(value: Any, message: str) -> None:
    _require(isinstance(value, list) and len(value) == 2 and all(_finite_number(item) for item in value),
             message)


