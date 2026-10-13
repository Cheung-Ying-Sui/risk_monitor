"use client";

import { useState } from "react";
import {
  cancelDeclarationImport,
  confirmDeclarationImport,
  createManualDeclaration,
  saveDeclarationImport,
  uploadDeclarationBundle,
} from "@/services/insurance";
import type {
  DeclarationImport,
  FrameworkPolicy,
  ParsedDeclarationData,
  ShipmentData,
} from "@/types/insurance";

interface DeclarationImportDialogProps {
  policies: FrameworkPolicy[];
  initialImport?: DeclarationImport | null;
  onClose: () => void;
  onConfirmed: (declarationNumber: string, status?: "draft" | "pending_review") => Promise<void>;
}

const numericFields = new Set<keyof ShipmentData>([
  "built_year",
  "quantity",
  "quantity_tolerance_percent",
  "invoice_value",
  "insured_value",
  "insurance_rate",
  "premium",
]);

function fieldValue(value: string | number | null | undefined) {
  return value === null || value === undefined ? "" : String(value);
}


function declarationDate(value?: string | null) {
  if (value && /^\d{4}-\d{2}-\d{2}/.test(value) && !/(Z|[+-]\d{2}:\d{2})$/.test(value)) return value.slice(0, 10);
  const date = value ? new Date(value) : new Date();
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(Number.isNaN(date.getTime()) ? new Date() : date);
}

function AutomaticDate({ value }: { value: string }) {
  return <label className="insurance-review-field"><span>材料接收 / 投保日期</span><input type="text" value={value} readOnly /><small>系统自动带出</small></label>;
}

function dateTimeValue(value: string | null) {
  return value ? value.slice(0, 16) : "";
}

function sanitizeParsedData(parsedData: ParsedDeclarationData): ParsedDeclarationData {
  return {
    ...parsedData,
    insured_name: parsedData.insured_name?.trim() || null,
    received_at: `${declarationDate(parsedData.received_at)}T00:00:00+08:00`,
    shipments: parsedData.shipments.map(shipment => {
      const cleaned = { ...shipment, extra_data: { ...shipment.extra_data } };
      for (const key of ["origin_country","destination_country","invoice_number","contract_number","bill_of_lading_number"] as const) cleaned[key] = null;
      for (const key of ["supplier","seller","member_assured","buyer","end_user","sanctions_screened","sanctions_findings","sanctions_licence"]) delete cleaned.extra_data[key];
      for (const key of ["mmsi_candidate", "mmsi_source", "mmsi_confirmed"]) delete cleaned.extra_data[key];
      for (const key of Object.keys(cleaned) as Array<keyof ShipmentData>) {
        if (key === "extra_data" || key === "id" || key === "declaration_id") continue;
        const value = cleaned[key];
        if (typeof value === "string") {
          const trimmed = value.trim();
          (cleaned as Record<string, unknown>)[key] = trimmed || null;
        }
        if (numericFields.has(key) && cleaned[key] === "") {
          (cleaned as Record<string, unknown>)[key] = null;
        }
      }
      return cleaned;
    }),
  };
}

function confirmationError(parsedData: ParsedDeclarationData) {
  if (!parsedData.shipments.length) return "至少需要一条运输标的信息。";
  for (const [index, shipment] of parsedData.shipments.entries()) {
    if (!String(shipment.extra_data?.insured_name ?? parsedData.insured_name ?? "").trim()) return `Excel 第 ${String(shipment.extra_data?.source_row ?? index + 2)} 行缺少被保险人。`;
    const formType = shipment.extra_data?.form_type;
    const required = formType === "vessel_information" ? [
      ["船名", shipment.vessel_name],
    ] : formType === "two_form_declaration" ? [
      ["船名", shipment.vessel_name], ["IMO", shipment.imo_number],
      ["货物名称", shipment.cargo_name], ["保险金额", shipment.insured_value],
      ["起运港", shipment.loading_port], ["目的港", shipment.discharge_port],
    ] : [
      ["船名", shipment.vessel_name],
      ["货物名称", shipment.cargo_name],
      ["数量", shipment.quantity],
      ["保险金额", shipment.insured_value],
      ["起运港", shipment.loading_port],
      ["目的港", shipment.discharge_port],
      ["ETD", shipment.etd],
    ];
    const missing = required.filter(([, value]) => value === null || value === undefined || String(value).trim() === "").map(([label]) => label);
    if (missing.length) return `运输标的 ${index + 1} 仍缺少必核字段：${missing.join("、")}。`;
    if (shipment.imo_number && !/^\d{7}$/.test(shipment.imo_number)) return `运输标的 ${index + 1} 的 IMO 应为 7 位数字。`;
    if (shipment.eta && shipment.etd && new Date(shipment.eta) < new Date(shipment.etd)) return `运输标的 ${index + 1} 的 ETA 不能早于 ETD。`;
  }
  return null;
}

