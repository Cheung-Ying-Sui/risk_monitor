import type * as maplibregl from "maplibre-gl";

export type MapTheme = "dark" | "light";

const OPEN_FREE_MAP_STYLES: Record<MapTheme, string> = {
  dark: "https://tiles.openfreemap.org/styles/dark",
  light: "https://tiles.openfreemap.org/styles/positron",
};

export function getBaseMapStyle(theme: MapTheme) {
  return OPEN_FREE_MAP_STYLES[theme];
}

export function getBaseMapLabel(theme: MapTheme) {
  return theme === "light" ? "OPENFREEMAP · POSITRON" : "OPENFREEMAP · DARK";
}

export function showOnlyMarineLabels(map: maplibregl.Map) {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type !== "symbol") continue;
    const sourceLayer = "source-layer" in layer ? layer["source-layer"] : undefined;
    map.setLayoutProperty(layer.id, "visibility", sourceLayer === "water_name" ? "visible" : "none");
  }
}
