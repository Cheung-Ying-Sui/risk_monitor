"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { UnderwritingConfirmationDialog } from "./underwriting-confirmation-dialog";
import { browserDownload, saveReport } from "@/services/report-save";
import {
  downloadDeclarationScreeningReport, generateDeclarationScreeningReport, listDeclarationScreeningCases, reviewDeclarationParty,
  screenDeclarationParty, uploadDeclarationPartyScreenshot, getDeclarationScreeningCase,
} from "@/services/sanctions";
import type { DeclarationScreeningCase, DeclarationScreeningParty } from "@/types/sanctions";

const reviewLabels: Record<string, string> = {
  no_match: "人工复核未发现匹配", possible_match: "疑似匹配",
  confirmed_match: "确认匹配", needs_escalation: "需升级复核",
};

type SavePickerWindow = Window & {
  showSaveFilePicker?: (options: { suggestedName: string; types: Array<{ description: string; accept: Record<string, string[]> }> }) => Promise<FileSystemFileHandle>;
};

function partyKey(party: DeclarationScreeningParty) {
  return `${party.shipment_id}:${party.role}`;
}

type ReviewDraft = { result: string; reviewer: string; note: string };
function savedReview(party: DeclarationScreeningParty | null): ReviewDraft {
  return { result: party?.review?.result ?? "", reviewer: party?.review?.reviewer ?? "", note: party?.review?.note ?? "" };
}
function draftKey(declarationId: string, party: DeclarationScreeningParty) {
  return JSON.stringify([declarationId, partyKey(party), party.name, party.preliminary?.screened_at, party.evidence?.document_id]);
}
function isChanged(draft: ReviewDraft | undefined, party: DeclarationScreeningParty) {
  const saved = savedReview(party);
  return Boolean(draft && (draft.result !== saved.result || draft.reviewer !== saved.reviewer || draft.note !== saved.note));
}

