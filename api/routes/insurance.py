from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status

from api.schemas.insurance import (
    CompanyCreate,
    CompanyResponse,
    DashboardSummaryResponse,
    DeclarationConfirmRequest,
    DeclarationConfirmResponse,
    DeclarationDetailResponse,
    DeclarationImportResponse,
    DeclarationImportUpdate,
    DeclarationSourceType,
    DeclarationStatus,
    DeclarationSummaryResponse,
    DeclarationUpdate,
    DocumentType,
    InsuranceDocumentResponse,
    InsuredVesselResponse,
    ManualDeclarationCreate,
    MmsiSuggestionRequest,
    MmsiSuggestionResponse,
    MmsiVerificationRequest,
    MmsiVerificationResponse,
    ParsedDeclarationData,
    PolicyCreate,
    PolicyDetailResponse,
    PolicyResponse,
    PolicyStatus,
    PolicyUpdate,
    UnderwritingConfirmRequest,
)


router = APIRouter(prefix="/api/v1/insurance", tags=["insurance"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
POLICY_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx"}
DECLARATION_EXTENSIONS = {".xls", ".xlsx"}
GENERAL_DOCUMENT_EXTENSIONS = DECLARATION_EXTENSIONS | POLICY_DOCUMENT_EXTENSIONS | {
    ".png",
    ".jpg",
    ".jpeg",
}


class InsuranceRepositoryDependency:
    def __getattr__(self, name: str):
        from risk_monitor.insurance_repository import InsuranceRepository

        if "_repository" not in self.__dict__:
            self._repository = InsuranceRepository()
        return getattr(self._repository, name)


def get_insurance_repository() -> InsuranceRepositoryDependency:
    return InsuranceRepositoryDependency()


def get_insurance_storage():
    from risk_monitor.insurance_storage import InsuranceDocumentStorage

    return InsuranceDocumentStorage()


def get_declaration_parser():
    from risk_monitor.insurance_excel_parser import parse_declaration_workbook

    return parse_declaration_workbook


def get_declaration_materials_parser():
    from risk_monitor.insurance_excel_parser import parse_declaration_materials

    return parse_declaration_materials


def get_insurance_tracking_service():
    from risk_monitor.insurance_tracking_service import InsuranceTrackingService

    return InsuranceTrackingService()


def get_insurance_submission_preparer():
    from risk_monitor.insurance_screening import prepare_shipments_for_screening

    return prepare_shipments_for_screening


def get_insurance_sanctions_workflow():
    from risk_monitor.declaration_sanctions_workflow import DeclarationSanctionsWorkflow

    return DeclarationSanctionsWorkflow()


def _repository_error(exc: Exception, action: str) -> HTTPException:
    message = str(exc).lower()
    if "23505" in message or "duplicate" in message or "unique" in message:
        return HTTPException(status_code=409, detail=f"{action} conflicts with an existing record.")
    if "23503" in message or "foreign key" in message:
        return HTTPException(status_code=422, detail=f"{action} references an unknown record.")
    return HTTPException(status_code=500, detail=f"{action} failed.")


async def _read_upload(file: UploadFile, allowed_extensions: set[str]) -> tuple[str, bytes]:
    file_name = Path(file.filename or "document").name
    extension = Path(file_name).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {allowed}.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The uploaded file exceeds 20 MB.")
    return file_name, content


def _signed_documents(documents: list[dict[str, Any]], storage: Any) -> list[dict[str, Any]]:
    enriched = []
    for document in documents:
        item = dict(document)
        try:
            item["download_url"] = storage.signed_url(item["storage_path"])
        except Exception:
            item["download_url"] = None
        enriched.append(item)
    return enriched


def _import_response(row: dict[str, Any]) -> DeclarationImportResponse:
    return DeclarationImportResponse(
        id=str(row["id"]),
        policy_id=str(row["policy_id"]),
        company_id=str(row["company_id"]),
        source_type=row["source_type"],
        source_file_name=row["source_file_name"],
        parser_name=row["parser_name"],
        parser_version=row["parser_version"],
        parsed_data=ParsedDeclarationData.model_validate(row.get("parsed_data") or {}),
        warnings=list(row.get("parse_warnings") or []),
        status=row["status"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _validate_mmsi_confirmations(shipments: list[dict[str, Any]], tracking_service: Any) -> None:
    from risk_monitor.insurance_tracking_service import MmsiSourceUnavailableError, MmsiVerificationError

    try:
        tracking_service.validate_confirmed_shipments(shipments)
    except MmsiVerificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MmsiSourceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/mmsi-suggestion", response_model=MmsiSuggestionResponse)
def suggest_declaration_mmsi(
    payload: MmsiSuggestionRequest,
    tracking_service: Any = Depends(get_insurance_tracking_service),
) -> MmsiSuggestionResponse:
    from risk_monitor.deepseek_mmsi_resolver import DeepSeekMmsiError
    from risk_monitor.insurance_tracking_service import MmsiSourceUnavailableError, MmsiVerificationError

    try:
        suggestion = tracking_service.suggest_mmsi(payload.imo_number, payload.vessel_name)
    except DeepSeekMmsiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MMSI 联网检索暂不可用。") from exc
    if not suggestion:
        return MmsiSuggestionResponse(mmsi=None, warning="网页搜索未找到同时包含该 IMO 和 MMSI 的可信摘要；请人工查询并录入。")
    mmsi = suggestion["mmsi"]
    evidence = {"mmsi": mmsi, "source_url": suggestion["source_url"], "source_title": suggestion["source_title"]}
    try:
        tracking_service.verify_confirmed_mmsi(payload.imo_number, mmsi)
    except MmsiVerificationError:
        return MmsiSuggestionResponse(**evidence, identity_check="mismatch", warning="网页搜索候选与 Chinaports 返回的 IMO 不符，请人工更正；此号码不能确认。")
    except MmsiSourceUnavailableError:
        return MmsiSuggestionResponse(**evidence, identity_check="unavailable", warning="Chinaports 暂不可用，网页搜索候选尚未核实；请人工检查。")
    return MmsiSuggestionResponse(**evidence, identity_check="matched", warning="Chinaports 返回的 IMO/MMSI 匹配；仍请人工核对网页来源后确认。")


@router.post("/mmsi-verification", response_model=MmsiVerificationResponse)
def verify_declaration_mmsi(
    payload: MmsiVerificationRequest,
    tracking_service: Any = Depends(get_insurance_tracking_service),
) -> MmsiVerificationResponse:
    from risk_monitor.insurance_tracking_service import MmsiSourceUnavailableError, MmsiVerificationError

    try:
        vessel = tracking_service.verify_confirmed_mmsi(payload.imo_number, payload.mmsi)
    except MmsiVerificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MmsiSourceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MmsiVerificationResponse(
        imo_number=payload.imo_number,
        mmsi=payload.mmsi,
        vessel_name=vessel.get("name"),
    )


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    repository: Any = Depends(get_insurance_repository),
) -> DashboardSummaryResponse:
    try:
        return DashboardSummaryResponse.model_validate(repository.get_dashboard_summary())
    except Exception as exc:
        raise _repository_error(exc, "Insurance dashboard query") from exc


@router.get("/insured-vessels", response_model=list[InsuredVesselResponse])
def list_insured_vessels(
    repository: Any = Depends(get_insurance_repository),
    tracking_service: Any = Depends(get_insurance_tracking_service),
) -> list[InsuredVesselResponse]:
    try:
        rows = repository.list_insured_vessels()
        response = []
        for row in rows:
            try:
                tracking_status = tracking_service.status_for(row.get("imo_number"), row.get("confirmed_mmsi"))
            except Exception:
                tracking_status = "unknown"
            response.append(InsuredVesselResponse.model_validate({**row, "tracking_status": tracking_status}))
        return response
    except Exception as exc:
        raise _repository_error(exc, "Insured vessel query") from exc


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(
    search: str | None = Query(default=None, max_length=240),
    repository: Any = Depends(get_insurance_repository),
) -> list[CompanyResponse]:
    try:
        return [CompanyResponse.model_validate(row) for row in repository.list_companies(search)]
    except Exception as exc:
        raise _repository_error(exc, "Company query") from exc


@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    repository: Any = Depends(get_insurance_repository),
) -> CompanyResponse:
    try:
        row = repository.create_company(payload.model_dump(mode="json"))
        return CompanyResponse.model_validate(row)
    except Exception as exc:
        raise _repository_error(exc, "Company creation") from exc


@router.get("/policies", response_model=list[PolicyResponse])
def list_policies(
    search: str | None = Query(default=None, max_length=300),
    company_id: str | None = None,
    insurer: str | None = Query(default=None, max_length=300),
    policy_status: PolicyStatus | None = Query(default=None, alias="status"),
    year: int | None = Query(default=None, ge=1900, le=2200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: Any = Depends(get_insurance_repository),
) -> list[PolicyResponse]:
    try:
        rows = repository.list_policies(
            search=search,
            company_id=company_id,
            insurer=insurer,
            status=policy_status,
            year=year,
            limit=limit,
            offset=offset,
        )
        return [PolicyResponse.model_validate(row) for row in rows]
    except Exception as exc:
        raise _repository_error(exc, "Policy query") from exc


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate,
    repository: Any = Depends(get_insurance_repository),
) -> PolicyResponse:
    try:
        row = repository.create_policy(payload.model_dump(mode="json"))
        return PolicyResponse.model_validate(row)
    except Exception as exc:
        raise _repository_error(exc, "Policy creation") from exc


@router.patch("/policies/{policy_id}", response_model=PolicyResponse)
def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    repository: Any = Depends(get_insurance_repository),
) -> PolicyResponse:
    updates = payload.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No policy fields were supplied.")
    try:
        row = repository.update_policy(policy_id, updates)
    except Exception as exc:
        raise _repository_error(exc, "Policy update") from exc
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return PolicyResponse.model_validate(row)


@router.get("/policies/{policy_id}", response_model=PolicyDetailResponse)
def get_policy(
    policy_id: str,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
) -> PolicyDetailResponse:
    try:
        policy = repository.get_policy(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found.")
        policy["recent_declarations"] = repository.list_declarations(
            policy_id=policy_id,
            limit=10,
            offset=0,
        )
        policy["documents"] = _signed_documents(
            repository.list_documents(policy_id=policy_id),
            storage,
        )
        return PolicyDetailResponse.model_validate(policy)
    except HTTPException:
        raise
    except Exception as exc:
        raise _repository_error(exc, "Policy detail query") from exc


@router.post(
    "/policies/{policy_id}/documents",
    response_model=InsuranceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_policy_document(
    policy_id: str,
    file: Annotated[UploadFile, File(...)],
    document_type: Annotated[DocumentType, Form()] = "framework_policy",
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
) -> InsuranceDocumentResponse:
    if document_type not in {"framework_policy", "endorsement", "other"}:
        raise HTTPException(status_code=422, detail="Invalid policy document type.")
    if not repository.get_policy(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found.")
    file_name, content = await _read_upload(file, POLICY_DOCUMENT_EXTENSIONS)
    storage_path = storage.build_path("policies", policy_id, file_name)
    try:
        storage.upload(path=storage_path, content=content, content_type=file.content_type)
        row = repository.create_document(
            {
                "policy_id": policy_id,
                "document_type": document_type,
                "file_name": file_name,
                "content_type": file.content_type,
                "file_size": len(content),
                "storage_bucket": storage.bucket,
                "storage_path": storage_path,
                "file_sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    except Exception as exc:
        try:
            storage.remove(storage_path)
        except Exception:
            pass
        raise _repository_error(exc, "Policy document upload") from exc
    return InsuranceDocumentResponse.model_validate(
        _signed_documents([row], storage)[0]
    )


@router.post(
    "/declaration-imports",
    response_model=DeclarationImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_declaration_import(
    policy_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File(...)],
    source_type: Annotated[DeclarationSourceType, Form()] = "manual_upload",
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    parser: Any = Depends(get_declaration_parser),
) -> DeclarationImportResponse:
    policy = repository.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    file_name, content = await _read_upload(file, DECLARATION_EXTENSIONS)
    try:
        parsed = parser(file_name, content)
        parsed_data = ParsedDeclarationData.model_validate(parsed["parsed_data"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    import_id = str(uuid4())
    storage_path = storage.build_path("declaration-imports", import_id, file_name)
    payload = {
        "id": import_id,
        "policy_id": policy_id,
        "company_id": policy["company_id"],
        "source_type": source_type,
        "source_file_name": file_name,
        "content_type": file.content_type,
        "file_size": len(content),
        "storage_bucket": storage.bucket,
        "storage_path": storage_path,
        "file_sha256": hashlib.sha256(content).hexdigest(),
        "parser_name": parsed["parser_name"],
        "parser_version": parsed["parser_version"],
        "parsed_data": parsed_data.model_dump(mode="json"),
        "parse_warnings": parsed.get("warnings") or [],
        "status": "pending_confirmation",
    }
    try:
        storage.upload(path=storage_path, content=content, content_type=file.content_type)
        row = repository.create_declaration_import(payload)
    except Exception as exc:
        try:
            storage.remove(storage_path)
        except Exception:
            pass
        raise _repository_error(exc, "Declaration import") from exc
    return _import_response(row)


@router.post(
    "/declaration-imports/bundle",
    response_model=DeclarationImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_declaration_import_bundle(
    policy_id: Annotated[str, Form()],
    underwriting_file: Annotated[UploadFile, File(...)],
    vessel_file: Annotated[UploadFile, File(...)],
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    parser: Any = Depends(get_declaration_materials_parser),
) -> DeclarationImportResponse:
    policy = repository.get_policy(policy_id)
    if not policy or policy.get("status") == "cancelled":
        raise HTTPException(status_code=404, detail="Framework agreement not found.")
    underwriting_name, underwriting_content = await _read_upload(underwriting_file, DECLARATION_EXTENSIONS)
    vessel_name, vessel_content = await _read_upload(vessel_file, DECLARATION_EXTENSIONS)
    try:
        parsed = parser(underwriting_name, underwriting_content, vessel_name, vessel_content)
        parsed_data = ParsedDeclarationData.model_validate(parsed["parsed_data"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"承保信息/{underwriting_name}", underwriting_content)
        bundle.writestr(f"船舶信息/{vessel_name}", vessel_content)
    content = archive.getvalue()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The combined declaration materials exceed 20 MB.")

    import_id = str(uuid4())
    file_name = "投保申报材料.zip"
    storage_path = storage.build_path("declaration-imports", import_id, file_name)
    payload = {
        "id": import_id,
        "policy_id": policy_id,
        "company_id": policy["company_id"],
        "source_type": "manual_upload",
        "source_file_name": file_name,
        "content_type": "application/zip",
        "file_size": len(content),
        "storage_bucket": storage.bucket,
        "storage_path": storage_path,
        "file_sha256": hashlib.sha256(content).hexdigest(),
        "parser_name": parsed["parser_name"],
        "parser_version": parsed["parser_version"],
        "parsed_data": parsed_data.model_dump(mode="json"),
        "parse_warnings": parsed.get("warnings") or [],
        "status": "pending_confirmation",
    }
    try:
        storage.upload(path=storage_path, content=content, content_type="application/zip")
        row = repository.create_declaration_import(payload)
    except Exception as exc:
        try:
            storage.remove(storage_path)
        except Exception:
            pass
        raise _repository_error(exc, "Declaration materials import") from exc
    return _import_response(row)


@router.post("/manual-declarations", response_model=DeclarationConfirmResponse, status_code=status.HTTP_201_CREATED)
def create_manual_declaration(
    payload: ManualDeclarationCreate,
    background_tasks: BackgroundTasks,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    tracking_service: Any = Depends(get_insurance_tracking_service),
    prepare_screening: Any = Depends(get_insurance_submission_preparer),
) -> DeclarationConfirmResponse:
    policy = repository.get_policy(payload.policy_id)
    if not policy or policy.get("status") == "cancelled":
        raise HTTPException(status_code=404, detail="Active framework agreement not found.")
    shipment = payload.shipment.model_copy(deep=True)
    if payload.insured_name and not shipment.extra_data.get("insured_name"):
        shipment.extra_data["insured_name"] = payload.insured_name
    parsed_data = ParsedDeclarationData(insured_name=payload.insured_name, received_at=payload.received_at, shipments=[shipment])
    if payload.status == "pending_review":
        try:
            parsed_data.shipments = [type(payload.shipment).model_validate(item) for item in prepare_screening(
                parsed_data.model_dump(mode="json")["shipments"], payload.insured_name)]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    _validate_mmsi_confirmations(parsed_data.model_dump(mode="json")["shipments"], tracking_service)
    source = json.dumps(parsed_data.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    import_id = str(uuid4())
    file_name = "manual-entry.json"
    storage_path = storage.build_path("declaration-imports", import_id, file_name)
    import_payload = {
        "id": import_id,
        "policy_id": payload.policy_id,
        "company_id": policy["company_id"],
        "source_type": "manual_upload",
        "source_file_name": file_name,
        "content_type": "application/json",
        "file_size": len(source),
        "storage_bucket": storage.bucket,
        "storage_path": storage_path,
        "file_sha256": hashlib.sha256(source).hexdigest(),
        "parser_name": "manual_entry",
        "parser_version": "1.0.0",
        "parsed_data": parsed_data.model_dump(mode="json"),
        "parse_warnings": [],
        "status": "pending_confirmation",
    }
    try:
        storage.upload(path=storage_path, content=source, content_type="application/json")
        repository.create_declaration_import(import_payload)
    except Exception as exc:
        try:
            storage.remove(storage_path)
        except Exception:
            pass
        raise _repository_error(exc, "Manual declaration creation") from exc
    try:
        row = repository.confirm_declaration_import(
            import_id=import_id,
            status=payload.status,
            notes=payload.notes,
            received_at=None,
            shipments=None,
        )
    except Exception as exc:
        raise _repository_error(exc, "Manual declaration confirmation") from exc
    return DeclarationConfirmResponse.model_validate(row)


@router.get("/declaration-imports", response_model=list[DeclarationImportResponse])
def list_pending_declaration_imports(
    repository: Any = Depends(get_insurance_repository),
) -> list[DeclarationImportResponse]:
    try:
        return [_import_response(row) for row in repository.list_pending_declaration_imports()]
    except Exception as exc:
        raise _repository_error(exc, "Declaration import query") from exc


@router.get("/declaration-imports/{import_id}", response_model=DeclarationImportResponse)
def get_declaration_import(
    import_id: str,
    repository: Any = Depends(get_insurance_repository),
) -> DeclarationImportResponse:
    try:
        row = repository.get_declaration_import(import_id)
    except Exception as exc:
        raise _repository_error(exc, "Declaration import query") from exc
    if not row:
        raise HTTPException(status_code=404, detail="Declaration import not found.")
    return _import_response(row)


@router.patch("/declaration-imports/{import_id}", response_model=DeclarationImportResponse)
def update_declaration_import(
    import_id: str,
    payload: DeclarationImportUpdate,
    repository: Any = Depends(get_insurance_repository),
) -> DeclarationImportResponse:
    try:
        row = repository.update_declaration_import(
            import_id,
            payload.parsed_data.model_dump(mode="json"),
        )
    except Exception as exc:
        raise _repository_error(exc, "Declaration import update") from exc
    if not row:
        raise HTTPException(
            status_code=409,
            detail="Only a pending declaration import can be edited.",
        )
    return _import_response(row)


@router.post(
    "/declaration-imports/{import_id}/confirm",
    response_model=DeclarationConfirmResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_declaration_import(
    import_id: str,
    payload: DeclarationConfirmRequest,
    background_tasks: BackgroundTasks,
    repository: Any = Depends(get_insurance_repository),
    tracking_service: Any = Depends(get_insurance_tracking_service),
    prepare_screening: Any = Depends(get_insurance_submission_preparer),
) -> DeclarationConfirmResponse:
    shipments = None
    if payload.shipments is not None:
        if not payload.shipments:
            raise HTTPException(status_code=422, detail="At least one shipment is required.")
        shipments = [item.model_dump(mode="json") for item in payload.shipments]
    try:
        import_record = repository.get_declaration_import(import_id)
        if not import_record:
            raise HTTPException(status_code=404, detail="Declaration import not found.")
        final_shipments = shipments if shipments is not None else (import_record.get("parsed_data") or {}).get("shipments") or []
        _validate_mmsi_confirmations(final_shipments, tracking_service)
        if payload.status == "pending_review":
            try:
                final_shipments = prepare_screening(final_shipments, (import_record.get("parsed_data") or {}).get("insured_name"))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        received_at = payload.received_at.isoformat() if payload.received_at else None
        if len(final_shipments) > 1 and payload.status == "pending_review":
            rows = repository.confirm_declaration_import_batch(
                import_id=import_id, notes=payload.notes,
                received_at=received_at, shipments=final_shipments,
            )
            if not rows:
                raise RuntimeError("Batch declaration confirmation returned no rows")
            return DeclarationConfirmResponse(**rows[0], declarations=rows)
        row = repository.confirm_declaration_import(
            import_id=import_id, status=payload.status, notes=payload.notes,
            received_at=received_at, shipments=final_shipments,
        )
        return DeclarationConfirmResponse.model_validate(row)
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "not found" in message:
            raise HTTPException(status_code=404, detail="Declaration import not found.") from exc
        if "already" in message or "pending_confirmation" in message:
            raise HTTPException(status_code=409, detail="Declaration import is no longer pending.") from exc
        raise _repository_error(exc, "Declaration confirmation") from exc


@router.post("/declaration-imports/{import_id}/cancel", response_model=DeclarationImportResponse)
def cancel_declaration_import(
    import_id: str,
    repository: Any = Depends(get_insurance_repository),
) -> DeclarationImportResponse:
    try:
        row = repository.cancel_declaration_import(import_id)
    except Exception as exc:
        raise _repository_error(exc, "Declaration import cancellation") from exc
    if not row:
        raise HTTPException(status_code=409, detail="Declaration import is no longer pending.")
    return _import_response(row)


@router.get("/declarations", response_model=list[DeclarationSummaryResponse])
def list_declarations(
    policy_id: str | None = None,
    declaration_status: DeclarationStatus | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: Any = Depends(get_insurance_repository),
) -> list[DeclarationSummaryResponse]:
    try:
        rows = repository.list_declarations(
            policy_id=policy_id,
            status=declaration_status,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
            search=search,
            limit=limit,
            offset=offset,
        )
        return [DeclarationSummaryResponse.model_validate(row) for row in rows]
    except Exception as exc:
        raise _repository_error(exc, "Declaration query") from exc


@router.get("/declarations/{declaration_id}", response_model=DeclarationDetailResponse)
def get_declaration(
    declaration_id: str,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
) -> DeclarationDetailResponse:
    try:
        row = repository.get_declaration(declaration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Declaration not found.")
        row["documents"] = _signed_documents(
            repository.list_documents(declaration_id=declaration_id),
            storage,
        )
        return DeclarationDetailResponse.model_validate(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _repository_error(exc, "Declaration detail query") from exc


@router.post("/declarations/{declaration_id}/underwriting-terms", response_model=DeclarationDetailResponse)
def confirm_underwriting_terms(
    declaration_id: str,
    payload: UnderwritingConfirmRequest,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    sanctions_workflow: Any = Depends(get_insurance_sanctions_workflow),
) -> DeclarationDetailResponse:
    try:
        sanctions_workflow.assert_underwriting_ready(declaration_id)
        repository.confirm_underwriting_terms(declaration_id, str(payload.rate))
        row = repository.get_declaration(declaration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Declaration not found.")
        row["documents"] = _signed_documents(repository.list_documents(declaration_id=declaration_id), storage)
        return DeclarationDetailResponse.model_validate(row)
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc).lower()
        if "not found" in message:
            raise HTTPException(status_code=404, detail="Declaration not found.") from exc
        if "possible sanctions match" in message:
            raise HTTPException(status_code=409, detail="存在制裁筛查候选命中，须先完成合规人工复核。") from exc
        if "pending underwriting" in message or "23505" in message:
            raise HTTPException(status_code=409, detail="申报已处理，不能确认承保条件。") from exc
        if "required" in message or "22023" in message:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise _repository_error(exc, "Underwriting terms confirmation") from exc


@router.post("/declarations/{declaration_id}/underwriting-complete", response_model=DeclarationDetailResponse)
def complete_underwriting(
    declaration_id: str, payload: UnderwritingConfirmRequest, background_tasks: BackgroundTasks,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    tracking_service: Any = Depends(get_insurance_tracking_service),
    sanctions_workflow: Any = Depends(get_insurance_sanctions_workflow),
) -> DeclarationDetailResponse:
    try:
        verification = sanctions_workflow.prepare_atomic_confirmation(declaration_id)
        result = repository.confirm_underwriting_atomic(declaration_id, str(payload.rate), verification)
        row = repository.get_declaration(declaration_id)
        if not row:
            raise HTTPException(status_code=404, detail='申报不存在。')
        row['documents'] = _signed_documents(repository.list_documents(declaration_id=declaration_id), storage)
        response = DeclarationDetailResponse.model_validate(row)
        if result.get('applied'):
            background_tasks.add_task(tracking_service.sync_shipments, row.get('shipments') or [])
        return response
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc).lower()
        if '23505' in message or '40001' in message:
            raise HTTPException(status_code=409, detail='申报或报告已变更，或已使用其他费率确认。请刷新后核实。') from exc
        if '22023' in message:
            raise HTTPException(status_code=422, detail='确认条件不满足：请检查单条运输标的、保额、币种、报告下载和全部主体的无匹配复核结论。') from exc
        raise _repository_error(exc, 'Atomic underwriting confirmation') from exc


@router.post("/declarations/{declaration_id}/underwriting-confirm", response_model=DeclarationDetailResponse)
def confirm_underwriting(
    declaration_id: str,
    background_tasks: BackgroundTasks,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    tracking_service: Any = Depends(get_insurance_tracking_service),
    sanctions_workflow: Any = Depends(get_insurance_sanctions_workflow),
) -> DeclarationDetailResponse:
    try:
        case = sanctions_workflow.assert_underwriting_ready(declaration_id)
        if (case.get("underwriting") or {}).get("status") != "confirmed":
            raise ValueError("请先确认承保条件，再完成投保确认。")
        repository.confirm_underwriting(declaration_id)
        row = repository.get_declaration(declaration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Declaration not found.")
        row["documents"] = _signed_documents(repository.list_documents(declaration_id=declaration_id), storage)
        background_tasks.add_task(tracking_service.sync_shipments, row.get("shipments") or [])
        return DeclarationDetailResponse.model_validate(row)
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc).lower()
        if "pending underwriting" in message or "23505" in message or "22023" in message:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise _repository_error(exc, "Final insurance confirmation") from exc


@router.post("/declarations/{declaration_id}/submit", response_model=DeclarationDetailResponse)
def submit_draft_declaration(
    declaration_id: str,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
    prepare_screening: Any = Depends(get_insurance_submission_preparer),
) -> DeclarationDetailResponse:
    try:
        row = repository.get_declaration(declaration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Declaration not found.")
        if row.get("status") != "draft":
            raise HTTPException(status_code=409, detail="Only a draft can be submitted.")
        shipments = row.get("shipments") or []
        if len(shipments) != 1:
            raise HTTPException(status_code=422, detail="Draft must contain exactly one shipment.")
        required = ("vessel_name", "imo_number", "cargo_name", "insured_value", "loading_port", "discharge_port")
        missing = [field for field in required if not shipments[0].get(field)]
        if missing:
            raise HTTPException(status_code=422, detail=f"草稿缺少必填字段：{', '.join(missing)}")
        prepared = prepare_screening(shipments, (shipments[0].get("extra_data") or {}).get("insured_name"))
        repository.submit_draft(declaration_id, prepared[0]["extra_data"]["sanctions_screening"])
        updated = repository.get_declaration(declaration_id)
        updated["documents"] = _signed_documents(repository.list_documents(declaration_id=declaration_id), storage)
        return DeclarationDetailResponse.model_validate(updated)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _repository_error(exc, "Draft submission") from exc


@router.patch("/declarations/{declaration_id}", response_model=DeclarationDetailResponse)
def update_declaration(
    declaration_id: str,
    payload: DeclarationUpdate,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
) -> DeclarationDetailResponse:
    try:
        row = repository.update_declaration_status(declaration_id, payload.status)
        if not row:
            raise HTTPException(status_code=404, detail="Active declaration not found.")
        row["documents"] = _signed_documents(
            repository.list_documents(declaration_id=declaration_id), storage
        )
        return DeclarationDetailResponse.model_validate(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise _repository_error(exc, "Declaration update") from exc


@router.post(
    "/declarations/{declaration_id}/documents",
    response_model=InsuranceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_declaration_document(
    declaration_id: str,
    file: Annotated[UploadFile, File(...)],
    document_type: Annotated[DocumentType, Form()] = "certificate",
    shipment_id: Annotated[str | None, Form()] = None,
    repository: Any = Depends(get_insurance_repository),
    storage: Any = Depends(get_insurance_storage),
) -> InsuranceDocumentResponse:
    declaration = repository.get_declaration(declaration_id)
    if not declaration:
        raise HTTPException(status_code=404, detail="Declaration not found.")
    if shipment_id and shipment_id not in {item["id"] for item in declaration.get("shipments", [])}:
        raise HTTPException(status_code=422, detail="Shipment does not belong to this declaration.")
    file_name, content = await _read_upload(file, GENERAL_DOCUMENT_EXTENSIONS)
    storage_path = storage.build_path("declarations", declaration_id, file_name)
    try:
        storage.upload(path=storage_path, content=content, content_type=file.content_type)
        row = repository.create_document(
            {
                "policy_id": declaration["policy_id"],
                "declaration_id": declaration_id,
                "shipment_id": shipment_id,
                "document_type": document_type,
                "file_name": file_name,
                "content_type": file.content_type,
                "file_size": len(content),
                "storage_bucket": storage.bucket,
                "storage_path": storage_path,
                "file_sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    except Exception as exc:
        try:
            storage.remove(storage_path)
        except Exception:
            pass
        raise _repository_error(exc, "Declaration document upload") from exc
    return InsuranceDocumentResponse.model_validate(_signed_documents([row], storage)[0])
