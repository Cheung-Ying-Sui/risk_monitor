export type InsuranceWorkspaceTab = "declarations" | "policies" | "ecargo" | "shipments";
export type InsuranceBusinessType = "Marine Cargo" | "Vessel" | "Marine Liability" | "Freight" | "War Risk" | "Other Marine";
export type ApplicationStatus = "draft" | "pending" | "submitted" | "quoted" | "bound" | "declined" | "cancelled";
export type PortfolioStatus = "active" | "pending" | "expiring" | "closed";
export type RiskLevel = "normal" | "elevated" | "high";

export interface InsuranceApplication {
  id: string;
  status: ApplicationStatus;
  client: string;
  insuranceType: InsuranceBusinessType;
  subject: string;
  vessel?: string;
  voyage?: string;
  sumInsured: number;
  currency: "USD";
  createdAt: string;
  owner: string;
  risk: RiskLevel;
}

export interface InsurancePolicy {
  id: string;
  policyNumber: string;
  client: string;
  insuranceType: InsuranceBusinessType;
  subject: string;
  sumInsured: number;
  currency: "USD";
  insurer: string;
  inception: string;
  expiry: string;
  status: PortfolioStatus;
}

export interface InsuredCargo {
  id: string;
  cargo: string;
  commodity: string;
  quantity: string;
  vessel: string;
  origin: string;
  destination: string;
  sumInsured: number;
  currency: "USD";
  policyNumber: string;
  status: PortfolioStatus;
}

export interface InsuredVessel {
  id: string;
  vessel: string;
  imo: string;
  mmsi: string;
  vesselType: string;
  policyNumber: string;
  sumInsured: number;
  currency: "USD";
  currentVoyage: string;
  risk: RiskLevel;
  status: PortfolioStatus;
}

export interface InsuranceTask {
  id: string;
  type: "quote_expiring" | "document_required" | "policy_expiring" | "review_required";
  subject: string;
  due: string;
  urgency: "normal" | "warning" | "critical";
}

export interface InsuranceActivity {
  id: string;
  time: string;
  description: string;
  actor: string;
}

export type FrameworkPolicyStatus = "active" | "pending" | "expiring_soon" | "expired" | "cancelled";
export type DeclarationStatus = "draft" | "pending_review" | "confirmed" | "covered" | "completed" | "cancelled";
export type DeclarationSourceType = "manual_upload" | "email" | "api";

export interface InsuranceDashboardSummary {
  active_policy_count: number;
  current_year_declaration_count: number;
  insured_value_total: string;
  active_shipment_count: number;
  pending_declaration_count: number;
}

export interface FrameworkPolicy {
  id: string;
  company_id: string;
  company_name: string | null;
  policy_name: string;
  policy_number: string;
  insurer: string;
  start_date: string;
  end_date: string;
  currency: string;
  rate: string | null;
  shipment_limit: string | null;
  annual_estimated_value: string | null;
  valuation_basis: string | null;
  deductible: string | null;
  cargo_scope: string | null;
  territory: string | null;
  transport_mode: string | null;
  insurance_clause: string | null;
  war_risk: string | null;
  special_conditions: string | null;
  status: FrameworkPolicyStatus;
  declaration_count: number;
  insured_value_total: string;
  premium_total: string;
  active_shipment_count: number;
  pending_declaration_count: number;
  recent_declaration_number: string | null;
  recent_vessel_name: string | null;
  recent_cargo_name: string | null;
  recent_declaration_at: string | null;
}

export interface FrameworkPolicyDetail extends FrameworkPolicy {
  recent_declarations: DeclarationSummary[];
  documents: InsuranceDocument[];
}

export interface ShipmentData {
  id?: string;
  declaration_id?: string;
  vessel_name: string | null;
  imo_number: string | null;
  voyage_number: string | null;
  flag: string | null;
  built_year: number | string | null;
  cargo_name: string | null;
  cargo_description: string | null;
  cargo_marks: string | null;
  quantity: string | number | null;
  quantity_unit: string | null;
  quantity_tolerance_percent: string | number | null;
  invoice_number: string | null;
  contract_number: string | null;
  bill_of_lading_number: string | null;
  invoice_value: string | number | null;
  insured_value: string | number | null;
  currency: string | null;
  loading_port: string | null;
  discharge_port: string | null;
  via_port: string | null;
  origin_country: string | null;
  destination_country: string | null;
  etd: string | null;
  eta: string | null;
  insurance_rate: string | number | null;
  premium: string | number | null;
  certificate_number: string | null;
  coverage_status: string | null;
  extra_data: Record<string, unknown>;
}

export interface InsuranceDocument {
  id: string;
  document_type: string;
  file_name: string;
  content_type: string | null;
  file_size: number | null;
  download_url: string | null;
  uploaded_at: string | null;
}

export interface DeclarationSummary {
  id: string;
  declaration_number: string;
  policy_id: string;
  company_id: string;
  company_name: string | null;
  policy_name: string | null;
  source_type: DeclarationSourceType;
  source_file_name: string | null;
  received_at: string;
  status: DeclarationStatus;
  notes: string | null;
  shipments: ShipmentData[];
  created_at: string | null;
  updated_at: string | null;
}

export interface DeclarationDetail extends DeclarationSummary {
  documents: InsuranceDocument[];
}

export interface DeclaredVessel {
  vessel_name: string;
  imo_number: string | null;
  confirmed_mmsi: string | null;
  declaration_count: number;
  declaration_number: string;
  company_name: string | null;
  tracking_status: "invalid_imo" | "awaiting_ais_provider" | "awaiting_imo_match" | "mmsi_confirmation_required" | "not_tracking" | "awaiting_position" | "stale_position" | "current" | "unknown" | null;
}

export interface ParsedDeclarationData {
  insured_name: string | null;
  received_at: string | null;
  shipments: ShipmentData[];
  extra_data: Record<string, unknown>;
}

export interface DeclarationImport {
  id: string;
  policy_id: string;
  company_id: string;
  source_type: DeclarationSourceType;
  source_file_name: string;
  parser_name: string;
  parser_version: string;
  parsed_data: ParsedDeclarationData;
  warnings: string[];
  status: "pending_confirmation" | "confirmed" | "cancelled" | "failed";
  created_at: string | null;
  updated_at: string | null;
}

export interface DeclarationConfirmation {
  declaration_id: string;
  declaration_number: string;
  declarations?: Array<{ declaration_id: string; declaration_number: string }>;
}
