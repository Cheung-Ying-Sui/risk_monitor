from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from api.schemas.sanctions import PartyManualReviewRequest, SanctionsSearchRequest, SanctionsSearchResponse
from risk_monitor.declaration_sanctions_workflow import (
    MAX_SCREENSHOT_BYTES, DeclarationSanctionsWorkflow, WorkflowError,
)
from risk_monitor.sanctions_screening_service import search_sanctions, search_with_ai_candidates


router = APIRouter(prefix="/api/v1/sanctions", tags=["sanctions"])


def get_declaration_workflow() -> DeclarationSanctionsWorkflow:
    return DeclarationSanctionsWorkflow()


def _workflow_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, WorkflowError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="申报主体筛查流程失败，请稍后重试。")


@router.post("/screen", response_model=SanctionsSearchResponse)
def screen_sanctions(request: SanctionsSearchRequest) -> SanctionsSearchResponse:
    if request.sanctions_list not in {"all", "OFAC"}:
        return SanctionsSearchResponse(
            keyword=request.query,
            normalized_keyword=request.query.strip().upper(),
            results=[],
            suggestions=[],
            message="当前真实数据源仅支持 OFAC SDN 名单。",
        )

    min_score = {"exact": 95, "standard": 65, "enhanced": 55}.get(
        request.mode, 65
    )
    try:
        result = search_sanctions(request.query, min_score=min_score)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="制裁筛查数据查询失败。") from exc

    message = None
    if not result["results"]:
        message = (
            "未发现正式命中。检测到可能的完整名称候选，请确认法定名称后重新筛查。"
            if result["suggestions"]
            else "未发现正式命中或简称候选。"
        )
    ai_candidates = []
    ai_message = None
    if result["suggestions"] or request.mode == "enhanced":
        try:
            ai_candidates = search_with_ai_candidates(request.query, min_score=min_score)
            ai_message = "AI 仅生成候选检索词；匹配概率来自候选词对 OFAC 数据库的二次检索，不等同于正式制裁结论。"
        except Exception:
            ai_message = "DeepSeek 辅助候选暂时不可用，正式 OFAC 筛查结果不受影响。"
    return SanctionsSearchResponse(
        **result,
        message=message,
        ai_candidates=ai_candidates,
        ai_message=ai_message,
    )


@router.get("/declaration-cases")
def list_declaration_cases(workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> list[dict[str, Any]]:
    try:
        return workflow.list_cases()
    except Exception as exc:
        raise _workflow_error(exc) from exc


@router.get("/declaration-cases/{declaration_id}")
def get_declaration_case(declaration_id: str,
                         workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> dict[str, Any]:
    try:
        return workflow.get_case(declaration_id)
    except Exception as exc:
        raise _workflow_error(exc) from exc


@router.post("/declaration-cases/{declaration_id}/parties/{shipment_id}/{role}/screen")
def screen_declaration_party(declaration_id: str, shipment_id: str, role: str,
                             workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> dict[str, Any]:
    try:
        return workflow.screen_party(declaration_id, shipment_id, role)
    except Exception as exc:
        raise _workflow_error(exc) from exc


@router.post("/declaration-cases/{declaration_id}/parties/{shipment_id}/{role}/evidence")
async def upload_declaration_party_evidence(declaration_id: str, shipment_id: str, role: str,
                                            file: Annotated[UploadFile, File(...)],
                                            workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> dict[str, Any]:
    content = await file.read(MAX_SCREENSHOT_BYTES + 1)
    try:
        return workflow.upload_evidence(declaration_id, shipment_id, role, content)
    except Exception as exc:
        raise _workflow_error(exc) from exc


@router.post("/declaration-cases/{declaration_id}/parties/{shipment_id}/{role}/review")
def review_declaration_party(declaration_id: str, shipment_id: str, role: str,
                             payload: PartyManualReviewRequest,
                             workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> dict[str, Any]:
    try:
        return workflow.review_party(declaration_id, shipment_id, role, payload.result, payload.reviewer, payload.note)
    except Exception as exc:
        raise _workflow_error(exc) from exc


@router.post("/declaration-cases/{declaration_id}/report")
def generate_declaration_report(declaration_id: str,
                                workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> dict[str, Any]:
    try:
        return workflow.generate_report(declaration_id)
    except Exception as exc:
        raise _workflow_error(exc) from exc


@router.get("/declaration-cases/{declaration_id}/report/download")
def download_declaration_report(declaration_id: str,
                                workflow: DeclarationSanctionsWorkflow = Depends(get_declaration_workflow)) -> Response:
    try:
        filename, content = workflow.download_report(declaration_id)
        media_type = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      if filename.endswith(".docx") else "text/html; charset=utf-8")
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="OFAC-screening-{declaration_id}.{filename.rsplit(".", 1)[-1]}"',
                                 "X-Content-Type-Options": "nosniff"})
    except Exception as exc:
        raise _workflow_error(exc) from exc
