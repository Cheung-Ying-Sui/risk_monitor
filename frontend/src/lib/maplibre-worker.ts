import * as maplibregl from "maplibre-gl";

const MAPLIBRE_WORKER_URL = "/maplibre-gl-worker.mjs";

export function configureMapLibreWorker() {
  maplibregl.setWorkerUrl(MAPLIBRE_WORKER_URL);
}
