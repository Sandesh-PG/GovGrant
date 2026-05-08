"""
GovGrant API Routes — Auth, Sessions, Chat (SSE), Results, Alerts.

Chat endpoint streams mock SSE events (2s delay each) so the frontend
can be developed immediately. Real agent logic will be plugged in later.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from db.database import get_session
from db.models import (
    Alert,
    ChatSession,
    GrantReport,
    RankedScheme,
    RawScheme,
    User,
    UserProfile,
)

router = APIRouter(prefix="/api")

# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response schemas
# ═══════════════════════════════════════════════════════════════════════════════


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: Optional[List[dict]] = None


class AlertRequest(BaseModel):
    session_id: str
    email: str
    whatsapp_enabled: bool = False
    phone: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Mock data — used until real agents are wired in
# ═══════════════════════════════════════════════════════════════════════════════

MOCK_PROFILE = {
    "name": "GreenLeaf Organics",
    "type": "private_limited",
    "sector": "food_processing",
    "state": "Maharashtra",
    "city": "Pune",
    "team_size": 12,
    "revenue_inr": 8000000,
    "funding_purpose": "technology_upgrade",
}

MOCK_SCHEMES = [
    {
        "scheme_name": "PM FME Scheme",
        "source_url": "https://pmfme.mofpi.gov.in/",
        "source_type": "live",
        "criteria_text": "Micro food processing enterprises with investment < ₹10 Cr",
        "deadline": "2025-12-31",
        "max_revenue_inr": 50000000,
        "eligible_types": '["startup","msme","proprietorship","private_limited"]',
    },
    {
        "scheme_name": "CGTMSE Credit Guarantee",
        "source_url": "https://www.cgtmse.in/",
        "source_type": "live",
        "criteria_text": "Collateral-free credit up to ₹5 Cr for MSMEs",
        "deadline": None,
        "max_revenue_inr": 100000000,
        "eligible_types": '["msme","proprietorship","private_limited","partnership"]',
    },
    {
        "scheme_name": "PMEGP",
        "source_url": "https://www.kviconline.gov.in/pmegpeportal/",
        "source_type": "live",
        "criteria_text": "Manufacturing projects up to ₹50L, service up to ₹20L",
        "deadline": None,
        "max_revenue_inr": 25000000,
        "eligible_types": '["startup","msme","proprietorship"]',
    },
    {
        "scheme_name": "MUDRA Loan - Kishore",
        "source_url": "https://www.mudra.org.in/",
        "source_type": "live",
        "criteria_text": "Loans from ₹50K to ₹5L for small businesses",
        "deadline": None,
        "max_revenue_inr": 15000000,
        "eligible_types": '["startup","msme","proprietorship"]',
    },
    {
        "scheme_name": "Maharashtra MSME Subsidy",
        "source_url": "https://maitri.mahaonline.gov.in/",
        "source_type": "offline",
        "criteria_text": "25% capital subsidy for new MSME units in Maharashtra",
        "deadline": "2025-09-30",
        "max_revenue_inr": 100000000,
        "eligible_types": '["msme","private_limited","partnership"]',
    },
]

MOCK_RANKED = [
    {
        "scheme_name": "PM FME Scheme",
        "match_score": 92,
        "rank": 1,
        "reason": "Directly targets food processing MSMEs with machinery upgrade grants up to ₹10L",
        "urgency_score": 8.5,
        "composite_rank": 1,
        "portal_url": "https://pmfme.mofpi.gov.in/",
        "deadline": "2025-12-31",
        "grant_amount": "₹10,00,000",
    },
    {
        "scheme_name": "Maharashtra MSME Subsidy",
        "match_score": 85,
        "rank": 2,
        "reason": "State-specific 25% capital subsidy for manufacturing and food processing units",
        "urgency_score": 9.2,
        "composite_rank": 2,
        "portal_url": "https://maitri.mahaonline.gov.in/",
        "deadline": "2025-09-30",
        "grant_amount": "25% of capital investment",
    },
    {
        "scheme_name": "CGTMSE Credit Guarantee",
        "match_score": 78,
        "rank": 3,
        "reason": "Collateral-free credit guarantee enables easier bank loans for equipment purchase",
        "urgency_score": 5.0,
        "composite_rank": 3,
        "portal_url": "https://www.cgtmse.in/",
        "deadline": "Rolling",
        "grant_amount": "Up to ₹5 Cr guarantee",
    },
    {
        "scheme_name": "PMEGP",
        "match_score": 65,
        "rank": 4,
        "reason": "35% subsidy for manufacturing projects, though better suited for new units",
        "urgency_score": 4.0,
        "composite_rank": 4,
        "portal_url": "https://www.kviconline.gov.in/pmegpeportal/",
        "deadline": "Rolling",
        "grant_amount": "35% of project cost",
    },
    {
        "scheme_name": "MUDRA Loan - Kishore",
        "match_score": 55,
        "rank": 5,
        "reason": "Quick working capital access, but loan amount may be insufficient for machinery",
        "urgency_score": 3.0,
        "composite_rank": 5,
        "portal_url": "https://www.mudra.org.in/",
        "deadline": "Rolling",
        "grant_amount": "₹50K – ₹5L",
    },
]

MOCK_REPORT = {
    "documents": [
        {"name": "Aadhaar Card", "description": "Aadhaar of all directors/promoters", "mandatory": True},
        {"name": "PAN Card", "description": "PAN of company and promoters", "mandatory": True},
        {"name": "Certificate of Incorporation", "description": "MCA incorporation certificate", "mandatory": True},
        {"name": "GST Certificate", "description": "GST registration certificate", "mandatory": True},
        {"name": "Udyam Registration", "description": "MSME/Udyam registration certificate", "mandatory": True},
        {"name": "Bank Statements", "description": "Last 12 months current account statements", "mandatory": True},
        {"name": "ITR Filings", "description": "Income tax returns for last 2 years", "mandatory": True},
        {"name": "Project Report", "description": "Detailed project report for machinery upgrade", "mandatory": True},
        {"name": "FSSAI License", "description": "Food safety license (for PM FME)", "mandatory": True},
        {"name": "Quotations", "description": "Machinery quotations from 3 vendors", "mandatory": False},
    ],
    "action_cards": [
        {
            "scheme_name": "PM FME Scheme",
            "portal_url": "https://pmfme.mofpi.gov.in/",
            "deadline": "2025-12-31",
            "steps": [
                "Register on PM FME portal with Aadhaar",
                "Complete online application with business details",
                "Upload project report and FSSAI license",
                "Submit machinery quotations from 3 vendors",
                "Attend DIC verification visit",
                "Receive sanction letter and start procurement",
            ],
            "estimated_days": 45,
            "tips": [
                "Apply through your District Industries Centre for faster processing",
                "FSSAI license is mandatory — apply in parallel if you don't have one",
            ],
        },
        {
            "scheme_name": "Maharashtra MSME Subsidy",
            "portal_url": "https://maitri.mahaonline.gov.in/",
            "deadline": "2025-09-30",
            "steps": [
                "Register on MAITRI portal",
                "Apply under Package Scheme of Incentives (PSI 2019)",
                "Upload Udyam, GST, and incorporation certificates",
                "Submit project report with investment breakdown",
                "Await DIC inspection and approval",
            ],
            "estimated_days": 60,
            "tips": [
                "Pune district falls in Group C — 25% subsidy on fixed capital",
                "Apply before the September deadline for current financial year",
            ],
        },
    ],
    "cover_summary": (
        "We are GreenLeaf Organics, a private limited food processing company based in "
        "Pune, Maharashtra, operating for three years with a dedicated team of twelve "
        "professionals. Our annual revenue stands at eighty lakh rupees, reflecting "
        "consistent growth in the organic food segment. We seek funding to upgrade our "
        "packaging machinery, which will double our production capacity and enable us to "
        "meet rising demand from retail chains across western India. This technology "
        "upgrade aligns directly with the government's mission to strengthen micro food "
        "processing enterprises and boost the Make in India initiative. Our Udyam-registered "
        "unit maintains full FSSAI compliance and has established distribution networks in "
        "three states. We are confident that with the right support, our expansion will "
        "create fifteen new jobs and contribute meaningfully to India's food processing "
        "sector. We respectfully request consideration for the schemes identified in this report."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/auth/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_session)):
    existing = db.exec(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    return AuthResponse(
        token=token,
        user={"id": user.id, "email": user.email, "name": user.name},
    )


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.email)
    return AuthResponse(
        token=token,
        user={"id": user.id, "email": user.email, "name": user.name},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/sessions")
def create_session(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.session_id}


@router.get("/sessions")
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    sessions = db.exec(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at.desc())
    ).all()
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CHAT ROUTE — Conversational intake + SSE pipeline
# ═══════════════════════════════════════════════════════════════════════════════

# Mock intake conversation: bot asks 6 questions one-by-one
INTAKE_QUESTIONS = [
    {
        "question": "What is the name of your business or organisation?",
        "field": "name",
        "example": "e.g. GreenLeaf Organics Pvt. Ltd.",
    },
    {
        "question": "What type of entity is it?",
        "field": "type",
        "example": "e.g. Private Limited, Proprietorship, Partnership, LLP, Startup, MSME",
    },
    {
        "question": "Which sector or industry does your business operate in?",
        "field": "sector",
        "example": "e.g. Food Processing, IT Services, Manufacturing, Textiles, Agriculture",
    },
    {
        "question": "Which state and city is your business located in?",
        "field": "state",
        "example": "e.g. Maharashtra, Pune",
    },
    {
        "question": "How many people are on your team?",
        "field": "team_size",
        "example": "e.g. 12 employees",
    },
    {
        "question": "What is your approximate annual revenue (in ₹) and what do you need the funding for?",
        "field": "revenue_and_purpose",
        "example": "e.g. ₹80 lakhs annual revenue; need funding for technology upgrade",
    },
]


def _verify_session_ownership(
    session_id: str, user: User, db: Session
) -> ChatSession:
    chat = db.get(ChatSession, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Session not found")
    if chat.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    return chat


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Conversational intake: returns a JSON reply with the next question.
    After all 6 answers are collected, returns intake_complete = true
    so the frontend can redirect to the /processing page.
    """
    _verify_session_ownership(body.session_id, user, db)

    # Count how many user messages are in the history (each = one answered question)
    history = body.history or []
    user_messages = [m for m in history if m.get("role") == "user"]
    step = len(user_messages)  # 0-indexed: 0 means first question not yet answered

    # If the user just sent a message, that's the answer to question[step-1]
    # and the bot should ask question[step] next.
    # But on the very first call (step=0, user just said "Ready" or similar),
    # the bot should ask question 0.

    if step < len(INTAKE_QUESTIONS):
        q = INTAKE_QUESTIONS[step]
        reply = f"{q['question']}\n\n💡 {q['example']}"
        return {
            "reply": reply,
            "intake_complete": False,
            "fields_collected": step,
            "total_fields": len(INTAKE_QUESTIONS),
        }
    else:
        # All 6 questions answered — persist profile and signal completion
        profile_data = {**MOCK_PROFILE, "session_id": body.session_id}
        return {
            "reply": (
                "✅ Perfect! I have everything I need. Here's what I captured:\n\n"
                f"• **Business:** {MOCK_PROFILE['name']}\n"
                f"• **Type:** {MOCK_PROFILE['type']}\n"
                f"• **Sector:** {MOCK_PROFILE['sector']}\n"
                f"• **Location:** {MOCK_PROFILE['city']}, {MOCK_PROFILE['state']}\n"
                f"• **Team:** {MOCK_PROFILE['team_size']} people\n"
                f"• **Revenue:** ₹{MOCK_PROFILE['revenue_inr']:,}\n"
                f"• **Purpose:** {MOCK_PROFILE['funding_purpose']}\n\n"
                "🔍 Starting grant search now..."
            ),
            "intake_complete": True,
            "fields_collected": len(INTAKE_QUESTIONS),
            "total_fields": len(INTAKE_QUESTIONS),
            "profile": profile_data,
        }


