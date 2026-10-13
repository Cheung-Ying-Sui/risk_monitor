import type { VesselRiskCount } from "@/services/ukmto";
export type RiskLoadStatus = "loading" | "ready" | "error";
export function vesselRiskLabel(row: VesselRiskCount | undefined, status: RiskLoadStatus): string {
  if (status === "error") return "附近事件计算服务暂不可用";
  if (status === "loading") return "正在计算 500 海里内事件…";
  if (!row || row.calculation_status === "position_unavailable") return "位置不可用，无法计算";
  if (row.calculation_status === "position_stale") return "位置过期，无法计算（AIS 超过 24 小时或时间无效）";
  return row.event_count === 0 ? "当前筛选范围内未发现附近事件" : `500 海里内 ${row.event_count} 条风险事件`;
}
