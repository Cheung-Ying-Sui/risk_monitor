"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { DeclarationImportDialog } from "@/components/insurance/declaration-import-dialog";
import { FrameworkPolicyCreateDialog } from "@/components/insurance/framework-policy-create-dialog";
import { getDeclaration, getFrameworkPolicy, loadInsuranceWorkspace, submitDraftDeclaration, voidDeclaration, voidFrameworkPolicy } from "@/services/insurance";
import type {
  DeclarationDetail,
  DeclarationImport,
  DeclarationSummary,
  FrameworkPolicy,
  FrameworkPolicyDetail,
  InsuranceDocument,
  InsuranceWorkspaceTab,
  ShipmentData,
} from "@/types/insurance";

const STATUS_LABELS: Record<string, string> = {
  active: "有效",
  pending: "待补资料",
  expiring_soon: "即将到期",
  expired: "已到期",
  cancelled: "已作废",
  draft: "草稿",
  pending_review: "待筛查与承保确认",
  confirmed: "投保确认",
  covered: "已承保",
  completed: "航程已结束",
};

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ").toUpperCase();
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`insurance-status ${status}`}>{statusLabel(status)}</span>;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    timeZone: "Asia/Shanghai", hour12: false,
  }).format(new Date(value));
}

function voyageLifecycle(shipment: ShipmentData) {
  return (shipment.extra_data?.voyage_lifecycle ?? {}) as {
    state?: string; port?: string; first_berth_observed_at?: string;
    berth_confirmed_at?: string; ended_at?: string; last_observed_at?: string;
  };
}

function voyageStatus(shipment: ShipmentData, declarationStatus?: string) {
  if (shipment.coverage_status === "ended_by_mvp_departure") return "保障结束（MVP推定）";
  if (declarationStatus === "completed") return "航程已结束";
  if (declarationStatus === "draft" || declarationStatus === "pending_review") return "待投保确认";
  const state = voyageLifecycle(shipment).state;
  if (state === "berthed") return "目的港停泊，待再次启动";
  if (state === "berth_candidate") return "疑似目的港停泊";
  return "航程监测中";
}

function formatMoney(value: string | number | null | undefined, currency = "USD") {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return `${currency} ${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(amount)}`;
}

function shipmentSummary(declaration: DeclarationSummary) {
  return declaration.shipments[0] ?? null;
}

