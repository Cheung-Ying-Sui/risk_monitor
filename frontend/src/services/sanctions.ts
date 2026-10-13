import type { DeclarationScreeningCase, SanctionsCandidate, SanctionsList, ScreeningEntityType } from "@/types/sanctions";
import type { ScreeningMode } from "@/components/sanctions-screening/screening-toolbar";
import { authenticatedFetch } from "@/lib/api-fetch";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000").replace(/\/$/, "");

interface ApiMatch {
  profile_id: string;
  source: string;
  names: string[];
  addresses: string[];
  programs: string[];
  matched_name: string;
  match_type: string;
  score: number;
}

export interface SanctionsScreeningResponse {
  keyword: string;
  normalized_keyword: string;
  results: ApiMatch[];
  suggestions: Array<{ name: string; score: number }>;
  ai_candidates: Array<{
    query: string;
    reason: string;
    ai_probability: number | null;
    matched_name: string | null;
    match_score: number | null;
    profile_id: string | null;
    programs: string[];
    formal_match: boolean;
  }>;
  ai_message: string | null;
  message: string | null;
}

function statusFor(score: number): SanctionsCandidate["status"] {
  if (score >= 95) return "likely_match";
  if (score >= 80) return "possible_match";
  return "review_required";
}

export function toSanctionsCandidates(
  response: SanctionsScreeningResponse,
  entityType: "all" | ScreeningEntityType,
): SanctionsCandidate[] {
  const subjectType = entityType === "all" ? "other" : entityType;
  return response.results.map(match => {
    const aliases = match.names.filter(name => name !== match.matched_name);
    const status = statusFor(match.score);
    const highConfidence = match.score >= 95;
    return {
      id: `${match.source}-${match.profile_id}`,
      subject: { id: `query-${match.profile_id}`, name: response.keyword, entityType: subjectType },
      matchedName: match.matched_name,
      aliases,
      sanctionsList: "OFAC",
      programs: match.programs,
      matchScore: match.score,
      status,
      evidence: [
        { type: "name_similarity", label: "名称相似度", value: `${match.score.toFixed(1)}%`, score: Math.round(match.score) },
        { type: "exact_tokens", label: "匹配方式", value: match.match_type === "exact" ? "精确匹配" : "标准化模糊匹配" },
        ...(aliases.length ? [{ type: "alias" as const, label: "相关别名", value: aliases.join(" · ") }] : []),
        ...(match.addresses.length ? [{ type: "country" as const, label: "登记地址", value: match.addresses.join(" · ") }] : []),
      ],
      sanctionsRecord: {
        primaryName: match.names[0] || match.matched_name,
        aliases,
        listLabel: `${match.source} SDN`,
        programs: match.programs,
        entityType: subjectType,
        referenceId: `${match.source}-${match.profile_id}`,
      },
      assessment: {
        assessment: highConfidence ? "高可信匹配" : "需要人工复核",
        confidence: highConfidence ? "High" : match.score >= 80 ? "Medium" : "Low",
        summary: `输入名称与制裁名单记录“${match.matched_name}”的相似度为 ${match.score.toFixed(1)}%。该结果来自真实 ${match.source} 数据库，仍需结合主体身份资料进行人工核验。`,
        keyReasons: ["名称匹配", ...(aliases.length ? ["存在相关别名"] : []), ...(match.programs.length ? ["存在制裁项目记录"] : [])],
        missingInformation: ["主体注册信息", "受益所有权资料"],
        recommendedNextStep: highConfidence ? "立即暂停业务并提交合规复核" : "核验完整法定名称及身份资料",
      },
      initialReviewStatus: "not_reviewed",
    };
  });
}

