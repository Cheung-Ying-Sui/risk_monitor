import type { Feature, LineString } from "geojson";

export type PortCallType = "origin" | "scheduled" | "unscheduled" | "bunker" | "destination";
export type VoyageStatus = "completed" | "in_progress" | "abnormal";

export interface VoyagePortCall {
  id: string;
  portName: string;
  countryCode?: string;
  type: PortCallType;
  coordinates: [number, number];
  arrivedAt?: string;
  departedAt?: string;
}

export interface VoyageLeg {
  id: string;
  sequence: number;
  originPort: string;
  destinationPort: string;
  distanceNm?: number;
}

export interface VoyageTrackGeometry {
  fullVoyage: Feature<LineString>;
  legTracks: Record<string, Feature<LineString>>;
}

export interface VoyageHistoryItem {
  id: string;
  originPort: string;
  destinationPort: string;
  startedAt: string;
  completedAt?: string;
  status: VoyageStatus;
  totalDistanceNm?: number;
  portCalls: VoyagePortCall[];
  legs: VoyageLeg[];
  trackGeometry: VoyageTrackGeometry;
}
