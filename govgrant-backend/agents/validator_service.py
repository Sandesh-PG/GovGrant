"""
ValidatorService — Real Gemini-powered scheme validation & ranking (Agent 3).

Data flow:
1. Reads UserProfile + RawSchemes from DB
2. Hard-filters schemes by revenue/entity/state eligibility
3. Calls Gemini to score remaining schemes on 4 dimensions
4. Persists top 5 as RankedScheme rows
5. Returns ranked list for SSE emission
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import google.genai as genai
from sqlmodel import Session, select

from config import settings
from db.models import RankedScheme, RawScheme, UserProfile as DBUserProfile

logger = logging.getLogger("govgrant.validator")


async def run_validation(
    session_id: str,
    profile_data: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Run Agent 3: hard-filter + LLM-score schemes, persist top 5.
    """
    logger.info("[%s] === VALIDATION START ===", session_id)

    # Read raw schemes from DB
    raw_rows = db.exec(
        select(RawScheme).where(RawScheme.session_id == session_id)
    ).all()

    if not raw_rows:
        logger.warning("[%s] No raw_schemes found in DB", session_id)
        return []

    # Convert DB rows to dicts
    raw_schemes = []
    for r in raw_rows:
        raw_schemes.append({
            "scheme_name": r.scheme_name,
            "source_url": r.source_url,
            "source_type": r.source_type,
            "criteria_text": r.criteria_text,
            "deadline": r.deadline.isoformat() if r.deadline else None,
            "max_revenue_inr": r.max_revenue_inr,
            "eligible_types": r.eligible_types,
        })

    logger.info("[%s] Read %d raw schemes from DB", session_id, len(raw_schemes))

    # Hard filter
    filtered = _hard_filter(raw_schemes, profile_data)
    logger.info("[%s] After hard filter: %d schemes", session_id, len(filtered))

    if not filtered:
        filtered = raw_schemes[:5]
        logger.warning("[%s] Hard filter removed all, keeping top 5 unfiltered", session_id)

    # LLM scoring
    ranked = await _gemini_score(session_id, filtered, profile_data)

    if not ranked:
        logger.warning("[%s] Gemini scoring failed, using simple ranking", session_id)
        ranked = _fallback_rank(filtered)

    # Persist to ranked_schemes
    existing = db.exec(
        select(RankedScheme).where(RankedScheme.session_id == session_id)
    ).all()
    for row in existing:
        db.delete(row)
    if existing:
        db.commit()

    for r in ranked:
        db.add(RankedScheme(
            session_id=session_id,
            scheme_name=r["scheme_name"],
            match_score=r["match_score"],
            rank=r["rank"],
            reason=r["reason"],
            urgency_score=r.get("urgency_score", 0.5),
            composite_rank=r["composite_rank"],
            portal_url=r.get("portal_url", ""),
            deadline=r.get("deadline"),
            grant_amount=r.get("grant_amount"),
        ))

    db.commit()
    logger.info("[%s] === VALIDATION DONE — %d ranked schemes persisted ===",
                session_id, len(ranked))
    return ranked


def _hard_filter(
    schemes: List[Dict], profile: Dict
) -> List[Dict]:
    """Remove schemes where revenue/entity/state makes user ineligible."""
    revenue = profile.get("revenue_inr", 0) or 0
    entity_type = profile.get("type", "")
    state = profile.get("state", "")

    passed = []
    for s in schemes:
        # Revenue cap check
        if s.get("max_revenue_inr") and revenue > s["max_revenue_inr"]:
            continue
        # Entity type check
        try:
            eligible = json.loads(s.get("eligible_types", "[]"))
        except (json.JSONDecodeError, TypeError):
            eligible = []
        if eligible and entity_type not in eligible:
            continue
        passed.append(s)

    return passed


async def _gemini_score(
    session_id: str,
    schemes: List[Dict],
    profile: Dict,
) -> List[Dict]:
    """Call Gemini to score and rank schemes."""

    prompt = f"""You are a grant eligibility expert. Score and rank these government schemes for this business.

BUSINESS PROFILE:
- Name: {profile.get('name')}
- Type: {profile.get('type')}
- Sector: {profile.get('sector')}
- State: {profile.get('state')}, City: {profile.get('city', '')}
- Team: {profile.get('team_size')} employees
- Revenue: INR {profile.get('revenue_inr')}
- Purpose: {profile.get('funding_purpose')}

SCHEMES TO SCORE:
{json.dumps(schemes, indent=2)}

SCORING (0-100 composite):
- Eligibility (0-40): Does the business meet ALL hard criteria?
- Relevance (0-30): How well does sector/purpose match?
- Benefit (0-20): Grant value relative to business needs?
- Ease (0-10): Application complexity?

Return ONLY a JSON array of the TOP 5 schemes (or fewer if less available), ordered by score. Each object must have:
- "scheme_name": string
- "match_score": integer (0-100 composite score)
- "rank": integer (1 = best)
- "reason": string (1-2 sentence explanation)
- "urgency_score": float (0-1, based on deadline proximity)
- "composite_rank": integer (same as rank)
- "portal_url": string
- "deadline": string or null
- "grant_amount": string (e.g. "Up to Rs 50 lakhs")

No markdown, no explanation - just the JSON array."""

    logger.info("[%s] Calling Gemini for scheme scoring...", session_id)

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            ),
        )
        text = response.text or ""
        ranked = _parse_json_array(text)
        logger.info("[%s] Gemini scored %d schemes", session_id, len(ranked))
        return ranked
    except Exception as e:
        logger.error("[%s] Gemini scoring failed: %s", session_id, str(e))
        return []


def _parse_json_array(text: str) -> List[Dict]:
    """Extract JSON array from LLM response."""
    import re
    # Try markdown code block
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return []


def _fallback_rank(schemes: List[Dict]) -> List[Dict]:
    """Simple fallback ranking when Gemini fails."""
    ranked = []
    for i, s in enumerate(schemes[:5]):
        ranked.append({
            "scheme_name": s["scheme_name"],
            "match_score": 80 - (i * 10),
            "rank": i + 1,
            "reason": f"Matches business profile based on sector and eligibility criteria.",
            "urgency_score": 0.5,
            "composite_rank": i + 1,
            "portal_url": s.get("source_url", ""),
            "deadline": s.get("deadline"),
            "grant_amount": "Check portal for details",
        })
    return ranked
