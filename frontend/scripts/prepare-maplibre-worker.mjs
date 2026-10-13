import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const mapLibreDistribution = path.join(frontendDirectory, "node_modules", "maplibre-gl", "dist");
const publicDirectory = path.join(frontendDirectory, "public");
const workerAssets = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

await mkdir(publicDirectory, { recursive: true });
await Promise.all(workerAssets.map(fileName => copyFile(
  path.join(mapLibreDistribution, fileName),
  path.join(publicDirectory, fileName),
)));

console.log(`MapLibre worker 已准备：${workerAssets.map(fileName => `/${fileName}`).join("、")}`);
