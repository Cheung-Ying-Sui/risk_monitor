import type {
  DeclarationConfirmation,
  DeclarationDetail,
  DeclarationImport,
  DeclarationSourceType,
  DeclarationSummary,
  FrameworkPolicy,
  FrameworkPolicyDetail,
  DeclaredVessel,
  ParsedDeclarationData,
  ShipmentData,
} from "@/types/insurance";
import { authenticatedFetch } from "@/lib/api-fetch";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000").replace(/\/$/, "");

async function responseBody<T>(response: Response, fallback: string): Promise<T> {
  const body = await response.json().catch(() => null) as T | { detail?: string } | null;
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" && detail ? detail : fallback);
  }
  return body as T;
}

async function apiFetch<T>(path: string, init?: RequestInit, fallback = "保险服务请求失败。"): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${baseUrl}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("无法连接保险服务，请确认 FastAPI 已启动。");
  }
  return responseBody<T>(response, fallback);
}

export async function loadInsuranceWorkspace(): Promise<{
  policies: FrameworkPolicy[];
  declarations: DeclarationSummary[];
  pendingImports: DeclarationImport[];
}> {
  async function loadAll<T>(path: string): Promise<T[]> {
    const pageSize = 500;
    const rows: T[] = [];
    for (let offset = 0; ; offset += pageSize) {
      const page = await apiFetch<T[]>(`${path}?limit=${pageSize}&offset=${offset}`);
      rows.push(...page);
      if (page.length < pageSize) return rows;
    }
  }
  const [policies, declarations, pendingImports] = await Promise.all([
    loadAll<FrameworkPolicy>("/api/v1/insurance/policies"),
    loadAll<DeclarationSummary>("/api/v1/insurance/declarations"),
    apiFetch<DeclarationImport[]>("/api/v1/insurance/declaration-imports"),
  ]);
  return { policies, declarations, pendingImports };
}

export function getFrameworkPolicy(policyId: string): Promise<FrameworkPolicyDetail> {
  return apiFetch<FrameworkPolicyDetail>(`/api/v1/insurance/policies/${encodeURIComponent(policyId)}`);
}

export interface InsuranceCompany { id: string; name: string; }

export function getInsuranceCompanies(): Promise<InsuranceCompany[]> {
  return apiFetch<InsuranceCompany[]>("/api/v1/insurance/companies");
}

export function createInsuranceCompany(name: string): Promise<InsuranceCompany> {
  return apiFetch<InsuranceCompany>("/api/v1/insurance/companies", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  }, "企业创建失败。");
}

export function createFrameworkPolicy(input: {
  company_id: string; policy_name: string; policy_number: string; insurer: string;
  start_date: string; end_date: string; currency: string; status: "active" | "pending";
}): Promise<FrameworkPolicy> {
  return apiFetch<FrameworkPolicy>("/api/v1/insurance/policies", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }, "框架协议创建失败。");
}

export function voidFrameworkPolicy(policyId: string): Promise<FrameworkPolicy> {
  return apiFetch<FrameworkPolicy>(`/api/v1/insurance/policies/${encodeURIComponent(policyId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "cancelled" }),
  }, "框架协议作废失败。");
}

export function voidDeclaration(declarationId: string): Promise<DeclarationDetail> {
  return apiFetch<DeclarationDetail>(`/api/v1/insurance/declarations/${encodeURIComponent(declarationId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "cancelled" }),
  }, "投保申报作废失败。");
}

export function getDeclaration(declarationId: string): Promise<DeclarationDetail> {
  return apiFetch<DeclarationDetail>(`/api/v1/insurance/declarations/${declarationId}`);
}

export function getInsuredVessels(signal?: AbortSignal): Promise<DeclaredVessel[]> {
  return apiFetch<DeclaredVessel[]>("/api/v1/insurance/insured-vessels", { signal });
}

export function createManualDeclaration(input: {
  policyId: string;
  receivedAt: string;
  insuredName: string | null;
  shipment: Partial<ShipmentData>;
  notes: string | null;
  status?: "draft" | "pending_review";
}): Promise<DeclarationConfirmation> {
  return apiFetch<DeclarationConfirmation>("/api/v1/insurance/manual-declarations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy_id: input.policyId, received_at: input.receivedAt, insured_name: input.insuredName, shipment: input.shipment, notes: input.notes, status: input.status ?? "pending_review" }),
  }, "手动创建投保申报失败。");
}

