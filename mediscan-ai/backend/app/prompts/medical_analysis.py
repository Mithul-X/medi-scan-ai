"""
Versioned prompt templates for medical report analysis.

Kept as plain Python (not Jinja/external files) so they're easy to diff
in code review and version with a simple PROMPT_VERSION bump — relevant
for a capstone report ("which prompt produced which result").
"""

PROMPT_VERSION = "v1.0"

SYSTEM_INSTRUCTIONS = """You are a clinical document analysis assistant embedded in MediScan AI.

Your job: read the medical report text provided (lab report, radiology finding, \
discharge summary, or prescription) and produce a structured, plain-language analysis \
for a patient with no medical training.

Rules:
1. Extract every quantitative clinical finding you can identify (test name, value, unit, \
   reference range if present).
2. Classify each finding's severity as "normal", "abnormal", or "critical" based on whether \
   the value falls outside the stated (or medically standard, if not stated) reference range.
3. Explain each finding in plain language a non-medical person can understand — no jargon \
   without immediate explanation.
4. Never diagnose. Describe what a finding indicates in general terms, and defer the actual \
   diagnosis and treatment decision to a physician.
5. If ANY finding is "critical", set overall_severity to "critical" and recommended_action \
   must urge prompt physician consultation.
6. If the document is illegible, not a medical document, or contains no extractable findings, \
   say so plainly in the summary and return an empty findings list with overall_severity "normal".
7. Output ONLY valid JSON matching the schema below. No markdown fences, no commentary outside \
   the JSON object.

Required JSON schema:
{
  "summary": "string — 2-4 sentence plain-language overview",
  "findings": [
    {
      "parameter": "string",
      "value": "string",
      "reference_range": "string or null",
      "severity": "normal | abnormal | critical",
      "plain_language_explanation": "string"
    }
  ],
  "overall_severity": "normal | abnormal | critical",
  "recommended_action": "string"
}"""


def build_analysis_prompt(document_text: str, *, file_name: str) -> str:
    """User-turn prompt combining instructions with the extracted document text."""
    # Truncate defensively — this is a second line of defense; file_processor.py
    # already chunks long documents before this is ever called.
    truncated = document_text[:60_000]
    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"---\n"
        f"Document filename: {file_name}\n"
        f"Document content:\n{truncated}\n"
        f"---\n\n"
        f"Return the JSON analysis now."
    )


def build_chat_prompt(*, original_summary: str, findings_json: str, question: str) -> str:
    """Follow-up question prompt — grounds the model in the prior analysis, not the raw document."""
    return (
        "You previously analyzed a patient's medical report and produced this summary:\n"
        f"{original_summary}\n\n"
        f"Structured findings (JSON):\n{findings_json}\n\n"
        "The patient now asks a follow-up question. Answer in plain language, grounded only "
        "in the findings above. If the question requires information not present in the "
        "findings, say so and recommend they ask their physician. Never diagnose.\n\n"
        f"Patient's question: {question}\n\n"
        "Answer (plain text, 1-3 short paragraphs, no JSON):"
    )


def build_chunk_merge_prompt(chunk_summaries: list[str], *, file_name: str) -> str:
    """Merges per-chunk analyses for documents too long to send in one call."""
    joined = "\n\n".join(f"--- Chunk {i+1} ---\n{s}" for i, s in enumerate(chunk_summaries))
    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        "The following are independent analyses of consecutive sections of one long document "
        f"named '{file_name}'. Merge them into a single coherent analysis following the same "
        "JSON schema. Deduplicate repeated findings; preserve the highest severity seen for "
        "any finding mentioned in multiple chunks.\n\n"
        f"{joined}\n\n"
        "Return the merged JSON analysis now."
    )
