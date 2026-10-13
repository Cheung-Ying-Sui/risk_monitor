from copy import deepcopy
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from docx import Document
from PIL import Image

from risk_monitor.declaration_sanctions_workflow import DeclarationSanctionsWorkflow, WorkflowError, _screening_summary


class FakeGateway:
    bucket = "insurance-documents"

    def __init__(self):
        self.declaration = {
            "id": "decl-1", "declaration_number": "DEC-1", "policy_id": "policy-1",
            "company_name": "Test Company", "status": "pending_review", "received_at": "2026-10-12",
            "shipments": [{"id": "ship-1", "declaration_id": "decl-1", "updated_at": 1,
                           "extra_data": {"insured_name": "ABC Fertilizer", "shipper": "XYZ Shipping"}}],
        }
        self.documents = []
        self.files = {}

    def list_declarations(self):
        return [deepcopy(self.declaration)]

    def get_declaration(self, declaration_id):
        return deepcopy(self.declaration) if declaration_id == "decl-1" else None

    def get_shipment(self, shipment_id):
        row = self.declaration["shipments"][0]
        return deepcopy(row) if row["id"] == shipment_id else None

    def save_workflow(self, shipment, workflow):
        row = self.declaration["shipments"][0]
        if row["updated_at"] != shipment["updated_at"]:
            return False
        row["extra_data"]["sanctions_workflow"] = deepcopy(workflow)
        row["updated_at"] += 1
        return True

    def create_document(self, payload):
        row = {**payload, "id": str(uuid4())}
        self.documents.append(row)
        return row

    def list_documents(self, declaration_id):
        return [row for row in self.documents if row["declaration_id"] == declaration_id]

    def upload(self, path, content, content_type):
        self.files[path] = content

    def download(self, path):
        return self.files[path]

    def signed_url(self, path):
        return "https://example.test/" + path

    def path(self, declaration_id, filename):
        return f"sanctions/{declaration_id}/{filename}"


_png_buffer = BytesIO()
Image.new("RGB", (2, 2), "white").save(_png_buffer, format="PNG")
PNG = _png_buffer.getvalue()


def make_workflow():
    gateway = FakeGateway()
    calls = []

    def search(name, **kwargs):
        calls.append((name, kwargs))
        return {"results": [{"source": "OFAC", "profile_id": "12", "matched_name": "Test", "score": 83}],
                "suggestions": []}

    return DeclarationSanctionsWorkflow(gateway, search), gateway, calls


def test_persisted_stage_and_atomic_guard_with_expired_or_corrupt_reports():
    workflow, gateway, _ = make_workflow()
    assert workflow.get_case('decl-1')['stage'] == 'pending_screening'
    with pytest.raises(WorkflowError):
        workflow.prepare_atomic_confirmation('decl-1')
    for role in ('insured_name', 'shipper'):
        workflow.screen_party('decl-1', 'ship-1', role)
        workflow.upload_evidence('decl-1', 'ship-1', role, PNG)
        workflow.review_party('decl-1', 'ship-1', role, 'no_match', 'Reviewer', '')
    assert workflow.get_case('decl-1')['stage'] == 'pending_report_download'
    workflow.generate_report('decl-1')
    with pytest.raises(WorkflowError, match='下载'):
        workflow.prepare_atomic_confirmation('decl-1')
    workflow.download_report('decl-1')
    restarted = DeclarationSanctionsWorkflow(gateway)
    assert restarted.get_case('decl-1')['stage'] == 'pending_underwriting'
    assert restarted.prepare_atomic_confirmation('decl-1')['sha256']
    saved = gateway.declaration['shipments'][0]['extra_data']['sanctions_workflow']
    saved['parties']['insured_name']['review']['note'] = 'changed without timestamp'
    assert restarted.get_case('decl-1')['report'] is None
    with pytest.raises(WorkflowError):
        restarted.prepare_atomic_confirmation('decl-1')
    saved['parties']['insured_name']['review']['note'] = ''
    report_doc = next(d for d in gateway.documents if d['id'] == saved['report']['document_id'])
    gateway.files[report_doc['storage_path']] = b'corrupt'
    with pytest.raises(WorkflowError, match='校验'):
        restarted.prepare_atomic_confirmation('decl-1')


