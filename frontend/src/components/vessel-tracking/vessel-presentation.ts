import type { ApiLatestPosition, ApiVessel, ApiVesselSearchResult, LiveVessel, VesselSearchResult } from "@/types/vessels";
import { vesselDirection } from "@/lib/vessel-marker";

export type VesselSearchIdentifier = { kind: "imo" | "mmsi"; value: string };

const NAVIGATION_STATUS_LABELS: Record<string, string> = {
  "0": "主机航行中", "1": "锚泊", "2": "失控", "3": "操纵能力受限", "4": "受吃水限制", "5": "系泊", "6": "搁浅", "7": "从事捕捞", "8": "帆航中", "9": "高速船预留", "10": "地效翼船预留", "11": "机动船拖带", "12": "机动船顶推或旁拖", "13": "预留", "14": "AIS 搜救发射器", "15": "未定义",
};

export function navigationStatusLabel(value: string | null) {
  const normalized = value?.trim();
  if (!normalized) return "暂无数据";
  if (NAVIGATION_STATUS_LABELS[normalized]) return NAVIGATION_STATUS_LABELS[normalized];
  if (/^\d+$/.test(normalized)) return `未知（${normalized}）`;
  return normalized;
}

export function toLiveVessel(vessel: ApiVessel, position: ApiLatestPosition): LiveVessel {
  if (typeof position.latitude !== "number" || typeof position.longitude !== "number"
    || !Number.isFinite(position.latitude) || !Number.isFinite(position.longitude)
    || Math.abs(position.latitude) > 90 || Math.abs(position.longitude) > 180) {
    throw new Error("AIS 船位坐标无效。");
  }
  return {
    id: vessel.id,
    name: vessel.name?.trim() || "未命名船舶",
    imo: vessel.imo?.trim() || null,
    mmsi: vessel.mmsi?.trim() || null,
    shipType: vessel.ship_type?.trim() || null,
    position: [position.longitude, position.latitude],
    sog: position.sog,
    cog: position.cog,
    heading: position.heading,
    markerDirection: vesselDirection(position.heading, position.cog),
    navigationStatus: navigationStatusLabel(position.navigation_status),
    destination: position.destination?.trim() || null,
    observedAt: position.observed_at,
    aisStatus: "ONLINE",
  };
}

export function toVesselSearchResult(result: ApiVesselSearchResult): VesselSearchResult {
  return {
    id: result.id,
    name: result.name?.trim() || "未命名船舶",
    imo: result.imo?.trim() || null,
    mmsi: result.mmsi?.trim() || null,
    shipType: result.ship_type?.trim() || null,
    isTracked: result.is_tracked,
    latestPosition: result.latest_position ? {
      position: [result.latest_position.longitude, result.latest_position.latitude],
      sog: result.latest_position.sog,
      cog: result.latest_position.cog,
      heading: result.latest_position.heading,
      navigationStatus: navigationStatusLabel(result.latest_position.navigation_status),
      destination: result.latest_position.destination?.trim() || null,
      observedAt: result.latest_position.observed_at,
    } : null,
  };
}

export function parseVesselSearchIdentifier(query: string): VesselSearchIdentifier | null {
  const normalized = query.trim().replace(/^(IMO|MMSI)\s*/i, "").replace(/\s+/g, "");
  if (/^\d{7}$/.test(normalized)) return { kind: "imo", value: normalized };
  if (/^\d{9}$/.test(normalized)) return { kind: "mmsi", value: normalized };
  return null;
}

export function formatCoordinate(value: number, axis: "latitude" | "longitude") {
  const positive = axis === "latitude" ? "N" : "E";
  const negative = axis === "latitude" ? "S" : "W";
  return `${Math.abs(value).toFixed(5)}°${value >= 0 ? positive : negative}`;
}

export function formatNullableNumber(value: number | null, suffix = "") {
  return value === null ? "—" : `${value.toFixed(1)}${suffix}`;
}

export function formatObservedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "UTC" }).format(date).replace(",", " ·") + " UTC";
}

export function formatAisAge(value: string, now = Date.now()) {
  const observedAt = new Date(value).getTime();
  if (Number.isNaN(observedAt)) return "更新时间未知";
  const elapsedMinutes = Math.max(0, Math.floor((now - observedAt) / 60_000));
  if (elapsedMinutes < 1) return "刚刚";
  if (elapsedMinutes < 60) return `${elapsedMinutes} 分钟前`;
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours} 小时前`;
  return `${Math.floor(elapsedHours / 24)} 天前`;
}
