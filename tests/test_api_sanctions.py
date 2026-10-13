from fastapi.testclient import TestClient

from api.main import app
import api.routes.sanctions as sanctions_route


def test_screen_sanctions_returns_real_service_shape(monkeypatch):
    monkeypatch.setattr(
        sanctions_route,
        "search_sanctions",
        lambda query, min_score: {
            "keyword": query,
            "normalized_keyword": query.upper(),
            "results": [{
                "profile_id": "36", "source": "OFAC",
                "names": ["AEROCARIBBEAN AIRLINES"], "addresses": ["Havana"],
                "programs": ["CUBA"], "matched_name": "AEROCARIBBEAN AIRLINES",
                "match_type": "normalized_fuzzy", "score": 86.96,
            }],
            "suggestions": [],
        },
    )
    response = TestClient(app).post(
        "/api/v1/sanctions/screen",
        json={"query": "AEROCARIBBEAN AIRLINE", "sanctions_list": "OFAC", "mode": "standard"},
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["score"] == 86.96


def test_screen_sanctions_explains_unsupported_future_list():
    response = TestClient(app).post(
        "/api/v1/sanctions/screen",
        json={"query": "Example", "sanctions_list": "EU"},
    )
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert "仅支持 OFAC" in response.json()["message"]


def test_declaration_screening_routes_use_workflow_dependency():
    class FakeWorkflow:
        def list_cases(self):
            return [{"declaration_id": "d1", "parties": []}]

        def screen_party(self, declaration_id, shipment_id, role):
            return {"declaration_id": declaration_id, "shipment_id": shipment_id, "role": role}

        def upload_evidence(self, declaration_id, shipment_id, role, content):
            return {"size": len(content)}

        def review_party(self, declaration_id, shipment_id, role, result, reviewer, note):
            return {"review": result, "reviewer": reviewer}

        def generate_report(self, declaration_id):
            return {"report": declaration_id}

        def download_report(self, declaration_id):
            return "screening.docx", b"word-report"

    app.dependency_overrides[sanctions_route.get_declaration_workflow] = lambda: FakeWorkflow()
    try:
        client = TestClient(app)
        assert client.get("/api/v1/sanctions/declaration-cases").json()[0]["declaration_id"] == "d1"
        prefix = "/api/v1/sanctions/declaration-cases/d1/parties/s1/shipper"
        assert client.post(prefix + "/screen").json()["role"] == "shipper"
        assert client.post(prefix + "/evidence", files={"file": ("screen.png", b"123", "image/png")}).json()["size"] == 3
        assert client.post(prefix + "/review", json={"result": "no_match", "reviewer": "Reviewer"}).json()["review"] == "no_match"
        assert client.post("/api/v1/sanctions/declaration-cases/d1/report").json()["report"] == "d1"
        report = client.get("/api/v1/sanctions/declaration-cases/d1/report/download")
        assert report.status_code == 200
        assert report.content == b"word-report"
        assert "attachment" in report.headers["content-disposition"]
        assert report.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    finally:
        app.dependency_overrides.clear()