def test_atomic_guard_rejects_unresolved_match_and_multiple_shipments():
    workflow, gateway, _ = make_workflow()
    for role in ('insured_name', 'shipper'):
        workflow.screen_party('decl-1', 'ship-1', role)
        workflow.upload_evidence('decl-1', 'ship-1', role, PNG)
        workflow.review_party('decl-1', 'ship-1', role, 'possible_match', 'Reviewer', '')
    workflow.generate_report('decl-1')
    workflow.download_report('decl-1')
    with pytest.raises(WorkflowError, match='合规升级'):
        workflow.prepare_atomic_confirmation('decl-1')


def test_corrupt_screenshot_is_rejected_before_storage():
    workflow, gateway, _ = make_workflow()
    workflow.screen_party("decl-1", "ship-1", "insured_name")
    with pytest.raises(WorkflowError, match="损坏"):
        workflow.upload_evidence("decl-1", "ship-1", "insured_name", b"\x89PNG\r\n\x1a\ninvalid")
    assert gateway.documents == []
    assert gateway.files == {}


def test_queue_extracts_declaration_parties_and_uses_same_search():
    workflow, _, calls = make_workflow()
    case = workflow.list_cases()[0]
    assert [(item["role"], item["name"]) for item in case["parties"]] == [
        ("insured_name", "ABC Fertilizer"), ("shipper", "XYZ Shipping")]
    case = workflow.screen_party("decl-1", "ship-1", "insured_name")
    assert calls == [("ABC Fertilizer", {"min_score": 65, "limit": 50, "include_suggestions": True})]
    assert case["parties"][0]["preliminary"]["results"][0]["score"] == 83
    assert case["parties"][1]["preliminary"] is None


def test_queue_only_contains_submitted_pending_review_declarations():
    workflow, gateway, _ = make_workflow()
    gateway.declaration["status"] = "draft"
    assert workflow.list_cases() == []
    gateway.declaration["status"] = "confirmed"
    assert workflow.list_cases() == []


