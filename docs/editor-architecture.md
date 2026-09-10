# Browser and server ownership

The authoring format remains JSON. Human state remains a separate,
revision-checked overlay. Refactoring does not migrate identities or overwrite
saved state.

## Browser

`src/app.js` composes source loading, selection, navigation and renderer
lifetime. This transitional JavaScript shell is checked for missing references;
it must not grow another implementation of an extracted owner.

Strict TypeScript owns the editing behavior:

| Module | Owns |
| --- | --- |
| `editor/model.ts` | Text, table, snapshot and request contracts |
| `editor/snapshot.ts` | Mutable snapshots and replay of post-request intent |
| `editor/save-queue.ts` | One writer, coalescing, conflict/retry transitions |
| `editor/text.ts` | Safe rendering and atomic wording-plus-formatting commands |
| `editor/tables.ts` | Stable identities, structural commands, paste and resizing |
| `editor/regions.ts` | Bounded regions and canonical-coordinate gestures |
| `editor/fit.ts` | Fitting and observer lifetime |
| `editor/viewport.ts` | Proportional canvas and fullscreen behavior |

Acknowledging our own save does not reconstruct unchanged slide DOM. Only
changed remote content/source requires rendering. The browser keeps the active
editing node and caret; `browser_save_lifecycle.py` exercises delayed ACKs.

Each recipe has a module under `src/recipes/`. Recipes own spatial decisions,
not persistence. JointJS, JSXGraph, KaTeX and Plotly retain native rendering
ownership and lazy loading. Recipes and the application composition shell
remain JavaScript in this increment; strict coverage is not claimed for them.

No React runtime is introduced. TSX is appropriate only when a UI feature
benefits from it, not as a prerequisite for typed behavior or a requirement to
replace DOM-native editing and scientific renderers.

## Python

The `slidekit` package preserves `from slidekit import ...`. Dependencies flow
from `common` to overlay validation, source validation, catalog discovery and
state reconciliation/merging. HTTP and file serving remain in `server.py`.
On-disk and transport schemas are unchanged.

## Build and checks

```sh
npm ci
npm run build:browser
./scripts/test.sh
python3 tools/run_browser_checks.py --list
python3 tools/run_browser_checks.py save_lifecycle text_boxes wysiwyg concurrency
```

Edit `src/`, never generated `public/app.js` or `public/recipes.js`. Their URLs
remain stable; content revisions invalidate caches. The fast gate includes
strict type checking, JavaScript reference checking, pure Node tests and
generated-asset equivalence. esbuild erases types; `tsc` verifies them.

Every browser tool declares scratch or read-only-probe mode. The runner
discovers all scratch tests and retires temporary outputs; live probes require
explicit URLs and selection. Pure tests also use automatically retired build
directories. Generated assets are committed, so serving needs no Node install.

References: [TypeScript incremental migration](https://www.typescriptlang.org/tsconfig/allowJs.html),
[esbuild TypeScript support](https://esbuild.github.io/content-types/#typescript),
[React incremental adoption](https://react.dev/learn/add-react-to-an-existing-project),
[contenteditable ownership](https://react.dev/reference/react-dom/components/common).
