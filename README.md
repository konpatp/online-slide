# online-slide

A small, dependency-free reference implementation of a browser-based slide
editor. It is deliberately filled with synthetic demo content so it can be
shared publicly and used as a starting point for another project.

The demo shows the interaction pattern that matters for a high-latency link:

- the slide canvas changes immediately (optimistic UI);
- rapid moves, visibility changes, and text edits are coalesced into the newest
  snapshot rather than waiting for each previous gesture;
- the server persists JSON atomically and checks a revision before accepting a
  write; and
- a stale editor receives a visible `409 Conflict` state instead of silently
  overwriting someone else's changes.

There are no framework or runtime dependencies. The browser uses ordinary DOM
APIs and `fetch()`, and the server uses Python's standard library.

## Run it

```bash
git clone git@github.com:konpatp/online-slide.git
cd online-slide
python3 server.py --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. Click **Enable edit**, then try:

1. moving a thumbnail with ↑/↓;
2. hiding a slide with the eye button;
3. editing a title or body directly on the canvas; and
4. making several changes before the save indicator returns to **Saved**.

The browser stores the latest accepted snapshot in `data/live-state.json`.
That file is ignored by Git; `data/seed.json` is the resettable demo deck.

## Edit protocol

`GET /api/deck-state` returns:

```json
{
  "schema": "online-slide/demo@1",
  "revision": 3,
  "order": ["welcome", "signal"],
  "hidden": [],
  "slides": {"welcome": {"title": "...", "body": "...", "accent": "#2f6fed"}}
}
```

The client sends the same snapshot to `POST /api/deck-state` together with its
`baseRevision`. The server returns the new revision on success. If another
editor has already saved, the server returns `409` and the accepted snapshot;
the client shows that conflict instead of guessing how to merge prose or
ordering.

The server write uses a temporary file plus `os.replace`, so a refresh cannot
observe a partially written state file. The browser has one in-flight request
and one pending latest snapshot; this is the key coalescing rule that keeps a
remote editor responsive.

## Tests

```bash
python3 -m unittest discover -s tests -v
node --check public/app.js
python3 -m py_compile server.py
```

## Extending the demo

The project is intentionally easy for another coding agent to pick up:

- change only `data/seed.json` to provide different mock slides;
- keep the revision and atomic-write contract when adding fields;
- put presentation-only behavior in `public/app.js` and visual styling in
  `public/styles.css`; and
- add a server test before changing conflict or persistence behavior.

This repository is a reference demo, not an authentication or multi-tenant
production service. Put it behind your own identity layer before exposing
private material.
