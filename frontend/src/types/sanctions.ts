export type ScreeningEntityType = "company" | "supplier" | "shipowner" | "vessel" | "individual" | "other";
export type SanctionsList = "OFAC" | "UK" | "EU" | "UN";
export type ScreeningResultStatus = "clear" | "possible_match" | "likely_match" | "confirmed_match" | "review_required";
export type ReviewStatus = "not_reviewed" | "under_review" | "cleared" | "confirmed" | "escalated";

export interface ScreeningSubject {
  id: string;
  name: string;
  entityType: ScreeningEntityType;
  country?: string;
  registrationNo?: string;
  imo?: string;
  mmsi?: string;
  flag?: string;
  owner?: string;
}

export interface MatchEvidence {
  type: "name_similarity" | "exact_tokens" | "alias" | "country" | "entity_type" | "identifier";
  label: string;
  value: string | number;
  score?: number;
}

export interface MatchedSanctionsRecord {
  primaryName: string;
  aliases: string[];
  listLabel: string;
  programs: string[];
  entityType: ScreeningEntityType;
  referenceId: string;
}

export interface PreliminaryAssessment {
  assessment: string;
  confidence: "Low" | "Medium" | "High";
  summary: string;
  keyReasons: string[];
  missingInformation: string[];
  recommendedNextStep: string;
}

export interface SanctionsCandidate {
  id: string;
  subject: ScreeningSubject;
  matchedName: string;
  aliases: string[];
  sanctionsList: SanctionsList;
  programs: string[];
  matchScore: number;
  status: ScreeningResultStatus;
  evidence: MatchEvidence[];
  sanctionsRecord: MatchedSanctionsRecord;
  assessment: PreliminaryAssessment;
  initialReviewStatus: ReviewStatus;
}

export interface ScreeningRecord {
  id: string;
  screenedAt: string;
  subject: ScreeningSubject;
  result: ScreeningResultStatus;
  matchScore: number;
  sanctionsList?: SanctionsList;
  reviewStatus: ReviewStatus;
  screenedBy: string;
}

export interface DeclarationScreeningParty {
  shipment_id: string;
  role: string;
  label: string;
  name: string;
  preliminary: { screened_at: string; source: string; query: string; results: Array<{
    profile_id: string; source: string; matched_name: string; score: number; programs?: string[];
  }>; suggestions: Array<{ name: string; score: number }> } | null;
  evidence: { document_id: string; file_name: string; sha256: string; uploaded_at: string; url: string | null } | null;
  review: { result: string; reviewer: string; note: string; reviewed_at: string; source: string } | null;
}

export interface DeclarationScreeningCase {
  stage: "pending_screening" | "pending_report_download" | "pending_underwriting" | "confirmed";
  declaration_id: string;
  declaration_number: string;
  company_name: string | null;
  status: string;
  received_at: string;
  parties: DeclarationScreeningParty[];
  report: { document_id: string; generated_at: string; downloaded_at?: string; template_version?: string; file_name: string; sha256: string; url: string | null; download_path: string } | null;
  underwriting: { shipment_count: number; cargo_name: string | null; currency: string | null; insured_value: string | number | null; insured_value_tolerance_percent: string | number | null;
    status: string; rate: string | number | null; premium: string | number | null; confirmed_at: string | null };
  official_search_url: string;
}
