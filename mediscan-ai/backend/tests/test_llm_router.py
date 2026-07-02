"""
Unit tests for app/services/llm_router.py.

All HTTP calls are mocked via monkeypatching httpx.AsyncClient.post —
no real network calls, no real API keys needed, deterministic.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import AllProvidersExhaustedError
from app.services import llm_router


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self) -> dict:
        return self._json


def _gemini_success_payload(text: str = "Gemini response text") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _openrouter_success_payload(text: str = "OpenRouter response text") -> dict:
    return {"choices": [{"message": {"content": text}}]}


@pytest.mark.asyncio
async def test_gemini_success_returns_immediately(monkeypatch):
    async def fake_post(self, url, **kwargs):
        assert "generativelanguage" in url
        return _FakeResponse(200, _gemini_success_payload("All good"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await llm_router.generate("analyze this report")
    assert result.provider_used == "gemini"
    assert result.raw_text == "All good"


@pytest.mark.asyncio
async def test_gemini_429_falls_back_to_openrouter(monkeypatch):
    call_log = []

    async def fake_post(self, url, **kwargs):
        call_log.append(url)
        if "generativelanguage" in url:
            return _FakeResponse(429, text="rate limited")
        return _FakeResponse(200, _openrouter_success_payload("Fallback worked"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await llm_router.generate("analyze this report")
    assert result.provider_used.startswith("openrouter:")
    assert result.raw_text == "Fallback worked"
    # Gemini retried (max_retries + 1 attempts) before falling through
    gemini_calls = [u for u in call_log if "generativelanguage" in u]
    assert len(gemini_calls) >= 1


@pytest.mark.asyncio
async def test_all_providers_exhausted_raises(monkeypatch):
    async def fake_post(self, url, **kwargs):
        return _FakeResponse(500, text="server on fire")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(AllProvidersExhaustedError):
        await llm_router.generate("analyze this report")


@pytest.mark.asyncio
async def test_openrouter_chain_walks_to_second_model(monkeypatch):
    async def fake_post(self, url, **kwargs):
        if "generativelanguage" in url:
            return _FakeResponse(429, text="rate limited")
        payload = kwargs.get("json", {})
        model = payload.get("model")
        if model == "openrouter/free":
            return _FakeResponse(500, text="router down")
        return _FakeResponse(200, _openrouter_success_payload(f"answered by {model}"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await llm_router.generate("analyze this report")
    assert "openrouter:" in result.provider_used
    assert "openrouter/free" not in result.provider_used
