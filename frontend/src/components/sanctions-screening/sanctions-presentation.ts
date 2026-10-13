import type { ReviewStatus, ScreeningEntityType, ScreeningResultStatus } from "@/types/sanctions";

export const ENTITY_TYPE_LABELS: Record<ScreeningEntityType, string> = {
  company: "公司",
  supplier: "供应商",
  shipowner: "船东",
  vessel: "船舶",
  individual: "个人",
  other: "其他",
};

export const RESULT_STATUS_LABELS: Record<ScreeningResultStatus, string> = {
  clear: "未发现匹配",
  possible_match: "可能匹配",
  likely_match: "高度疑似匹配",
  confirmed_match: "确认匹配",
  review_required: "需要复核",
};

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  not_reviewed: "未复核",
  under_review: "复核中",
  cleared: "已排除",
  confirmed: "已确认",
  escalated: "已升级",
};

export function formatScreenedAt(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" })
    .format(new Date(value)).replace(",", " ·");
}
