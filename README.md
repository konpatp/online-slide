# online-slide · ScientificSlideKit pilot

A public, dependency-free vertical slice for fast scientific slide authoring
and revision-safe browser editing. All content and data in this repository are
synthetic. It contains no private research evidence or internal project names.

The pilot answers four practical questions with working code:

1. Can authors describe plots, tables, diagrams, and galleries without solving
   slide geometry from scratch?
2. Can contributors add independent slide files without editing one shared
   deck source or order file?
3. Can human order, visibility, text formatting, and image replacement survive
   source rebuilds?
4. Can the common validation path remain nearly instantaneous while a real
   1920×1080 browser check is reserved for acceptance?

## Run it

```bash
git clone git@github.com:konpatp/online-slide.git
cd online-slide
python3 server.py --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. Enable edit mode to:

- edit any semantic text leaf directly;
- change the selected leaf's font size or theme color;
- reorder or hide slides without changing their source;
- drop an external image onto a gallery cell;
- resize the selected image inside its non-cropping slot; and
- undo an optimistic edit burst.

Use `?present=1#slide-id` for an exact 16:9 presentation surface, for example:

<http://127.0.0.1:8000/?present=1#mock-growth-trajectories>

## Four canonical recipes

Each file in [`slides/`](slides/) is independently authored and has a permanent
slide id plus stable semantic component ids.

| Recipe | Demonstrates | Geometry owned by the recipe |
|---|---|---|
| `hero-plot` | Multi-series line plot with an incomplete trace | Axes, ticks, grid, legend, line endpoints, protocol strip |
| `evidence-table` | Row-wise minima and one global best cell | Projector-scale table, alignment, emphasis, numeric spacing |
| `mechanism-diagram` | Semantic nodes and anchored directed connectors | Node placement, connector endpoints, arrowheads, edge labels |
| `matched-gallery` | Three identities across five matched conditions | Non-cropping grid, row/column alignment, image drop zones |

The source gives scientific intent and data. The recipe owns repeated spatial
decisions. Custom layout remains possible by adding another recipe rather than
embedding arbitrary markup into a slide file.

## Concurrency and human authority

The repository separates three kinds of state:

```text
slides/*.json                 immutable contributor-owned SlideSpecs
data/live-state.json          service-owned order, visibility, and overlays
data/uploads/<sha256>.*       content-addressed human image replacements
```

The service discovers new slide files and inserts them through their optional
`placement.after` intention. Existing human order is never regenerated from
source. Two contributors can therefore add two different files without
touching a shared order document.

Human edits are stored against semantic targets such as:

```text
mock-growth-trajectories @ headline
mock-matched-gallery @ image-01-a
```

The server checks both the mutable state revision and a hash of the complete
source catalog. An edited semantic leaf may move among siblings without losing
its override. Removing an edited leaf or a published slide fails closed rather
than silently moving or discarding the human change.

## Fast path and browser acceptance

The normal source gate uses only Python's standard library:

```bash
./scripts/test.sh
```

`validate_deck.py` checks every independent source, permanent id, component
reference, recipe contract, gallery asset, and non-cropping invariant. It emits
a machine-readable receipt and should complete in milliseconds.

The optional browser acceptance gate requires Playwright and exercises actual
click/type/format/save/reload, slide ordering, external image drop, semantic
overlay persistence, component geometry, and four 1920×1080 captures:

```bash
ONLINE_SLIDE_BROWSER_CHECK=1 ./scripts/test.sh
```

It writes captures and `receipt.json` under `artifacts/browser-smoke/`, which is
ignored by Git.

## Add a slide independently

Copy the closest file from [`slides/`](slides/) and change:

- `id` to a new permanent id;
- `createdAt` for deterministic simultaneous insertion;
- `placement.after` to the intended narrative anchor;
- semantic `components`; and
- the selected recipe's `data`.

Do not edit `data/live-state.json`. The service owns reconciliation and the
human owns the accepted order.

## Scope

This is a deliberately small reference implementation, not a hosted
multi-tenant service. Add authentication, authorization, durable object
storage, and production observability before exposing it outside a trusted
environment. The code remains intentionally framework-free so another coding
agent can inspect the complete source-to-render path without a build tool.
