"use client";

import { useEffect, useState } from "react";
import { createFrameworkPolicy, createInsuranceCompany, getInsuranceCompanies, type InsuranceCompany } from "@/services/insurance";

export function FrameworkPolicyCreateDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (policyNumber: string) => Promise<void> }) {
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [newCompany, setNewCompany] = useState("");
  const [policyName, setPolicyName] = useState("");
  const [policyNumber, setPolicyNumber] = useState("");
  const [insurer, setInsurer] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getInsuranceCompanies().then(rows => {
      if (!active) return;
      setCompanies(rows);
      setCompanyId(rows[0]?.id ?? "");
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "企业列表加载失败。"); });
    return () => { active = false; };
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newCompany.trim() && !companyId) { setError("请选择或填写企业。"); return; }
    if (endDate < startDate) { setError("保险结束日期不能早于起始日期。"); return; }
    setBusy(true);
    setError(null);
    try {
      const resolvedCompanyId = newCompany.trim() ? (await createInsuranceCompany(newCompany.trim())).id : companyId;
      const policy = await createFrameworkPolicy({
        company_id: resolvedCompanyId,
        policy_name: policyName.trim(), policy_number: policyNumber.trim(), insurer: insurer.trim(),
        start_date: startDate, end_date: endDate, currency: currency.trim().toUpperCase(), status: "active",
      });
      await onCreated(policy.policy_number);
    } catch (err) {
      setError(err instanceof Error ? err.message : "框架协议创建失败。");
    } finally {
      setBusy(false);
    }
  }

  return <div className="insurance-modal-backdrop" role="presentation">
    <section className="insurance-modal insurance-import-modal" role="dialog" aria-modal="true" aria-labelledby="create-policy-title">
      <header><div><span>框架协议</span><h2 id="create-policy-title">新增框架协议</h2></div><button type="button" onClick={onClose} disabled={busy} aria-label="关闭">×</button></header>
      <form className="insurance-upload-form" onSubmit={submit}>
        <label><span>企业 *</span><select value={companyId} onChange={event => setCompanyId(event.target.value)} disabled={Boolean(newCompany.trim())}><option value="">选择已有企业</option>{companies.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>
        <label><span>或新增企业</span><input value={newCompany} onChange={event => setNewCompany(event.target.value)} placeholder="企业全称" /></label>
        <label><span>项目名称 *</span><input value={policyName} onChange={event => setPolicyName(event.target.value)} required maxLength={300} /></label>
        <label><span>框架协议保单号 *</span><input value={policyNumber} onChange={event => setPolicyNumber(event.target.value)} required maxLength={160} /></label>
        <label><span>承保公司 *</span><input value={insurer} onChange={event => setInsurer(event.target.value)} required maxLength={300} /></label>
        <div className="insurance-review-grid">
          <label><span>保险起期 *</span><input type="date" value={startDate} onChange={event => setStartDate(event.target.value)} required /></label>
          <label><span>保险止期 *</span><input type="date" value={endDate} onChange={event => setEndDate(event.target.value)} required /></label>
          <label><span>币种 *</span><input value={currency} onChange={event => setCurrency(event.target.value)} maxLength={3} minLength={3} required /></label>
        </div>
        {error && <div className="insurance-inline-error" role="alert">{error}</div>}
        <div className="insurance-modal-actions"><button type="button" onClick={onClose} disabled={busy}>取消</button><button type="submit" className="primary" disabled={busy}>{busy ? "正在创建…" : "创建框架协议"}</button></div>
      </form>
    </section>
  </div>;
}
