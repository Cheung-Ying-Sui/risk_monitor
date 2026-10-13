import { ENTITY_TYPE_LABELS, formatScreenedAt, RESULT_STATUS_LABELS, REVIEW_STATUS_LABELS } from "./sanctions-presentation";
import type { ScreeningRecord } from "@/types/sanctions";

export function ScreeningHistoryTable({ records }: { records: ScreeningRecord[] }) {
  return (
    <div className="screening-history-wrap">
      <table className="screening-history-table">
        <thead><tr><th>日期</th><th>主体</th><th>类型</th><th>结果</th><th>匹配度</th><th>名单</th><th>复核状态</th><th>筛查人员</th></tr></thead>
        <tbody>{records.map(record => <tr key={record.id}><td>{formatScreenedAt(record.screenedAt)}</td><td><strong>{record.subject.name}</strong></td><td>{ENTITY_TYPE_LABELS[record.subject.entityType]}</td><td><span className={`screening-result-status ${record.result}`}>{RESULT_STATUS_LABELS[record.result]}</span></td><td>{record.matchScore.toFixed(1)}%</td><td>{record.sanctionsList ?? "—"}</td><td><span className={`review-status-text ${record.reviewStatus}`}>{REVIEW_STATUS_LABELS[record.reviewStatus]}</span></td><td>{record.screenedBy}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
