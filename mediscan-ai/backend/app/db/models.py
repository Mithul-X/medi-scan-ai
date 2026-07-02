"""
SQLAlchemy ORM models.

Two tables only:
  - sessions:  one row per browser session (localStorage UUID)
  - analyses:  one row per analyzed file, FK'd to a session

History pruning (keep last N sessions, last N analyses per session) is
enforced in app/services at write-time, not via DB triggers — keeps the
schema simple and the logic visible in Python where it's easy to reason
about and test.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    analyses: Mapped[list["AnalysisRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="desc(AnalysisRecord.created_at)",
    )


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_db_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)

    file_name: Mapped[str] = mapped_column(String(255))
    file_mime_type: Mapped[str] = mapped_column(String(100))
    file_hash: Mapped[str] = mapped_column(String(32), index=True)  # MD5 hex digest

    provider_used: Mapped[str] = mapped_column(String(50))  # "gemini" | "openrouter:<model>"

    extracted_text_excerpt: Mapped[str] = mapped_column(Text, default="")
    structured_result_json: Mapped[str] = mapped_column(Text)  # serialized AnalysisResponse
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed | failed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    session: Mapped["SessionRecord"] = relationship(back_populates="analyses")
