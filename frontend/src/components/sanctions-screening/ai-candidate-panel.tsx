import type { SanctionsScreeningResponse } from "@/services/sanctions";

export function AiCandidatePanel({ candidates, message, onUseCandidate }: {
  candidates: SanctionsScreeningResponse["ai_candidates"];
  message: string | null;
  onUseCandidate: (candidate: string) => void;
}) {
  if (!message && candidates.length === 0) return null;
  return (
    <section className="ai-candidate-panel">
      <header><span>DEEPSEEK 辅助筛查</span><small>{candidates.length} 个候选全称</small></header>
      {message && <p>{message}</p>}
      <div className="ai-candidate-list">
        {candidates.map(candidate => (
          <button type="button" key={candidate.query} onClick={() => onUseCandidate(candidate.query)}>
            <span><strong>{candidate.query}</strong><small>{candidate.reason}</small></span>
            <span className={candidate.formal_match ? "formal" : "candidate"}>
              <strong>{candidate.match_score !== null ? `OFAC ${candidate.match_score.toFixed(1)}%` : candidate.ai_probability !== null ? `AI ${candidate.ai_probability.toFixed(0)}%` : "待核验"}</strong>
              <small>{candidate.formal_match ? `候选词检索命中 · ${candidate.matched_name}` : candidate.matched_name ? `库内可能全称 · ${candidate.matched_name}` : "AI 候选 · 点击后重新筛查"}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
