import type { ApiLatestPosition, ApiTrackPoint, ApiTrackingStatus, ApiVessel, ApiVesselSearchResult } from "@/types/vessels";
import type { NavigationPrediction, InsuranceVoyagePrediction } from "@/types/navigation";
import { authenticatedFetch } from "@/lib/api-fetch";

const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

export class VesselApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "VesselApiError";
  }
}

function apiUrl(path: string) {
  const baseUrl = configuredBaseUrl || "http://localhost:8000";
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function responseMessage(response: Response) {
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    // The status and endpoint still provide a useful service-layer error below.
  }
  return `Vessel API request failed with HTTP ${response.status}.`;
}

interface VesselRequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  signal?: AbortSignal;
}

async function requestJson<T>(path: string, options: VesselRequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedFetch(apiUrl(path), {
      method: options.method ?? "GET",
      headers: { Accept: "application/json", ...(options.body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new VesselApiError("无法连接船舶数据服务，请确认 FastAPI 已启动。");
  }

  if (!response.ok) throw new VesselApiError(await responseMessage(response), response.status);

  try {
    return await response.json() as T;
  } catch {
    throw new VesselApiError("Vessel API returned invalid JSON.", response.status);
  }
}

export async function getVessels(signal?: AbortSignal): Promise<ApiVessel[]> {
  const vessels = await requestJson<unknown>("/api/v1/vessels", { signal });
  if (!Array.isArray(vessels)) throw new VesselApiError("Vessel API returned an invalid vessel list.");
  return vessels as ApiVessel[];
}

export async function getHistoricalVessels(signal?: AbortSignal): Promise<ApiVessel[]> {
  const vessels = await requestJson<unknown>("/api/v1/vessels/history/vessels", { signal });
  if (!Array.isArray(vessels)) throw new VesselApiError("Vessel API returned an invalid historical vessel list.");
  return vessels as ApiVessel[];
}

export async function getLatestPosition(vesselId: string, signal?: AbortSignal): Promise<ApiLatestPosition> {
  const position = await requestJson<unknown>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/latest-position`, { signal });
  if (!position || typeof position !== "object") throw new VesselApiError("Vessel API returned an invalid latest position.");
  return position as ApiLatestPosition;
}

export async function getVesselTrack(vesselId: string, limit = 1000, signal?: AbortSignal): Promise<ApiTrackPoint[]> {
  const points = await requestJson<unknown>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/track?limit=${limit}`, { signal });
  if (!Array.isArray(points)) throw new VesselApiError("Vessel API returned an invalid track.");
  return points as ApiTrackPoint[];
}

export async function getNavigationPrediction(vesselId: string, signal?: AbortSignal): Promise<NavigationPrediction> {
  const prediction = await requestJson<unknown>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/navigation-prediction`, { signal });
  if (!prediction || typeof prediction !== "object") throw new VesselApiError("Vessel API returned an invalid navigation prediction.");
  return prediction as NavigationPrediction;
}

export async function getInsuranceVoyagePredictions(signal?: AbortSignal): Promise<InsuranceVoyagePrediction[]> {
  const result = await requestJson<{ items: InsuranceVoyagePrediction[] }>("/api/v1/insurance/voyage-predictions", { signal });
  if (!Array.isArray(result.items)) throw new VesselApiError("承保航程预测数据格式异常。");
  return result.items;
}

async function searchVessel(query: "imo" | "mmsi", value: string, signal?: AbortSignal): Promise<ApiVesselSearchResult> {
  const result = await requestJson<unknown>(`/api/v1/vessels/search?${query}=${encodeURIComponent(value)}`, { signal });
  if (!result || typeof result !== "object") throw new VesselApiError("Vessel API returned an invalid search result.");
  return result as ApiVesselSearchResult;
}

export function searchVesselByImo(imo: string, signal?: AbortSignal) {
  return searchVessel("imo", imo, signal);
}

export function searchVesselByMmsi(mmsi: string, signal?: AbortSignal) {
  return searchVessel("mmsi", mmsi, signal);
}

export async function addTrackingVessel(vesselId: string): Promise<ApiTrackingStatus> {
  return requestJson<ApiTrackingStatus>(`/api/v1/tracking/vessels/${encodeURIComponent(vesselId)}`, { method: "POST" });
}

export async function stopTrackingVessel(vesselId: string): Promise<ApiTrackingStatus> {
  return requestJson<ApiTrackingStatus>(`/api/v1/tracking/vessels/${encodeURIComponent(vesselId)}`, { method: "PATCH", body: { is_active: false } });
}
