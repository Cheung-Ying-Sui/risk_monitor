"use client";

import { useState } from "react";
import { ScreeningDetailPanel } from "./screening-detail-panel";
import { ScreeningHistoryTable } from "./screening-history";
import { ScreeningResults } from "./screening-results";
import { ScreeningToolbar, type ScreeningMode } from "./screening-toolbar";
import { AiCandidatePanel } from "./ai-candidate-panel";
import { DeclarationScreeningQueue } from "./declaration-screening-queue";
import { screenSanctions, toSanctionsCandidates } from "@/services/sanctions";
import type { ReviewStatus, SanctionsCandidate, SanctionsList, ScreeningEntityType, ScreeningRecord } from "@/types/sanctions";

type WorkspaceTab = "queue" | "screening" | "history";

export function SanctionsScreeningWorkbench() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("queue");
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState<"all" | ScreeningEntityType>("all");
  const [sanctionsList, setSanctionsList] = useState<"all" | SanctionsList>("OFAC");
  const [mode, setMode] = useState<ScreeningMode>("standard");
  const [candidates, setCandidates] = useState<SanctionsCandidate[]>([]);
  const [history, setHistory] = useState<ScreeningRecord[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [reviewStatuses, setReviewStatuses] = useState<Record<string, ReviewStatus>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [noteOpen, setNoteOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [screeningMessage, setScreeningMessage] = useState("请输入主体名称后执行真实 OFAC SDN 筛查。");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [aiCandidates, setAiCandidates] = useState<Awaited<ReturnType<typeof screenSanctions>>["ai_candidates"]>([]);
  const [aiMessage, setAiMessage] = useState<string | null>(null);

  const selectedCandidate = candidates.find(candidate => candidate.id === selectedCandidateId) ?? null;
  const selectedReviewStatus = selectedCandidate ? reviewStatuses[selectedCandidate.id] : "not_reviewed";

  const runScreening = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setScreeningMessage("");
    setSuggestions([]);
    setAiCandidates([]);
    setAiMessage(null);
    try {
      const response = await screenSanctions({ query, entityType, sanctionsList, mode });
      const nextCandidates = toSanctionsCandidates(response, entityType);
      setCandidates(nextCandidates);
      setSelectedCandidateId(nextCandidates[0]?.id ?? null);
      setReviewStatuses(Object.fromEntries(nextCandidates.map(candidate => [candidate.id, candidate.initialReviewStatus])));
      setSuggestions(response.suggestions.map(item => item.name));
      setAiCandidates(response.ai_candidates);
      setAiMessage(response.ai_message);
      setScreeningMessage(response.message ?? `筛查完成，共发现 ${nextCandidates.length} 条正式匹配。`);
      const top = nextCandidates[0];
      setHistory(current => [{
        id: `screen-${Date.now()}`,
        screenedAt: new Date().toISOString(),
        subject: { id: `query-${Date.now()}`, name: response.keyword, entityType: entityType === "all" ? "other" : entityType },
        result: top?.status ?? "clear",
        matchScore: top?.matchScore ?? 0,
        sanctionsList: top?.sanctionsList,
        reviewStatus: "not_reviewed",
        screenedBy: "当前用户",
      }, ...current]);
    } catch (error) {
      setCandidates([]);
      setSelectedCandidateId(null);
      setScreeningMessage(error instanceof Error ? error.message : "制裁筛查失败。");
    } finally {
      setLoading(false);
      setActiveTab("screening");
      setNoteOpen(false);
    }
  };

  const selectCandidate = (candidateId: string) => {
    setSelectedCandidateId(candidateId);
    setNoteOpen(false);
  };

  const updateReviewStatus = (status: ReviewStatus) => {
    if (!selectedCandidate) return;
    setReviewStatuses(current => ({ ...current, [selectedCandidate.id]: status }));
  };

  return (
    <div className={`sanctions-workbench${activeTab === "screening" ? " search-mode" : ""}`}>
      <nav className="screening-tabs sanctions-workspace-tabs" aria-label="制裁筛查视图"><button type="button" className={activeTab === "queue" ? "active" : ""} onClick={() => setActiveTab("queue")}>申报待筛查</button><button type="button" className={activeTab === "screening" ? "active" : ""} onClick={() => setActiveTab("screening")}>名称检索</button><button type="button" className={activeTab === "history" ? "active" : ""} onClick={() => setActiveTab("history")}>检索历史</button></nav>
      {activeTab === "screening" && <ScreeningToolbar query={query} entityType={entityType} sanctionsList={sanctionsList} mode={mode} loading={loading} onQueryChange={setQuery} onEntityTypeChange={setEntityType} onSanctionsListChange={setSanctionsList} onModeChange={setMode} onScreen={runScreening} />}
      {activeTab === "queue" ? <DeclarationScreeningQueue /> : <div className="sanctions-main">
        <section className="screening-primary-panel">
          {activeTab === "screening" ? <><div className={`screening-api-message${candidates.length ? " success" : ""}`}>{screeningMessage}{suggestions.length > 0 && <small>数据库建议完整名称：{suggestions.join("、")}</small>}</div><AiCandidatePanel candidates={aiCandidates} message={aiMessage} onUseCandidate={candidate => setQuery(candidate)} /><ScreeningResults candidates={candidates} selectedCandidateId={selectedCandidateId} onSelectCandidate={selectCandidate} /></> : <ScreeningHistoryTable records={history} />}
        </section>
        <ScreeningDetailPanel candidate={selectedCandidate} reviewStatus={selectedReviewStatus} note={selectedCandidate ? notes[selectedCandidate.id] ?? "" : ""} noteOpen={noteOpen} onReviewStatusChange={updateReviewStatus} onNoteChange={note => selectedCandidate && setNotes(current => ({ ...current, [selectedCandidate.id]: note }))} onToggleNote={() => setNoteOpen(current => !current)} />
      </div>}
    </div>
  );
}
