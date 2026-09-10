"""Revision-safe state reconciliation and three-way edit merging."""
from __future__ import annotations
import copy
from typing import Any
from .common import (ContractError, _require, STATE_SCHEMA, LEGACY_STATE_SCHEMAS)
from .overlays import (validate_tables, validate_objects, validate_text_boxes, validate_overlays)
from .catalog import (source_revisions)

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