@router.post("/pipeline")
async def run_pipeline(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """SSE streaming endpoint — runs the 4-stage mock pipeline."""
    chat_session = _verify_session_ownership(body.session_id, user, db)

    async def sse_stream():
        # ── Stage 1: Intake done ──────────────────────────────────────
        await asyncio.sleep(2)
        profile_data = {**MOCK_PROFILE, "session_id": body.session_id}
        db.add(UserProfile(session_id=body.session_id, **MOCK_PROFILE))
        chat_session.status = "researching"
        db.add(chat_session)
        db.commit()
        yield f"event: intake_done\ndata: {json.dumps(profile_data)}\n\n"

        # ── Stage 2: Research done ────────────────────────────────────
        await asyncio.sleep(2)
        for s in MOCK_SCHEMES:
            db.add(RawScheme(session_id=body.session_id, **s))
        db.commit()
        yield f"event: research_done\ndata: {json.dumps(MOCK_SCHEMES)}\n\n"

        # ── Stage 3: Validation done ──────────────────────────────────
        await asyncio.sleep(2)
        chat_session.status = "validating"
        db.add(chat_session)
        for r in MOCK_RANKED:
            db.add(RankedScheme(session_id=body.session_id, **r))
        db.commit()
        yield f"event: validation_done\ndata: {json.dumps(MOCK_RANKED)}\n\n"

        # ── Stage 4: Report ready ─────────────────────────────────────
        await asyncio.sleep(2)
        chat_session.status = "done"
        db.add(chat_session)
        db.add(
            GrantReport(
                session_id=body.session_id,
                documents_json=json.dumps(MOCK_REPORT["documents"]),
                action_cards_json=json.dumps(MOCK_REPORT["action_cards"]),
                cover_summary=MOCK_REPORT["cover_summary"],
            )
        )
        db.commit()
        yield f"event: report_ready\ndata: {json.dumps(MOCK_REPORT)}\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS ROUTE
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/results/{session_id}")
def get_results(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    _verify_session_ownership(session_id, user, db)

    report = db.exec(
        select(GrantReport).where(GrantReport.session_id == session_id)
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    ranked = db.exec(
        select(RankedScheme)
        .where(RankedScheme.session_id == session_id)
        .order_by(RankedScheme.composite_rank)
    ).all()

    return {
        "session_id": session_id,
        "schemes": [
            {
                "scheme_name": r.scheme_name,
                "match_score": r.match_score,
                "rank": r.rank,
                "reason": r.reason,
                "urgency_score": r.urgency_score,
                "composite_rank": r.composite_rank,
                "portal_url": r.portal_url,
                "deadline": r.deadline,
                "grant_amount": r.grant_amount,
            }
            for r in ranked
        ],
        "documents": json.loads(report.documents_json),
        "action_cards": json.loads(report.action_cards_json),
        "cover_summary": report.cover_summary,
        "created_at": report.created_at.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ALERTS ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/alerts")
def create_alerts(
    body: AlertRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    _verify_session_ownership(body.session_id, user, db)

    ranked = db.exec(
        select(RankedScheme).where(RankedScheme.session_id == body.session_id)
    ).all()

    alerts_created = 0
    deadlines = []
    today = date.today()

    for r in ranked:
        if not r.deadline or r.deadline == "Rolling":
            continue
        try:
            dl = date.fromisoformat(r.deadline)
        except ValueError:
            continue
        days_left = (dl - today).days
        if days_left > 60 or days_left < 0:
            continue

        alert_type = "email"
        db.add(
            Alert(
                session_id=body.session_id,
                user_email=body.email,
                scheme_name=r.scheme_name,
                deadline=dl,
                alert_type=alert_type,
            )
        )
        if body.whatsapp_enabled and body.phone:
            db.add(
                Alert(
                    session_id=body.session_id,
                    user_email=body.email,
                    scheme_name=r.scheme_name,
                    deadline=dl,
                    alert_type="whatsapp",
                )
            )
            alerts_created += 1

        alerts_created += 1
        deadlines.append(
            {"scheme_name": r.scheme_name, "deadline": r.deadline, "days_left": days_left}
        )

    db.commit()
    return {"alerts_created": alerts_created, "deadlines": deadlines}


@router.get("/alerts/{session_id}")
def get_alerts(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    _verify_session_ownership(session_id, user, db)

    alerts = db.exec(
        select(Alert).where(Alert.session_id == session_id)
    ).all()
    return {
        "alerts": [
            {
                "scheme_name": a.scheme_name,
                "deadline": a.deadline.isoformat(),
                "status": a.status,
                "alert_type": a.alert_type,
            }
            for a in alerts
        ]
    }
