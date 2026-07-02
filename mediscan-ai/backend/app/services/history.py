"""
Session + analysis persistence with bounded history.

Enforces "last N sessions, last N analyses per session" at write-time in
plain Python/SQL rather than DB triggers — keeps the policy visible and
unit-testable (see tests/test_routes.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AnalysisRecord, SessionRecord
from app.schemas.response import AnalysisResponse


async def get_or_create_session(db: AsyncSession, session_id: str) -> SessionRecord:
    result = await db.execute(
        select(SessionRecord).where(SessionRecord.session_id == session_id)
    )
    record = result.scalar_one_or_none()
    if record is not None:
        record.last_active_at = datetime.now(timezone.utc)
        await db.commit()
        return record

    record = SessionRecord(session_id=session_id)
    db.add(record)
    await db.commit()
    await db.refresh(record)

    await _prune_old_sessions(db)
    return record


async def _prune_old_sessions(db: AsyncSession) -> None:
    settings = get_settings()
    result = await db.execute(
        select(SessionRecord.id).order_by(SessionRecord.last_active_at.desc())
    )
    ids = [row[0] for row in result.all()]
    stale_ids = ids[settings.max_sessions_history :]
    if stale_ids:
        await db.execute(delete(SessionRecord).where(SessionRecord.id.in_(stale_ids)))
        await db.commit()


async def save_analysis(
    db: AsyncSession,
    *,
    session_db_id: str,
    file_name: str,
    file_mime_type: str,
    file_hash: str,
    provider_used: str,
    extracted_text_excerpt: str,
    response: AnalysisResponse,
) -> AnalysisRecord:
    record = AnalysisRecord(
        id=response.analysis_id,
        session_db_id=session_db_id,
        file_name=file_name,
        file_mime_type=file_mime_type,
        file_hash=file_hash,
        provider_used=provider_used,
        extracted_text_excerpt=extracted_text_excerpt[:500],
        structured_result_json=response.model_dump_json(),
        status="completed",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    await _prune_old_analyses(db, session_db_id=session_db_id)
    return record


async def _prune_old_analyses(db: AsyncSession, *, session_db_id: str) -> None:
    settings = get_settings()
    result = await db.execute(
        select(AnalysisRecord.id)
        .where(AnalysisRecord.session_db_id == session_db_id)
        .order_by(AnalysisRecord.created_at.desc())
    )
    ids = [row[0] for row in result.all()]
    stale_ids = ids[settings.max_analyses_per_session :]
    if stale_ids:
        await db.execute(delete(AnalysisRecord).where(AnalysisRecord.id.in_(stale_ids)))
        await db.commit()


async def get_analysis_by_hash(
    db: AsyncSession, *, session_db_id: str, file_hash: str
) -> AnalysisRecord | None:
    result = await db.execute(
        select(AnalysisRecord)
        .where(
            AnalysisRecord.session_db_id == session_db_id,
            AnalysisRecord.file_hash == file_hash,
        )
        .order_by(AnalysisRecord.created_at.desc())
    )
    return result.scalars().first()


async def get_analysis_by_id(db: AsyncSession, *, analysis_id: str) -> AnalysisRecord | None:
    result = await db.execute(select(AnalysisRecord).where(AnalysisRecord.id == analysis_id))
    return result.scalar_one_or_none()


def deserialize_response(record: AnalysisRecord) -> AnalysisResponse:
    return AnalysisResponse(**json.loads(record.structured_result_json))
