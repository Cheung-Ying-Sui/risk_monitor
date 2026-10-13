import { ENTITY_TYPE_LABELS, RESULT_STATUS_LABELS } from "./sanctions-presentation";
import type { SanctionsCandidate } from "@/types/sanctions";

function CandidateMatchRow({ candidate, selected, onSelect }: { candidate: SanctionsCandidate; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={`candidate-match-row${selected ? " selected" : ""}`} onClick={onSelect} aria-pressed={selected}>
      <div className="candidate-match-heading"><span><strong>{candidate.subject.name}</strong><small>{ENTITY_TYPE_LABELS[candidate.subject.entityType]} · {candidate.sanctionsList}</small></span><em className={`screening-result-status ${candidate.status}`}>{RESULT_STATUS_LABELS[candidate.status]}</em></div>
      <div className="candidate-match-name"><span>匹配名称</span><strong>{candidate.matchedName}</strong></div>
      <div className="candidate-score"><span><small>匹配度</small><strong>{candidate.matchScore.toFixed(1)}%</strong></span><i><b style={{ width: `${candidate.matchScore}%` }} /></i></div>
    </button>
  );
}

export function ScreeningResults({ candidates, selectedCandidateId, onSelectCandidate }: { candidates: SanctionsCandidate[]; selectedCandidateId: string | null; onSelectCandidate: (candidateId: string) => void }) {
  return (
    <div className="screening-results">
      <header className="screening-results-summary"><span>候选匹配</span><strong>{candidates.length}</strong><small>按匹配度排序</small></header>
      <div className="candidate-match-list">
        {candidates.map(candidate => <CandidateMatchRow key={candidate.id} candidate={candidate} selected={candidate.id === selectedCandidateId} onSelect={() => onSelectCandidate(candidate.id)} />)}
        {!candidates.length && <div className="screening-empty"><strong>未发现候选匹配</strong><span>请调整搜索条件或筛选项后重新执行筛查。</span></div>}
      </div>
    </div>
  );
}
