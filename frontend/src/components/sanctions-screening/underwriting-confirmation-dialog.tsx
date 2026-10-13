"use client";

import { useEffect, useRef, useState } from "react";
import type { DeclarationScreeningCase } from "@/types/sanctions";
import type { DeclarationDetail } from "@/types/insurance";
import { completeUnderwriting } from "@/services/insurance";

export function UnderwritingConfirmationDialog({ declaration, onClose, onConfirmed }: {
  declaration: DeclarationScreeningCase; onClose: () => void; onConfirmed: (detail: DeclarationDetail) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const submitting = useRef(false);
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const terms = declaration.underwriting;
  const valid = rate.trim() !== "" && Number.isFinite(Number(rate)) && Number(rate) >= 0 && Number(rate) <= 100;
  const eligible = terms.shipment_count === 1 && terms.insured_value !== null && Boolean(terms.currency);
  return <dialog ref={dialog} className="underwriting-confirmation-dialog" aria-labelledby="underwriting-title"
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <form onSubmit={async event => {
      event.preventDefault();
      if (submitting.current) return;
      if (!valid) { setError("请输入 0 至 100 之间的有效综合费率（%）。"); return; }
      submitting.current = true; setBusy(true); setError(null);
      try {
        const detail = await completeUnderwriting(declaration.declaration_id, Number(rate));
        if (detail.status !== "confirmed") throw new Error("服务端未返回投保确认状态，请刷新核实。");
        onConfirmed(detail);
      } catch (cause) { setError(cause instanceof Error ? cause.message : "确认失败，请重试。"); }
      finally { submitting.current = false; setBusy(false); }
    }}>
      <header><h2 id="underwriting-title">承保条件确认</h2><button type="button" disabled={busy} onClick={onClose} aria-label="关闭">×</button></header>
      <dl><dt>申报编号</dt><dd>{declaration.declaration_number}</dd><dt>企业</dt><dd>{declaration.company_name || "未提供"}</dd>
        <dt>货物</dt><dd>{terms.cargo_name || "未提供"}</dd><dt>保险金额</dt><dd>{terms.insured_value ?? "未提供"} {terms.currency}</dd>
        <dt>保额浮动</dt><dd>{terms.insured_value_tolerance_percent ?? "未提供"}%</dd></dl>
      {!eligible && <p role="alert">当前仅支持单条运输标的，且需完整保额和币种。请先完善申报。</p>}
      <label>综合费率（%）<input autoFocus type="number" min="0" max="100" step="any" required value={rate} disabled={busy} onChange={e => setRate(e.target.value)} /></label>
      <p>预估保费：{valid && eligible ? (Number(terms.insured_value) * Number(rate) / 100).toFixed(2) : "—"} {terms.currency}</p>
      <p>保费 = 保险金额 × 综合费率 ÷ 100，四舍五入至两位小数，以服务端计算为准。</p>
      <p>点击确认将保存承保条件并完成投保确认，启动现有船舶跟踪流程；不代表保险人已出单或正式签发保单。</p>
      {error && <p className="declaration-screening-error" role="alert">{error}</p>}
      <button type="submit" disabled={busy || !eligible}>{busy ? "正在确认…" : "确认承保条件并完成投保确认"}</button>
    </form>
  </dialog>;
}
