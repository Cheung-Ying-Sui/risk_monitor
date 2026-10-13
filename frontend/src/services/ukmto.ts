import type { MaritimeIntelligenceEvent, UKMTOIncidentType } from "@/types/maritime-intelligence";
import { authenticatedFetch } from "@/lib/api-fetch";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000").replace(/\/$/, "");
export interface UKMTOIncident {
  external_id: string;
  incident_type: UKMTOIncidentType;
  title: string | null;
  description: string | null;
  incident_time: string | null;
  published_at: string | null;
  last_seen_at: string | null;
  source_updated_at: string | null;
  location_text: string | null;
  latitude: number | null;
  longitude: number | null;
  location_precision: string | null;
  region: string | null;
  vessel_type: string | null;
  source_url: string;
}

export interface IncidentQuery {
  category: "all" | UKMTOIncidentType;
  timeRange: "all" | "7d" | "30d" | "custom";
  start: string;
  end: string;
}

export function incidentToEvent(row: UKMTOIncident): MaritimeIntelligenceEvent {
  return {
    id: row.external_id, title: row.title || row.external_id, category: row.incident_type,
    severity: "unknown", occurredAt: row.incident_time, publishedAt: row.published_at,
    lastSeenAt: row.last_seen_at, sourceUpdatedAt: row.source_updated_at,
    latitude: row.latitude, longitude: row.longitude,
    locationName: row.location_text || row.region || "位置未提供",
    locationPrecision: row.location_precision || "unknown", region: row.region,
    vesselType: row.vessel_type, summary: row.description || "来源未提供事件描述。",
    sources: [{ id: "ukmto", name: "UKMTO", url: row.source_url }],
  };
}

export function hasCoordinates(event: MaritimeIntelligenceEvent): event is MaritimeIntelligenceEvent & { latitude: number; longitude: number } {
  return typeof event.latitude === "number" && typeof event.longitude === "number"
    && Number.isFinite(event.latitude) && Number.isFinite(event.longitude)
    && Math.abs(event.latitude) <= 90 && Math.abs(event.longitude) <= 180;
}

export function incidentQueryParams(query: IncidentQuery, now = Date.now()): URLSearchParams {
  const params = new URLSearchParams({ limit: "1000" });
  if (query.category !== "all") params.set("incident_type", query.category);
  if (query.timeRange === "custom") {
    if (!query.start || !query.end || query.start > query.end) throw new Error("请选择有效的开始和结束日期。");
    params.set("from", `${query.start}T00:00:00Z`);
    params.set("to", `${query.end}T23:59:59.999Z`);
  } else if (query.timeRange !== "all") {
    params.set("from", new Date(now - (query.timeRange === "7d" ? 7 : 30) * 86400000).toISOString());
    params.set("to", new Date(now).toISOString());
  }
  return params;
}

export interface VesselRiskCount {
  vessel_id: string | null;
  imo: string | null;
  mmsi: string | null;
  name: string;
  latest_position: { latitude: number; longitude: number; observed_at: string } | null;
  calculation_status: "ok" | "position_stale" | "position_unavailable";
  radius_nm: number;
  event_count: number | null;
  event_ids: string[];
}

export async function fetchVesselRiskCounts(params: URLSearchParams, signal: AbortSignal): Promise<VesselRiskCount[]> {
  const response = await authenticatedFetch(`${baseUrl}/api/v1/ukmto/vessel-risk-counts?${params}`, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), cache: "no-store",
  });
  if (!response.ok) throw new Error(`附近事件计算失败（${response.status}），请重试或缩小时间范围。`);
  const body = await response.json();
  if (!Array.isArray(body.items)) throw new Error("附近事件计算返回格式异常。");
  return body.items;
}

export async function fetchUKMTOEvents(query: IncidentQuery, signal: AbortSignal, snapshot?: URLSearchParams): Promise<MaritimeIntelligenceEvent[]> {
  const params = new URLSearchParams(snapshot ?? incidentQueryParams(query));
  const events = new Map<string, MaritimeIntelligenceEvent>();
  let offset = 0;
  while (true) {
    params.set("offset", String(offset));
    const response = await authenticatedFetch(`${baseUrl}/api/v1/ukmto/incidents?${params}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), cache: "no-store",
    });
    if (!response.ok) throw new Error(`UKMTO 事件加载失败（${response.status}），请稍后重试。`);
    const page = await response.json() as { items: UKMTOIncident[]; has_more: boolean; next_offset: number | null };
    if (!Array.isArray(page.items)) throw new Error("事件数据格式异常，请稍后重试。");
    for (const row of page.items) events.set(row.external_id, incidentToEvent(row));
    if (!page.has_more) break;
    if (typeof page.next_offset !== "number" || !Number.isInteger(page.next_offset) || page.next_offset <= offset) throw new Error("事件分页异常，请稍后重试。");
    offset = page.next_offset;
  }
  return [...events.values()];
}
