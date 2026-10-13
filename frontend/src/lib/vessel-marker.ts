/** Shared with both maps; invalid AIS heading 511 must not rotate the icon. */
export function vesselDirection(heading: number | null, cog: number | null): number {
  return [heading, cog].find((value): value is number => value !== null && Number.isFinite(value) && value >= 0 && value < 360) ?? 0;
}

export function createVesselMarkerBody(direction: number): HTMLSpanElement {
  const body = document.createElement("span");
  body.className = "vessel-marker-body";
  body.style.transform = `rotate(${vesselDirection(direction, null)}deg)`;
  body.setAttribute("aria-hidden", "true");
  return body;
}
