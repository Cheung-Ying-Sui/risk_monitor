import { authenticatedFetch } from "@/lib/api-fetch";

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000").replace(/\/$/, "");

export interface WeatherPort {
  port: { port_code: string; name_zh: string };
  analysis_location: {
    id: string; name: string; is_primary: boolean; verification_status: string;
    requested_latitude: number | null; requested_longitude: number | null;
  };
  coverage_start_utc: string | null;
  coverage_end_utc: string | null;
  data_quality_status: string;
}

export interface HumidityProfile {
  location_id: string;
  scope: {
    eta_date: string; eta_time: string | null; rh_threshold: number;
    historical_years_requested: [number, number]; historical_years_used: number[];
    date_ranges: Array<{ year: number; start: string; end: string }>;
  };
  metrics: {
    mean_rh: number | null; p90_rh: number | null; exceedance_fraction: number | null;
    event_mean_hours: number | null; event_p90_hours: number | null; events_per_year: number | null;
  };
  eta_24h: null | {
    continuous_6h_frequency: number | null; success_count: number;
    valid_window_count: number; excluded_window_count: number;
  };
  quality: {
    valid_hour_count: number; expected_hour_count: number; coverage_fraction: number | null;
    valid_year_count: number; excluded_years: Array<{ year: number; reason: string }>;
    censored_event_count: number; warnings: string[];
  };
  provenance: {
    source: string; model: string; coordinate_status: string; coordinate_source: string | null;
    requested_coordinates: { latitude: number; longitude: number };
    grid_coordinates: { latitude: number; longitude: number } | null;
    data_revision: string | null; method_version: string;
  };
}

export interface HumiditySeasonalBucket {
  index: number;
  valid_hours: number;
  exceedance_hours: number;
  expected_hours: number;
  percentage: number | null;
}

export interface HumiditySeasonal {
  port_code: string;
  location_id: string;
  month: number;
  rh_threshold: number;
  historical_years: [number, number];
  timezone: string;
  monthly: HumiditySeasonalBucket[];
  daily: HumiditySeasonalBucket[];
  provenance: { source: string; model: string; data_revision: string | null };
}

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`湿度数据服务返回 ${response.status}`);
  return response.json() as Promise<T>;
}

export async function fetchWeatherPorts(signal?: AbortSignal): Promise<WeatherPort[]> {
  return jsonOrThrow<WeatherPort[]>(await authenticatedFetch(`${BASE_URL}/api/v1/port-weather/ports`, { signal }));
}

export interface PortArrival {
  vessel_name: string;
  imo_number: string | null;
  eta: string;
  eta_source: "insurance_declaration";
  eta_scope: "declaration_voyage";
  declaration_id: string;
  shipment_id: string;
  discharge_port: string | null;
  matched_port_codes: string[];
}

export interface PortArrivals {
  port_code: string;
  timezone: "Asia/Shanghai";
  window_start: string;
  window_end: string;
  eta_source: "insurance_declaration";
  arrivals: PortArrival[];
}

export async function fetchPortArrivals(portCode: string, signal?: AbortSignal): Promise<PortArrivals> {
  return jsonOrThrow<PortArrivals>(await authenticatedFetch(
    `${BASE_URL}/api/v1/port-weather/ports/${encodeURIComponent(portCode)}/arrivals`,
    { signal },
  ));
}

export async function fetchHumidityProfile(
  portCode: string, etaDate: string, etaTime: string, threshold: number, signal?: AbortSignal,
): Promise<HumidityProfile> {
  const params = new URLSearchParams({ eta_date: etaDate, rh_threshold: String(threshold) });
  if (etaTime) params.set("eta_time", etaTime);
  return jsonOrThrow<HumidityProfile>(await authenticatedFetch(
    `${BASE_URL}/api/v1/port-weather/ports/${encodeURIComponent(portCode)}/profile?${params}`,
    { signal },
  ));
}

export async function fetchHumiditySeasonal(
  portCode: string, month: number, threshold: number, signal?: AbortSignal,
): Promise<HumiditySeasonal> {
  const params = new URLSearchParams({ month: String(month), rh_threshold: String(threshold) });
  return jsonOrThrow<HumiditySeasonal>(await authenticatedFetch(
    `${BASE_URL}/api/v1/port-weather/ports/${encodeURIComponent(portCode)}/seasonal?${params}`,
    { signal },
  ));
}
