# online-slide · ScientificSlideKit

A public reference implementation for fast scientific slide authoring
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

The compiled JointJS, JSXGraph, and KaTeX runtimes are committed, so viewing
and editing do not require Node. To change them, run
`npm ci && npm run build:diagram`.

Open <http://127.0.0.1:8000/>. Enable edit mode to:

- edit any semantic text leaf directly;
- change the selected leaf's font size or theme color;
- reorder or hide slides without changing their source;
- drop an external image onto a gallery cell;
- resize the selected image inside its non-cropping slot; and
- undo an optimistic edit burst.

Choose **Present fullscreen** (or press `F`) to enter a chrome-free browser
presentation. Use the briefly revealed **Exit presentation** control, `F`, or
Escape to return—even from a shared `?present=1` URL. The server normalizes mounted URLs with
or without a trailing slash and fingerprints the browser runtime, so a newly
published math or layout engine cannot be mixed with stale cached code.

Use `?present=1#slide-id` for an exact 16:9 presentation surface, for example:

<http://127.0.0.1:8000/?present=1#mock-growth-trajectories>

## Five canonical recipes

Each file in [`slides/`](slides/) is independently authored and has a permanent
slide id plus stable semantic component ids.

| Recipe | Demonstrates | Geometry owned by the recipe |
|---|---|---|
| `hero-plot` | Multi-series line plot with an incomplete trace | Axes, ticks, grid, legend, line endpoints, protocol strip |
| `evidence-table` | Row-wise minima and one global best cell | Projector-scale table, alignment, emphasis, numeric spacing, whole-table region fit |
| `mechanism-pipeline` | A shared query forks and rejoins | JointJS/Dagre ranks, semantic nodes, orthogonal routing, proportional arrowheads, live rerouting |
| `vector-geometry` | Projection, tangent direction, rotation, and equal norm | JSXGraph equal-aspect coordinates, bounded vectors/arcs, explicit label regions, KaTeX equations |
| `hierarchical-gallery` | Faceted classes, methods, doses, and identity pages | Compact controls, changing metric, persistent view state, snug non-cropping images, fitted caption regions |

The source gives scientific intent and data. The recipe owns repeated spatial
decisions. Custom layout remains possible by adding another recipe rather than
embedding arbitrary markup into a slide file. The diagram and gallery
dependency decisions are recorded in
[`docs/technology-decisions.md`](docs/technology-decisions.md).

Mechanism nodes are content-sized by default: the browser measures their
actual label, detail, and rendered math before JointJS lays out the graph, then
reflows the graph after live text edits. Measurements use the slide's own
untransformed coordinate system, so editor chrome cannot change the result;
the entire content-aware row/column composition is fitted as one group in
both editor and presentation views. Authors do not tune box dimensions. A
deliberately fixed box must opt in with `"sizing": "fixed"` and positive
`width` and `height` values.

Parallel conceptual paths use `"layout": "lanes"`: each node declares a
semantic `lane` and `step`, while the runtime owns sizing, aligned coordinates,
centering, and connector routing. This avoids both Dagre rank drift and manual
pixel placement. Audience-facing recipe labels default to at least 26 pt;
compact controls, protocol metadata, and presenter chrome remain smaller.

Text is always fitted to a declared region rather than positioned as an
unbounded label. Gallery captions have a fixed-height reading region: a short
caption keeps the recipe's maximum size, while a wrapped caption shrinks only
as far as needed to remain contained. Vector labels declare percentage `box`
regions in source, which keeps text off construction lines and makes overflow a
source-validation error instead of a visual surprise. Evidence tables choose
the largest uniform type/padding scale that contains the complete table in the
body region. If even the allowed minimum cannot fit, the browser receipt fails
closed so an author can remove content rather than ship a clipped slide.

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

The normal source gate uses Python's standard library and the already-built
browser bundle:

```bash
./scripts/test.sh
```

`validate_deck.py` checks every independent source, permanent id, component
reference, complete gallery facet matrix, diagram node/edge identity, gallery
asset, snug-frame/non-cropping invariant, and cache-versioned runtime. It emits
a machine-readable receipt and completes in milliseconds.

The optional browser acceptance gate requires Playwright and exercises actual
click/type/format/save/reload, slide ordering, external image drop, semantic
overlay persistence, editor-mode KaTeX hydration, fullscreen entry/exit,
component geometry, and five 1920×1080 captures:

```bash
ONLINE_SLIDE_BROWSER_CHECK=1 ./scripts/test.sh
```

It writes captures and `receipt.json` under `artifacts/browser-smoke/`, which is
ignored by Git. The browser gate also physically drags a JointJS node and proves
that its connector reroutes, then leaves and re-enters the gallery to prove its
selection and page return intact.

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
environment. The application shell remains framework-free; mature diagram,
geometry, and math engines are bundled behind narrow recipe boundaries.
