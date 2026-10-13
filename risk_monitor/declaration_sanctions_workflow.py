"""Evidence-backed manual OFAC workflow for insurance declaration parties.

The existing declaration remains the source of truth for party names. No
absence of a name-search candidate is treated as a sanctions clearance.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from PIL import Image

from risk_monitor.insurance_screening import PARTY_FIELDS
from risk_monitor.sanctions_screening_service import search_sanctions
from risk_monitor.sanctions_report import REPORT_TEMPLATE_VERSION, render_report


OFAC_SEARCH_URL = "https://sanctionssearch.ofac.treas.gov/"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024
REVIEW_RESULTS = {"no_match", "possible_match", "confirmed_match", "needs_escalation"}
ROLE_LABELS = dict(PARTY_FIELDS)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _party_name(shipment: dict[str, Any], role: str) -> str:
    return str((shipment.get("extra_data") or {}).get(role) or "").strip()


def _image_type(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def _case_fingerprint(parties: list[dict[str, Any]]) -> str:
    values = [(party["shipment_id"], party["role"], party["name"],
               (party.get("preliminary") or {}).get("screened_at"),
               (party.get("evidence") or {}).get("document_id"),
               (party.get("review") or {}).get("reviewed_at")) for party in parties]
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()


def _screening_summary(shipment: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
    report = workflow.get("report")
    parties = workflow.get("parties") or {}
    summary = []
    for role, label in PARTY_FIELDS:
        name = _party_name(shipment, role)
        if not name:
            continue
        item = parties.get(role) or {}
        review = item.get("review") or {}
        summary.append({"role": role, "label": label, "name": name,
                        "possible_match": review.get("result") != "no_match",
                        "matches": (item.get("preliminary") or {}).get("results") or []})
    complete = bool(report) and bool(summary) and all(
        (parties.get(item["role"]) or {}).get("name") == item["name"]
        and (parties.get(item["role"]) or {}).get("preliminary")
        and (parties.get(item["role"]) or {}).get("evidence")
        and (parties.get(item["role"]) or {}).get("review") for item in summary)
    return {"status": "completed" if complete else "pending",
            "source": "OFAC SDN + manual review",
            "screened_at": report.get("generated_at") if complete else None,
            "possible_match_count": sum(bool(item["possible_match"]) for item in summary) if complete else 0,
            "parties": summary if complete else []}


class WorkflowError(ValueError):
    pass


class DeclarationSanctionsGateway:
    def __init__(self):
        from risk_monitor.insurance_repository import InsuranceRepository
        from risk_monitor.insurance_storage import InsuranceDocumentStorage
        self.repository = InsuranceRepository()
        self.storage = InsuranceDocumentStorage()

    def list_declarations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.repository.list_declarations(limit=500, offset=offset)
            rows.extend(page)
            if len(page) < 500:
                return rows
            offset += 500

    def get_declaration(self, declaration_id: str) -> dict[str, Any] | None:
        return self.repository.get_declaration(declaration_id)

    def get_shipment(self, shipment_id: str) -> dict[str, Any] | None:
        from risk_monitor.supabase_client import supabase
        rows = (supabase.table("insurance_shipments").select("id,declaration_id,extra_data,updated_at")
                .eq("id", shipment_id).limit(1).execute()).data or []
        return rows[0] if rows else None

    def save_workflow(self, shipment: dict[str, Any], workflow: dict[str, Any]) -> bool:
        from risk_monitor.supabase_client import supabase
        extra = {**(shipment.get("extra_data") or {}), "sanctions_workflow": workflow}
        extra["sanctions_screening"] = _screening_summary(shipment, workflow)
        terms = extra.get("underwriting_terms") or {}
        if terms.get("report_sha256") != (workflow.get("report") or {}).get("sha256"):
            extra.pop("underwriting_terms", None)
        rows = (supabase.table("insurance_shipments").update({"extra_data": extra})
                .eq("id", shipment["id"]).eq("updated_at", shipment["updated_at"]).execute()).data or []
        return bool(rows)

    def create_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.create_document(payload)

    def list_documents(self, declaration_id: str) -> list[dict[str, Any]]:
        return self.repository.list_documents(declaration_id=declaration_id)

    def upload(self, path: str, content: bytes, content_type: str) -> None:
        self.storage.upload(path=path, content=content, content_type=content_type)

    def download(self, path: str) -> bytes:
        return self.storage.download(path)

    def signed_url(self, path: str) -> str | None:
        return self.storage.signed_url(path)

    def path(self, declaration_id: str, filename: str) -> str:
        return self.storage.build_path("sanctions", declaration_id, filename)

    @property
    def bucket(self) -> str:
        return self.storage.bucket


class DeclarationSanctionsWorkflow:
    def __init__(self, gateway: DeclarationSanctionsGateway | None = None,
                 search: Callable[..., dict[str, Any]] = search_sanctions):
        self.gateway = gateway or DeclarationSanctionsGateway()
        self.search = search

    def list_cases(self) -> list[dict[str, Any]]:
        return [self._project(row) for row in self.gateway.list_declarations()
                if row.get("status") == "pending_review" and any(
                    _party_name(shipment, role) for shipment in row.get("shipments") or [] for role in ROLE_LABELS)]

    def get_case(self, declaration_id: str, *, include_urls: bool = True) -> dict[str, Any]:
        row = self.gateway.get_declaration(declaration_id)
        if not row or row.get("status") in {"draft", "cancelled"}:
            raise LookupError("投保申报不存在、尚未提交或已作废。")
        return self._project(row, include_urls=include_urls)

    def _project(self, declaration: dict[str, Any], *, include_urls: bool = True) -> dict[str, Any]:
        documents = {row["id"]: row for row in self.gateway.list_documents(declaration["id"])}
        parties = []
        report = None
        for shipment in declaration.get("shipments") or []:
            workflow = (shipment.get("extra_data") or {}).get("sanctions_workflow") or {}
            for role, label in PARTY_FIELDS:
                name = _party_name(shipment, role)
                if not name:
                    continue
                item = (workflow.get("parties") or {}).get(role) or {}
                if item.get("name") != name:
                    item = {}
                evidence = item.get("evidence")
                document = documents.get(evidence.get("document_id")) if isinstance(evidence, dict) else None
                if document and (document.get('shipment_id') != shipment['id']
                                 or document.get('file_sha256') != evidence.get('sha256')):
                    document = None
                parties.append({"shipment_id": shipment["id"], "role": role, "label": label, "name": name,
                                "preliminary": item.get("preliminary"), "review": item.get("review"),
                                "evidence": ({**evidence, "url": self.gateway.signed_url(document["storage_path"]) if include_urls else None}
                                             if document else None)})
            stored_report = workflow.get("report")
            report_document = documents.get(stored_report.get("document_id")) if isinstance(stored_report, dict) else None
            if report_document and report_document.get('file_sha256') == stored_report.get('sha256'):
                report = {**stored_report, "url": self.gateway.signed_url(report_document["storage_path"]) if include_urls else None,
                          "download_path": f"/api/v1/sanctions/declaration-cases/{declaration['id']}/report/download"}
        if report and report.get("case_fingerprint") != _case_fingerprint(parties):
            report = None
        snapshot = {s['id']: ((s.get('extra_data') or {}).get('sanctions_workflow') or {}).get('parties', {})
                    for s in declaration.get('shipments') or []}
        if report and report.get('screening_snapshot') != snapshot:
            report = None
        first_shipment = (declaration.get("shipments") or [{}])[0]
        terms = (first_shipment.get("extra_data") or {}).get("underwriting_terms") or {}
        if not report or terms.get("report_sha256") != report.get("sha256"):
            terms = {}
        complete = bool(parties) and all(p['preliminary'] and p['evidence'] and p['review'] for p in parties)
        stage = ('confirmed' if declaration['status'] == 'confirmed' else
                 'pending_screening' if not complete else
                 'pending_report_download' if not report or not report.get('downloaded_at') else
                 'pending_underwriting')
        return {"declaration_id": declaration["id"], "declaration_number": declaration["declaration_number"],
                "company_name": declaration.get("company_name"), "status": declaration["status"],
                "received_at": declaration.get("received_at"), "parties": parties, "report": report,
                "stage": stage,
                "underwriting": {"shipment_count": len(declaration.get('shipments') or []),
                                 "cargo_name": first_shipment.get('cargo_name'),
                                 "currency": first_shipment.get("currency"),
                                 "insured_value": first_shipment.get("insured_value"),
                                 "insured_value_tolerance_percent": (first_shipment.get("extra_data") or {}).get("insured_value_tolerance_percent"),
                                 "status": terms.get("status", "pending"), "rate": terms.get("rate"),
                                 "premium": terms.get("premium"), "confirmed_at": terms.get("confirmed_at")},
                "official_search_url": OFAC_SEARCH_URL}

    def _target(self, declaration_id: str, shipment_id: str, role: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        if role not in ROLE_LABELS:
            raise WorkflowError("不支持的主体角色。")
        declaration = self.gateway.get_declaration(declaration_id)
        if not declaration or declaration.get("status") in {"draft", "cancelled"}:
            raise LookupError("投保申报不存在、尚未提交或已作废。")
        if declaration["status"] != "pending_review":
            raise WorkflowError("只有待审核的投保申报可以执行主体筛查。")
        shipment = next((item for item in declaration.get("shipments") or [] if item["id"] == shipment_id), None)
        if not shipment:
            raise LookupError("该主体不属于此投保申报。")
        name = _party_name(shipment, role)
        if not name:
            raise WorkflowError("此主体名称为空，不能筛查。")
        return declaration, shipment, name

    def _change_party(self, declaration_id: str, shipment_id: str, role: str,
                      mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        for _ in range(3):
            current = self.gateway.get_shipment(shipment_id)
            if not current or current["declaration_id"] != declaration_id:
                raise LookupError("投保标的不存在。")
            workflow = dict((current.get("extra_data") or {}).get("sanctions_workflow") or {})
            parties = dict(workflow.get("parties") or {})
            parties[role] = mutate(dict(parties.get(role) or {}))
            workflow["parties"] = parties
            workflow.pop("report", None)
            if self.gateway.save_workflow(current, workflow):
                return
        raise RuntimeError("主体筛查数据发生并发更新，请重试。")

    def screen_party(self, declaration_id: str, shipment_id: str, role: str) -> dict[str, Any]:
        _, _, name = self._target(declaration_id, shipment_id, role)
        result = self.search(name, min_score=65, limit=50, include_suggestions=True)
        preliminary = {"screened_at": _utc_now(), "source": "OFAC SDN local snapshot",
                       "query": name, "results": result.get("results") or [],
                       "suggestions": result.get("suggestions") or []}
        self._change_party(declaration_id, shipment_id, role,
                           lambda old: {"name": name, "preliminary": preliminary})
        return self.get_case(declaration_id)

    def upload_evidence(self, declaration_id: str, shipment_id: str, role: str,
                        content: bytes) -> dict[str, Any]:
        declaration, shipment, name = self._target(declaration_id, shipment_id, role)
        item = ((shipment.get("extra_data") or {}).get("sanctions_workflow") or {}).get("parties", {}).get(role) or {}
        if item.get("name") != name or not item.get("preliminary"):
            raise WorkflowError("请先执行初步筛查。")
        image = _image_type(content)
        if not image or not content or len(content) > MAX_SCREENSHOT_BYTES:
            raise WorkflowError("请上传不超过 2 MB 的 PNG、JPEG 或 WebP 截图。")
        try:
            with Image.open(BytesIO(content)) as screenshot:
                screenshot.verify()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise WorkflowError("截图文件已损坏或无法读取，请重新选择 PNG、JPEG 或 WebP 图片。") from exc
        content_type, extension = image
        filename = f"OFAC-{role}-{uuid4().hex[:8]}{extension}"
        path = self.gateway.path(declaration_id, filename)
        self.gateway.upload(path, content, content_type)
        document = self.gateway.create_document({"policy_id": declaration["policy_id"],
            "declaration_id": declaration_id, "shipment_id": shipment_id, "document_type": "other",
            "file_name": filename, "content_type": content_type, "file_size": len(content),
            "storage_bucket": self.gateway.bucket, "storage_path": path,
            "file_sha256": hashlib.sha256(content).hexdigest()})
        evidence = {"document_id": document["id"], "file_name": filename,
                    "sha256": document["file_sha256"], "uploaded_at": _utc_now()}
        self._change_party(declaration_id, shipment_id, role,
                           lambda old: {**old, "name": name, "evidence": evidence, "review": None})
        return self.get_case(declaration_id)

    def review_party(self, declaration_id: str, shipment_id: str, role: str,
                     result: str, reviewer: str, note: str) -> dict[str, Any]:
        _, shipment, name = self._target(declaration_id, shipment_id, role)
        item = ((shipment.get("extra_data") or {}).get("sanctions_workflow") or {}).get("parties", {}).get(role) or {}
        if item.get("name") != name or not item.get("preliminary") or not item.get("evidence"):
            raise WorkflowError("请先完成初筛并上传该主体的 OFAC 截图。")
        if result not in REVIEW_RESULTS or not reviewer.strip():
            raise WorkflowError("请选择人工复核结果并填写复核人。")
        review = {"result": result, "reviewer": reviewer.strip(), "note": note.strip(), "reviewed_at": _utc_now(),
                  "source": OFAC_SEARCH_URL}
        self._change_party(declaration_id, shipment_id, role,
                           lambda old: {**old, "name": name, "review": review})
        return self.get_case(declaration_id)

    def generate_report(self, declaration_id: str) -> dict[str, Any]:
        case = self.get_case(declaration_id, include_urls=False)
        if case["status"] != "pending_review":
            raise WorkflowError("只有待审核的投保申报可以生成筛查报告。")
        if not case["parties"]:
            raise WorkflowError("申报中没有可筛查主体。")
        if any(not (item["preliminary"] and item["evidence"] and item["review"]) for item in case["parties"]):
            raise WorkflowError("每个主体都必须完成初筛、截图上传和人工复核后才能生成报告。")
        declaration = self.gateway.get_declaration(declaration_id)
        screenshot_documents = {row["id"]: row for row in self.gateway.list_documents(declaration_id)}
        images = []
        for party in case["parties"]:
            document = screenshot_documents.get(party["evidence"]["document_id"])
            if not document or document.get("shipment_id") != party["shipment_id"]:
                raise WorkflowError("截图与主体不匹配，请重新上传。")
            image = self.gateway.download(document["storage_path"])
            if _image_type(image) is None or len(image) > MAX_SCREENSHOT_BYTES:
                raise WorkflowError("截图文件无效，请重新上传。")
            images.append((party, image))
        generated_at = _utc_now()
        try:
            report_content = render_report(case, declaration, images, generated_at)
        except Exception as exc:
            raise WorkflowError("报告生成失败，请检查报告模板及截图文件后重试。") from exc
        if len(report_content) > 20 * 1024 * 1024:
            raise WorkflowError("报告超过 20 MB，请压缩截图后重新上传。")
        filename = f"OFAC-screening-{declaration['declaration_number']}-{uuid4().hex[:8]}.docx"
        path = self.gateway.path(declaration_id, filename)
        self.gateway.upload(path, report_content, DOCX_MIME)
        document = self.gateway.create_document({"policy_id": declaration["policy_id"], "declaration_id": declaration_id,
            "document_type": "other", "file_name": filename, "content_type": DOCX_MIME,
            "file_size": len(report_content), "storage_bucket": self.gateway.bucket, "storage_path": path,
            "file_sha256": hashlib.sha256(report_content).hexdigest()})
        first_shipment = declaration["shipments"][0]
        for _ in range(3):
            current = self.gateway.get_shipment(first_shipment["id"])
            workflow = dict((current.get("extra_data") or {}).get("sanctions_workflow") or {})
            workflow["report"] = {"document_id": document["id"], "generated_at": generated_at,
                                  "screening_snapshot": {s['id']: ((s.get('extra_data') or {}).get('sanctions_workflow') or {}).get('parties', {}) for s in declaration['shipments']},
                                  "file_name": filename, "sha256": document["file_sha256"],
                                  "template_version": REPORT_TEMPLATE_VERSION,
                                  "case_fingerprint": _case_fingerprint(case["parties"])}
            if self.gateway.save_workflow(current, workflow):
                return self.get_case(declaration_id)
        raise RuntimeError("报告已存档但状态更新失败，请刷新后重试。")

    def assert_underwriting_ready(self, declaration_id: str, *, allow_confirmed: bool = False) -> dict[str, Any]:
        case = self.get_case(declaration_id, include_urls=False)
        if case["status"] not in ({"pending_review", "confirmed"} if allow_confirmed else {"pending_review"}):
            raise WorkflowError("申报不在待承保确认状态。")
        if not case["parties"] or not case["report"]:
            raise WorkflowError("请先完成全部主体筛查、上传截图并生成筛查报告。")
        if not case["report"].get("downloaded_at"):
            raise WorkflowError("请先下载筛查报告，再确认承保条件。")
        if any(not (party["preliminary"] and party["evidence"] and party["review"])
               for party in case["parties"]):
            raise WorkflowError("主体筛查结果已变更，请重新生成报告。")
        if any(party["review"]["result"] != "no_match" for party in case["parties"]):
            raise WorkflowError("存在疑似或确认命中，请先进行合规升级复核，暂不能承保确认。")
        return case

    def prepare_atomic_confirmation(self, declaration_id: str) -> dict[str, Any]:
        """Verify stored bytes outside the transaction, then bind that receipt to a locked snapshot."""
        case = self.assert_underwriting_ready(declaration_id, allow_confirmed=True)
        declaration = self.gateway.get_declaration(declaration_id)
        shipments = declaration.get('shipments') or []
        if len(shipments) != 1:
            raise WorkflowError('当前仅支持一份申报对应一条运输标的，不能统一套用费率。')
        shipment = shipments[0]
        workflow = (shipment.get('extra_data') or {}).get('sanctions_workflow') or {}
        if workflow.get('report') != {k: v for k, v in case['report'].items() if k not in {'url', 'download_path'}}:
            raise WorkflowError('筛查报告已变更，请刷新后重试。')
        document = next((d for d in self.gateway.list_documents(declaration_id)
                         if d['id'] == case['report']['document_id']), None)
        if not document or document.get('file_sha256') != case['report']['sha256']:
            raise WorkflowError('报告文件校验失败，请重新生成。')
        content = self.gateway.download(document['storage_path'])
        if hashlib.sha256(content).hexdigest() != case['report']['sha256']:
            raise WorkflowError('报告内容校验失败，请重新生成。')
        return {'workflow': workflow, 'sha256': case['report']['sha256'],
                'insured_value': shipment.get('insured_value'), 'currency': shipment.get('currency')}

    def download_report(self, declaration_id: str) -> tuple[str, bytes]:
        case = self.get_case(declaration_id, include_urls=False)
        report = case["report"]
        if not report:
            raise WorkflowError("尚无有效的筛查报告可下载。")
        document = next((item for item in self.gateway.list_documents(declaration_id)
                         if item["id"] == report["document_id"]), None)
        if not document or document.get("content_type") not in {DOCX_MIME, "text/html; charset=utf-8"}:
            raise WorkflowError("筛查报告文件不存在或格式不正确。")
        content = self.gateway.download(document["storage_path"])
        if hashlib.sha256(content).hexdigest() != report["sha256"]:
            raise WorkflowError("筛查报告校验失败，请重新生成。")
        if not report.get("downloaded_at"):
            first_shipment = self.gateway.get_declaration(declaration_id)["shipments"][0]
            for _ in range(3):
                current = self.gateway.get_shipment(first_shipment["id"])
                workflow = dict((current.get("extra_data") or {}).get("sanctions_workflow") or {})
                stored_report = dict(workflow.get("report") or {})
                if stored_report.get("sha256") != report["sha256"]:
                    raise WorkflowError("筛查报告已更新，请重新下载。")
                stored_report["downloaded_at"] = _utc_now()
                workflow["report"] = stored_report
                if self.gateway.save_workflow(current, workflow):
                    break
            else:
                raise RuntimeError("报告下载记录发生并发更新，请重试。")
        return report["file_name"], content


