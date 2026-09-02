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
