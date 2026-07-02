"""
GET /api/v1/history/{session_id}              — last N analyses for a session (summary view)
GET /api/v1/history/{session_id}/{analysis_id} — full stored analysis (for re-opening from history)
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SessionNotFoundError
from app.db.database import get_db
from app.db.models import AnalysisRecord, SessionRecord
from app.schemas.response import AnalysisHistoryItem, AnalysisResponse, SessionHistoryResponse
from app.services.history import deserialize_response

router = APIRouter(tags=["history"])


@router.get("/history/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> SessionHistoryResponse:
    session_result = await db.execute(
        select(SessionRecord).where(SessionRecord.session_id == session_id)
    )
    session_record = session_result.scalar_one_or_none()

    if session_record is None:
        return SessionHistoryResponse(session_id=session_id, analyses=[])

    analyses_result = await db.execute(
        select(AnalysisRecord)
        .where(AnalysisRecord.session_db_id == session_record.id)
        .order_by(AnalysisRecord.created_at.desc())
    )
    records = analyses_result.scalars().all()

    items = []
    for record in records:
        data = json.loads(record.structured_result_json)
        items.append(
            AnalysisHistoryItem(
                analysis_id=record.id,
                file_name=record.file_name,
                overall_severity=data["overall_severity"],
                summary=data["summary"],
                created_at=record.created_at,
            )
        )

    return SessionHistoryResponse(session_id=session_id, analyses=items)


@router.get("/history/{session_id}/{analysis_id}", response_model=AnalysisResponse)
async def get_session_analysis(
    session_id: str, analysis_id: str, db: AsyncSession = Depends(get_db)
) -> AnalysisResponse:
    session_result = await db.execute(
        select(SessionRecord).where(SessionRecord.session_id == session_id)
    )
    session_record = session_result.scalar_one_or_none()
    if session_record is None:
        raise SessionNotFoundError(f"No session found with id {session_id}")

    analysis_result = await db.execute(
        select(AnalysisRecord).where(
            AnalysisRecord.id == analysis_id,
            AnalysisRecord.session_db_id == session_record.id,
        )
    )
    record = analysis_result.scalar_one_or_none()
    if record is None:
        raise SessionNotFoundError(
            f"No analysis with id {analysis_id} found in session {session_id}"
        )

    return deserialize_response(record)
