import { build } from "esbuild";

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
