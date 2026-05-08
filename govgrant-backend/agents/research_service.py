"""
ResearchService - Real Gemini-powered scheme research (Agent 2).

Data flow:
1. Reads UserProfile from DB by session_id
2. Calls Gemini to find 15-25 real government schemes
3. Parses response into scheme objects
4. Writes to raw_schemes table
5. Returns schemes for SSE emission
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

import google.genai as genai
from sqlmodel import Session, select

from config import settings
from db.models import RawScheme, UserProfile as DBUserProfile

logger = logging.getLogger("govgrant.research")


async def run_research(
    session_id: str,
    profile_data: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Run Agent 2: call Gemini to find government schemes, persist to DB.

    Returns list of scheme dicts written to raw_schemes table.
    """
    logger.info("[%s] === RESEARCH START ===", session_id)
    logger.info(
        "[%s] Profile: sector=%s, state=%s, entity=%s, revenue=%s",
        session_id,
        profile_data.get("sector"),
        profile_data.get("state"),
        profile_data.get("entity_type", profile_data.get("type")),
        profile_data.get("annual_revenue_inr", profile_data.get("revenue_inr")),
    )

    # Call Gemini for real scheme research
    schemes = await _gemini_search(session_id, profile_data)

    if not schemes:
        logger.warning("[%s] Gemini returned 0 schemes - using fallback", session_id)
        schemes = _fallback_schemes(profile_data)

    # Persist to raw_schemes table
    logger.info("[%s] Writing %d schemes to raw_schemes", session_id, len(schemes))

    # Clear existing (idempotent re-runs)
    existing = db.exec(
        select(RawScheme).where(RawScheme.session_id == session_id)
    ).all()
    for row in existing:
        db.delete(row)
    if existing:
        db.commit()

    for i, s in enumerate(schemes):
        try:
            deadline_val = None
            if s.get("deadline"):
                try:
                    deadline_val = date.fromisoformat(str(s["deadline"]))
                except (ValueError, TypeError):
                    pass

            db.add(RawScheme(
                session_id=session_id,
                scheme_name=s.get("name", s.get("scheme_name", f"Scheme {i+1}")),
                source_url=s.get("portal_url", s.get("source_url", "")),
                source_type=s.get("source", "web_search"),
                criteria_text=s.get("description", s.get("criteria_text", "")),
                deadline=deadline_val,
                max_revenue_inr=s.get("max_revenue_inr"),
                eligible_types=json.dumps(
                    s.get("eligible_entity_types", s.get("eligible_types", []))
                ),
            ))
            logger.info("  [%s] Scheme %d: %s", session_id, i+1,
                        s.get("name", s.get("scheme_name", "?")))
        except Exception as e:
            logger.error("[%s] Failed to persist scheme %d: %s", session_id, i+1, str(e))

    db.commit()
    logger.info("[%s] === RESEARCH DONE - %d schemes persisted ===", session_id, len(schemes))
    return schemes


async def _gemini_search(
    session_id: str,
    profile_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Call Gemini to find real government schemes."""
    sector = profile_data.get("sector", "general")
    state = profile_data.get("state", "India")
    entity = profile_data.get("entity_type", profile_data.get("type", "msme"))
    revenue = profile_data.get("annual_revenue_inr", profile_data.get("revenue_inr", 0))
    purpose = profile_data.get("purpose", profile_data.get("funding_purpose", "general"))

    prompt = f"""Find 15-20 REAL Indian government grant schemes and subsidies for this business:
- Sector: {sector}
- State: {state}
- Entity type: {entity}
- Annual revenue: INR {revenue}
- Funding purpose: {purpose}

Return ONLY a valid JSON array. Each object must have these exact keys:
- "name": string (official scheme name)
- "portal_url": string (official website URL)
- "description": string (1-line eligibility summary)
- "eligible_entity_types": string[] (e.g. ["startup", "msme"])
- "eligible_states": string[] (empty = pan-India)
- "max_revenue_inr": number or null
- "deadline": string (ISO date) or null
- "source": "web_search"

IMPORTANT:
- Only include REAL schemes with actual portal URLs
- Include both central (pan-India) and {state} state schemes
- Include MSME schemes, startup schemes, and sector-specific schemes
- No markdown, no explanation - just the JSON array"""

    logger.info("[%s] Calling Gemini for scheme search...", session_id)

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=8192,
            ),
        )
        text = response.text or ""
        schemes = _parse_json_array(text, session_id)
        logger.info("[%s] Gemini returned %d schemes", session_id, len(schemes))
        return schemes
    except Exception as e:
        logger.error("[%s] Gemini search failed: %s", session_id, str(e))
        return []


def _parse_json_array(text: str, session_id: str) -> List[Dict]:
    """Extract JSON array from LLM text output."""
    # Try markdown code block first
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.error("[%s] Could not parse JSON from Gemini output", session_id)
    return []


def read_profile_from_db(session_id: str, db: Session) -> Optional[Dict[str, Any]]:
    """Read UserProfile from DB for a given session_id."""
    logger.info("[%s] Reading profile from DB", session_id)
    profile = db.exec(
        select(DBUserProfile).where(DBUserProfile.session_id == session_id)
    ).first()

    if not profile:
        logger.warning("[%s] No profile found in DB", session_id)
        return None

    result = {
        "session_id": profile.session_id,
        "name": profile.name,
        "type": profile.type,
        "sector": profile.sector,
        "state": profile.state,
        "city": profile.city,
        "team_size": profile.team_size,
        "revenue_inr": profile.revenue_inr,
        "funding_purpose": profile.funding_purpose,
    }
    logger.info("[%s] Profile loaded: %s (%s, %s)", session_id,
                result["name"], result["sector"], result["state"])
    return result


def _fallback_schemes(profile_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Curated fallback when Gemini fails."""
    return [
        {
            "name": "CGTMSE Credit Guarantee",
            "portal_url": "https://www.cgtmse.in/",
            "description": "Collateral-free credit up to Rs 5 Cr for MSMEs",
            "eligible_entity_types": ["msme", "proprietorship", "private_limited"],
            "eligible_states": [],
            "max_revenue_inr": 100000000,
            "deadline": None,
            "source": "curated",
        },
        {
            "name": "MUDRA Loan Scheme",
            "portal_url": "https://www.mudra.org.in/",
            "description": "Micro-credit loans from Rs 50K to Rs 10L",
            "eligible_entity_types": ["startup", "msme", "proprietorship"],
            "eligible_states": [],
            "max_revenue_inr": 15000000,
            "deadline": None,
            "source": "curated",
        },
        {
            "name": "Stand Up India",
            "portal_url": "https://www.standupmitra.in/",
            "description": "Loans Rs 10L-1Cr for SC/ST and women entrepreneurs",
            "eligible_entity_types": ["startup", "msme", "private_limited"],
            "eligible_states": [],
            "max_revenue_inr": None,
            "deadline": None,
            "source": "curated",
        },
        {
            "name": "PMEGP",
            "portal_url": "https://www.kviconline.gov.in/pmegpeportal/",
            "description": "35% subsidy for manufacturing projects",
            "eligible_entity_types": ["startup", "msme", "proprietorship"],
            "eligible_states": [],
            "max_revenue_inr": 25000000,
            "deadline": None,
            "source": "curated",
        },
        {
            "name": "Startup India Seed Fund",
            "portal_url": "https://seedfund.startupindia.gov.in/",
            "description": "Up to Rs 50L for proof of concept and prototype",
            "eligible_entity_types": ["startup", "private_limited"],
            "eligible_states": [],
            "max_revenue_inr": 50000000,
            "deadline": None,
            "source": "curated",
        },
    ]
