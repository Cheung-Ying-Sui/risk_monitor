from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PolicyStatus = Literal["active", "expiring_soon", "expired", "pending", "cancelled"]
DeclarationStatus = Literal[
    "draft",
    "pending_review",
    "confirmed",
    "covered",
    "completed",
    "cancelled",
]
DeclarationSourceType = Literal["manual_upload", "email", "api"]
DocumentType = Literal[
    "framework_policy",
    "declaration_form",
    "certificate",
    "endorsement",
    "invoice",
    "bill_of_lading",
    "other",
]


class InsuranceBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class CompanyCreate(InsuranceBaseModel):
    name: str = Field(min_length=1, max_length=240)
    name_en: str | None = Field(default=None, max_length=240)
    aliases: list[str] = Field(default_factory=list)


class CompanyResponse(CompanyCreate):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PolicyCreate(InsuranceBaseModel):
    company_id: str
    policy_name: str = Field(min_length=1, max_length=300)
    policy_number: str = Field(min_length=1, max_length=160)
    insurer: str = Field(min_length=1, max_length=300)
    start_date: date
    end_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    rate: Decimal | None = Field(default=None, ge=0)
    shipment_limit: Decimal | None = Field(default=None, ge=0)
    annual_estimated_value: Decimal | None = Field(default=None, ge=0)
    valuation_basis: str | None = None
    deductible: str | None = None
    cargo_scope: str | None = None
    territory: str | None = None
    transport_mode: str | None = None
    insurance_clause: str | None = None
    war_risk: str | None = None
    special_conditions: str | None = None
    status: Literal["active", "pending", "cancelled"] = "active"

    @model_validator(mode="after")
    def validate_dates(self) -> "PolicyCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class PolicyUpdate(InsuranceBaseModel):
    policy_name: str | None = Field(default=None, min_length=1, max_length=300)
    policy_number: str | None = Field(default=None, min_length=1, max_length=160)
    insurer: str | None = Field(default=None, min_length=1, max_length=300)
    start_date: date | None = None
    end_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    rate: Decimal | None = Field(default=None, ge=0)
    shipment_limit: Decimal | None = Field(default=None, ge=0)
    annual_estimated_value: Decimal | None = Field(default=None, ge=0)
    valuation_basis: str | None = None
    deductible: str | None = None
    cargo_scope: str | None = None
    territory: str | None = None
    transport_mode: str | None = None
    insurance_clause: str | None = None
    war_risk: str | None = None
    special_conditions: str | None = None
    status: Literal["active", "pending", "cancelled"] | None = None


class PolicyResponse(InsuranceBaseModel):
    id: str
    company_id: str
    company_name: str | None = None
    policy_name: str
    policy_number: str
    insurer: str
    start_date: date
    end_date: date
    currency: str
    rate: Decimal | None = None
    shipment_limit: Decimal | None = None
    annual_estimated_value: Decimal | None = None
    valuation_basis: str | None = None
    deductible: str | None = None
    cargo_scope: str | None = None
    territory: str | None = None
    transport_mode: str | None = None
    insurance_clause: str | None = None
    war_risk: str | None = None
    special_conditions: str | None = None
    status: PolicyStatus
    declaration_count: int = 0
    insured_value_total: Decimal = Decimal("0")
    premium_total: Decimal = Decimal("0")
    active_shipment_count: int = 0
    pending_declaration_count: int = 0
    recent_declaration_number: str | None = None
    recent_vessel_name: str | None = None
    recent_cargo_name: str | None = None
    recent_declaration_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ShipmentInput(InsuranceBaseModel):
    vessel_name: str | None = None
    imo_number: str | None = Field(default=None, pattern=r"^\d{7}$")
    voyage_number: str | None = None
    flag: str | None = None
    built_year: int | None = Field(default=None, ge=1800, le=2200)
    cargo_name: str | None = None
    cargo_description: str | None = None
    cargo_marks: str | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    quantity_unit: str | None = None
    quantity_tolerance_percent: Decimal | None = Field(default=None, ge=0)
    invoice_number: str | None = None
    contract_number: str | None = None
    bill_of_lading_number: str | None = None
    invoice_value: Decimal | None = Field(default=None, ge=0)
    insured_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    loading_port: str | None = None
    discharge_port: str | None = None
    via_port: str | None = None
    origin_country: str | None = None
    destination_country: str | None = None
    etd: datetime | None = None
    eta: datetime | None = None
    insurance_rate: Decimal | None = Field(default=None, ge=0)
    premium: Decimal | None = Field(default=None, ge=0)
    certificate_number: str | None = None
    coverage_status: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_voyage_dates(self) -> "ShipmentInput":
        if self.etd and self.eta and self.eta < self.etd:
            raise ValueError("eta must be on or after etd")
        return self