function ReviewField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string | number | null | undefined;
  onChange: (value: string) => void;
  type?: "text" | "number" | "date" | "datetime-local";
  placeholder?: string;
}) {
  const inputValue = type === "date" ? fieldValue(value).slice(0, 10) : type === "datetime-local" ? dateTimeValue(typeof value === "string" ? value : null) : fieldValue(value);
  return (
    <label className="insurance-review-field">
      <span>{label}</span>
      <input type={type} step={type === "number" ? "any" : undefined} value={inputValue} placeholder={placeholder} onChange={event => onChange(event.target.value)} />
    </label>
  );
}

export function DeclarationImportDialog({ policies, initialImport, onClose, onConfirmed }: DeclarationImportDialogProps) {
  const [receivedDate] = useState(() => declarationDate());
  const [mode, setMode] = useState<"manual" | "upload">("upload");
  const [policyId, setPolicyId] = useState(initialImport?.policy_id ?? policies[0]?.id ?? "");
  const [underwritingFile, setUnderwritingFile] = useState<File | null>(null);
  const [vesselFile, setVesselFile] = useState<File | null>(null);
  const [importRecord, setImportRecord] = useState<DeclarationImport | null>(initialImport ?? null);
  const [parsedData, setParsedData] = useState<ParsedDeclarationData | null>(initialImport ? sanitizeParsedData(structuredClone(initialImport.parsed_data)) : null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState({
    business_type: "", vessel_name: "", imo_number: "", flag: "", vessel_owner: "",
    charterer: "", classification: "", pi_insurance: "", built_year: "",
    insured_name: "", cedant: "", etd_window: "", eta_window: "",
    intermediary_port_answer: "", transshipment_answer: "", loading_port: "", discharge_port: "",
    other_route_description: "", invoice_value: "", insured_value: "", currency: "USD",
    insured_value_tolerance_percent: "", cargo_name: "", hs_code: "", shipper: "",
    consignee: "",
  });

  function updateManual(field: keyof typeof manual, value: string) {
    setManual(current => ({ ...current, [field]: value }));
  }

  async function handleManual(status: "draft" | "pending_review") {
    if (!policyId || !manual.vessel_name.trim()) return;
    if (status === "pending_review" && !manual.insured_name.trim()) {
      setError("申报前请填写被保险人，以便进行主体制裁筛查。");
      return;
    }
    if (!manual.imo_number.trim() || !manual.cargo_name.trim() || !manual.insured_value.trim() || !manual.loading_port.trim() || !manual.discharge_port.trim()) {
      setError("请填写 IMO、货物、保险金额、起运港和目的港。");
      return;
    }
    if (manual.imo_number && !/^\d{7}$/.test(manual.imo_number.trim())) {
      setError("IMO 应为 7 位数字。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await createManualDeclaration({
        policyId,
        receivedAt: `${receivedDate}T00:00:00+08:00`,
        insuredName: manual.insured_name.trim() || null,
        status,
        notes: notes.trim() || null,
        shipment: {
          vessel_name: manual.vessel_name.trim(),
          imo_number: manual.imo_number.trim() || null,
          flag: manual.flag.trim() || null,
          built_year: manual.built_year ? Number(manual.built_year) : null,
          loading_port: manual.loading_port.trim(),
          discharge_port: manual.discharge_port.trim(),
          insured_value: Number(manual.insured_value),
          invoice_value: manual.invoice_value ? Number(manual.invoice_value) : null,
          currency: manual.currency.trim().toUpperCase(),
          cargo_name: manual.cargo_name.trim(),
          extra_data: {
            form_type: "two_form_declaration",
            insured_name: manual.insured_name.trim(),
            business_type: manual.business_type.trim(),
            vessel_owner: manual.vessel_owner.trim(),
            charterer: manual.charterer.trim(),
            classification: manual.classification.trim(),
            pi_insurance: manual.pi_insurance.trim(),
            cedant: manual.cedant.trim(),
            etd_window: manual.etd_window.trim(),
            eta_window: manual.eta_window.trim(),
            intermediary_port_answer: manual.intermediary_port_answer.trim(),
            transshipment_answer: manual.transshipment_answer.trim(),
            other_route_description: manual.other_route_description.trim(),
            insured_value_tolerance_percent: manual.insured_value_tolerance_percent.trim(),
            hs_code: manual.hs_code.trim(),
            shipper: manual.shipper.trim(),
            consignee: manual.consignee.trim(),
          },
        },
      });
      await onConfirmed(result.declaration_number, status);
    } catch (manualError) {
      setError(manualError instanceof Error ? manualError.message : "手动创建投保申报失败。");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!underwritingFile || !vesselFile || !policyId) return;
    setBusy(true);
    setError(null);
    try {
      const uploaded = await uploadDeclarationBundle({ policyId, underwritingFile, vesselFile });
      setImportRecord(uploaded);
      setParsedData(sanitizeParsedData({ ...structuredClone(uploaded.parsed_data), received_at: uploaded.parsed_data.received_at || uploaded.created_at || `${receivedDate}T00:00:00+08:00` }));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "投保表上传失败。");
    } finally {
      setBusy(false);
    }
  }

  function updateShipment(index: number, field: keyof ShipmentData, value: string) {
    setParsedData(current => {
      if (!current) return current;
      const shipments = current.shipments.map((shipment, shipmentIndex) => (
        shipmentIndex === index ? {
          ...shipment, [field]: value,
        } : shipment
      ));
      return { ...current, shipments };
    });
  }

  function updateVesselInfo(index: number, field: string, value: string) {
    setParsedData(current => current ? {
      ...current,
      shipments: current.shipments.map((shipment, shipmentIndex) => shipmentIndex === index
        ? { ...shipment, extra_data: { ...shipment.extra_data, [field]: value } }
        : shipment),
    } : current);
  }

  async function saveReview() {
    if (!importRecord || !parsedData) return null;
    const sanitized = sanitizeParsedData(parsedData);
    const updated = await saveDeclarationImport(importRecord.id, sanitized);
    setImportRecord(updated);
    setParsedData(structuredClone(updated.parsed_data));
    return updated;
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      await saveReview();
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "核实结果保存失败。");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!importRecord || !parsedData) return;
    const validationError = confirmationError(parsedData);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await saveReview();
      if (!updated) return;
      const result = await confirmDeclarationImport({ importId: updated.id, notes: notes.trim() || null, status: "pending_review" });
      await onConfirmed(result.declarations?.length && result.declarations.length > 1
        ? `${result.declarations.length} 票（${result.declarations[0].declaration_number} 起）` : result.declaration_number);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "确认创建申报失败。");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!window.confirm("确认取消导入吗？未申报的内容将不会生成投保记录。")) return;
    if (!importRecord) { onClose(); return; }
    setBusy(true);
    setError(null);
    try {
      await cancelDeclarationImport(importRecord.id);
      onClose();
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "取消导入失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="insurance-modal-backdrop" role="presentation">
      <section className="insurance-modal insurance-import-modal" role="dialog" aria-modal="true" aria-labelledby="declaration-import-title">
        <header>
          <div>
            <span>{importRecord ? "第 2 步，共 2 步 · 信息核实" : "选择录入方式"}</span>
            <h2 id="declaration-import-title">新增投保申报</h2>
          </div>
          <button type="button" onClick={handleCancel} disabled={busy} aria-label="取消导入">×</button>
        </header>

        {!importRecord ? <>
          <div className="insurance-entry-modes" role="group" aria-label="投保申报录入方式">
            <button type="button" className={mode === "upload" ? "active" : ""} onClick={() => { setMode("upload"); setError(null); }}>上传投保表格</button>
            <button type="button" className={mode === "manual" ? "active" : ""} onClick={() => { setMode("manual"); setError(null); }}>手动录入</button>
          </div>
          {mode === "manual" ? <form className="insurance-upload-form insurance-manual-form" onSubmit={event => { event.preventDefault(); void handleManual("pending_review"); }}>
            <div className="insurance-workflow-note">先核实投保主体与标的；点击申报后自动进行主体制裁筛查，再录入保司承保条件。仅投保确认后开始跟踪船舶。</div>
            <AutomaticDate value={receivedDate} />
            <label><span>归属框架协议</span><select value={policyId} onChange={event => setPolicyId(event.target.value)} required>{policies.map(policy => <option key={policy.id} value={policy.id}>{policy.company_name} · {policy.policy_number}</option>)}</select></label>
            <section className="insurance-declaration-section"><h3>1. 投保相关主体</h3>
            <div className="insurance-review-grid">
              {([["被保险人","insured_name"],["托运人","shipper"],["收货人","consignee"],["分出公司","cedant"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={manual[field]} onChange={value => updateManual(field, value)} />)}
            </div>
            </section>
            <section className="insurance-declaration-section"><h3>2. 拟投保标的</h3>
            <div className="insurance-review-grid">
              {([["货物名称 *","cargo_name"],["每船货物发票金额","invoice_value"],["每船货物保额 *","insured_value"],["保额浮动 %","insured_value_tolerance_percent"],["币种","currency"],["HS 编码","hs_code"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={manual[field]} type={["invoice_value", "insured_value", "insured_value_tolerance_percent"].includes(field) ? "number" : "text"} onChange={value => updateManual(field, value)} />)}
            </div>
            </section>
            <section className="insurance-declaration-section"><h3>3. 船舶信息</h3>
            <div className="insurance-review-grid">
              {([["船名 *","vessel_name"],["IMO 号 *","imo_number"],["船旗","flag"],["建造年份","built_year"],["船东","vessel_owner"],["租船人","charterer"],["船级","classification"],["保赔险","pi_insurance"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={manual[field]} type={["built_year", "insured_value", "insured_value_tolerance_percent"].includes(field) ? "number" : "text"} onChange={value => updateManual(field, value)} />)}
            </div>
            </section>
            <section className="insurance-declaration-section"><h3>4. 航程与运输安排</h3>
            <div className="insurance-review-grid">
              {([["起运港 *","loading_port"],["目的港 *","discharge_port"],["预计起运日期 / 区间","etd_window"],["预计到达日期 / 区间","eta_window"],["中途停靠港","intermediary_port_answer"],["中途转船","transshipment_answer"],["其他航程描述","other_route_description"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={manual[field]} type={["built_year", "insured_value", "insured_value_tolerance_percent"].includes(field) ? "number" : "text"} onChange={value => updateManual(field, value)} />)}
            </div>
            </section>
            <label className="insurance-review-notes"><span>备注</span><textarea value={notes} onChange={event => setNotes(event.target.value)} /></label>
            {error && <div className="insurance-inline-error" role="alert">{error}</div>}
            <div className="insurance-modal-actions"><button type="button" onClick={() => void handleManual("draft")} disabled={busy}>暂存</button><button type="submit" className="primary" disabled={busy || !manual.vessel_name.trim() || !manual.imo_number.trim() || !manual.cargo_name.trim() || !manual.insured_value.trim() || !manual.loading_port.trim() || !manual.discharge_port.trim() || !policyId}>{busy ? "正在提交…" : "申报"}</button></div>
          </form> : (
          <form className="insurance-upload-form" onSubmit={handleUpload}>
            <div className="insurance-workflow-note">
              两份表格共同组成投保材料；承保信息表的每一条申报记录会分别创建一票。上传后先核实，再申报并自动筛查主体。
            </div>
            <label><span>归属框架协议</span><select value={policyId} onChange={event => setPolicyId(event.target.value)} required>{policies.map(policy => <option key={policy.id} value={policy.id}>{policy.company_name} · {policy.policy_number}</option>)}</select></label>
            <AutomaticDate value={receivedDate} />
            <h3>投保材料</h3>
            <label><span>承保信息表</span><input type="file" accept=".xls,.xlsx" required onChange={event => setUnderwritingFile(event.target.files?.[0] ?? null)} /></label>
            <label><span>船舶信息表</span><input type="file" accept=".xls,.xlsx" required onChange={event => setVesselFile(event.target.files?.[0] ?? null)} /></label>
            {error && <div className="insurance-inline-error" role="alert">{error}</div>}
            <div className="insurance-modal-actions"><button type="submit" className="primary" disabled={busy || !underwritingFile || !vesselFile || !policyId}>{busy ? "正在解析…" : "上传并解析"}</button></div>
          </form>
          )}
        </> : parsedData ? (
          <div className="insurance-review-workspace">
            <div className="insurance-review-source">
              <span>原始材料</span><strong>{String(parsedData.extra_data?.underwriting_file_name ?? "承保信息")} + {String(parsedData.extra_data?.vessel_file_name ?? "船舶信息")}</strong><small>{importRecord.parser_name} · {importRecord.parser_version}</small>
            </div>
            {importRecord.warnings.length > 0 && <div className="insurance-review-warnings"><strong>解析提示</strong>{importRecord.warnings.map(warning => <span key={warning}>{warning}</span>)}</div>}
            <h3>归属框架协议</h3>
            <p>{policies.find(policy => policy.id === policyId)?.company_name} · {policies.find(policy => policy.id === policyId)?.policy_number}</p>
            <div className="insurance-review-general">
              <AutomaticDate value={declarationDate(parsedData.received_at)} />
            </div>

            <div className="insurance-review-shipments">
              {parsedData.shipments.map((shipment, index) => (
                <section className="insurance-review-shipment" key={`${importRecord.id}-${index}`}>
                  {parsedData.shipments.length > 1 && <p className="insurance-source-row">Excel 第 {String(shipment.extra_data?.source_row ?? index + 2)} 行 · {shipment.vessel_name || "待补船名"}</p>}
                  <section className="insurance-declaration-section"><h4>1. 投保相关主体</h4>
                    <div className="insurance-review-grid">
                      <ReviewField label="被保险人" value={String(shipment.extra_data?.insured_name ?? parsedData.insured_name ?? "")} onChange={value => updateVesselInfo(index, "insured_name", value)} />
                      {([["托运人", "shipper"], ["收货人", "consignee"], ["分出公司", "cedant"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={String(shipment.extra_data?.[field] ?? "")} onChange={value => updateVesselInfo(index, field, value)} />)}
                    </div>
                  </section>
                  <section className="insurance-declaration-section"><h4>2. 拟投保标的</h4>
                    <div className="insurance-review-grid">
                      {([["货物名称 *", "cargo_name", "text"], ["每船货物发票金额", "invoice_value", "number"], ["每船货物保额 *", "insured_value", "number"], ["币种", "currency", "text"]] as const).map(([label, field, type]) => <ReviewField key={field} label={label} type={type} value={shipment[field]} onChange={value => updateShipment(index, field, value)} />)}
                      <ReviewField label="保额浮动 %" value={String(shipment.extra_data?.insured_value_tolerance_percent ?? "")} type="number" onChange={value => updateVesselInfo(index, "insured_value_tolerance_percent", value)} />
                      <ReviewField label="HS 编码" value={String(shipment.extra_data?.hs_code ?? "")} onChange={value => updateVesselInfo(index, "hs_code", value)} />
                    </div>
                  </section>
                  <section className="insurance-declaration-section"><h4>3. 船舶信息</h4>
                    <div className="insurance-review-grid">
                      {([["船名 *", "vessel_name", "text"], ["IMO *", "imo_number", "text"], ["船旗", "flag", "text"], ["建造年份", "built_year", "number"]] as const).map(([label, field, type]) => <ReviewField key={field} label={label} type={type} value={shipment[field]} onChange={value => updateShipment(index, field, value)} />)}
                      {([["船东", "vessel_owner"], ["租船人", "charterer"], ["船级", "classification"], ["保赔险", "pi_insurance"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={String(shipment.extra_data?.[field] ?? "")} onChange={value => updateVesselInfo(index, field, value)} />)}
                    </div>
                  </section>
                  {shipment.extra_data?.form_type !== "vessel_information" && <section className="insurance-declaration-section"><h4>4. 航程与运输安排</h4>
                    <div className="insurance-review-grid">
                      {([["起运港 *", "loading_port", "text"], ["目的港 *", "discharge_port", "text"], ["途经港", "via_port", "text"], ["预计起运日期", "etd", "date"], ["预计到达日期", "eta", "date"]] as const).map(([label, field, type]) => <ReviewField key={field} label={label} type={type} value={shipment[field]} onChange={value => updateShipment(index, field, value)} />)}
                      {([["预计起运区间（原文）", "etd_window"], ["预计到达区间（原文）", "eta_window"], ["中途停靠港", "intermediary_port_answer"], ["中途转船", "transshipment_answer"], ["其他航程描述", "other_route_description"]] as const).map(([label, field]) => <ReviewField key={field} label={label} value={String(shipment.extra_data?.[field] ?? "")} onChange={value => updateVesselInfo(index, field, value)} />)}
                    </div>
                  </section>}
                </section>
              ))}
            </div>
            <label className="insurance-review-notes"><span>核实备注</span><textarea value={notes} onChange={event => setNotes(event.target.value)} placeholder="记录信息来源、缺失项或需要后续补充的材料。" /></label>
            {error && <div className="insurance-inline-error" role="alert">{error}</div>}
            <div className="insurance-modal-actions insurance-review-actions">
              <button type="button" onClick={handleSave} disabled={busy}>{busy ? "处理中…" : "暂存"}</button>
              <button type="button" className="primary" onClick={handleConfirm} disabled={busy || !parsedData.shipments.length}>{busy ? "处理中…" : "申报"}</button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
