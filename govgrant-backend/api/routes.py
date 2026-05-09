"""
GovGrant API Routes — Auth, Sessions, Chat (SSE), Results, Alerts.

Chat endpoint uses real Gemini IntakeAgent for conversational intake.
Pipeline endpoint runs Agent 2 (Research) with real Gemini search.
Agents 3-4 still use mock data (to be wired later).
"""
from __future__ import annotations

import asyncio
import json
import logging
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
    ChatMessage,
    ChatSession,
    GrantReport,
    IntakeProfile,
    RankedScheme,
    RawScheme,
    User,
    UserProfile,
)
from agents.research_service import run_research, read_profile_from_db
from agents.intake_service import process_intake_message
from agents.validator_service import run_validation
from agents.planner_service import run_planner

# ─── Logging setup ────────────────────────────────────────────────────────────
import sys
logger = logging.getLogger("govgrant.routes")
_handler = logging.StreamHandler(stream=sys.stderr)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
))
logging.getLogger("govgrant").setLevel(logging.INFO)
logging.getLogger("govgrant").addHandler(_handler)

router = APIRouter(prefix="/api")

OPENING_MESSAGE = json.dumps({
    "step": 1,
    "message": (
        "Hello! Welcome. I'm your Government Funding Intake Assistant. I'm here to help you "
        "identify and apply for central and state government funding schemes that best fit your business.\n\n"
        "This will just take a few minutes. Could you please share your full name and the name of your business or organisation?"
    ),
    "input_type": "text",
    "options": [],
    "field": "name_and_org",
    "collected": {},
})

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
    # Store opening message for this session
    db.add(ChatMessage(
        session_id=session.session_id,
        role="assistant",
        content=OPENING_MESSAGE,
    ))
    db.commit()
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

# ── Conversational intake fields ─────────────────────────────────────────────
# These define the data we need, but the conversation flow is dynamic,
# not a rigid one-question-per-field form.

_INTAKE_FIELDS = ["name", "type", "sector", "state", "team_size", "revenue_and_purpose"]

# Known entity types / sectors for fuzzy matching in user answers
_ENTITY_TYPES = {
    "startup", "msme", "proprietorship", "partnership", "private_limited",
    "public_limited", "llp", "ngo", "cooperative", "other",
    # common aliases
    "pvt ltd", "pvt. ltd", "pvt. ltd.", "private limited", "sole proprietorship",
    "limited liability partnership",
}
_SECTORS = {
    "agriculture", "manufacturing", "it_tech", "it", "tech", "software",
    "healthcare", "education", "food_processing", "food", "textile", "textiles",
    "renewable_energy", "solar", "fintech", "retail", "logistics", "export",
    "construction", "real_estate", "pharma", "biotech", "ev", "electric_vehicle",
    "handicraft", "handloom", "tourism", "hospitality", "other",
}
_INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "chandigarh", "jammu and kashmir", "ladakh", "puducherry",
}


