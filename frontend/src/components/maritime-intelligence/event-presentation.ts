import type { MaritimeEventCategory, MaritimeEventSeverity, UKMTOIncidentType } from "@/types/maritime-intelligence";

export const UKMTO_CATEGORIES: readonly UKMTOIncidentType[] = [
  "attack",
  "suspicious_activity",
  "hijack",
  "advisory",
  "military_interaction",
  "unknown",
];

export const CATEGORY_PRESENTATION: Record<MaritimeEventCategory, { label: string; shortLabel: string }> = {
  attack: { label: "袭击", shortLabel: "袭击" },
  suspicious_activity: { label: "可疑活动", shortLabel: "可疑" },
  hijack: { label: "劫持", shortLabel: "劫持" },
  advisory: { label: "通告", shortLabel: "通告" },
  military_interaction: { label: "军事活动", shortLabel: "军事" },
  unknown: { label: "未分类", shortLabel: "其他" },
  security: { label: "安全事件", shortLabel: "安全" },
  piracy: { label: "海盗事件", shortLabel: "海盗" },
  war_conflict: { label: "战争／冲突", shortLabel: "冲突" },
  port_disruption: { label: "港口中断", shortLabel: "港口" },
  chokepoint: { label: "航运要道", shortLabel: "要道" },
  weather: { label: "恶劣天气", shortLabel: "天气" },
  marine_casualty: { label: "海事事故", shortLabel: "事故" },
};

export const SEVERITY_LABELS: Record<MaritimeEventSeverity, string> = {
  unknown: "未评级",
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

export const PRECISION_LABELS: Record<string, string> = {
  exact: "来源明确坐标", approximate: "近似位置", region: "海域范围", unknown: "精度未知",
};

export function formatRelativeTime(occurredAt: string | null | undefined) {
  if (!occurredAt || !Number.isFinite(Date.parse(occurredAt))) return "时间未提供";
  const elapsed = Date.now() - Date.parse(occurredAt);
  if (elapsed < 0) return formatOccurredAt(occurredAt);
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} 小时前` : `${Math.floor(hours / 24)} 天前`;
}

export function formatOccurredAt(occurredAt: string | null | undefined) {
  if (!occurredAt || !Number.isFinite(Date.parse(occurredAt))) return "未提供";
  return new Intl.DateTimeFormat("zh-CN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(occurredAt)).replace(",", " ·") + " UTC";
}