function DeclarationsTable({
  declarations,
  selectedId,
  onSelect,
  onOpen,
}: {
  declarations: DeclarationSummary[];
  selectedId: string | null;
  onSelect: (declaration: DeclarationSummary) => void;
  onOpen: (declaration: DeclarationSummary) => void;
}) {
  return (
    <div className="insurance-table-scroll">
      <table className="insurance-table applications-table">
        <thead>
          <tr><th>状态</th><th>申报编号</th><th>企业</th><th>船舶</th><th>货物</th><th>航程</th><th>保险金额</th><th>申报日期</th></tr>
        </thead>
        <tbody>
          {declarations.map((declaration) => {
            const shipment = shipmentSummary(declaration);
            return (
              <tr
                key={declaration.id}
                className={selectedId === declaration.id ? "selected" : ""}
                onClick={() => onSelect(declaration)}
                onDoubleClick={() => onOpen(declaration)}
                onKeyDown={(event) => { if (event.key === "Enter") onOpen(declaration); }}
                tabIndex={0}
                aria-label={`打开申报 ${declaration.declaration_number} 详情`}
              >
                <td><StatusBadge status={declaration.status} /></td>
                <td><strong>{declaration.declaration_number}</strong><small>{declaration.source_file_name === "manual-entry.json" ? "手动录入" : declaration.source_file_name ?? declaration.source_type}</small></td>
                <td>{declaration.company_name ?? "—"}</td>
                <td>{shipment?.vessel_name ?? "—"}</td>
                <td>{shipment?.cargo_name ?? "—"}</td>
                <td>{shipment ? `${shipment.loading_port ?? "—"} → ${shipment.discharge_port ?? "—"}` : "—"}</td>
                <td className="numeric">{formatMoney(shipment?.insured_value, shipment?.currency ?? "USD")}</td>
                <td>{formatDate(declaration.received_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!declarations.length && <div className="insurance-empty">没有符合当前条件的投保申报。</div>}
    </div>
  );
}

function PoliciesTable({ policies, declarations, onOpen }: { policies: FrameworkPolicy[]; declarations: DeclarationSummary[]; onOpen: (policy: FrameworkPolicy) => void }) {
  return (
    <div className="insurance-table-scroll">
      <table className="insurance-table insurance-policies-table">
        <thead>
          <tr><th>状态</th><th>框架协议保单号</th><th>企业</th><th>项目名称</th><th>保险期间</th><th>申报</th><th>累计保额</th><th>累计保费</th></tr>
        </thead>
        <tbody>
          {policies.map((policy) => {
            const linked = declarations.filter((item) => item.policy_id === policy.id);
            const shipments = linked.flatMap((item) => item.shipments);
            return <tr key={policy.id} onDoubleClick={() => onOpen(policy)} onKeyDown={(event) => { if (event.key === "Enter") onOpen(policy); }} tabIndex={0} aria-label={`打开框架协议 ${policy.policy_number} 详情`}>
              <td><StatusBadge status={policy.status} /></td>
              <td><strong>{policy.policy_number}</strong></td>
              <td>{policy.company_name ?? "—"}</td>
              <td>{policy.policy_name}</td>
              <td>{formatDate(policy.start_date)} – {formatDate(policy.end_date)}</td>
              <td className="numeric">{linked.length}</td>
              <td className="numeric">{formatMoney(shipments.some(item => item.insured_value != null) ? shipments.reduce((sum, item) => sum + Number(item.insured_value ?? 0), 0) : null, policy.currency)}</td>
              <td className="numeric">{formatMoney(shipments.some(item => item.premium != null) ? shipments.reduce((sum, item) => sum + Number(item.premium ?? 0), 0) : null, policy.currency)}</td>
            </tr>;
          })}
        </tbody>
      </table>
      {!policies.length && <div className="insurance-empty">尚未创建框架协议。</div>}
    </div>
  );
}

interface ShipmentRow {
  shipment: ShipmentData;
  declaration: DeclarationSummary;
}

function ShipmentsTable({ rows }: { rows: ShipmentRow[] }) {
  return (
    <div className="insurance-table-scroll">
      <table className="insurance-table">
        <thead>
          <tr><th>申报编号</th><th>船舶</th><th>IMO</th><th>货物</th><th>数量</th><th>航程</th><th>航程状态</th><th>ETD</th><th>ETA</th><th>保险金额</th><th>保险费</th></tr>
        </thead>
        <tbody>
          {rows.map(({ shipment, declaration }, index) => (
            <tr key={shipment.id ?? `${declaration.id}-${index}`}>
              <td><strong>{declaration.declaration_number}</strong></td>
              <td>{shipment.vessel_name ?? "—"}</td>
              <td>{shipment.imo_number ?? "待补"}</td>
              <td>{shipment.cargo_name ?? "—"}</td>
              <td>{shipment.quantity ?? "—"} {shipment.quantity_unit ?? ""}</td>
              <td>{shipment.loading_port ?? "—"} → {shipment.discharge_port ?? "—"}</td>
              <td>{voyageStatus(shipment, declaration.status)}</td>
              <td>{formatDate(shipment.etd)}</td>
              <td>{formatDate(shipment.eta)}</td>
              <td className="numeric">{formatMoney(shipment.insured_value, shipment.currency ?? "USD")}</td>
              <td className="numeric">{formatMoney(shipment.premium, shipment.currency ?? "USD")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="insurance-empty">尚无结构化运输标的。</div>}
    </div>
  );
}

function DetailDocuments({ documents }: { documents: InsuranceDocument[] }) {
  return <section className="insurance-detail-documents">
    <h3>附件与凭证</h3>
    {documents.map((document) => document.download_url
      ? <a key={document.id} href={document.download_url} target="_blank" rel="noreferrer">{document.file_name}<small>{document.document_type}</small></a>
      : <span key={document.id}>{document.file_name}</span>)}
    {!documents.length && <span>暂无附件。</span>}
  </section>;
}

function VoidAction({ label, busy, onVoid }: { label: string; busy: boolean; onVoid: () => Promise<void> }) {
  const [armed, setArmed] = useState(false);
  return <div className="insurance-void-action">
    {armed && <span role="alert">将作废 {label} 并从列表移除。原始资料保留用于核查。</span>}
    {armed && <button type="button" onClick={() => setArmed(false)} disabled={busy}>取消</button>}
    <button type="button" className={armed ? "confirm" : ""} onClick={() => { if (armed) void onVoid(); else setArmed(true); }} disabled={busy}>
      {busy ? "正在作废…" : armed ? "再次点击，确认作废" : "作废"}
    </button>
  </div>;
}

function PolicyDetailDialog({ detail, busy, error, onClose, onVoid }: { detail: FrameworkPolicyDetail; busy: boolean; error: string | null; onClose: () => void; onVoid: () => Promise<void> }) {
  return <div className="insurance-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="insurance-modal insurance-detail-modal" role="dialog" aria-modal="true" aria-labelledby="policy-detail-title">
      <header><div><span>框架协议详情</span><h2 id="policy-detail-title">{detail.policy_name}</h2></div><button type="button" onClick={onClose} disabled={busy} aria-label="关闭框架协议详情">×</button></header>
      <div className="insurance-detail-body">
        <div className="insurance-detail-status"><StatusBadge status={detail.status} /><span>{detail.policy_number}</span><span>{detail.company_name}</span></div>
        <dl className="insurance-detail-grid">
          <div><dt>承保公司</dt><dd>{detail.insurer}</dd></div><div><dt>保险期间</dt><dd>{formatDate(detail.start_date)} – {formatDate(detail.end_date)}</dd></div>
          <div><dt>保险费率</dt><dd>{detail.rate ?? "—"}</dd></div><div><dt>单票限额</dt><dd>{detail.shipment_limit ? formatMoney(detail.shipment_limit, detail.currency) : "—"}</dd></div>
          <div><dt>预计年度货值</dt><dd>{detail.annual_estimated_value ? formatMoney(detail.annual_estimated_value, detail.currency) : "—"}</dd></div><div><dt>计价基础</dt><dd>{detail.valuation_basis ?? "—"}</dd></div>
          <div><dt>货种范围</dt><dd>{detail.cargo_scope ?? "—"}</dd></div><div><dt>承保区域</dt><dd>{detail.territory ?? "—"}</dd></div>
          <div><dt>运输方式</dt><dd>{detail.transport_mode ?? "—"}</dd></div><div><dt>免赔额</dt><dd>{detail.deductible ?? "—"}</dd></div>
          <div><dt>保险条款</dt><dd>{detail.insurance_clause ?? "—"}</dd></div><div><dt>战争险</dt><dd>{detail.war_risk ?? "—"}</dd></div>
          <div className="wide"><dt>特别约定</dt><dd>{detail.special_conditions ?? "—"}</dd></div>
        </dl>
        <DetailDocuments documents={detail.documents} />
        {error && <div className="insurance-inline-error" role="alert">{error}</div>}
        <VoidAction label={`框架协议 ${detail.policy_number}`} busy={busy} onVoid={onVoid} />
      </div>
    </section>
  </div>;
}

function DeclarationDetailDialog({ detail, busy, error, onClose, onVoid, onSubmitDraft }: { detail: DeclarationDetail; busy: boolean; error: string | null; onClose: () => void; onVoid: () => Promise<void>; onSubmitDraft: () => Promise<void> }) {
  const shipment = detail.shipments[0];
  const screening = shipment?.extra_data?.sanctions_screening as { status?: string } | undefined;
  const workflow = shipment?.extra_data?.sanctions_workflow as { report?: { sha256?: string } } | undefined;
  const terms = shipment?.extra_data?.underwriting_terms as { status?: string; report_sha256?: string } | undefined;
  const reportReady = screening?.status === "completed" && Boolean(workflow?.report?.sha256);
  const termsReady = reportReady && terms?.status === "confirmed" && terms.report_sha256 === workflow?.report?.sha256;

  return (
    <div className="insurance-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section className="insurance-modal insurance-detail-modal insurance-declaration-detail" role="dialog" aria-modal="true" aria-labelledby="declaration-detail-title">
        <header>
          <div><span>投保申报详情</span><h2 id="declaration-detail-title">{detail.declaration_number}</h2></div>
          <button type="button" onClick={onClose} disabled={busy} aria-label="关闭申报详情">×</button>
        </header>
        <div className="insurance-detail-body">
          <div className="insurance-detail-status"><StatusBadge status={detail.status} /><span>企业 <strong>{detail.company_name || "待补"}</strong></span><span>框架协议 <strong>{detail.policy_name || "待补"}</strong></span></div>
          {detail.shipments.map((shipment, index) => (
            <section className="insurance-shipment-detail" key={shipment.id ?? index}>
              <h3>船舶与运输{detail.shipments.length > 1 ? ` · ${index + 1}` : ""}</h3>
              <dl className="insurance-detail-grid">
              <div><dt>船舶</dt><dd>{shipment.vessel_name ?? "待补"}</dd></div><div><dt>IMO</dt><dd>{shipment.imo_number ?? "待补"}</dd></div>
              <div><dt>货物</dt><dd>{shipment.cargo_name ?? "待补"}</dd></div><div><dt>数量</dt><dd>{shipment.quantity ?? "—"} {shipment.quantity_unit ?? ""}</dd></div>
              <div className="wide"><dt>航程 · 起运港 → 申报目的地</dt><dd>{shipment.loading_port ?? "—"} → {shipment.discharge_port ?? "—"}</dd></div>
              <div><dt>ETD · 预计起运</dt><dd>{formatDate(shipment.etd)}</dd></div><div><dt>ETA · 申报预计抵达</dt><dd>{formatDate(shipment.eta)}</dd></div>
              </dl>
              <h4>保险金额与费用</h4>
              <dl className="insurance-detail-grid insurance-detail-financial">
                <div><dt>保险金额</dt><dd>{formatMoney(shipment.insured_value, shipment.currency || "币种待补")}</dd></div>
                <div><dt>综合费率</dt><dd>{shipment.insurance_rate == null ? "—" : `${shipment.insurance_rate}%`}</dd></div>
                <div><dt>保费</dt><dd>{formatMoney(shipment.premium, shipment.currency || "币种待补")}</dd></div>
                <div><dt>每船货物发票金额</dt><dd>{formatMoney(shipment.invoice_value, shipment.currency || "币种待补")}</dd></div>
              </dl>
              <h4>补充资料与跟踪状态</h4>
              <dl className="insurance-detail-grid">
              {(shipment.extra_data?.form_type === "vessel_information" || shipment.extra_data?.form_type === "two_form_declaration") && <>
                <div><dt>业务类型</dt><dd>{String(shipment.extra_data.business_type ?? "—")}</dd></div>
                <div><dt>船旗</dt><dd>{shipment.flag ?? "—"}</dd></div>
                <div><dt>船东</dt><dd>{String(shipment.extra_data.vessel_owner ?? "—")}</dd></div>
                <div><dt>租船人</dt><dd>{String(shipment.extra_data.charterer ?? "—")}</dd></div>
                <div><dt>船级</dt><dd>{String(shipment.extra_data.classification ?? "—")}</dd></div>
                <div><dt>保赔险</dt><dd>{String(shipment.extra_data.pi_insurance ?? "—")}</dd></div>
                <div><dt>建造年份</dt><dd>{shipment.built_year ?? "—"}</dd></div>
              </>}
              <div><dt>航程保障状态</dt><dd>{voyageStatus(shipment, detail.status)}</dd></div>
              {shipment.extra_data?.form_type === "two_form_declaration" && <>
                <div><dt>ETD 区间</dt><dd>{String(shipment.extra_data.etd_window ?? "—")}</dd></div>
                <div><dt>ETA 区间</dt><dd>{String(shipment.extra_data.eta_window ?? "—")}</dd></div>
                <div><dt>保额浮动</dt><dd>{shipment.extra_data.insured_value_tolerance_percent ? `${shipment.extra_data.insured_value_tolerance_percent}%` : "—"}</dd></div>
                <div><dt>托运人</dt><dd>{String(shipment.extra_data.shipper ?? "—")}</dd></div>
                <div><dt>收货人</dt><dd>{String(shipment.extra_data.consignee ?? "—")}</dd></div>
                <div><dt>分出公司</dt><dd>{String(shipment.extra_data.cedant ?? "—")}</dd></div>
              </>}
              </dl>
              {voyageLifecycle(shipment).state && <div className="insurance-voyage-note">
                <strong>MVP 航程结束规则</strong>
                <p>系统依据目的港附近连续 AIS 停泊记录及随后再次启动的船位，推定本票航程保障结束；这不是卸货完成证明，也不替代保险合同条款核定。</p>
                <span>目的港：{voyageLifecycle(shipment).port ?? shipment.discharge_port ?? "—"}</span>
                <span>停泊确认：{formatDateTime(voyageLifecycle(shipment).berth_confirmed_at)}</span>
                {shipment.coverage_status === "ended_by_mvp_departure" && <span>推定结束：{formatDateTime(voyageLifecycle(shipment).ended_at)}</span>}
              </div>}
            </section>
          ))}
          {detail.status === "draft" && <section className="insurance-underwriting-panel">
            <h3>暂存草稿</h3>
            <p>确认上述信息后点击申报，相关主体会进入制裁筛查模块的待筛查列表。申报前不会关联船舶跟踪。</p>
            <button type="button" className="insurance-underwriting-confirm" disabled={busy} onClick={() => void onSubmitDraft()}>{busy ? "处理中…" : "申报"}</button>
          </section>}
          {detail.status === "pending_review" && shipment && <section className="insurance-underwriting-panel">
            <h3>申报处理顺序</h3>
            <p>待主体筛查 → 逐主体初筛、上传截图并记录人工结论 → 生成并下载报告 → 承保条件确认 → 投保确认。</p>
            <p>当前进度：{termsReady ? "承保条件已确认，待投保确认" : reportReady ? "筛查报告已生成，待确认承保条件" : "待主体筛查及报告"}。所有后续操作均在制裁筛查模块完成。</p>
            <a className="insurance-underwriting-confirm" href={`/sanctions-screening?declaration=${encodeURIComponent(detail.id)}`}>前往制裁筛查与承保确认 →</a>
          </section>}
          <DetailDocuments documents={detail.documents} />
          {detail.notes && <div className="insurance-detail-notes"><strong>核实备注</strong><p>{detail.notes}</p></div>}
          {error && <div className="insurance-inline-error" role="alert">{error}</div>}
          <VoidAction label={`投保申报 ${detail.declaration_number}`} busy={busy} onVoid={onVoid} />
        </div>
      </section>
    </div>
  );
}

export function InsuranceWorkbench() {
  const [activeTab, setActiveTab] = useState<InsuranceWorkspaceTab>("declarations");
  const [policies, setPolicies] = useState<FrameworkPolicy[]>([]);
  const [declarations, setDeclarations] = useState<DeclarationSummary[]>([]);
  const [pendingImports, setPendingImports] = useState<DeclarationImport[]>([]);
  const [resumeImport, setResumeImport] = useState<DeclarationImport | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selected, setSelected] = useState<DeclarationSummary | null>(null);
  const [detail, setDetail] = useState<DeclarationDetail | null>(null);
  const [policyDetail, setPolicyDetail] = useState<FrameworkPolicyDetail | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [showPolicyCreate, setShowPolicyCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [voidBusy, setVoidBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const data = await loadInsuranceWorkspace();
      setPolicies(data.policies);
      setDeclarations(data.declarations);
      setPendingImports(data.pendingImports);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "保单数据加载失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    loadInsuranceWorkspace()
      .then((data) => {
        if (!active) return;
        setPolicies(data.policies);
        setDeclarations(data.declarations);
        setPendingImports(data.pendingImports);
      })
      .catch((loadError: unknown) => {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "保单数据加载失败。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible" || showImport || showPolicyCreate || voidBusy) return;
      void refresh();
      if (detail?.id) void getDeclaration(detail.id).then(setDetail).catch(() => undefined);
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [refresh, detail?.id, showImport, showPolicyCreate, voidBusy]);

  const needle = query.trim().toLowerCase();
  useEffect(() => {
    const update = () => {
      void refresh();
      if (detail?.id) void getDeclaration(detail.id).then(setDetail).catch(() => undefined);
    };
    const storageUpdate = (event: StorageEvent) => { if (event.key === "insurance-workspace-updated") update(); };
    window.addEventListener("insurance-workspace-updated", update);
    window.addEventListener("focus", update);
    window.addEventListener("storage", storageUpdate);
    return () => {
      window.removeEventListener("insurance-workspace-updated", update);
      window.removeEventListener("focus", update);
      window.removeEventListener("storage", storageUpdate);
    };
  }, [refresh, detail?.id]);
  const activeDeclarations = useMemo(() => declarations.filter((item) => item.status !== "cancelled"), [declarations]);
  const activePolicies = useMemo(() => policies.filter((item) => item.status !== "cancelled"), [policies]);
  const filteredDeclarations = useMemo(() => activeDeclarations.filter((declaration) => {
    const shipment = shipmentSummary(declaration);
    const searchable = [declaration.declaration_number, declaration.company_name, declaration.policy_name, declaration.source_file_name, shipment?.vessel_name, shipment?.cargo_name, shipment?.loading_port, shipment?.discharge_port].filter(Boolean).join(" ").toLowerCase();
    return searchable.includes(needle) && (statusFilter === "all" || declaration.status === statusFilter);
  }), [activeDeclarations, needle, statusFilter]);

  const filteredPolicies = useMemo(() => activePolicies.filter((policy) => {
    const searchable = [policy.policy_number, policy.policy_name, policy.company_name, policy.insurer].filter(Boolean).join(" ").toLowerCase();
    return searchable.includes(needle) && (statusFilter === "all" || policy.status === statusFilter);
  }), [activePolicies, needle, statusFilter]);

  const shipmentRows = useMemo(() => filteredDeclarations.flatMap((declaration) => declaration.shipments.map((shipment) => ({ declaration, shipment }))), [filteredDeclarations]);
  const tabs: Array<{ id: InsuranceWorkspaceTab; label: string; count?: number }> = [
    { id: "declarations", label: "投保申报", count: activeDeclarations.length },
    { id: "policies", label: "框架协议", count: activePolicies.length },
    { id: "ecargo", label: "E-cargo" },
    { id: "shipments", label: "运输标的", count: activeDeclarations.reduce((total, item) => total + item.shipments.length, 0) },
  ];

  async function openDeclaration(declaration: DeclarationSummary) {
    setError(null);
    try {
      setSelected(declaration);
      setDetail(await getDeclaration(declaration.id));
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "申报详情加载失败。");
    }
  }

  async function openPolicy(policy: FrameworkPolicy) {
    setError(null);
    try {
      setPolicyDetail(await getFrameworkPolicy(policy.id));
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "框架协议详情加载失败。");
    }
  }

  async function handleVoidDeclaration() {
    if (!detail) return;
    setVoidBusy(true);
    setError(null);
    try {
      await voidDeclaration(detail.id);
      setDetail(null);
      setSelected(null);
      setNotice(`${detail.declaration_number} 已作废并从列表移除。`);
      await refresh();
    } catch (voidError) {
      setError(voidError instanceof Error ? voidError.message : "申报作废失败。");
    } finally {
      setVoidBusy(false);
    }
  }

  async function handleVoidPolicy() {
    if (!policyDetail) return;
    setVoidBusy(true);
    setError(null);
    try {
      await voidFrameworkPolicy(policyDetail.id);
      setPolicyDetail(null);
      setNotice(`${policyDetail.policy_number} 已作废并从列表移除。`);
      await refresh();
    } catch (voidError) {
      setError(voidError instanceof Error ? voidError.message : "框架协议作废失败。");
    } finally {
      setVoidBusy(false);
    }
  }

  async function handleConfirmed(declarationNumber: string, status: "draft" | "pending_review" = "pending_review") {
    setShowImport(false);
    setResumeImport(null);
    setNotice(status === "draft"
      ? `${declarationNumber} 已暂存为草稿，可从投保申报列表打开后继续申报。`
      : `${declarationNumber} 已申报，请前往制裁筛查模块完成逐主体筛查、报告和承保确认。投保确认后才会启动船舶跟踪。`);
    await refresh();
  }

  async function handleSubmitDraft() {
    if (!detail) return;
    setVoidBusy(true);
    setError(null);
    try {
      const updated = await submitDraftDeclaration(detail.id);
      setDetail(updated);
      setNotice(`${detail.declaration_number} 已申报，请前往制裁筛查模块逐主体筛查、下载报告并确认承保条件。`);
      await refresh();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "草稿申报失败。");
    } finally {
      setVoidBusy(false);
    }
  }

  async function handlePolicyCreated(policyNumber: string) {
    setShowPolicyCreate(false);
    setNotice(`框架协议 ${policyNumber} 已创建。`);
    await refresh();
  }

  return (
    <div className="insurance-page">
      <div className="insurance-context-bar">
        <label className="insurance-context-search"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索企业、保单号、申报号、船舶或货物…" aria-label="搜索保单与申报" /></label>
        <div className="insurance-context-selectors">
          <label><span className="sr-only">状态</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">状态：全部</option><option value="pending_review">申报待审核</option><option value="confirmed">申报已确认</option><option value="covered">已承保</option><option value="completed">航程已结束</option><option value="active">保单有效</option><option value="pending">框架资料待补</option></select></label>
          <label><span className="sr-only">保险期间</span><select defaultValue="2026"><option value="2026">期间：2026 年</option></select></label>
        </div>
      </div>

      {(error || notice) && (
        <div className={`insurance-page-message ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>
          <span>{error ?? notice}</span><button type="button" onClick={() => { setError(null); setNotice(null); }} aria-label="关闭消息">×</button>
        </div>
      )}

      <div className="insurance-workspace-grid">
        <section className="insurance-workbench-column insurance-panel">
          <div className="insurance-workbench-toolbar">
            <nav className="insurance-tabs" role="tablist" aria-label="保单管理视图">
              {tabs.map((tab) => <button type="button" role="tab" aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)} key={tab.id}>{tab.label}{tab.count !== undefined && <small>{tab.count}</small>}</button>)}
            </nav>
            {activeTab === "declarations" && <>
              {pendingImports.length > 0 && <select className="insurance-resume-select" aria-label="继续暂存导入" value="" onChange={event => { const item = pendingImports.find(record => record.id === event.target.value); if (item) { setResumeImport(item); setShowImport(true); } }}>
                <option value="">继续暂存导入（{pendingImports.length}）</option>
                {pendingImports.map(record => <option key={record.id} value={record.id}>{record.created_at?.slice(0, 10) ?? "未标日期"} · {record.source_file_name} · {record.parsed_data.shipments.length} 票</option>)}
              </select>}
              <button type="button" className="new-application-button insurance-tab-action" onClick={() => { setResumeImport(null); setShowImport(true); }} disabled={!activePolicies.length}>＋ 新增投保申报</button>
            </>}
            {activeTab === "policies" && <button type="button" className="new-application-button insurance-tab-action" onClick={() => setShowPolicyCreate(true)}>＋ 新增框架协议</button>}
          </div>
          <div className="insurance-table-region" role="tabpanel">
            {activeTab === "ecargo" ? <div className="insurance-ecargo-placeholder"><h2>E-cargo</h2><p>保司 API 尚未接入。此模块预留用于后续调取承保和申报数据，当前无操作功能。</p></div> : loading ? <div className="insurance-loading">正在加载协议与申报数据…</div> : activeTab === "declarations" ? <DeclarationsTable declarations={filteredDeclarations} selectedId={selected?.id ?? null} onSelect={setSelected} onOpen={(item) => void openDeclaration(item)} /> : activeTab === "policies" ? <PoliciesTable policies={filteredPolicies} declarations={activeDeclarations} onOpen={(item) => void openPolicy(item)} /> : <ShipmentsTable rows={shipmentRows} />}
          </div>
        </section>
      </div>

      {showImport && <DeclarationImportDialog policies={activePolicies} initialImport={resumeImport} onClose={() => { setShowImport(false); setResumeImport(null); void refresh(); }} onConfirmed={handleConfirmed} />}
      {showPolicyCreate && <FrameworkPolicyCreateDialog onClose={() => setShowPolicyCreate(false)} onCreated={handlePolicyCreated} />}
      {detail && <DeclarationDetailDialog key={detail.id} detail={detail} busy={voidBusy} error={error} onClose={() => setDetail(null)} onVoid={handleVoidDeclaration} onSubmitDraft={handleSubmitDraft} />}
      {policyDetail && <PolicyDetailDialog key={policyDetail.id} detail={policyDetail} busy={voidBusy} error={error} onClose={() => setPolicyDetail(null)} onVoid={handleVoidPolicy} />}
    </div>
  );
}
