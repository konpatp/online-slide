#!/usr/bin/env python3
"""Dependency-free server for the ScientificSlideKit pilot.

Authored SlideSpecs are loaded independently from ``slides/*.json``. Mutable
human state contains order, visibility, semantic component overlays, and
semantic evidence-table structure.
Both source and state revisions participate in saves, so a source change can
never silently retarget a live edit.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gzip
from functools import lru_cache
import hashlib
import json
import mimetypes
import os
import re
import tempfile
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, parse_qs, unquote
from display_media import display_bytes, display_references, publish_image, RASTERS

from slidekit import (
    ContractError,
    EditConflict,
    STATE_SCHEMA,
    catalog_receipt,
    catalog_revision,
    empty_state,
    load_catalog,
    reconcile_state,
    merge_state_snapshot,
    source_revisions,
    validate_state_snapshot,
)
from slide_templates import make_starter, starter_catalog


MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 8 * 1024 * 1024


@lru_cache(maxsize=16)
def compressed(raw: bytes) -> bytes:
    """Bounded, content-keyed cache; no timestamp or stale-path identities."""
    return gzip.compress(raw, compresslevel=6, mtime=0)


def accepts_gzip(header: str) -> bool:
    encodings = {}
    for entry in header.lower().split(','):
        name, *params = entry.strip().split(';')
        quality = 1.0
        for param in params:
            if param.strip().startswith('q='):
                try:
                    quality = float(param.strip()[2:])
                except ValueError:
                    quality = 0.0
        encodings[name] = quality
    return encodings.get('gzip', encodings.get('*', 0)) > 0


UPLOAD_NAME = re.compile(r"^[0-9a-f]{64}\.(?:png|jpe?g|webp|gif|svg)$")
ALLOWED_ASSETS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_state(seed_path: Path, state_path: Path) -> dict[str, Any]:
    if state_path.exists():
        return read_json(state_path)
    seed = read_json(seed_path) if seed_path.exists() else empty_state()
    atomic_write_json(state_path, seed)
    return seed


def make_server(
    public_dir: Path,
    slides_dir: Path,
    seed_path: Path,
    state_path: Path,
    uploads_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Build a revision-safe server used by the demo and its real HTTP tests."""

    lock = threading.RLock()
    uploads_dir = uploads_dir or state_path.parent / "uploads"
    display_manifest = public_dir.parent / "data" / "display-media.json"
    display_map = read_json(display_manifest) if display_manifest.is_file() else {}
    # Existing user uploads receive derivatives at activation, never on GET.
    # Original uploads and curator state remain untouched and recoverable.
    for source in sorted(uploads_dir.glob("*")):
        if source.is_file() and source.suffix.lower() in RASTERS:
            target = publish_image(source, uploads_dir)
            display_map[f"uploads/{source.name}"] = f"uploads/{target.name}"
    display_revision = hashlib.sha256(json.dumps(display_map, sort_keys=True).encode()).hexdigest()
    runtime_assets = [
        "index.html", "runtime-version.js",
        "styles.css", "app.js", "slide-previews.js", "new-slide.js", "recipes.js", "joint-diagram.js",
        "geometry-runtime.js", "geometry-runtime.css", "chart-panels.js", "plotly.min.js",
        "math-runtime.js", "math-runtime.css",
    ]
    asset_revision = hashlib.sha256(b"".join(
        (public_dir / name).read_bytes() for name in runtime_assets
    )).hexdigest()[:16]
    stored = load_state(seed_path, state_path)
    catalog = load_catalog(slides_dir, stored.get("createdSlides"))
    source_revision = catalog_revision(catalog)
    state, changed = reconcile_state(stored, catalog)
    if changed:
        atomic_write_json(state_path, state)

    def send_bytes(handler, status, raw, content_type, cache_control="no-store"):
        text = content_type.startswith('text/') or any(
            kind in content_type for kind in ('json', 'javascript', 'svg'))
        encoded = text and len(raw) >= 1024 and accepts_gzip(handler.headers.get('Accept-Encoding', ''))
        if encoded:
            raw = compressed(raw)
        etag = '"' + hashlib.sha256(raw).hexdigest() + '"'
        not_modified = status == 200 and cache_control != 'no-store' and handler.headers.get('If-None-Match') == etag
        handler.send_response(304 if not_modified else status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", cache_control)
        handler.send_header("Vary", "Accept-Encoding")
        handler.send_header("ETag", etag)
        if encoded:
            handler.send_header("Content-Encoding", "gzip")
        if not_modified:
            handler.end_headers()
            return
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            return

    def response(handler: SimpleHTTPRequestHandler, status: int, payload: Any, cache_control="no-store") -> None:
        payload = display_references(payload, display_map)
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        send_bytes(handler, status, raw, "application/json; charset=utf-8", cache_control)

    def static_response(handler: SimpleHTTPRequestHandler, path: Path, cache_control: str) -> None:
        send_bytes(handler, 200, path.read_bytes(),
                   mimetypes.guess_type(path.name)[0] or "application/octet-stream", cache_control)

    def refresh_sources() -> None:
        nonlocal catalog, source_revision, state
        candidate = load_catalog(slides_dir, state.get("createdSlides"))
        candidate_revision = catalog_revision(candidate)
        if candidate_revision == source_revision:
            return
        reconciled, reconciled_changed = reconcile_state(state, candidate)
        if reconciled_changed:
            atomic_write_json(state_path, reconciled)
        catalog = candidate
        source_revision = candidate_revision
        state = reconciled

    def deck_payload(compact=False) -> dict[str, Any]:
        payload = dict(state)
        payload.pop("createdSlides", None)  # Sources travel once, through the catalog.
        payload["order"] = list(state["order"])
        payload["hidden"] = list(state["hidden"])
        payload["overlays"] = json.loads(json.dumps(state["overlays"]))
        payload["tables"] = json.loads(json.dumps(state.get("tables", {})))
        payload["objects"] = json.loads(json.dumps(state.get("objects", {})))
        payload["sourceRevision"] = source_revision
        payload["runtimeRevision"] = asset_revision
        payload["displayRevision"] = display_revision
        payload["slideRevisions"] = source_revisions(catalog)
        if not compact:
            payload["slides"] = catalog
        return payload

    def bootstrap(requested):
        payload = deck_payload(compact=True)
        # Enough for navigation and curator order/visibility, not unrelated evidence.
        payload['slides'] = {key: {field: slide[field] for field in
            ('id', 'recipe', 'headline', 'theme', 'routes') if field in slide}
            for key, slide in catalog.items()}
        for key, slide in catalog.items():
            payload['slides'][key]['components'] = {slide['headline']: slide['components'][slide['headline']]}
        sid = requested if requested in catalog else next((key for key, slide in catalog.items()
            if any(route['id'] == requested for route in slide.get('routes', []))), state['order'][0])
        payload['slides'][sid] = catalog[sid]
        payload['loadedSlides'] = [sid]
        return payload

    class Handler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def end_headers(self):
            self.send_header('X-Slidekit-Runtime', asset_revision)
            super().end_headers()

        def runtime_matches(self):
            revision = self.headers.get('X-Slidekit-Runtime')
            if revision and revision != asset_revision:
                self.close_connection = True  # A refused POST body must not become another request.
                response(self, 409, {'error': 'Slide renderer updated; reload before continuing.'})
                return False
            return True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(public_dir), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-File-Name")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if not self.runtime_matches():
                return
            if urlsplit(self.path).path == '/api/runtime':
                response(self, 200, {'runtimeRevision': asset_revision}, 'no-store')
                return
            route = urlsplit(self.path).path
            query = parse_qs(urlsplit(self.path).query)
            try:
                with lock:
                    if route.startswith('/api/'):
                        refresh_sources()
                    if route == '/api/bootstrap':
                        payload = bootstrap(query.get('slide', [''])[0])
                    elif route == '/api/layouts':
                        payload = starter_catalog()
                    elif route.startswith('/api/slides/'):
                        sid = unquote(route.removeprefix('/api/slides/'))
                        if sid not in catalog:
                            response(self, 404, {'error': 'slide not found'})
                            return
                        if query.get('revision', [''])[0] != source_revisions(catalog)[sid]:
                            response(self, 409, {'error': 'source revision changed; reload the deck'})
                            return
                        payload = catalog[sid]
                    else:
                        payload = None
                    if route == "/api/health":
                        response(self, 200, {
                            "ok": True,
                            "stateSchema": STATE_SCHEMA,
                            "catalog": catalog_receipt(catalog),
                            "stateRevision": state["revision"],
                        })
                        return
                    if route == "/api/deck-state":
                        payload = deck_payload()
                # Do not hold the curator lock while a distant client downloads evidence.
                if payload is not None:
                    response(self, 200, payload, 'private, max-age=31536000, immutable'
                             if route.startswith('/api/slides/') else 'no-store')
                    return
            except (ContractError, OSError, json.JSONDecodeError) as exc:
                response(self, 503, {"error": f"source contract failed: {exc}"})
                return
            if route.startswith("/uploads/"):
                name = route.removeprefix("/uploads/")
                if not UPLOAD_NAME.fullmatch(name):
                    response(self, 404, {"error": "asset not found"})
                    return
                path = uploads_dir / name
                if not path.is_file():
                    response(self, 404, {"error": "asset not found"})
                    return
                raw = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if route in {"/", "/index.html"}:
                raw = (public_dir / "index.html").read_text(encoding="utf-8")
                raw = raw.replace("__ASSET_REVISION__", asset_revision).encode("utf-8")
                send_bytes(self, 200, raw, 'text/html; charset=utf-8', 'no-cache, must-revalidate')
                return
            candidate = (public_dir / route.lstrip("/")).resolve()
            if not candidate.is_relative_to(public_dir.resolve()) or not candidate.is_file():
                response(self, 404, {"error": "not found"})
                return
            static_response(
                self,
                candidate,
                "public, max-age=31536000, immutable"
                if query.get('v') == [asset_revision] else "no-cache, must-revalidate",
            )

        def do_POST(self) -> None:  # noqa: N802
            if not self.runtime_matches():
                return
            nonlocal state
            route = urlsplit(self.path).path
            if route == "/api/assets":
                self._upload_asset()
                return
            if route == "/api/slides":
                self._create_slide()
                return
            if route != "/api/deck-state":
                response(self, 404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                response(self, 400, {"error": "invalid Content-Length"})
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                response(self, 413, {"error": "request body is too large or empty"})
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                base_revision = int(body.get("baseRevision"))
                base_source_revision = str(body.get("baseSourceRevision"))
            except (ValueError, TypeError, json.JSONDecodeError):
                response(self, 400, {"error": "invalid JSON or revision"})
                return
            with lock:
                try:
                    refresh_sources()
                except (ContractError, OSError, json.JSONDecodeError) as exc:
                    response(self, 503, {"error": f"source contract failed: {exc}"})
                    return
                if "baseSnapshot" not in body and (
                    base_revision != int(state["revision"]) or base_source_revision != source_revision
                ):
                    response(self, 409, {"error": "revision conflict", "state": deck_payload()})
                    return
                try:
                    if "baseSnapshot" in body:
                        candidate = merge_state_snapshot(
                            body["baseSnapshot"], body.get("snapshot"), state, catalog,
                            body.get("baseSlideRevisions"))
                    else:
                        candidate = validate_state_snapshot(body.get("snapshot"), state, catalog)
                    atomic_write_json(state_path, candidate)
                    state = candidate
                except EditConflict as exc:
                    response(self, 409, {"error": str(exc), "state": deck_payload()})
                    return
                except (ContractError, OSError) as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                # Old API clients retain their full response; the native editor opts
                # into an ACK with no source data when its catalog is still current.
                payload = deck_payload(compact=body.get('compact') is True and base_source_revision == source_revision)
            response(self, 200, payload)

        def _create_slide(self) -> None:
            """Commit source + placement once, before acknowledging creation.

            Requests express insertion intent, not a replacement order. Retry
            identity is retained with the source so uncertain ACKs are safe.
            """
            nonlocal state, catalog, source_revision
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ContractError("creation request must be 1–4096 bytes")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {"requestId", "template", "after"}:
                    raise ContractError("creation needs requestId, template and after")
                request_id = str(uuid.UUID(body["requestId"]))
                sid = "user-" + uuid.UUID(request_id).hex
                with lock:
                    refresh_sources()
                    intent = {"requestId": request_id, "template": body["template"], "after": body["after"]}
                    existing = catalog.get(sid)
                    if existing:
                        if existing.get("creation") != intent:
                            raise EditConflict("creation identity already belongs to a different request")
                    else:
                        if body["after"] not in catalog:
                            raise EditConflict("insertion anchor is no longer available; reload the deck")
                        spec = make_starter(body["template"], sid, datetime.now(timezone.utc).isoformat(), body["after"])
                        spec["creation"] = intent
                        candidate = copy.deepcopy(state)
                        candidate.setdefault("createdSlides", {})[sid] = spec
                        merged = load_catalog(slides_dir, candidate["createdSlides"])
                        candidate["order"].insert(candidate["order"].index(body["after"])+1, sid)
                        candidate = validate_state_snapshot(candidate, candidate, merged)
                        atomic_write_json(state_path, candidate)
                        state, catalog = candidate, merged
                        source_revision = catalog_revision(catalog)
                    payload = bootstrap(sid)
                response(self, 200 if existing else 201, payload)
            except EditConflict as exc:
                response(self, 409, {"error": str(exc)})
            except (ContractError, ValueError, TypeError, AttributeError, KeyError) as exc:
                response(self, 400, {"error": str(exc)})
            except OSError as exc:
                response(self, 503, {"error": str(exc)})

        def _upload_asset(self) -> None:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            extension = ALLOWED_ASSETS.get(content_type)
            if extension is None:
                response(self, 415, {"error": "supported images: PNG, JPEG, WebP, GIF, SVG"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                response(self, 400, {"error": "invalid Content-Length"})
                return
            if length <= 0 or length > MAX_ASSET_BYTES:
                response(self, 413, {"error": "image is too large or empty"})
                return
            raw = self.rfile.read(length)
            original = raw
            original_extension = extension
            try:
                raw, suffix = display_bytes(raw, "." + extension)
                extension = suffix.lstrip(".")
            except (OSError, ValueError) as exc:
                response(self, 400, {"error": f"invalid display image: {exc}"})
                return
            digest = hashlib.sha256(raw).hexdigest()
            name = f"{digest}.{extension}"
            path = uploads_dir / name
            try:
                if original != raw:
                    original_digest = hashlib.sha256(original).hexdigest()
                    retained = uploads_dir / "originals" / f"{original_digest}.{original_extension}"
                    if not retained.exists():
                        atomic_write_bytes(retained, original)
                if not path.exists():
                    atomic_write_bytes(path, raw)
            except OSError as exc:
                response(self, 500, {"error": str(exc)})
                return
            response(self, 201, {"src": f"uploads/{name}", "sha256": digest, "bytes": len(raw)})

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the ScientificSlideKit pilot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data", type=Path, default=Path("data/live-state.json"))
    parser.add_argument("--slides", type=Path, default=Path("slides"))
    parser.add_argument("--uploads", type=Path, default=Path("data/uploads"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    public_dir = root / "public"
    seed_path = root / "data" / "seed-state.json"
    state_path = args.data if args.data.is_absolute() else root / args.data
    slides_path = args.slides if args.slides.is_absolute() else root / args.slides
    uploads_path = args.uploads if args.uploads.is_absolute() else root / args.uploads

    server = make_server(public_dir, slides_path, seed_path, state_path, uploads_path, args.host, args.port)
    print(f"online-slide listening on http://{args.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