export function suggestDeclarationMmsi(imoNumber: string, vesselName: string | null): Promise<{
  mmsi: string | null;
  source: "deepseek_web_search";
  source_url: string | null;
  source_title: string | null;
  identity_check: "matched" | "mismatch" | "unavailable" | "not_checked";
  warning: string;
}> {
  return apiFetch("/api/v1/insurance/mmsi-suggestion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ imo_number: imoNumber, vessel_name: vesselName }),
  }, "MMSI 联网检索失败。请手动录入并核实。");
}

export function verifyDeclarationMmsi(imoNumber: string, mmsi: string): Promise<{
  imo_number: string;
  mmsi: string;
  vessel_name: string | null;
}> {
  return apiFetch("/api/v1/insurance/mmsi-verification", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ imo_number: imoNumber, mmsi }),
  }, "MMSI 核实失败，请稍后重试。");
}

export async function uploadDeclaration(input: {
  policyId: string;
  sourceType: DeclarationSourceType;
  file: File;
}): Promise<DeclarationImport> {
  const form = new FormData();
  form.set("policy_id", input.policyId);
  form.set("source_type", input.sourceType);
  form.set("file", input.file);
  return apiFetch<DeclarationImport>("/api/v1/insurance/declaration-imports", {
    method: "POST",
    body: form,
  }, "投保表上传或解析失败。");
}

export async function uploadDeclarationBundle(input: {
  policyId: string; underwritingFile: File; vesselFile: File;
}): Promise<DeclarationImport> {
  const form = new FormData();
  form.set("policy_id", input.policyId);
  form.set("underwriting_file", input.underwritingFile);
  form.set("vessel_file", input.vesselFile);
  return apiFetch<DeclarationImport>("/api/v1/insurance/declaration-imports/bundle", {
    method: "POST", body: form,
  }, "两份投保材料上传或解析失败。");
}

export function saveDeclarationImport(importId: string, parsedData: ParsedDeclarationData): Promise<DeclarationImport> {
  return apiFetch<DeclarationImport>(`/api/v1/insurance/declaration-imports/${importId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parsed_data: parsedData }),
  }, "核实结果保存失败。");
}

export function confirmDeclarationImport(input: {
  importId: string;
  notes: string | null;
  status?: "draft" | "pending_review";
}): Promise<DeclarationConfirmation> {
  return apiFetch<DeclarationConfirmation>(`/api/v1/insurance/declaration-imports/${input.importId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: input.status ?? "pending_review", notes: input.notes }),
  }, "确认创建申报失败。");
}

export function confirmUnderwritingTerms(declarationId: string, rate: number): Promise<DeclarationDetail> {
  return apiFetch<DeclarationDetail>(`/api/v1/insurance/declarations/${encodeURIComponent(declarationId)}/underwriting-terms`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rate }),
  }, "承保条件确认失败。");
}

export function confirmUnderwriting(declarationId: string): Promise<DeclarationDetail> {
  return apiFetch<DeclarationDetail>(`/api/v1/insurance/declarations/${encodeURIComponent(declarationId)}/underwriting-confirm`, {
    method: "POST",
  }, "投保确认失败。");
}

export function completeUnderwriting(declarationId: string, rate: number): Promise<DeclarationDetail> {
  return apiFetch<DeclarationDetail>(`/api/v1/insurance/declarations/${encodeURIComponent(declarationId)}/underwriting-complete`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rate }),
  }, "确认失败，请检查费率（0–100%）并刷新申报状态后重试。");
}

export function submitDraftDeclaration(declarationId: string): Promise<DeclarationDetail> {
  return apiFetch<DeclarationDetail>(`/api/v1/insurance/declarations/${encodeURIComponent(declarationId)}/submit`, {
    method: "POST",
  }, "草稿申报失败。");
}

export function cancelDeclarationImport(importId: string): Promise<DeclarationImport> {
  return apiFetch<DeclarationImport>(`/api/v1/insurance/declaration-imports/${importId}/cancel`, {
    method: "POST",
  }, "取消导入失败。");
}
