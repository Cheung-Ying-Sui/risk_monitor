export interface ApiVessel {
  id: string;
  mmsi: string | null;
  imo: string | null;
  name: string | null;
  ship_type: string | null;
}

export interface ApiLatestPosition {
  vessel_id: string;
  latitude: number;
  longitude: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
  navigation_status: string | null;
  destination: string | null;
  observed_at: string;
}

export interface ApiTrackPoint extends ApiLatestPosition {
  id: number | null;
  received_at: string | null;
}

export interface ApiVesselSearchResult extends ApiVessel {
  is_tracked: boolean;
  latest_position: ApiLatestPosition | null;
}

export interface ApiTrackingStatus {
  vessel_id: string;
  is_active: boolean;
}

export interface LiveVessel {
  id: string;
  name: string;
  imo: string | null;
  mmsi: string | null;
  shipType: string | null;
  position: [number, number];
  sog: number | null;
  cog: number | null;
  heading: number | null;
  markerDirection: number;
  navigationStatus: string;
  destination: string | null;
  observedAt: string;
  aisStatus: "ONLINE";
}

export interface LiveVesselLoadIssue {
  vesselId: string;
  kind: "position_not_found" | "position_request_failed" | "stale_position";
  message: string;
}

export interface VesselSearchPosition {
  position: [number, number];
  sog: number | null;
  cog: number | null;
  heading: number | null;
  navigationStatus: string;
  destination: string | null;
  observedAt: string;
}

export interface VesselSearchResult {
  id: string;
  name: string;
  imo: string | null;
  mmsi: string | null;
  shipType: string | null;
  isTracked: boolean;
  latestPosition: VesselSearchPosition | null;
}
