// Bundles the MV3 extension into dist/ with esbuild. `node build.mjs --watch` rebuilds on change.
import { build, context } from "esbuild";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const watch = process.argv.includes("--watch");
const prod = process.env.NODE_ENV === "production" || !watch;
rmSync("dist", { recursive: true, force: true });
mkdirSync("dist", { recursive: true });
cpSync("public", "dist", { recursive: true });

const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const manifest = JSON.parse(readFileSync("manifest.json", "utf8"));
manifest.version = pkg.version;
writeFileSync("dist/manifest.json", JSON.stringify(manifest, null, 2));

const options = {
  entryPoints: {
    background: "src/background/index.ts",
    content: "src/content/index.ts",
    popup: "src/popup/popup.tsx",
    sidepanel: "src/sidepanel/sidepanel.tsx",
  },
  outdir: "dist",
  bundle: true,
  format: "iife",
  target: "chrome116",
  minify: prod,
  sourcemap: watch ? "inline" : false,
  jsx: "automatic",
  define: { "process.env.NODE_ENV": JSON.stringify(prod ? "production" : "development") },
  legalComments: "none",
  logLevel: "info",
};

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
} else {
  await build(options);
}