def test_evidence_review_and_report_require_complete_workflow():
    workflow, gateway, _ = make_workflow()
    gateway.declaration['shipments'][0].update(vessel_name='MV CURRENT TEST', imo_number='1234567',
                                              cargo_name='Potash', insured_value=12345, currency='USD')
    with pytest.raises(WorkflowError, match="初步筛查"):
        workflow.upload_evidence("decl-1", "ship-1", "insured_name", PNG)
    workflow.screen_party("decl-1", "ship-1", "insured_name")
    with pytest.raises(WorkflowError, match="截图"):
        workflow.upload_evidence("decl-1", "ship-1", "insured_name", b"not an image")
    with pytest.raises(WorkflowError, match="截图"):
        workflow.review_party("decl-1", "ship-1", "insured_name", "no_match", "Reviewer", "")
    case = workflow.upload_evidence("decl-1", "ship-1", "insured_name", PNG)
    assert case["parties"][0]["evidence"]["url"].startswith("https://example.test/")
    workflow.review_party("decl-1", "ship-1", "insured_name", "no_match", "Reviewer", "verified")
    with pytest.raises(WorkflowError, match="每个主体"):
        workflow.generate_report("decl-1")
    workflow.screen_party("decl-1", "ship-1", "shipper")
    workflow.upload_evidence("decl-1", "ship-1", "shipper", PNG)
    workflow.review_party("decl-1", "ship-1", "shipper", "possible_match", "Reviewer", "escalate")
    case = workflow.generate_report("decl-1")
    assert workflow.download_report("decl-1")[0].endswith(".docx")
    with pytest.raises(WorkflowError, match="合规升级复核"):
        workflow.assert_underwriting_ready("decl-1")
    assert case["report"]["url"].startswith("https://example.test/")
    report_file = next(row for row in gateway.documents if row["id"] == case["report"]["document_id"])
    assert report_file["content_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    document = Document(BytesIO(gateway.download(report_file["storage_path"])))
    body = "\n".join(p.text for p in document.paragraphs)
    assert "ABC Fertilizer" in body and "XYZ Shipping" in body
    assert len(document.inline_shapes) == 2
    assert "不自动认定制裁命中或合规放行" in body
    assert case['report']['template_version'] == 'sinochem-questionnaire-v1'
    table = document.tables[1]
    assert table.cell(0, 1).text == 'MV CURRENT TEST'
    assert table.cell(1, 1).text == '1234567'
    assert table.cell(3, 1).text == 'ABC Fertilizer'
    assert table.cell(4, 1).text == '未提供'
    assert '12345 USD' in table.cell(14, 1).text
    assert '未执行英国、联合国及欧盟' in table.cell(21, 1).text
    assert '疑似匹配' in table.cell(22, 1).text
    assert document.sections[0].header._element.xpath('.//w:drawing')
    with ZipFile(BytesIO(gateway.download(report_file['storage_path']))) as package:
        xml = b'\n'.join(package.read(name) for name in package.namelist() if name.endswith('.xml'))
        assert b'MV OCEAN ALINA' not in xml
        assert b'9614854' not in xml
        assert b'Markel' not in xml
        assert not any(name.startswith('customXml/') for name in package.namelist())


def test_party_name_change_invalidates_review_and_report():
    workflow, gateway, _ = make_workflow()
    for role in ("insured_name", "shipper"):
        workflow.screen_party("decl-1", "ship-1", role)
        workflow.upload_evidence("decl-1", "ship-1", role, PNG)
        workflow.review_party("decl-1", "ship-1", role, "no_match", "Reviewer", "")
    assert workflow.generate_report("decl-1")["report"]
    gateway.declaration["shipments"][0]["extra_data"]["shipper"] = "Changed Name"
    case = workflow.get_case("decl-1")
    assert case["report"] is None
    assert case["parties"][1]["preliminary"] is None
    with pytest.raises(WorkflowError, match="初步筛查"):
        workflow.upload_evidence("decl-1", "ship-1", "shipper", PNG)


def test_all_no_match_reviews_unlock_underwriting_only_after_report():
    workflow, _, _ = make_workflow()
    with pytest.raises(WorkflowError, match="筛查报告"):
        workflow.assert_underwriting_ready("decl-1")
    for role in ("insured_name", "shipper"):
        workflow.screen_party("decl-1", "ship-1", role)
        workflow.upload_evidence("decl-1", "ship-1", role, PNG)
        workflow.review_party("decl-1", "ship-1", role, "no_match", "Reviewer", "")
    with pytest.raises(WorkflowError, match="筛查报告"):
        workflow.assert_underwriting_ready("decl-1")
    workflow.generate_report("decl-1")
    with pytest.raises(WorkflowError, match="下载筛查报告"):
        workflow.assert_underwriting_ready("decl-1")
    workflow.download_report("decl-1")
    assert workflow.assert_underwriting_ready("decl-1")["declaration_id"] == "decl-1"


def test_compact_screening_status_remains_pending_until_report():
    shipment = {"extra_data": {"insured_name": "ABC Fertilizer"}}
    party = {"name": "ABC Fertilizer", "preliminary": {"results": [{"matched_name": "ABC"}]},
             "evidence": {"document_id": "doc-1"}, "review": {"result": "no_match"}}
    workflow = {"parties": {"insured_name": party}}
    assert _screening_summary(shipment, workflow)["status"] == "pending"
    workflow["report"] = {"generated_at": "2026-10-12T00:00:00+00:00"}
    summary = _screening_summary(shipment, workflow)
    assert summary["status"] == "completed"
    assert summary["possible_match_count"] == 0
    assert summary["parties"][0]["matches"][0]["matched_name"] == "ABC"


def test_word_report_treats_party_names_as_text():
    workflow, gateway, _ = make_workflow()
    gateway.declaration["shipments"][0]["extra_data"]["insured_name"] = '<script>alert("x")</script>'
    for role in ("insured_name", "shipper"):
        workflow.screen_party("decl-1", "ship-1", role)
        workflow.upload_evidence("decl-1", "ship-1", role, PNG)
        workflow.review_party("decl-1", "ship-1", role, "no_match", "Reviewer", "")
    case = workflow.generate_report("decl-1")
    report_file = next(row for row in gateway.documents if row["id"] == case["report"]["document_id"])
    document = Document(BytesIO(gateway.download(report_file["storage_path"])))
    assert '<script>alert("x")</script>' in "\n".join(p.text for p in document.paragraphs)
