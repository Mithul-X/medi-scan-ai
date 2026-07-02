"""
LLM provider router: Gemini primary -> OpenRouter fallback chain.

Design:
  1. Try Gemini first (gemini-2.5-flash, vision-capable, generous free tier).
  2. On 429 / 5xx / timeout, fall through the OpenRouter chain in order:
     "openrouter/free" (smart free-model router) -> named free models.
  3. Exponential-ish backoff between attempts on the SAME provider; no
     backoff between DIFFERENT providers (failing over fast is the point).
  4. Every call result records which provider actually answered, so the
     frontend/report can show "analyzed via Gemini" or "via OpenRouter (X)".

This module talks to providers over plain httpx — no heavyweight SDK
dependency, easier to reason about exactly what's sent and keeps the
free-tier request shape fully visible/auditable in one file.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import AllProvidersExhaustedError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResult:
    raw_text: str
    provider_used: str  # "gemini" | "openrouter:<model>"


class _RetryableProviderError(Exception):
    """Internal signal: this provider failed in a way worth falling back from."""


async def _call_gemini_text(
    client: httpx.AsyncClient, settings: Settings, prompt: str
) -> str:
    url = (
        f"{settings.gemini_base_url}/models/{settings.gemini_model_text}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = await client.post(url, json=payload, timeout=settings.llm_request_timeout_seconds)
    return _handle_gemini_response(resp)


async def _call_gemini_vision(
    client: httpx.AsyncClient,
    settings: Settings,
    prompt: str,
    image_bytes: bytes,
    image_mime: str,
) -> str:
    url = (
        f"{settings.gemini_base_url}/models/{settings.gemini_model_vision}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": image_mime, "data": b64}},
                ]
            }
        ]
    }
    resp = await client.post(url, json=payload, timeout=settings.llm_request_timeout_seconds)
    return _handle_gemini_response(resp)


def _handle_gemini_response(resp: httpx.Response) -> str:
    if resp.status_code == 429:
        raise _RetryableProviderError(f"Gemini rate limited: {resp.text[:200]}")
    if resp.status_code >= 500:
        raise _RetryableProviderError(f"Gemini server error {resp.status_code}: {resp.text[:200]}")
    if resp.status_code != 200:
        # 4xx other than 429 (bad key, bad request) — not worth retrying same provider,
        # but DO fall through to OpenRouter since the failure is provider-specific.
        raise _RetryableProviderError(f"Gemini error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        candidates = data["candidates"]
        parts = candidates[0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError) as exc:
        # Common cause: response blocked by safety filters (finishReason SAFETY)
        finish_reason = (data.get("candidates") or [{}])[0].get("finishReason", "UNKNOWN")
        raise _RetryableProviderError(
            f"Gemini returned no usable content (finishReason={finish_reason})"
        ) from exc

    if not text.strip():
        raise _RetryableProviderError("Gemini returned empty text")
    return text


async def _call_openrouter(
    client: httpx.AsyncClient,
    settings: Settings,
    model: str,
    prompt: str,
    image_bytes: bytes | None,
    image_mime: str | None,
) -> str:
    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }

    if image_bytes and image_mime:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{b64}"}},
        ]
    else:
        content = prompt  # type: ignore[assignment]

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }

    resp = await client.post(
        url, json=payload, headers=headers, timeout=settings.llm_request_timeout_seconds
    )

    if resp.status_code == 429:
        raise _RetryableProviderError(f"OpenRouter[{model}] rate limited: {resp.text[:200]}")
    if resp.status_code >= 500:
        raise _RetryableProviderError(
            f"OpenRouter[{model}] server error {resp.status_code}: {resp.text[:200]}"
        )
    if resp.status_code != 200:
        raise _RetryableProviderError(
            f"OpenRouter[{model}] error {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise _RetryableProviderError(f"OpenRouter[{model}] returned no usable content") from exc

    if not text or not text.strip():
        raise _RetryableProviderError(f"OpenRouter[{model}] returned empty text")
    return text


async def _with_retries(coro_factory, *, max_retries: int, backoff_seconds: float) -> str:
    """Retries the SAME provider call on transient failure before giving up on it."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except _RetryableProviderError as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(backoff_seconds * (attempt + 1))
                continue
            break
    assert last_exc is not None
    raise last_exc


async def generate(
    prompt: str,
    *,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
) -> LLMResult:
    """
    Primary entry point used by routes/services. Tries Gemini, then walks
    the OpenRouter fallback chain in order. Raises AllProvidersExhaustedError
    only if every single provider in the chain fails.
    """
    settings = get_settings()
    errors: list[str] = []

    async with httpx.AsyncClient() as client:
        # --- 1. Gemini primary ---
        if settings.gemini_api_key:
            try:
                if image_bytes and image_mime:
                    text = await _with_retries(
                        lambda: _call_gemini_vision(client, settings, prompt, image_bytes, image_mime),
                        max_retries=settings.llm_max_retries,
                        backoff_seconds=settings.llm_retry_backoff_seconds,
                    )
                else:
                    text = await _with_retries(
                        lambda: _call_gemini_text(client, settings, prompt),
                        max_retries=settings.llm_max_retries,
                        backoff_seconds=settings.llm_retry_backoff_seconds,
                    )
                return LLMResult(raw_text=text, provider_used="gemini")
            except _RetryableProviderError as exc:
                logger.warning("gemini_failed_falling_back", extra={"error": str(exc)})
                errors.append(f"gemini: {exc}")
        else:
            errors.append("gemini: no API key configured, skipped")

        # --- 2. OpenRouter fallback chain ---
        if settings.openrouter_api_key:
            for model in settings.openrouter_fallback_models:
                try:
                    text = await _with_retries(
                        lambda m=model: _call_openrouter(
                            client, settings, m, prompt, image_bytes, image_mime
                        ),
                        max_retries=settings.llm_max_retries,
                        backoff_seconds=settings.llm_retry_backoff_seconds,
                    )
                    return LLMResult(raw_text=text, provider_used=f"openrouter:{model}")
                except _RetryableProviderError as exc:
                    logger.warning(
                        "openrouter_model_failed", extra={"model": model, "error": str(exc)}
                    )
                    errors.append(f"openrouter:{model}: {exc}")
        else:
            errors.append("openrouter: no API key configured, skipped")

    logger.error("all_providers_exhausted", extra={"errors": errors})
    raise AllProvidersExhaustedError(
        "All configured LLM providers failed or are unavailable.",
        details={"attempts": errors},
    )
