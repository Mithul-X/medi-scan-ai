"""Pydantic request models."""

from pydantic import BaseModel, Field


class AnalyzeRequestMeta(BaseModel):
    """
    Metadata sent alongside the multipart file upload on POST /analyze.

    The file itself arrives as multipart form data (handled directly in the
    route via FastAPI's UploadFile) — this model covers the accompanying
    JSON fields sent in the same request.
    """

    session_id: str = Field(
        ...,
        min_length=8,
        max_length=64,
        description="Client-generated UUID from localStorage, identifies the browsing session.",
    )
    follow_up_question: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional natural-language question about the report, for the chat panel.",
    )


class ChatRequest(BaseModel):
    """POST /analyze/{analysis_id}/chat — follow-up question about an existing analysis."""

    session_id: str = Field(..., min_length=8, max_length=64)
    question: str = Field(..., min_length=1, max_length=2000)
