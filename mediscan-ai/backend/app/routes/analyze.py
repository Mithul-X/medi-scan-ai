"""
POST /api/v1/analyze        — upload a file, get a structured analysis back
POST /api/v1/analyze/{id}/chat — follow-up question about a prior analysis
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidRequestError, SessionNotFoundError
from app.core.logging import get_logger
from app.db.database import get_db
from app.schemas.request import ChatRequest
from app.schemas.response import AnalysisResponse, ChatResponse
from app.services import cache, file_processor, history, llm_router, report_parser
from app.services.file_processor import ContentKind
from app.prompts.medical_analysis import (
    build_analysis_prompt,
    build_chat_prompt,
    build_chunk_merge_prompt,
)

router = APIRouter(tags=["analyze"])
logger = get_logger(__name__)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_report(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    if not file.filename:
        raise InvalidRequestError("Uploaded file has no filename.")

    raw = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    file_hash = cache.hash_bytes(raw)

    session_record = await history.get_or_create_session(db, session_id)

    # --- Dedup check: DB first (durable across cold starts), then in-memory cache ---
    existing = await history.get_analysis_by_hash(
        db, session_db_id=session_record.id, file_hash=file_hash
    )
    if existing is not None:
        logger.info("cache_hit_db", extra={"file_hash": file_hash})
        return history.deserialize_response(existing)

    cached_id = cache.get_cached_analysis_id(file_hash)
    if cached_id:
        existing = await history.get_analysis_by_id(db, analysis_id=cached_id)
        if existing is not None:
            logger.info("cache_hit_memory", extra={"file_hash": file_hash})
            return history.deserialize_response(existing)

    # --- Process the upload (PDF/text extraction or image compression) ---
    processed = file_processor.process_upload(raw, mime_type=mime_type, file_name=file.filename)

    # --- Run the LLM analysis ---
    if processed.kind == ContentKind.IMAGE:
        prompt = build_analysis_prompt("(see attached image)", file_name=file.filename)
        result = await llm_router.generate(
            prompt, image_bytes=processed.image_bytes, image_mime=processed.image_mime
        )
        excerpt = "(image upload — no extracted text)"
    elif len(processed.text_chunks) == 1:
        prompt = build_analysis_prompt(processed.text_chunks[0], file_name=file.filename)
        result = await llm_router.generate(prompt)
        excerpt = processed.text_chunks[0]
    else:
        # Long document: analyze each chunk, then merge. The merge call's
        # provider becomes the recorded provider_used for this analysis.
        chunk_summaries: list[str] = []
        for chunk in processed.text_chunks:
            chunk_prompt = build_analysis_prompt(chunk, file_name=file.filename)
            chunk_result = await llm_router.generate(chunk_prompt)
            chunk_summaries.append(chunk_result.raw_text)
        merge_prompt = build_chunk_merge_prompt(chunk_summaries, file_name=file.filename)
        result = await llm_router.generate(merge_prompt)
        excerpt = processed.text_chunks[0]

    parsed = report_parser.parse_analysis_output(result.raw_text)

    response = AnalysisResponse(
        analysis_id=str(uuid.uuid4()),
        session_id=session_id,
        file_name=file.filename,
        summary=parsed["summary"],
        findings=parsed["findings"],
        overall_severity=parsed["overall_severity"],
        recommended_action=parsed["recommended_action"],
        provider_used=result.provider_used,
        created_at=datetime.now(timezone.utc),
    )

    saved = await history.save_analysis(
        db,
        session_db_id=session_record.id,
        file_name=file.filename,
        file_mime_type=mime_type,
        file_hash=file_hash,
        provider_used=result.provider_used,
        extracted_text_excerpt=excerpt,
        response=response,
    )
    cache.set_cached_analysis_id(file_hash, saved.id)

    return response


@router.post("/analyze/{analysis_id}/chat", response_model=ChatResponse)
async def chat_about_analysis(
    analysis_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    record = await history.get_analysis_by_id(db, analysis_id=analysis_id)
    if record is None:
        raise SessionNotFoundError(f"No analysis found with id {analysis_id}")

    stored = history.deserialize_response(record)
    prompt = build_chat_prompt(
        original_summary=stored.summary,
        findings_json=stored.model_dump_json(include={"findings"}),
        question=body.question,
    )
    result = await llm_router.generate(prompt)

    return ChatResponse(
        analysis_id=analysis_id,
        question=body.question,
        answer=result.raw_text.strip(),
        provider_used=result.provider_used,
    )
