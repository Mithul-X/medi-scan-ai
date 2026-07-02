"""
Integration tests for the FastAPI routes, using an in-memory DB (conftest.py)
and a mocked LLM router so no real API keys or network calls are needed.

Note: we monkeypatch `app.services.llm_router.generate` directly rather than
patching `httpx.AsyncClient.post`. The test client itself (see conftest.py's
app_client fixture) is built on httpx.AsyncClient — patching the class method
globally would also intercept the test's own requests to the ASGI app, not
just the LLM router's internal calls. Patching at the llm_router module
boundary keeps the two concerns properly isolated (HTTP-call-level mocking
for llm_router is already covered in test_llm_router.py).
"""

from __future__ import annotations

import pytest

from app.services import llm_router
from app.services.llm_router import LLMResult

SESSION_ID = "test-session-0001"


def _mock_generate(text: str, provider: str = "gemini"):
    async def fake_generate(prompt, *, image_bytes=None, image_mime=None):
        return LLMResult(raw_text=text, provider_used=provider)

    return fake_generate


VALID_ANALYSIS_JSON = """{
  "summary": "Mild anemia detected, otherwise normal.",
  "findings": [
    {
      "parameter": "Hemoglobin",
      "value": "10.2 g/dL",
      "reference_range": "12.0-15.5 g/dL",
      "severity": "abnormal",
      "plain_language_explanation": "Hemoglobin carries oxygen in your blood; this is slightly low."
    }
  ],
  "overall_severity": "abnormal",
  "recommended_action": "Discuss with your physician at your next visit."
}"""


@pytest.mark.asyncio
async def test_health_endpoint(app_client):
    resp = await app_client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["gemini_configured"] is True


@pytest.mark.asyncio
async def test_analyze_text_file(app_client, monkeypatch):
    monkeypatch.setattr(llm_router, "generate", _mock_generate(VALID_ANALYSIS_JSON))

    files = {"file": ("report.txt", b"Hemoglobin: 10.2 g/dL", "text/plain")}
    data = {"session_id": SESSION_ID}
    resp = await app_client.post("/api/v1/analyze", files=files, data=data)

    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_severity"] == "abnormal"
    assert body["findings"][0]["parameter"] == "Hemoglobin"
    assert body["provider_used"] == "gemini"


@pytest.mark.asyncio
async def test_analyze_then_history_shows_it(app_client, monkeypatch):
    monkeypatch.setattr(llm_router, "generate", _mock_generate(VALID_ANALYSIS_JSON))

    files = {"file": ("report.txt", b"Hemoglobin: 10.2 g/dL", "text/plain")}
    data = {"session_id": SESSION_ID}
    await app_client.post("/api/v1/analyze", files=files, data=data)

    history_resp = await app_client.get(f"/api/v1/history/{SESSION_ID}")
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert len(history_data["analyses"]) == 1
    assert history_data["analyses"][0]["file_name"] == "report.txt"


@pytest.mark.asyncio
async def test_duplicate_upload_is_cached(app_client, monkeypatch):
    call_count = {"n": 0}

    async def counting_generate(prompt, *, image_bytes=None, image_mime=None):
        call_count["n"] += 1
        return LLMResult(raw_text=VALID_ANALYSIS_JSON, provider_used="gemini")

    monkeypatch.setattr(llm_router, "generate", counting_generate)

    files = {"file": ("report.txt", b"Hemoglobin: 10.2 g/dL", "text/plain")}
    data = {"session_id": SESSION_ID}

    first = await app_client.post("/api/v1/analyze", files=files, data=data)
    second = await app_client.post("/api/v1/analyze", files=files, data=data)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["analysis_id"] == second.json()["analysis_id"]
    assert call_count["n"] == 1  # second upload hit cache, no second LLM call


@pytest.mark.asyncio
async def test_history_pruned_to_last_three(app_client, monkeypatch):
    monkeypatch.setattr(llm_router, "generate", _mock_generate(VALID_ANALYSIS_JSON))

    for i in range(5):
        files = {"file": (f"report{i}.txt", f"Finding {i}".encode(), "text/plain")}
        data = {"session_id": SESSION_ID}
        resp = await app_client.post("/api/v1/analyze", files=files, data=data)
        assert resp.status_code == 200

    history_resp = await app_client.get(f"/api/v1/history/{SESSION_ID}")
    history_data = history_resp.json()
    assert len(history_data["analyses"]) == 3
    # Most recent uploads (2, 3, 4) should be the ones retained
    names = {item["file_name"] for item in history_data["analyses"]}
    assert names == {"report2.txt", "report3.txt", "report4.txt"}


@pytest.mark.asyncio
async def test_unsupported_file_type_returns_415(app_client):
    files = {"file": ("archive.zip", b"PK\x03\x04", "application/zip")}
    data = {"session_id": SESSION_ID}
    resp = await app_client.post("/api/v1/analyze", files=files, data=data)
    assert resp.status_code == 415
    assert resp.json()["code"] == "unsupported_file_type"


@pytest.mark.asyncio
async def test_chat_on_unknown_analysis_returns_404(app_client):
    resp = await app_client.post(
        "/api/v1/analyze/nonexistent-id/chat",
        json={"session_id": SESSION_ID, "question": "What does this mean?"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "session_not_found"
