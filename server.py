#!/usr/bin/env python3
"""Dependency-free server for the ScientificSlideKit pilot.

Authored SlideSpecs are loaded independently from ``slides/*.json``. Mutable
human state contains only order, visibility, and semantic component overlays.
Both source and state revisions participate in saves, so a source change can
never silently retarget a live edit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from slidekit import (
    ContractError,
    STATE_SCHEMA,
    catalog_receipt,
    catalog_revision,
    empty_state,
    load_catalog,
    reconcile_state,
    validate_state_snapshot,
)


MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 8 * 1024 * 1024
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
    catalog = load_catalog(slides_dir)
    source_revision = catalog_revision(catalog)
    state, changed = reconcile_state(load_state(seed_path, state_path), catalog)
    if changed:
        atomic_write_json(state_path, state)

    def response(handler: SimpleHTTPRequestHandler, status: int, payload: Any) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def refresh_sources() -> None:
        nonlocal catalog, source_revision, state
        candidate = load_catalog(slides_dir)
        candidate_revision = catalog_revision(candidate)
        if candidate_revision == source_revision:
            return
        reconciled, reconciled_changed = reconcile_state(state, candidate)
        catalog = candidate
        source_revision = candidate_revision
        if reconciled_changed:
            state = reconciled
            atomic_write_json(state_path, state)

    def deck_payload() -> dict[str, Any]:
        payload = dict(state)
        payload["order"] = list(state["order"])
        payload["hidden"] = list(state["hidden"])
        payload["overlays"] = json.loads(json.dumps(state["overlays"]))
        payload["sourceRevision"] = source_revision
        payload["slides"] = catalog
        return payload

    class Handler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

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
            route = urlsplit(self.path).path
            try:
                with lock:
                    refresh_sources()
                    if route == "/api/health":
                        response(self, 200, {
                            "ok": True,
                            "stateSchema": STATE_SCHEMA,
                            "catalog": catalog_receipt(catalog),
                            "stateRevision": state["revision"],
                        })
                        return
                    if route == "/api/deck-state":
                        response(self, 200, deck_payload())
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
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            nonlocal state
            route = urlsplit(self.path).path
            if route == "/api/assets":
                self._upload_asset()
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
                if base_revision != int(state["revision"]) or base_source_revision != source_revision:
                    response(self, 409, {"error": "revision conflict", "state": deck_payload()})
                    return
                try:
                    state = validate_state_snapshot(body.get("snapshot"), state, catalog)
                    atomic_write_json(state_path, state)
                except (ContractError, OSError) as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                response(self, 200, deck_payload())

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
            digest = hashlib.sha256(raw).hexdigest()
            name = f"{digest}.{extension}"
            path = uploads_dir / name
            try:
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