export function DeclarationScreeningQueue() {
  const [cases, setCases] = useState<DeclarationScreeningCase[]>([]);
  const [underwritingId, setUnderwritingId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedPartyKey, setSelectedPartyKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [operation, setOperation] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [preparedReport, setPreparedReport] = useState<{ declarationId: string; sha256: string; filename: string; blob: Blob } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const screenshotInputRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const refreshVersion = useRef(0);
  const beginOperation = (label: string) => {
    if (busyRef.current) return false;
    busyRef.current = true;
    refreshVersion.current += 1;
    setLoading(false);
    setBusy(true);
    setOperation(label);
    setNotice(null);
    return true;
  };
  const endOperation = () => { busyRef.current = false; setBusy(false); setOperation(""); };

  const refresh = useCallback(async () => {
    if (busyRef.current) return;
    const version = ++refreshVersion.current;
    setLoading(true);
    setError(null);
    try {
      const rows = await listDeclarationScreeningCases();
      if (version !== refreshVersion.current) return;
      setCases(rows);
      const linkedId = new URLSearchParams(window.location.search).get("declaration");
      setSelectedId(current => current && rows.some(row => row.declaration_id === current) ? current
        : linkedId && rows.some(row => row.declaration_id === linkedId) ? linkedId : rows[0]?.declaration_id ?? null);
    } catch (cause) {
      if (version === refreshVersion.current) setError(cause instanceof Error ? cause.message : "待筛查列表加载失败。");
    } finally {
      if (version === refreshVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => {
    const onFocus = () => { void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const selectedCase = cases.find(row => row.declaration_id === selectedId) ?? null;
  const party = selectedCase?.parties.find(item => partyKey(item) === selectedPartyKey) ?? selectedCase?.parties[0] ?? null;
  const currentDraftKey = selectedCase && party ? draftKey(selectedCase.declaration_id, party) : "";
  const currentDraft = drafts[currentDraftKey] ?? savedReview(party);
  const { result: reviewResult, reviewer, note } = currentDraft;
  const reviewDirty = Boolean(party && isChanged(drafts[currentDraftKey], party));
  const updateDraft = (value: Partial<ReviewDraft>) => setDrafts(previous => ({
    ...previous, [currentDraftKey]: { ...currentDraft, ...value },
  }));
  const unsavedParties = selectedCase?.parties.filter(item => isChanged(drafts[draftKey(selectedCase.declaration_id, item)], item)) ?? [];
  const completed = selectedCase?.parties.filter(item => item.preliminary && item.evidence && item.review).length ?? 0;
  const reportReady = Boolean(selectedCase?.parties.length && completed === selectedCase.parties.length && !unsavedParties.length);
  const incompleteParties = selectedCase?.parties.filter(item => !item.preliminary || !item.evidence || !item.review) ?? [];

  const selectParty = (next: DeclarationScreeningParty | null) => {
    setSelectedPartyKey(next ? partyKey(next) : null);
    setUploadError(null);
    setReportError(null);
    setNotice(null);
    setError(null);
  };

  const uploadScreenshot = async (file: File) => {
    if (!selectedCase || !party || busyRef.current) return;
    if (screenshotInputRef.current) screenshotInputRef.current.value = "";
    if (file.size > 2 * 1024 * 1024) {
      setUploadError("截图不能超过 2 MB。");
      return;
    }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setUploadError("请上传 PNG、JPEG 或 WebP 格式的截图。");
      return;
    }
    if (party.evidence && !window.confirm("替换截图后，需要重新保存人工复核结论并生成报告。是否继续？")) return;
    if (!beginOperation("正在上传截图…")) return;
    setUploadError(null); setError(null);
    try {
      if (!party.preliminary) {
        const screened = await screenDeclarationParty(selectedCase.declaration_id, party.shipment_id, party.role);
        setCases(rows => rows.map(row => row.declaration_id === screened.declaration_id ? screened : row));
      }
      const updated = await uploadDeclarationPartyScreenshot(selectedCase.declaration_id, party.shipment_id, party.role, file);
      setCases(rows => rows.map(row => row.declaration_id === updated.declaration_id ? updated : row));
      setNotice(`${party.label}的截图已保存，请核查初筛候选并记录人工复核结论。`);
    } catch (cause) {
      setUploadError(cause instanceof Error ? cause.message : "截图上传失败，请重试。");
    } finally {
      if (screenshotInputRef.current) screenshotInputRef.current.value = "";
      endOperation();
    }
  };

  const run = async (action: () => Promise<DeclarationScreeningCase>, message: string, label: string, clearDraft = false) => {
    if (!beginOperation(label)) return;
    setError(null);
    try {
      const updated = await action();
      setCases(rows => rows.map(row => row.declaration_id === updated.declaration_id ? updated : row));
      if (clearDraft) setDrafts(previous => {
        const next = { ...previous };
        delete next[currentDraftKey];
        return next;
      });
      setNotice(message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败，请稍后重试。");
    } finally {
      endOperation();
    }
  };

  const generateReport = async () => {
    if (!selectedCase || !reportReady || !beginOperation("正在准备报告…")) return;
    setReportError(null);
    const existingWordReport = selectedCase.report?.file_name.endsWith(".docx")
      && selectedCase.report.template_version === "sinochem-questionnaire-v1" ? selectedCase.report : null;
    const picker = (window as SavePickerWindow).showSaveFilePicker;
    setError(null);
    try {
      // A second click retains browser user activation; no file is created until
      // the complete report has been downloaded and verified in memory.
      if (preparedReport && preparedReport.declarationId === selectedCase.declaration_id
          && preparedReport.sha256 === existingWordReport?.sha256) {
        const result = await saveReport(preparedReport.blob, preparedReport.filename, picker?.bind(window), browserDownload);
        if (result === "saved") setNotice("Word 报告已保存并验证文件大小。");
        else if (result === "fallback") setNotice("浏览器限制了直接写入，已转为普通下载。请查看浏览器下载列表；原选择位置可能留有空文件，请以新下载的文件为准。");
        else if (result === "download") setNotice("Word 报告已交给浏览器下载，请在下载列表中查看。");
        return;
      }
      setPreparedReport(null);
      setOperation("正在生成 Word 报告…");
      let updated = existingWordReport;
      if (!updated) {
        const generated = await generateDeclarationScreeningReport(selectedCase.declaration_id);
        setCases(rows => rows.map(row => row.declaration_id === generated.declaration_id ? generated : row));
        updated = generated.report;
      }
      if (!updated) throw new Error("筛查报告生成失败，请重试。");
      setOperation("正在下载报告…");
      const blob = await downloadDeclarationScreeningReport(selectedCase.declaration_id, updated.sha256);
      const downloadedCase = await getDeclarationScreeningCase(selectedCase.declaration_id);
      setCases(rows => rows.map(row => row.declaration_id === downloadedCase.declaration_id ? downloadedCase : row));
      setPreparedReport({ declarationId: selectedCase.declaration_id, sha256: updated.sha256, filename: updated.file_name, blob });
      setNotice("报告已生成并校验，请点击“选择位置并保存 Word”完成保存。");
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) {
        setReportError(cause instanceof Error ? cause.message : "报告生成或下载失败，请重试。");
      }
    } finally { endOperation(); }
  };

  return <div className="declaration-screening">
    <aside className="declaration-screening-list">
      <header><strong>待筛查申报</strong><button type="button" onClick={() => void refresh()} disabled={loading || busy}>刷新</button></header>
      <p>来自投保申报的被保险人、托运人、收货人及分出公司。逐主体完成初筛、截图和人工复核后，可生成 Word 报告。</p>
      {loading && <div className="declaration-screening-note">正在加载…</div>}
      {!loading && cases.length === 0 && <div className="declaration-screening-note">暂无包含待筛查主体的投保申报。</div>}
      {cases.map(row => {
        const done = row.parties.filter(item => item.preliminary && item.evidence && item.review).length;
        const unsaved = row.parties.some(item => isChanged(drafts[draftKey(row.declaration_id, item)], item));
        return <button type="button" disabled={busy} key={row.declaration_id} className={selectedId === row.declaration_id ? "selected" : ""}
          onClick={() => { setSelectedId(row.declaration_id); selectParty(row.parties[0] ?? null);
            if (row.stage === "pending_underwriting" && !unsaved) setUnderwritingId(row.declaration_id);
          }}>
          <strong>{row.declaration_number}</strong><span>{row.company_name || "未填写企业"}</span>
          <span>{unsaved ? "待保存复核结论" : ({ pending_screening: "待主体筛查", pending_report_download: "待下载报告", pending_underwriting: "承保条件确认 · 点击打开", confirmed: "投保确认" })[row.stage]}</span>
          <small>{done}/{row.parties.length} 主体完成复核{row.report ? " · 已生成报告" : ""}</small>
        </button>;
      })}
      {selectedCase && <section className="declaration-screening-sidebar-subjects">
        <h3>申报主体 <small>{completed}/{selectedCase.parties.length} 已复核</small></h3>
        <div className="declaration-screening-parties" aria-label="申报主体">
          {selectedCase.parties.map(item => {
            const dirty = isChanged(drafts[draftKey(selectedCase.declaration_id, item)], item);
            const reviewed = Boolean(item.preliminary && item.evidence && item.review && !dirty);
            const selected = Boolean(party && partyKey(party) === partyKey(item));
            return <button type="button" disabled={busy} key={partyKey(item)} className={selected ? "selected" : ""} aria-pressed={selected} onClick={() => selectParty(item)}>
              <span className="declaration-screening-party-title"><small>{item.label}</small>{reviewed && <span className="declaration-screening-review-check" role="img" aria-label="已完成复核" title="已完成复核，不代表合规放行"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 8 3 3 5-6" /></svg></span>}</span>
              <strong>{item.name}</strong><span>{dirty ? "有未保存结论" : reviewed ? "已复核" : item.evidence ? "待人工复核" : item.preliminary ? "待上传截图" : "待初筛"}</span>
            </button>;
          })}
        </div>
        <footer className="declaration-screening-bottom-actions">
          <span>{unsavedParties.length ? `请先保存复核结论：${unsavedParties.map(item => item.label).join("、")}` : reportReady ? "全部主体已完成筛查，可以生成 Word 报告" : `尚有 ${selectedCase.parties.length - completed} 个主体待完成：${incompleteParties.map(item => item.label).join("、")}`}</span>
          <button type="button" disabled={!reportReady || busy} onClick={() => void generateReport()}>{preparedReport?.declarationId === selectedCase.declaration_id && preparedReport.sha256 === selectedCase.report?.sha256 ? "选择位置并保存 Word" : "生成并下载筛查结果报告"}</button>
          {reportError && <p className="declaration-screening-error" role="alert">{reportError}</p>}
        </footer>
      </section>}
    </aside>
    <main className="declaration-screening-content">
      {error && <div className="declaration-screening-error" role="alert">{error}</div>}
      {notice && <div className="declaration-screening-note" role="status">{notice}</div>}
      {busy && <div className="declaration-screening-note" role="status" aria-live="polite">{operation}</div>}
      {!selectedCase ? <div className="declaration-screening-note">选择一份申报，开始逐主体筛查。</div> : <>
        <header className="declaration-screening-heading">
          <div><small>投保申报 · {selectedCase.status}</small><h2>{selectedCase.declaration_number}</h2><span>{selectedCase.company_name || "未填写企业"}</span></div>
          <div><span>{completed}/{selectedCase.parties.length} 已完成</span></div>
        </header>
        <p className="declaration-screening-disclaimer">本地初筛仅检索已保存的 OFAC SDN 名单，不构成合规放行。请在 OFAC 官网以完整法定名称再次查询，并上传该主体的查询截图。</p>
        {party && <h3 className="declaration-screening-active-party">{party.label} · {party.name}</h3>}
        {party && <div className="declaration-screening-steps">
          <section><h3>1 · 系统初步筛查</h3><p>使用与名称搜索栏相同的 OFAC SDN 本地检索逻辑。</p>
            <button type="button" disabled={busy} onClick={() => {
              if ((party.evidence || reviewDirty) && !window.confirm("重新初筛后，需要重新上传截图并保存人工复核结论。是否继续？")) return;
              void run(() => screenDeclarationParty(selectedCase.declaration_id, party.shipment_id, party.role), "初筛已完成，请继续官网复核并上传截图。", "正在初筛…");
            }}>{party.preliminary ? "重新初筛" : "开始初筛"}</button>
            {party.preliminary && <div className="declaration-screening-result"><strong>初筛时间：{new Date(party.preliminary.screened_at).toLocaleString("zh-CN")}</strong>
              <span>候选匹配 {party.preliminary.results.length} 条；{party.preliminary.results.length === 0 ? "未发现本地候选，不等于无制裁风险。" : "请逐条核验身份。"}</span>
              {party.preliminary.results.map(match => <div key={`${match.source}-${match.profile_id}`}>{match.matched_name} · {match.score.toFixed(1)}% · {match.source} {match.programs?.join("、")}</div>)}
              {party.preliminary.suggestions.length > 0 && <small>建议核实完整名称：{party.preliminary.suggestions.map(item => item.name).join("、")}</small>}
            </div>}
          </section>
          <section><h3>2 · OFAC 官网人工复核与截图</h3><p>在官网输入“{party.name}”再次筛查。官网结果由操作人判断，截图按主体留存。</p>
            <a className="declaration-screening-ofac-link" href={selectedCase.official_search_url} target="_blank" rel="noopener noreferrer">打开 OFAC 官方名单搜索 ↗</a>
            {!party.preliminary && <p className="declaration-screening-prerequisite">尚未初筛：选择截图后，系统会先执行初筛，再保存截图。</p>}
            <div className="declaration-screening-upload">
              <input ref={screenshotInputRef} key={partyKey(party)} className="sr-only" aria-label={`${party.label} OFAC 查询截图`} type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={event => {
                const file = event.target.files?.[0];
                if (file) void uploadScreenshot(file);
              }} />
              <button type="button" disabled={busy} onClick={() => screenshotInputRef.current?.click()}>{operation === "正在上传截图…" ? "上传中…" : party.evidence ? "替换截图" : "上传截图"}</button>
              <small>点击按钮选择 PNG、JPEG 或 WebP 文件（不超过 2 MB）</small>
            </div>
            {uploadError && <p className="declaration-screening-error" role="alert">{uploadError}</p>}
            {party.evidence && <div className="declaration-screening-evidence">
              <small>截图已保存 · {new Date(party.evidence.uploaded_at).toLocaleString("zh-CN")}</small>
              {party.evidence.url ? <a href={party.evidence.url} target="_blank" rel="noopener noreferrer">
                <Image className="declaration-screening-thumbnail" src={party.evidence.url} alt={`${party.label} OFAC 复核截图`} width={480} height={260} unoptimized />
                查看原图
              </a> : <small>预览链接暂不可用，请刷新列表后重试。</small>}
            </div>}
          </section>
          <section id="declaration-manual-review"><h3>3 · 记录人工复核结论</h3><div className="declaration-screening-form">
            <label>复核结果<select value={reviewResult} onChange={event => updateDraft({ result: event.target.value })} disabled={!party.evidence || busy}><option value="">请选择人工结论</option>{Object.entries(reviewLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>复核人<input value={reviewer} onChange={event => updateDraft({ reviewer: event.target.value })} disabled={!party.evidence || busy} placeholder="请输入姓名" /></label>
            <label className="wide">复核说明<textarea value={note} onChange={event => updateDraft({ note: event.target.value })} disabled={!party.evidence || busy} placeholder="说明官网查询结果及判断依据" /></label>
          </div>
            <button type="button" disabled={!party.evidence || !reviewResult || !reviewer.trim() || busy || (!!party.review && !reviewDirty)} onClick={() => void run(() => reviewDeclarationParty(selectedCase.declaration_id, party.shipment_id, party.role, reviewResult, reviewer, note), `${party.label}的复核结论已保存。`, "正在保存复核结论…", true)}>{operation === "正在保存复核结论…" ? "保存中…" : party.review && !reviewDirty ? "复核结论已保存" : "保存复核结论"}</button>
            {reviewDirty && <small>有未保存的修改。切换主体时会保留当前输入，刷新页面前请保存。</small>}
            {!party.evidence && <small>上传该主体截图后，即可填写人工复核结论。</small>}
            {party.review && <small>已由 {party.review.reviewer} 于 {new Date(party.review.reviewed_at).toLocaleString("zh-CN")} 记录：{reviewLabels[party.review.result] ?? party.review.result}</small>}
          </section>
        </div>}
      </>}
    </main>
    {underwritingId && cases.find(row => row.declaration_id === underwritingId) && <UnderwritingConfirmationDialog
      key={underwritingId} declaration={cases.find(row => row.declaration_id === underwritingId)!}
      onClose={() => setUnderwritingId(null)} onConfirmed={detail => {
        setUnderwritingId(null);
        setCases(rows => rows.filter(row => row.declaration_id !== detail.id));
        setNotice(`${detail.declaration_number} 已投保确认。`);
        try { window.localStorage.setItem("insurance-workspace-updated", String(Date.now())); } catch { /* Storage may be disabled; focus refresh still works. */ }
        window.dispatchEvent(new Event("insurance-workspace-updated"));
        void refresh();
      }} />}
  </div>;
}
