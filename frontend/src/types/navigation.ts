export interface ApiLineString {
  type: "LineString";
  coordinates: Array<[number, number]>;
}

export interface InsuranceVoyagePrediction {
  declaration_id: string;
  shipment_id: string;
  declaration_number: string;
  vessel_id: string | null;
  vessel_name: string | null;
  imo: string | null;
  mmsi: string | null;
  status: "eligible" | "estimated" | "ais_stale" | "position_unavailable" | "destination_unresolved" | "destination_mismatch" | "route_pending" | "voyage_completed" | "ambiguous_active_shipments" | "needs_review";
  loading_port_raw: string | null;
  loading_port_normalized: string | null;
  discharge_port_raw: string | null;
  discharge_port_normalized: string | null;
  ais_destination_raw: string | null;
  ais_destination_normalized: string | null;
  destination_normalized: string | null;
  destination_source: "declaration" | "ais_fallback" | null;
  etd: string | null;
  latest_ais_at: string | null;
  route_prediction_id: string | null;
  route_version: number | null;
  progress: number | null;
  remaining_distance_nm: number | null;
  eta: string | null;
  confidence: number | null;
  warnings: string[];
  prediction: NavigationPrediction | null;
}

export interface NavigationPrediction {
  status: "estimated" | "partial" | string;
  vessel_id: string;
  mmsi: string;
  prediction_timestamp: string;
  based_on_observed_at: string;
  destination: {
    port_id: string | null;
    name: string | null;
    confidence: number;
  };
  route: {
    prediction_id: string;
    version: number;
    geojson: ApiLineString;
    remaining_geojson: ApiLineString;
    remaining_distance_nm: number;
    total_distance_nm: number;
    progress: number;
    cross_track_error_nm: number;
    cross_track_error_m: number;
    projected_position: {
      longitude: number;
      latitude: number;
    };
    source: string;
    status: string;
    latest_ais_destination: string | null;
    destination_matches_latest_ais: boolean | null;
  };
  eta: {
    estimated_arrival_at: string | null;
    remaining_hours: number | null;
    estimated_speed_knots: number | null;
    speed_method: string;
    speed_sample_count: number;
    speed_variability: number | null;
    confidence: number;
  };
  risk_zone_crossings: Array<Record<string, unknown>>;
  prediction_quality: {
    confidence: number;
    ais_age_seconds: number | null;
    reroute_reason: string | null;
    warnings: string[];
  };
}
