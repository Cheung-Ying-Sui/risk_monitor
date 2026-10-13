import { ENTITY_TYPE_LABELS, RESULT_STATUS_LABELS, REVIEW_STATUS_LABELS } from "./sanctions-presentation";
import type { ReviewStatus, SanctionsCandidate } from "@/types/sanctions";

function DetailField({ label, value }: { label: string; value?: string }) {
  return <div><span>{label}</span><strong>{value || "—"}</strong></div>;
}

export function ScreeningDetailPanel({ candidate, reviewStatus, note, noteOpen, onReviewStatusChange, onNoteChange, onToggleNote }: {
  candidate: SanctionsCandidate | null;
  reviewStatus: ReviewStatus;
  note: string;
  noteOpen: boolean;
  onReviewStatusChange: (status: ReviewStatus) => void;
  onNoteChange: (note: string) => void;
  onToggleNote: () => void;
}) {
  if (!candidate) return <aside className="screening-detail screening-detail-empty"><span>筛查详情</span><p>请选择一条候选匹配，查看匹配依据及复核状态。</p></aside>;

  const { subject, sanctionsRecord, assessment } = candidate;
  return (
    <aside className="screening-detail" aria-label={`${subject.name} screening detail`}>
      <header className="screening-detail-header"><span>筛查详情 · 演示数据</span><div><h2>{subject.name}</h2><em className={`screening-result-status ${candidate.status}`}>{RESULT_STATUS_LABELS[candidate.status]}</em></div><strong>{candidate.matchScore.toFixed(1)}% <small>匹配度</small></strong></header>
      <div className="screening-detail-scroll">
        <section className="screening-detail-section"><h3>待筛查主体</h3><div className="screening-detail-fields"><DetailField label={subject.entityType === "vessel" ? "船名" : "名称"} value={subject.name} /><DetailField label="主体类型" value={ENTITY_TYPE_LABELS[subject.entityType]} /><DetailField label="国家或地区" value={subject.country} />{subject.entityType === "vessel" ? <><DetailField label="IMO" value={subject.imo} /><DetailField label="MMSI" value={subject.mmsi} /><DetailField label="船旗" value={subject.flag} /><DetailField label="所有人" value={subject.owner} /></> : <DetailField label="注册号" value={subject.registrationNo} />}</div></section>

        <section className="screening-detail-section evidence-section"><h3>匹配依据</h3><div className="match-evidence-list">{candidate.evidence.map(item => <div key={`${item.type}-${item.label}`}><span><small>{item.label}</small><strong>{item.value}</strong></span>{item.score !== undefined && <span className="evidence-score"><b>{item.score}%</b><i><em style={{ width: `${item.score}%` }} /></i></span>}</div>)}</div></section>

        <section className="screening-detail-section"><h3>制裁记录 · 演示数据</h3><div className="sanctions-record-grid"><DetailField label="主要名称" value={sanctionsRecord.primaryName} /><DetailField label="别名" value={sanctionsRecord.aliases.join(" · ")} /><DetailField label="名单" value={sanctionsRecord.listLabel} /><DetailField label="制裁项目" value={sanctionsRecord.programs.join(" · ")} /><DetailField label="主体类型" value={ENTITY_TYPE_LABELS[sanctionsRecord.entityType]} /><DetailField label="参考编号" value={sanctionsRecord.referenceId} /></div></section>

        <section className="screening-detail-section ai-assessment"><h3>AI 初步评估 · 演示数据</h3><p>{assessment.summary}</p><div className="assessment-facts"><DetailField label="评估结论" value={assessment.assessment} /><DetailField label="置信度" value={assessment.confidence} /></div><div className="assessment-columns"><div><span>主要依据</span><ul>{assessment.keyReasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div><div><span>缺失信息</span>{assessment.missingInformation.length ? <ul>{assessment.missingInformation.map(item => <li key={item}>{item}</li>)}</ul> : <strong>未发现</strong>}</div></div><div className="assessment-next-step"><span>建议下一步</span><strong>{assessment.recommendedNextStep}</strong></div><small>仅供初步辅助参考，不构成法律或合规结论</small></section>

        <section className="screening-detail-section review-section"><h3>复核状态</h3><label><span>当前状态</span><select value={reviewStatus} onChange={event => onReviewStatusChange(event.target.value as ReviewStatus)}><option value="not_reviewed">{REVIEW_STATUS_LABELS.not_reviewed}</option><option value="under_review">{REVIEW_STATUS_LABELS.under_review}</option><option value="cleared">{REVIEW_STATUS_LABELS.cleared}</option><option value="confirmed">{REVIEW_STATUS_LABELS.confirmed}</option><option value="escalated">{REVIEW_STATUS_LABELS.escalated}</option></select></label><div className="review-actions"><button type="button" onClick={() => onReviewStatusChange("cleared")}>排除匹配</button><button type="button" className="confirm" onClick={() => onReviewStatusChange("confirmed")}>确认匹配</button><button type="button" className="escalate" onClick={() => onReviewStatusChange("escalated")}>升级处理</button><button type="button" onClick={onToggleNote}>添加备注</button></div>{noteOpen && <label className="review-note"><span>复核备注 · 仅本地保存</span><textarea value={note} onChange={event => onNoteChange(event.target.value)} placeholder="补充复核说明…" /></label>}</section>
      </div>
    </aside>
  );
}