class ShipmentResponse(ShipmentInput):
    id: str
    declaration_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InsuranceDocumentResponse(InsuranceBaseModel):
    id: str
    policy_id: str | None = None
    declaration_id: str | None = None
    shipment_id: str | None = None
    document_type: DocumentType
    file_name: str
    content_type: str | None = None
    file_size: int | None = None
    storage_bucket: str
    storage_path: str
    download_url: str | None = None
    uploaded_at: datetime | None = None


class DeclarationSummaryResponse(InsuranceBaseModel):
    id: str
    declaration_number: str
    policy_id: str
    company_id: str
    company_name: str | None = None
    policy_name: str | None = None
    source_type: DeclarationSourceType
    source_file_name: str | None = None
    received_at: datetime
    status: DeclarationStatus
    notes: str | None = None
    shipments: list[ShipmentResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeclarationDetailResponse(DeclarationSummaryResponse):
    documents: list[InsuranceDocumentResponse] = Field(default_factory=list)


class DeclarationUpdate(InsuranceBaseModel):
    status: Literal["cancelled"]


class PolicyDetailResponse(PolicyResponse):
    recent_declarations: list[DeclarationSummaryResponse] = Field(default_factory=list)
    documents: list[InsuranceDocumentResponse] = Field(default_factory=list)


class DashboardSummaryResponse(InsuranceBaseModel):
    active_policy_count: int = 0
    current_year_declaration_count: int = 0
    insured_value_total: Decimal = Decimal("0")
    active_shipment_count: int = 0
    pending_declaration_count: int = 0


class ParsedDeclarationData(InsuranceBaseModel):
    insured_name: str | None = None
    received_at: datetime | None = None
    shipments: list[ShipmentInput] = Field(default_factory=list)
    extra_data: dict[str, Any] = Field(default_factory=dict)


class DeclarationImportResponse(InsuranceBaseModel):
    id: str
    policy_id: str
    company_id: str
    source_type: DeclarationSourceType
    source_file_name: str
    parser_name: str
    parser_version: str
    parsed_data: ParsedDeclarationData
    warnings: list[str] = Field(default_factory=list)
    status: Literal["pending_confirmation", "confirmed", "cancelled", "failed"]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeclarationImportUpdate(InsuranceBaseModel):
    parsed_data: ParsedDeclarationData


class DeclarationConfirmRequest(InsuranceBaseModel):
    status: Literal["draft", "pending_review"] = "pending_review"
    notes: str | None = None
    received_at: datetime | None = None
    shipments: list[ShipmentInput] | None = None


class ManualDeclarationCreate(InsuranceBaseModel):
    policy_id: str
    received_at: datetime | None = None
    insured_name: str | None = None
    notes: str | None = None
    status: Literal["draft", "pending_review"] = "pending_review"
    shipment: ShipmentInput

    @model_validator(mode="after")
    def validate_vessel(self) -> "ManualDeclarationCreate":
        if not self.shipment.vessel_name:
            raise ValueError("vessel name is required")
        return self


class MmsiSuggestionRequest(InsuranceBaseModel):
    imo_number: str = Field(pattern=r"^\d{7}$")
    vessel_name: str | None = Field(default=None, max_length=120)


class MmsiSuggestionResponse(InsuranceBaseModel):
    mmsi: str | None = None
    source: Literal["deepseek_web_search"] = "deepseek_web_search"
    source_url: str | None = None
    source_title: str | None = None
    identity_check: Literal["matched", "mismatch", "unavailable", "not_checked"] = "not_checked"
    warning: str = "网页搜索候选仍需人工核对船舶身份。"


class MmsiVerificationRequest(InsuranceBaseModel):
    imo_number: str = Field(pattern=r"^\d{7}$")
    mmsi: str = Field(pattern=r"^\d{9}$")


class MmsiVerificationResponse(InsuranceBaseModel):
    imo_number: str
    mmsi: str
    vessel_name: str | None = None


class DeclarationConfirmResponse(InsuranceBaseModel):
    declaration_id: str
    declaration_number: str
    declarations: list[dict[str, str]] = Field(default_factory=list)


class UnderwritingConfirmRequest(InsuranceBaseModel):
    rate: Decimal = Field(ge=0, le=100)


class InsuredVesselResponse(InsuranceBaseModel):
    vessel_name: str
    imo_number: str | None = None
    confirmed_mmsi: str | None = None
    declaration_count: int
    declaration_number: str
    company_name: str | None = None
    tracking_status: str | None = None