def _verify_session_ownership(
    session_id: str, user: User, db: Session
) -> ChatSession:
    chat = db.get(ChatSession, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Session not found")
    if chat.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    return chat


def _read_chat_history(session_id: str, db: Session) -> List[dict]:
    """Return full chat history for a session in chronological order."""
    rows = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()

    history = []
    for row in rows:
        history.append({
            "role": row.role,
            "content": row.content,
        })
    return history


def _store_chat_message(session_id: str, role: str, content: str, db: Session) -> None:
    """Persist a chat message for a session."""
    if not content or not content.strip():
        return
    db.add(ChatMessage(
        session_id=session_id,
        role=role,
        content=content.strip(),
    ))
    db.commit()


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Conversational intake powered by real Gemini 2.0 Flash.
    Gemini asks natural questions to collect 6 business fields.
    When complete, persists UserProfile to DB and returns intake_complete=true.
    """
    logger.info("[%s] /chat called - message: %.80s", body.session_id, body.message)
    _verify_session_ownership(body.session_id, user, db)

    # Use full stored history for context
    history = _read_chat_history(body.session_id, db)

    # Store the incoming user message immediately
    _store_chat_message(body.session_id, "user", body.message, db)

    # Try real Gemini first, fall back to smart conversational flow if API fails
    try:
        result = await process_intake_message(
            session_id=body.session_id,
            message=body.message,
            history=history,
        )
        logger.info("[%s] Gemini intake OK", body.session_id)
    except Exception as e:
        logger.warning("[%s] Gemini intake failed (%s), using conversational fallback", body.session_id, str(e)[:120])
        result = _fallback_intake(history, body.message, body.session_id)

    # Store assistant reply for continuity
    if result.get("reply"):
        _store_chat_message(body.session_id, "assistant", result["reply"], db)

    # If intake is complete, persist the profile to DB
    if result["intake_complete"] and result.get("profile"):
        profile = result["profile"]
        logger.info(
            "[%s] Intake complete - persisting profile: name=%s, sector=%s, state=%s",
            body.session_id, profile.get("name"), profile.get("sector"), profile.get("state"),
        )

        # Clear existing profile (idempotent re-runs)
        existing = db.exec(
            select(UserProfile).where(UserProfile.session_id == body.session_id)
        ).first()
        if existing:
            db.delete(existing)
            db.commit()

        db.add(UserProfile(
            session_id=body.session_id,
            name=profile.get("name") or profile.get("business_name", ""),
            type=profile.get("type") or profile.get("registration_type", "other"),
            sector=profile.get("sector", "other"),
            state=profile.get("state", ""),
            city=profile.get("city", ""),
            team_size=profile.get("team_size", 1),
            revenue_inr=profile.get("revenue_inr", 0),
            funding_purpose=profile.get("funding_purpose", "general"),
        ))

        # Persist full intake profile JSON
        db.add(IntakeProfile(
            session_id=body.session_id,
            profile_json=json.dumps(profile),
        ))

        # Update session status
        chat_session = db.get(ChatSession, body.session_id)
        if chat_session:
            chat_session.status = "researching"
            db.add(chat_session)

        db.commit()
        logger.info("[%s] UserProfile persisted, status -> researching", body.session_id)

    return result


def _parse_fields_from_history(history: list, current_message: str) -> dict:
    """
    Intelligently extract business fields from the entire conversation so far.
    Scans ALL user messages (not just the latest) so multi-field answers work.
    """
    import re

    collected: dict = {}
    all_user_text = " ".join(
        m.get("content", m.get("text", ""))
        for m in history
        if m.get("role") == "user"
    )
    all_user_text += " " + current_message
    all_lower = all_user_text.lower()

    # ── Name: extract business name from patterns across all messages
    import re as _re
    name_patterns = [
        r"(?:we are|we're|i run|i own|my (?:company|business|firm|startup|organisation|organization) is|called|named)\s+([A-Z][A-Za-z\s&.'-]+?)(?:\s*[,.]|\s+(?:a|an|in|based|from|is|which|we|with|and|\d))",
        r"^([A-Z][A-Za-z\s&.'-]{2,}?)(?:\s*[,.]|\s+(?:is|a|an|in|based|from|we|which|pvt|private|llp))",
    ]
    for pat in name_patterns:
        for msg_text in ([current_message] + [m.get("content", m.get("text", "")) for m in history if m.get("role") == "user"]):
            match = _re.search(pat, msg_text)
            if match:
                name_candidate = match.group(1).strip().rstrip(".,")
                # Filter out generic words that aren't business names
                skip = {"we", "i", "my", "the", "a", "an", "hello", "hi", "hey", "yes", "ok"}
                if name_candidate.lower() not in skip and len(name_candidate) > 2:
                    collected["name"] = name_candidate
                    break
        if "name" in collected:
            break

    # Fallback: use first non-greeting user message as name
    if "name" not in collected:
        user_msgs = [m.get("content", m.get("text", "")) for m in history if m.get("role") == "user"]
        greetings = {"hi", "hello", "hey", "start", "begin", "yes", "ok", "sure", "ready"}
        for msg in user_msgs:
            cleaned = msg.strip()
            if cleaned.lower() not in greetings and len(cleaned) > 2 and len(cleaned.split()) <= 6:
                collected["name"] = cleaned
                break

    # ── Full name and business name from "Name, Business" pattern
    if "full_name" not in collected or "name" not in collected:
        for msg_text in [current_message] + [m.get("content", m.get("text", "")) for m in history if m.get("role") == "user"]:
            if "," in msg_text:
                parts = [p.strip() for p in msg_text.split(",") if p.strip()]
                if len(parts) >= 2:
                    collected.setdefault("full_name", parts[0])
                    collected.setdefault("name", parts[1])
                    break

    # Explicit full name and business name patterns
    if "full_name" not in collected:
        match = _re.search(r"(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z\s.'-]{2,})", current_message, _re.IGNORECASE)
        if match:
            collected["full_name"] = match.group(1).strip().rstrip(".,")

    if "name" not in collected:
        match = _re.search(r"(?:business|company|startup|organisation|organization)\s+name\s+(?:is|:)?\s*([A-Za-z0-9][A-Za-z0-9\s&.'-]{2,})", current_message, _re.IGNORECASE)
        if match:
            collected["name"] = match.group(1).strip().rstrip(".,")

    # ── Entity type
    type_map = {
        "startup": "startup", "msme": "msme", "proprietorship": "proprietorship",
        "sole proprietor": "proprietorship", "partnership": "partnership",
        "pvt ltd": "private_limited", "pvt. ltd": "private_limited",
        "private limited": "private_limited", "public limited": "public_limited",
        "llp": "llp", "limited liability": "llp", "ngo": "ngo",
        "cooperative": "cooperative", "society": "cooperative",
    }
    for keyword, etype in type_map.items():
        if keyword in all_lower:
            collected["type"] = etype
            break

    # ── Sector
    sector_map = {
        "food processing": "food_processing", "food": "food_processing",
        "pickle": "food_processing", "spice": "food_processing", "dairy": "food_processing",
        "agriculture": "agriculture", "farming": "agriculture", "agri": "agriculture",
        "organic farming": "agriculture", "crop": "agriculture",
        "it": "it_tech", "tech": "it_tech", "software": "it_tech", "saas": "it_tech",
        "app development": "it_tech", "ai": "it_tech", "fintech": "fintech",
        "healthcare": "healthcare", "hospital": "healthcare", "pharma": "healthcare",
        "medical": "healthcare", "biotech": "healthcare",
        "manufacturing": "manufacturing", "factory": "manufacturing",
        "textile": "textile", "garment": "textile", "fashion": "textile",
        "handloom": "textile", "handicraft": "manufacturing",
        "renewable": "renewable_energy", "solar": "renewable_energy",
        "wind energy": "renewable_energy", "ev": "renewable_energy",
        "education": "education", "edtech": "education", "school": "education",
        "retail": "retail", "ecommerce": "retail", "e-commerce": "retail",
        "logistics": "logistics", "transport": "logistics", "delivery": "logistics",
        "export": "export", "import": "export",
        "construction": "construction", "real estate": "construction",
        "tourism": "tourism", "hotel": "tourism", "hospitality": "tourism",
    }
    for keyword, sector in sector_map.items():
        if keyword in all_lower:
            collected["sector"] = sector
            break

    # ── State & city
    for state in _INDIAN_STATES:
        if state in all_lower:
            collected["state"] = state.title()
            break

    # Common city detection
    cities = {
        "mumbai": "Maharashtra", "pune": "Maharashtra", "nagpur": "Maharashtra",
        "bangalore": "Karnataka", "bengaluru": "Karnataka", "mysore": "Karnataka",
        "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu",
        "hyderabad": "Telangana", "delhi": "Delhi", "new delhi": "Delhi",
        "noida": "Uttar Pradesh", "gurgaon": "Haryana", "gurugram": "Haryana",
        "ahmedabad": "Gujarat", "surat": "Gujarat", "jaipur": "Rajasthan",
        "lucknow": "Uttar Pradesh", "kolkata": "West Bengal",
        "kochi": "Kerala", "thiruvananthapuram": "Kerala",
        "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh",
        "chandigarh": "Chandigarh", "patna": "Bihar",
    }
    for city, state in cities.items():
        if city in all_lower:
            collected["city"] = city.title()
            if "state" not in collected:
                collected["state"] = state
            break

    # ── Team size (look for numbers near team/employee/people keywords)
    team_patterns = [
        r"(\d+)\s*(?:employees?|people|members?|team\s*(?:size)?|persons?|staff|workers?)",
        r"(?:team|employees?|people|staff)\s*(?:of|:)?\s*(\d+)",
        r"(?:we\s*(?:are|have))\s*(\d+)",
    ]
    for pat in team_patterns:
        match = re.search(pat, all_lower)
        if match:
            collected["team_size"] = int(match.group(1))
            break

    # ── Revenue
    revenue_patterns = [
        r"(?:₹|rs\.?|inr)\s*([\d,]+)\s*(?:lakh|lac|l)\w*",
        r"([\d,]+)\s*(?:lakh|lac|l)\w*",
        r"(?:₹|rs\.?|inr)\s*([\d,]+)\s*(?:crore|cr)\w*",
        r"([\d,]+)\s*(?:crore|cr)\w*",
        r"(?:revenue|turnover|annual)\s*(?:is|of|:)?\s*(?:₹|rs\.?|inr)?\s*([\d,]+)",
    ]
    for pat in revenue_patterns:
        match = re.search(pat, all_lower)
        if match:
            num_str = match.group(1).replace(",", "")
            try:
                val = int(num_str)
                if "crore" in all_lower or "cr" in all_lower:
                    val *= 10_000_000
                elif "lakh" in all_lower or "lac" in all_lower:
                    val *= 100_000
                elif val < 1000:
                    # Likely in lakhs if small number mentioned with revenue
                    val *= 100_000
                collected["revenue_inr"] = val
            except ValueError:
                pass
            break

    # ── Funding purpose
    purpose_map = {
        "technology upgrade": "technology_upgrade", "tech upgrade": "technology_upgrade",
        "machinery": "technology_upgrade", "equipment": "technology_upgrade",
        "working capital": "working_capital", "cash flow": "working_capital",
        "expansion": "expansion", "scale up": "expansion", "grow": "expansion",
        "new unit": "expansion", "new branch": "expansion",
        "r&d": "r_and_d", "research": "r_and_d", "innovation": "r_and_d",
        "export": "export_promotion", "international": "export_promotion",
        "marketing": "marketing", "branding": "marketing",
        "hiring": "hiring", "recruit": "hiring", "talent": "hiring",
        "training": "skill_development", "skill": "skill_development",
        "capex": "capex", "capital expenditure": "capex",
    }
    for keyword, purpose in purpose_map.items():
        if keyword in all_lower:
            collected["funding_purpose"] = purpose
            break

    # ── Business stage
    stage_map = {
        "idea": "Idea / Pre-revenue",
        "pre-revenue": "Idea / Pre-revenue",
        "early stage": "Early stage (under 1 year)",
        "under 1 year": "Early stage (under 1 year)",
        "growth stage": "Growth stage (1-3 years)",
        "1-3 years": "Growth stage (1-3 years)",
        "1–3 years": "Growth stage (1-3 years)",
        "established": "Established (3+ years)",
        "3+ years": "Established (3+ years)",
    }
    for keyword, stage in stage_map.items():
        if keyword in all_lower:
            collected["business_stage"] = stage
            break

    # ── Annual turnover (range label + numeric)
    turnover_map = [
        ("not yet generating revenue", "Not yet generating revenue", 0),
        ("pre-revenue", "Not yet generating revenue", 0),
        ("under 10 lakh", "Under ₹10 lakhs", 900000),
        ("under ₹10", "Under ₹10 lakhs", 900000),
        ("10-50", "₹10–₹50 lakhs", 3000000),
        ("10–50", "₹10–₹50 lakhs", 3000000),
        ("50 lakhs", "₹50 lakhs–₹1 crore", 7500000),
        ("1 crore", "Above ₹1 crore", 15000000),
        ("above 1 crore", "Above ₹1 crore", 15000000),
    ]
    if "annual_turnover" not in collected:
        for keyword, label, value in turnover_map:
            if keyword in all_lower:
                collected["annual_turnover"] = label
                collected.setdefault("revenue_inr", value)
                break

    # ── Employee count (range label + numeric)
    employee_map = [
        ("just myself", "Just myself (solo)", 1),
        ("solo", "Just myself (solo)", 1),
        ("2-10", "2–10", 6),
        ("2–10", "2–10", 6),
        ("11-50", "11–50", 30),
        ("11–50", "11–50", 30),
        ("51-200", "51–200", 125),
        ("51–200", "51–200", 125),
        ("200+", "200+", 250),
    ]
    if "employee_count" not in collected:
        for keyword, label, value in employee_map:
            if keyword in all_lower:
                collected["employee_count"] = label
                collected.setdefault("team_size", value)
                break

    # ── Funding type
    funding_type_map = {
        "grant": "Grant (non-repayable)",
        "subsidised loan": "Subsidised loan",
        "subsidized loan": "Subsidised loan",
        "equity": "Equity / Seed funding",
        "seed": "Equity / Seed funding",
        "tax benefits": "Tax benefits / exemptions",
        "exemptions": "Tax benefits / exemptions",
        "infrastructure": "Infrastructure support",
        "not sure": "Not sure — show me options",
    }
    if "funding_type" not in collected:
        for keyword, label in funding_type_map.items():
            if keyword in all_lower:
                collected["funding_type"] = label
                break

    # ── Registration type (also map to entity type)
    registration_map = {
        "sole proprietorship": ("Sole proprietorship", "proprietorship"),
        "proprietorship": ("Sole proprietorship", "proprietorship"),
        "partnership": ("Partnership / LLP", "partnership"),
        "llp": ("Partnership / LLP", "llp"),
        "private limited": ("Private Limited", "private_limited"),
        "pvt ltd": ("Private Limited", "private_limited"),
        "public limited": ("Public Limited", "public_limited"),
        "ngo": ("NGO / Trust / Society", "ngo"),
        "trust": ("NGO / Trust / Society", "ngo"),
        "society": ("NGO / Trust / Society", "ngo"),
        "not yet registered": ("Not yet registered", "other"),
    }
    if "registration_type" not in collected:
        for keyword, (label, entity) in registration_map.items():
            if keyword in all_lower:
                collected["registration_type"] = label
                collected.setdefault("type", entity)
                break

    # ── Certifications
    certification_map = {
        "udyam": "Udyam / MSME registration",
        "msme": "Udyam / MSME registration",
        "dpiit": "DPIIT Startup recognition",
        "startup india": "DPIIT Startup recognition",
        "iso": "ISO certification",
        "fssai": "FSSAI / BIS / other regulatory",
        "bis": "FSSAI / BIS / other regulatory",
        "none": "None of the above",
    }
    if "certifications" not in collected:
        for keyword, label in certification_map.items():
            if keyword in all_lower:
                collected["certifications"] = label
                break

    return collected


def _fallback_intake(history: List[dict], current_message: str, session_id: str) -> dict:
    """
    Smart conversational fallback when Gemini API is unavailable.
    Parses ALL user messages to extract fields, acknowledges what was understood,
    and asks natural follow-up questions for missing fields.
    """
    import re
    import random

    user_messages = [m for m in history if m.get("role") == "user"]
    step = len(user_messages) + (1 if current_message.strip() else 0)

    # Parse everything the user has said so far
    collected = _parse_fields_from_history(history, current_message)

    # Required fields (no defaults allowed)
    required_fields = [
        "full_name",
        "name",
        "state",
        "sector",
        "business_stage",
        "annual_turnover",
        "employee_count",
        "funding_type",
        "funding_purpose",
        "registration_type",
        "certifications",
        "team_size",
        "revenue_inr",
        "type",
    ]

    has_all_required = all(f in collected for f in required_fields)

    # Progress count (6 steps for UI)
    step_keys = [
        ["full_name", "name"],
        ["state"],
        ["sector"],
        ["business_stage", "annual_turnover"],
        ["employee_count", "funding_type"],
        ["funding_purpose", "registration_type", "certifications"],
    ]
    fields_done = 0
    for keys in step_keys:
        if all(k in collected for k in keys):
            fields_done += 1

    # Opening message if needed
    if not any(m.get("role") == "assistant" for m in history):
        opening_ar = {
            "step": 1,
            "message": (
                "Hello! Welcome. I'm your Government Funding Intake Assistant. I'm here to help you "
                "identify and apply for central and state government funding schemes that best fit your business.\n\n"
                "This will just take a few minutes. Could you please share your full name and the name of your business or organisation?"
            ),
            "input_type": "text",
            "options": [],
            "field": "name_and_org",
            "collected": {},
        }
        return {
            "reply": opening_ar["message"],
            "intake_complete": False,
            "fields_collected": 0,
            "total_fields": 10,
            "agent_response": opening_ar,
        }

    # Clarify Udyam/DPIIT if user seems confused
    msg_lower = current_message.lower()
    if "udyam" in msg_lower and "what" in msg_lower:
        ar = {"step": 10, "message": "Udyam is the government portal for MSME registration. Could you confirm if you have Udyam / MSME registration?", "input_type": "confirm", "options": ["Yes, I have Udyam", "No, I don't"], "field": "certifications", "collected": collected}
        return {
            "reply": ar["message"],
            "intake_complete": False,
            "fields_collected": min(fields_done, 10),
            "total_fields": 10,
            "agent_response": ar,
        }
    if "dpiit" in msg_lower and "what" in msg_lower:
        ar = {"step": 10, "message": "DPIIT recognition is for startups under the Startup India programme. Do you have DPIIT Startup recognition?", "input_type": "confirm", "options": ["Yes, I have DPIIT", "No, I don't"], "field": "certifications", "collected": collected}
        return {
            "reply": ar["message"],
            "intake_complete": False,
            "fields_collected": min(fields_done, 10),
            "total_fields": 10,
            "agent_response": ar,
        }

    # ── Check if we have enough to complete
    if has_all_required:
        collected.setdefault("city", "")
        collected["session_id"] = session_id

        summary_msg = (
            "Thanks! I've collected all the information I need. Here's a summary of your profile:\n\n"
            f"• **Name & Organisation:** {collected.get('full_name', '')} — {collected.get('name', '')}\n"
            f"• **State:** {collected.get('state', '')}\n"
            f"• **Sector:** {collected.get('sector', '')}\n"
            f"• **Business Stage:** {collected.get('business_stage', '')}\n"
            f"• **Annual Turnover:** {collected.get('annual_turnover', '')}\n"
            f"• **Employees:** {collected.get('employee_count', '')}\n"
            f"• **Funding Type:** {collected.get('funding_type', '')}\n"
            f"• **Purpose of Funding:** {collected.get('funding_purpose', '')}\n"
            f"• **Registration Type:** {collected.get('registration_type', '')}\n"
            f"• **Certifications:** {collected.get('certifications', '')}\n\n"
            "Shall I proceed with identifying the government funding schemes you may be eligible for?"
        )
        summary_ar = {
            "step": "summary",
            "message": summary_msg,
            "input_type": "confirm",
            "options": ["Yes, show me eligible schemes", "I want to edit my answers"],
            "field": "confirmation",
            "collected": {
                "name_and_org": f"{collected.get('full_name', '')}, {collected.get('name', '')}",
                "state": collected.get("state", ""),
                "sector": collected.get("sector", ""),
                "business_stage": collected.get("business_stage", ""),
                "annual_turnover": collected.get("annual_turnover", ""),
                "employee_count": collected.get("employee_count", ""),
                "funding_type": collected.get("funding_type", ""),
                "funding_purpose": collected.get("funding_purpose", ""),
                "legal_registration": collected.get("registration_type", ""),
                "certifications": collected.get("certifications", ""),
            },
        }
        return {
            "reply": summary_msg,
            "intake_complete": True,
            "fields_collected": 10,
            "total_fields": 10,
            "profile": collected,
            "agent_response": summary_ar,
        }

    # Determine next missing step in order
    steps = [
        {
            "keys": ["full_name", "name"],
            "step_num": 1,
            "field": "name_and_org",
            "question": "Could you please share your full name and the name of your business or organisation?",
            "input_type": "text",
            "options": [],
        },
        {
            "keys": ["state"],
            "step_num": 2,
            "field": "state",
            "question": "Which state is your business primarily operating from? This helps us identify both central and state-level schemes applicable to you.",
            "input_type": "options",
            "options": ["Karnataka", "Maharashtra", "Tamil Nadu", "Delhi", "Telangana", "Gujarat", "Punjab", "Rajasthan", "Uttar Pradesh", "Kerala", "Other"],
        },
        {
            "keys": ["sector"],
            "step_num": 3,
            "field": "sector",
            "question": "What is the primary sector of your business?",
            "input_type": "options",
            "options": ["Agritech / Agriculture", "Manufacturing", "IT / Software", "Healthcare", "Clean Energy", "Retail / Commerce", "Education / Edtech", "Other"],
        },
        {
            "keys": ["business_stage"],
            "step_num": 4,
            "field": "business_stage",
            "question": "What is the current stage of your business?",
            "input_type": "options",
            "options": ["Idea / Pre-revenue", "Early stage (< 1 year)", "Growth stage (1–3 years)", "Established (3+ years)"],
        },
        {
            "keys": ["annual_turnover"],
            "step_num": 5,
            "field": "annual_turnover",
            "question": "What is your approximate annual turnover? This matters for schemes like PMEGP and MSME subsidies.",
            "input_type": "options",
            "options": ["Not yet generating revenue", "Under ₹10 lakhs", "₹10–₹50 lakhs", "₹50 lakhs–₹1 crore", "Above ₹1 crore"],
        },
        {
            "keys": ["employee_count"],
            "step_num": 6,
            "field": "employee_count",
            "question": "How many employees does your organisation currently have?",
            "input_type": "options",
            "options": ["Just myself (solo)", "2\u201310", "11\u201350", "51\u2013200", "200+"],
        },
        {
            "keys": ["funding_type"],
            "step_num": 7,
            "field": "funding_type",
            "question": "What type of funding are you looking for?",
            "input_type": "options",
            "options": ["Grant (non-repayable)", "Subsidised loan", "Equity / Seed funding", "Tax benefits / exemptions", "Infrastructure support", "Not sure \u2014 show me options"],
        },
        {
            "keys": ["funding_purpose"],
            "step_num": 8,
            "field": "funding_purpose",
            "question": "What is the primary purpose of the funding you're seeking?",
            "input_type": "options",
            "options": ["Research & development", "Equipment / machinery", "Working capital", "Export promotion", "Hiring & training", "Digital transformation", "Other"],
        },
        {
            "keys": ["registration_type"],
            "step_num": 9,
            "field": "legal_registration",
            "question": "Are you a registered entity? If so, what type?",
            "input_type": "options",
            "options": ["Sole proprietorship", "Partnership / LLP", "Private Limited", "Public Limited", "NGO / Trust / Society", "Not yet registered"],
        },
        {
            "keys": ["certifications"],
            "step_num": 10,
            "field": "certifications",
            "question": "Do you hold any existing certifications relevant to funding? (Udyam = MSME registration; DPIIT = Startup India recognition)",
            "input_type": "options",
            "options": ["Udyam / MSME registration", "DPIIT Startup recognition", "ISO certification", "FSSAI / BIS / other regulatory", "None of the above"],
        },
    ]

    next_step_def = None
    for step_def in steps:
        if not all(k in collected for k in step_def["keys"]):
            next_step_def = step_def
            break

    ack_choices = ["Got it!", "Thanks for sharing that.", "Perfect.", "Great."]
    ack = random.choice(ack_choices) if current_message.strip() else ""

    if next_step_def:
        reply = f"{ack} {next_step_def['question']}".strip()
        ar = {
            "step": next_step_def["step_num"],
            "message": reply,
            "input_type": next_step_def["input_type"],
            "options": next_step_def["options"],
            "field": next_step_def["field"],
            "collected": collected,
        }
    else:
        reply = ack
        ar = {
            "step": fields_done,
            "message": reply,
            "input_type": "text",
            "options": [],
            "field": "",
            "collected": collected,
        }

    return {
        "reply": reply,
        "intake_complete": False,
        "fields_collected": min(fields_done, 10),
        "total_fields": 10,
        "agent_response": ar,
    }


@router.post("/pipeline")
async def run_pipeline(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    SSE streaming endpoint — runs the 4-stage pipeline.
    Stage 1 (intake): reads real profile from DB (persisted by /chat).
    Stage 2 (research): runs real ResearchAgent (Gemini search).
    Stages 3-4: still mock (to be wired later).
    """
    logger.info(
        "🚀 [%s] ═══ PIPELINE START ═══",
        body.session_id,
    )
    chat_session = _verify_session_ownership(body.session_id, user, db)

    async def sse_stream():
        # Clear existing data for stages 2-4 (profile is kept from /chat)
        logger.info("[%s] Clearing previous pipeline data for re-run", body.session_id)
        db.query(RawScheme).filter(RawScheme.session_id == body.session_id).delete()
        db.query(RankedScheme).filter(RankedScheme.session_id == body.session_id).delete()
        db.query(GrantReport).filter(GrantReport.session_id == body.session_id).delete()
        db.commit()

        # ── Stage 1: Intake done ──────────────────────────────────────
        # Profile was already persisted by /chat endpoint.
        # Read it from DB to confirm and emit SSE event.
        logger.info(
            "📋 [%s] Stage 1: Reading profile from user_profiles table",
            body.session_id,
        )
        profile_data = read_profile_from_db(body.session_id, db)

        if not profile_data:
            # Fallback: if no profile in DB, use mock
            logger.warning(
                "⚠️ [%s] No profile in DB — using MOCK_PROFILE fallback",
                body.session_id,
            )
            profile_data = {**MOCK_PROFILE, "session_id": body.session_id}
            db.add(UserProfile(session_id=body.session_id, **MOCK_PROFILE))
            db.commit()

        chat_session.status = "researching"
        db.add(chat_session)
        db.commit()

        logger.info(
            "✅ [%s] Stage 1 DONE — intake_done fired. Profile: name=%s, sector=%s",
            body.session_id,
            profile_data.get("name"),
            profile_data.get("sector"),
        )
        yield f"event: intake_done\ndata: {json.dumps(profile_data)}\n\n"

        # ── Stage 2: Research (REAL Agent 2) ───────────────────────────
        logger.info(
            "🔬 [%s] Stage 2: Starting ResearchAgent with profile JSON",
            body.session_id,
        )
        try:
            research_schemes = await run_research(
                session_id=body.session_id,
                profile_data=profile_data,
                db=db,
            )
            logger.info(
                "✅ [%s] Stage 2 DONE — research_done fired. %d schemes found",
                body.session_id, len(research_schemes),
            )

            # Format schemes for SSE payload
            sse_schemes = []
            for s in research_schemes:
                sse_schemes.append({
                    "scheme_name": s.get("name", s.get("scheme_name", "")),
                    "source_url": s.get("portal_url", s.get("source_url", "")),
                    "source_type": s.get("source", s.get("source_type", "web_search")),
                    "criteria_text": s.get("description", s.get("criteria_text", "")),
                    "deadline": s.get("deadline"),
                    "max_revenue_inr": s.get("max_revenue_inr"),
                    "eligible_types": json.dumps(
                        s.get("eligible_entity_types", s.get("eligible_types", []))
                    ),
                })

        except Exception as e:
            logger.error(
                "❌ [%s] Stage 2 FAILED: %s — falling back to mock schemes",
                body.session_id, str(e), exc_info=True,
            )
            # Fallback to mock schemes
            sse_schemes = MOCK_SCHEMES
            for s in MOCK_SCHEMES:
                scheme_data = s.copy()
                if scheme_data.get("deadline"):
                    scheme_data["deadline"] = date.fromisoformat(scheme_data["deadline"])
                db.add(RawScheme(session_id=body.session_id, **scheme_data))
            db.commit()

        yield f"event: research_done\ndata: {json.dumps(sse_schemes)}\n\n"

        # ── Stage 3: Validation (REAL Agent 3) ───────────────────────
        logger.info("[%s] Stage 3: Starting ValidatorAgent", body.session_id)
        try:
            ranked_schemes = await run_validation(
                session_id=body.session_id,
                profile_data=profile_data,
                db=db,
            )
            logger.info("[%s] Stage 3 DONE — %d schemes ranked", body.session_id, len(ranked_schemes))
        except Exception as e:
            logger.error("[%s] Stage 3 FAILED: %s — falling back to mock", body.session_id, str(e))
            ranked_schemes = []
            for r in MOCK_RANKED:
                db.add(RankedScheme(session_id=body.session_id, **r))
            db.commit()
            ranked_schemes = MOCK_RANKED

        chat_session.status = "validating"
        db.add(chat_session)
        db.commit()
        yield f"event: validation_done\ndata: {json.dumps(ranked_schemes)}\n\n"

        # ── Stage 4: Report (REAL Agent 4) ───────────────────────────
        logger.info("[%s] Stage 4: Starting PlannerAgent", body.session_id)
        try:
            report = await run_planner(
                session_id=body.session_id,
                profile_data=profile_data,
                db=db,
            )
            logger.info("[%s] Stage 4 DONE — report generated", body.session_id)
        except Exception as e:
            logger.error("[%s] Stage 4 FAILED: %s — falling back to mock", body.session_id, str(e))
            report = MOCK_REPORT
            db.add(GrantReport(
                session_id=body.session_id,
                documents_json=json.dumps(MOCK_REPORT["documents"]),
                action_cards_json=json.dumps(MOCK_REPORT["action_cards"]),
                cover_summary=MOCK_REPORT["cover_summary"],
            ))
            db.commit()

        chat_session.status = "done"
        db.add(chat_session)
        db.commit()
        logger.info("[%s] === PIPELINE COMPLETE ===", body.session_id)
        yield f"event: report_ready\ndata: {json.dumps(report)}\n\n"

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

    documents_raw = json.loads(report.documents_json)
    documents_by_scheme = []
    documents = []

    if (
        isinstance(documents_raw, list)
        and documents_raw
        and isinstance(documents_raw[0], dict)
        and "scheme_name" in documents_raw[0]
    ):
        documents_by_scheme = documents_raw
        documents = _merge_documents_by_scheme(documents_by_scheme)
    elif isinstance(documents_raw, list):
        documents = documents_raw

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
        "documents": documents,
        "documents_by_scheme": documents_by_scheme,
        "action_cards": json.loads(report.action_cards_json),
        "cover_summary": report.cover_summary,
        "created_at": report.created_at.isoformat(),
    }


def _merge_documents_by_scheme(documents_by_scheme: List[dict]) -> List[dict]:
    """Merge per-scheme documents into a single deduped list."""
    merged: dict[str, dict] = {}
    for entry in documents_by_scheme:
        if not isinstance(entry, dict):
            continue
        for doc in entry.get("documents", []):
            if not isinstance(doc, dict):
                continue
            name = (doc.get("name") or "").strip()
            if not name:
                continue
            key = " ".join(name.lower().split())
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "mandatory": bool(doc.get("mandatory", False)),
                    "description": (doc.get("description") or "").strip(),
                }
            else:
                existing = merged[key]
                if doc.get("mandatory"):
                    existing["mandatory"] = True
                if len(doc.get("description", "")) > len(existing.get("description", "")):
                    existing["description"] = doc.get("description", "")

    return list(merged.values())


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
