"""
Turns raw LLM text output into a validated AnalysisResponse-shaped dict.

LLMs occasionally wrap JSON in markdown fences or add stray prose despite
instructions. This module is defensive about extraction, then hands off to
Pydantic for real validation — so malformed output fails loudly via
ReportParsingError rather than silently propagating bad data to the frontend.
"""

from __future__ import annotations

import json
import re

from app.core.exceptions import ReportParsingError
from app.core.logging import get_logger
from app.schemas.response import ClinicalFinding, FindingSeverity

logger = get_logger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_blob(raw_text: str) -> str:
    fenced = _JSON_FENCE_RE.search(raw_text)
    if fenced:
        return fenced.group(1)

    bare = _BARE_JSON_RE.search(raw_text)
    if bare:
        return bare.group(0)

    raise ReportParsingError(
        "No JSON object found in LLM response.", details={"raw_excerpt": raw_text[:300]}
    )


def parse_analysis_output(raw_text: str) -> dict:
    """
    Returns a dict with keys: summary, findings (list[ClinicalFinding]),
    overall_severity (FindingSeverity), recommended_action.

    Raises ReportParsingError on any structural failure.
    """
    blob = _extract_json_blob(raw_text)

    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise ReportParsingError(
            f"LLM output was not valid JSON: {exc}", details={"raw_excerpt": blob[:300]}
        ) from exc

    required_keys = {"summary", "findings", "overall_severity", "recommended_action"}
    missing = required_keys - data.keys()
    if missing:
        raise ReportParsingError(
            f"LLM output missing required keys: {sorted(missing)}",
            details={"raw_excerpt": blob[:300]},
        )

    try:
        findings = [ClinicalFinding(**f) for f in data["findings"]]
    except Exception as exc:
        raise ReportParsingError(f"Malformed finding object: {exc}") from exc

    try:
        overall_severity = FindingSeverity(data["overall_severity"])
    except ValueError as exc:
        raise ReportParsingError(
            f"Invalid overall_severity value: {data['overall_severity']!r}"
        ) from exc

    return {
        "summary": str(data["summary"]),
        "findings": findings,
        "overall_severity": overall_severity,
        "recommended_action": str(data["recommended_action"]),
    }


def merge_severities(severities: list[FindingSeverity]) -> FindingSeverity:
    """Highest-severity-wins, used when merging chunked analyses."""
    order = [FindingSeverity.NORMAL, FindingSeverity.ABNORMAL, FindingSeverity.CRITICAL]
    return max(severities, key=order.index) if severities else FindingSeverity.NORMAL