export async function screenSanctions(input: {
  query: string;
  entityType: "all" | ScreeningEntityType;
  sanctionsList: "all" | SanctionsList;
  mode: ScreeningMode;
}): Promise<SanctionsScreeningResponse> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${baseUrl}/api/v1/sanctions/screen`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ query: input.query, entity_type: input.entityType, sanctions_list: input.sanctionsList, mode: input.mode }),
    });
  } catch {
    throw new Error("无法连接制裁筛查服务，请确认 FastAPI 已启动。");
  }
  const body = await response.json().catch(() => null) as SanctionsScreeningResponse | { detail?: string } | null;
  if (!response.ok) throw new Error(body && "detail" in body && body.detail ? body.detail : "制裁筛查失败。");
  return body as SanctionsScreeningResponse;
}

async function caseRequest(path: string, init?: RequestInit): Promise<DeclarationScreeningCase> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${baseUrl}/api/v1/sanctions/declaration-cases${path}`, {
      ...init, headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("无法连接制裁筛查服务，请确认 FastAPI 已启动。");
  }
  const body = await response.json().catch(() => null) as DeclarationScreeningCase | { detail?: string } | null;
  if (!response.ok) throw new Error(body && "detail" in body && body.detail ? body.detail : "申报主体筛查请求失败。");
  return body as DeclarationScreeningCase;
}

export async function listDeclarationScreeningCases(): Promise<DeclarationScreeningCase[]> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${baseUrl}/api/v1/sanctions/declaration-cases`, { headers: { Accept: "application/json" } });
  } catch {
    throw new Error("无法连接制裁筛查服务，请确认 FastAPI 已启动。");
  }
  const body = await response.json().catch(() => null) as DeclarationScreeningCase[] | { detail?: string } | null;
  if (!response.ok) throw new Error(body && !Array.isArray(body) && "detail" in body && body.detail ? body.detail : "待筛查列表加载失败。");
  return body as DeclarationScreeningCase[];
}

export function getDeclarationScreeningCase(declarationId: string) {
  return caseRequest(`/${encodeURIComponent(declarationId)}`);
}

function partyPath(declarationId: string, shipmentId: string, role: string) {
  return `/${encodeURIComponent(declarationId)}/parties/${encodeURIComponent(shipmentId)}/${encodeURIComponent(role)}`;
}

export function screenDeclarationParty(declarationId: string, shipmentId: string, role: string) {
  return caseRequest(`${partyPath(declarationId, shipmentId, role)}/screen`, { method: "POST" });
}

export function uploadDeclarationPartyScreenshot(declarationId: string, shipmentId: string, role: string, file: File) {
  const form = new FormData();
  form.set("file", file);
  return caseRequest(`${partyPath(declarationId, shipmentId, role)}/evidence`, { method: "POST", body: form });
}

export function reviewDeclarationParty(declarationId: string, shipmentId: string, role: string, result: string, reviewer: string, note: string) {
  return caseRequest(`${partyPath(declarationId, shipmentId, role)}/review`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result, reviewer, note }),
  });
}

export function generateDeclarationScreeningReport(declarationId: string) {
  return caseRequest(`/${encodeURIComponent(declarationId)}/report`, { method: "POST" });
}

export async function downloadDeclarationScreeningReport(declarationId: string, expectedSha256: string): Promise<Blob> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${baseUrl}/api/v1/sanctions/declaration-cases/${encodeURIComponent(declarationId)}/report/download`);
  } catch {
    throw new Error("无法连接制裁筛查服务，请确认 FastAPI 已启动。");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail || "筛查报告下载失败。");
  }
  const blob = await response.blob();
  const bytes = await blob.arrayBuffer();
  const signature = new Uint8Array(bytes, 0, Math.min(4, bytes.byteLength));
  if (blob.size < 4 || signature[0] !== 0x50 || signature[1] !== 0x4b || signature[2] !== 3 || signature[3] !== 4) {
    throw new Error("下载内容为空或不是有效 Word 文件，尚未创建本地文件，请重试。");
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  if (sha256 !== expectedSha256) throw new Error("报告完整性校验失败，尚未创建本地文件，请重新生成。");
  return blob;
}
