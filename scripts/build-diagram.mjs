import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";

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

await build({
  entryPoints: ["src/geometry-runtime.js"],
  bundle: true,
  minify: true,
  format: "iife",
  outfile: "public/geometry-runtime.js",
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
await normalizeBundle("public/geometry-runtime.js");
