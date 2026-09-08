import { build } from "esbuild";
import { readFile, writeFile, copyFile } from "node:fs/promises";

async function normalizeBundle(path) {
  const source = await readFile(path, "utf8");
  await writeFile(path, source.replace(/[ \t]+$/gm, ""), "utf8");
}

await build({
  entryPoints: ["src/joint-diagram.js"],
  bundle: true,
  minify: true,
  format: "iife",
  outfile: "public/joint-diagram.js",
  legalComments: "linked",
  sourcemap: false,
  target: ["es2020"],
});
await normalizeBundle("public/joint-diagram.js");

for (const runtime of ["geometry-runtime", "math-runtime"]) {
await build({
  entryPoints: [`src/${runtime}.js`],
  bundle: true,
  minify: true,
  format: "iife",
  outfile: `public/${runtime}.js`,
  legalComments: "linked",
  sourcemap: false,
  target: ["es2020"],
  loader: {
    ".woff": "file",
    ".woff2": "file",
    ".ttf": "file",
  },
  assetNames: "assets/[name]-[hash]",
});
await normalizeBundle(`public/${runtime}.js`);
}
await copyFile("node_modules/plotly.js-dist-min/plotly.min.js", "public/plotly.min.js");
await copyFile("node_modules/plotly.js-dist-min/LICENSE", "public/plotly.LICENSE");
