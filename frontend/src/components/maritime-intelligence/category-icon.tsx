import type { MaritimeEventCategory } from "@/types/maritime-intelligence";

// Fixed vector geometry: no platform-dependent emoji/font substitution.
const PATHS: Record<MaritimeEventCategory, string> = {
  attack: "M13 2 4 13h7l-1 9 10-13h-7z",
  suspicious_activity: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M15 12a3 3 0 1 0-6 0 3 3 0 0 0 6 0",
  hijack: "M5 22V3h14l-3 5 3 5H5",
  advisory: "M5 3h14v18H5z M8 7h8 M8 11h8 M8 15h5",
  military_interaction: "m3 3 18 18 M21 3 3 21 M3 17l4 4 M17 3l4 4",
  unknown: "M8 7a4 4 0 1 1 6 4l-2 2v2 M12 18v2",
  security: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6z",
  piracy: "M5 5h14v10l-4 5H9l-4-5z M8 9h2 M14 9h2 M9 15h6",
  war_conflict: "m12 2 2 7 8-3-5 7 5 5-8-1-2 5-2-5-8 1 5-5-5-7 8 3z",
  port_disruption: "M3 21V8h18v13 M7 8V3h10v5 M3 14h18 M12 8v13",
  chokepoint: "M3 3l6 9-6 9 M21 3l-6 9 6 9",
  weather: "M2 8c3-4 6 4 10 0s7 4 10 0 M2 14c3-4 6 4 10 0s7 4 10 0 M2 20c3-4 6 4 10 0s7 4 10 0",
  marine_casualty: "M4 4l16 16 M20 4 4 20",
};
export function CategoryIcon({ category }: { category: MaritimeEventCategory }) {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[category]} /></svg>;
}
export function createCategoryIcon(category: MaritimeEventCategory) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ viewBox: "0 0 24 24", width: "16", height: "16", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(key, value);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", PATHS[category]);
  svg.appendChild(path);
  return svg;
}
