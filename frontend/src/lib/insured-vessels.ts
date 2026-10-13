import type { DeclaredVessel } from "@/types/insurance";
import type { LiveVessel } from "@/types/vessels";

export interface InsuredLiveVessel {
  declaration: DeclaredVessel;
  vessel: LiveVessel;
}

export function matchesInsuredVessel(
  tracked: { imo: string | null; mmsi?: string | null; name: string },
  insured: DeclaredVessel,
): boolean {
  const trackedImo = tracked.imo?.trim();
  const insuredImo = insured.imo_number?.trim();
  if (trackedImo && insuredImo) return trackedImo === insuredImo;
  if (tracked.mmsi && insured.confirmed_mmsi) return tracked.mmsi.trim() === insured.confirmed_mmsi.trim();
  // A name match is only used when neither side has a usable IMO.
  if (trackedImo || insuredImo) return false;
  return tracked.name.trim().toLocaleLowerCase() === insured.vessel_name.trim().toLocaleLowerCase();
}

export function matchInsuredLiveVessels(insured: DeclaredVessel[], tracked: LiveVessel[]): InsuredLiveVessel[] {
  return insured.flatMap(declaration => {
    const vessel = tracked.find(candidate => matchesInsuredVessel(candidate, declaration));
    return vessel ? [{ declaration, vessel }] : [];
  });
}
