#!/usr/bin/env python3
"""Small, dependency-free server for the online-slide demo.

The important part of this example is the edit protocol, not a framework:

* the browser applies edits immediately;
* a client coalesces a burst into the newest snapshot;
* the server accepts snapshots with a revision check; and
* the durable JSON write happens before the response is returned.

This is intentionally a teaching server.  Add authentication, authorization,
and a real database before using it for anything beyond a trusted demo.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA = "online-slide/demo@1"
MAX_BODY_BYTES = 512 * 1024


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Replace a state file atomically so a refresh never sees half a write."""

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


def load_seed(seed_path: Path, state_path: Path) -> dict[str, Any]:
    if state_path.exists():
        return read_json(state_path)
    seed = read_json(seed_path)
    atomic_write_json(state_path, seed)
    return seed


def validate_snapshot(candidate: Any, current: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one client snapshot.

    Keeping this strict is important: a browser cannot accidentally save a
    slide id that the server did not publish, or hide an unknown slide.
    """

    if not isinstance(candidate, dict):
        raise ValueError("snapshot must be an object")
    if candidate.get("schema") != SCHEMA:
        raise ValueError("unsupported snapshot schema")
    order = candidate.get("order")
    hidden = candidate.get("hidden")
    slides = candidate.get("slides")
    known = set(current["order"])
    if not isinstance(order, list) or set(order) != known or len(order) != len(known):
        raise ValueError("order must contain each published slide exactly once")
    if not all(isinstance(item, str) for item in order):
        raise ValueError("slide ids must be strings")
    if not isinstance(hidden, list) or not all(isinstance(item, str) for item in hidden):
        raise ValueError("hidden must be a list of slide ids")
    if not set(hidden) <= known:
        raise ValueError("hidden contains an unknown slide")
    if not isinstance(slides, dict) or set(slides) != known:
        raise ValueError("slides must contain each published slide exactly once")

    normalized_slides: dict[str, dict[str, str]] = {}
    for slide_id in known:
        item = slides[slide_id]
        if not isinstance(item, dict):
            raise ValueError("slide content must be an object")
        title = str(item.get("title", "")).strip()[:160]
        body = str(item.get("body", "")).strip()[:600]
        accent = str(item.get("accent", "#2f6fed"))
        if len(accent) != 7 or not accent.startswith("#"):
            raise ValueError("accent must be a hex color")
        try:
            int(accent[1:], 16)
        except ValueError as exc:
            raise ValueError("accent must be a hex color") from exc
        normalized_slides[slide_id] = {"title": title, "body": body, "accent": accent}

    return {
        "schema": SCHEMA,
        "revision": int(current["revision"]) + 1,
        "order": order,
        "hidden": sorted(set(hidden), key=order.index),
        "slides": normalized_slides,
    }


def make_server(
    public_dir: Path,
    seed_path: Path,
    state_path: Path,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Build a server instance.  This function is also used by the tests."""

    lock = threading.RLock()
    state = load_seed(seed_path, state_path)

    def response(handler: SimpleHTTPRequestHandler, status: int, payload: Any) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    class Handler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(public_dir), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            # Keep the demo terminal readable; override with normal logging if
            # this is embedded in another service.
            return

        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler API
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            nonlocal state
            route = urlsplit(self.path).path
            if route == "/api/health":
                response(self, 200, {"ok": True, "schema": SCHEMA})
                return
            if route == "/api/deck-state":
                with lock:
                    payload = dict(state)
                    payload["order"] = list(state["order"])
                    payload["hidden"] = list(state["hidden"])
                    payload["slides"] = dict(state["slides"])
                response(self, 200, payload)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            nonlocal state
            route = urlsplit(self.path).path
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
            except (ValueError, TypeError, json.JSONDecodeError):
                response(self, 400, {"error": "invalid JSON or baseRevision"})
                return
            with lock:
                if base_revision != int(state["revision"]):
                    response(self, 409, {"error": "revision conflict", "state": state})
                    return
                try:
                    state = validate_snapshot(body.get("snapshot"), state)
                    atomic_write_json(state_path, state)
                except (ValueError, OSError) as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                response(self, 200, state)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the online-slide demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data", type=Path, default=Path("data/live-state.json"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    public_dir = root / "public"
    seed_path = root / "data" / "seed.json"
    state_path = args.data if args.data.is_absolute() else root / args.data

    server = make_server(public_dir, seed_path, state_path, args.host, args.port)
    print(f"online-slide listening on http://{args.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
