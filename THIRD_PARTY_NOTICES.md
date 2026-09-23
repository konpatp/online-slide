# Third-party notices

Sidebar drag ordering bundles [SortableJS](https://github.com/SortableJS/Sortable)
under the MIT License. Its version is pinned in `package-lock.json`; the license
is served as `public/sortable.LICENSE`. Rebuild with `npm run build:browser`.

The diagram recipe bundles [JointJS](https://github.com/clientIO/joint),
distributed under the Mozilla Public License 2.0, and its directed-graph layout
package. Source package versions are pinned in `package-lock.json`; the bundled
browser artifact is rebuilt with `npm run build:diagram`.

The vector-geometry recipe bundles [JSXGraph](https://github.com/jsxgraph/jsxgraph),
distributed under LGPL-3.0-or-later or MIT terms, and
[KaTeX](https://github.com/KaTeX/KaTeX), distributed under the MIT License.
Exact versions and transitive notices are retained in `package-lock.json` and
the generated `.LEGAL.txt` files.

Chart panels load [Plotly.js](https://github.com/plotly/plotly.js) 2.35.2 under
the MIT License (`public/plotly.LICENSE`). A deck whose charts use only scatter,
bar or pie traces receives the official `plotly.js-basic-dist-min` partial
bundle; any other trace type selects the full `plotly.js-dist-min` bundle.
Both are pinned in `package-lock.json` and copied by `npm run build:diagram`.
