"""SQLModel table definitions for all 9 GovGrant database tables."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ─── Table 1: users ───────────────────────────────────────────────────────────

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(unique=True, index=True)
    name: str
    hashed_password: str
    created_at: datetime = Field(default_factory=_now)


# ─── Table 2: sessions ────────────────────────────────────────────────────────

class ChatSession(SQLModel, table=True):
    __tablename__ = "sessions"

    session_id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    status: str = Field(default="intake")  # intake | researching | validating | done


# ─── Table 3: chat_messages ───────────────────────────────────────────────────

class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    role: str  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=_now)


# ─── Table 4: intake_profiles ───────────────────────────────────────────────

class IntakeProfile(SQLModel, table=True):
    __tablename__ = "intake_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    profile_json: str
    created_at: datetime = Field(default_factory=_now)


# ─── Table 5: user_profiles ───────────────────────────────────────────────────

class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    name: str
    type: str  # startup | smb | ngo | other
    sector: str
    state: str
    city: str
    team_size: int
    revenue_inr: int
    funding_purpose: str
    created_at: datetime = Field(default_factory=_now)


# ─── Table 6: raw_schemes ─────────────────────────────────────────────────────

class RawScheme(SQLModel, table=True):
    __tablename__ = "raw_schemes"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    scheme_name: str
    source_url: str
    source_type: str  # live | offline
    criteria_text: str
    deadline: Optional[date] = None
    max_revenue_inr: Optional[int] = None
    eligible_types: str  # JSON array stored as string
    created_at: datetime = Field(default_factory=_now)


# ─── Table 7: ranked_schemes ──────────────────────────────────────────────────

class RankedScheme(SQLModel, table=True):
    __tablename__ = "ranked_schemes"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    scheme_name: str
    match_score: int
    rank: int
    reason: str
    urgency_score: float
    composite_rank: int
    portal_url: Optional[str] = None
    deadline: Optional[str] = None
    grant_amount: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


# ─── Table 8: grant_reports ───────────────────────────────────────────────────

class GrantReport(SQLModel, table=True):
    __tablename__ = "grant_reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True, unique=True)
    documents_json: str  # JSON array as string
    action_cards_json: str  # JSON array as string
    cover_summary: str
    created_at: datetime = Field(default_factory=_now)


# ─── Table 9: alerts ──────────────────────────────────────────────────────────

class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    user_email: str
    scheme_name: str
    deadline: date
    alert_type: str  # email | whatsapp
    status: str = Field(default="pending")  # pending | sent | failed
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_now)
