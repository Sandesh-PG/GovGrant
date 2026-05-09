"""
ValidatorService — Real Gemini-powered scheme validation & ranking (Agent 3).

Data flow:
1. Reads UserProfile + RawSchemes from DB (written by Agent 1 & 2)
2. Hard-filters schemes by revenue/entity/state eligibility
3. Calls Gemini 2.0 Flash to score remaining schemes on 4 dimensions
4. Persists top 5 as RankedScheme rows in ranked_schemes table
5. Returns ranked list for SSE emission

This is the service layer that bridges the ADK agent with the pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict, List

import google.genai as genai
from sqlmodel import Session, select

from config import settings
from db.models import RankedScheme, RawScheme, UserProfile as DBUserProfile

logger = logging.getLogger("govgrant.validator")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT — called by pipeline in routes.py
# ═══════════════════════════════════════════════════════════════════════════════

async def run_validation(
    session_id: str,
    profile_data: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Run Agent 3: hard-filter + LLM-score schemes, persist top 5.

    Args:
        session_id: Current session UUID
        profile_data: User profile dict from Agent 1
        db: SQLModel session for DB reads/writes

    Returns:
        List of ranked scheme dicts (top 5) for SSE payload
    """
    logger.info("[%s] === VALIDATION START ===", session_id)

    # ── Step 1: Read raw schemes from DB (written by Agent 2) ──────────
    raw_rows = db.exec(
        select(RawScheme).where(RawScheme.session_id == session_id)
    ).all()

    if not raw_rows:
        logger.warning("[%s] No raw_schemes found in DB", session_id)
        return []

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

    # ── Step 2: Hard filter ────────────────────────────────────────────
    filtered = _hard_filter(raw_schemes, profile_data)
    logger.info("[%s] After hard filter: %d schemes remain", session_id, len(filtered))

    if not filtered:
        # Don't lose everything — keep top 5 unfiltered as fallback
        filtered = raw_schemes[:5]
        logger.warning("[%s] Hard filter removed ALL schemes, keeping top 5 unfiltered", session_id)

    # ── Step 3: LLM scoring via Gemini ─────────────────────────────────
    ranked = await _gemini_score(session_id, filtered, profile_data)

    if not ranked:
        logger.warning("[%s] Gemini scoring returned nothing, using fallback ranking", session_id)
        ranked = _fallback_rank(filtered)

    # Ensure unique scheme names and backfill to top-5 if needed
    ranked = _dedupe_and_fill(ranked, filtered, target_count=5)
    ranked = _reindex_ranks(ranked)

    # Fill generic reasons with scheme-specific details
    ranked = _enrich_ranked_reasons(ranked, filtered, raw_schemes, profile_data)

    # ── Step 4: Persist to ranked_schemes table ────────────────────────
    # Clear existing (idempotent re-runs)
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
    logger.info(
        "[%s] === VALIDATION DONE === %d ranked schemes persisted",
        session_id, len(ranked),
    )
    return ranked


# ═══════════════════════════════════════════════════════════════════════════════
# HARD FILTER — deterministic eligibility checks (no LLM needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _hard_filter(schemes: List[Dict], profile: Dict) -> List[Dict]:
    """
    Remove schemes where the user clearly doesn't qualify.

    Checks (in order):
    1. Revenue cap: user revenue <= scheme max_revenue_inr
    2. Entity type: user entity in scheme's eligible list
    3. State: user state matches (empty list = pan-India = all pass)
    """
    revenue = profile.get("revenue_inr", 0) or 0
    entity_type = (profile.get("type", "") or "").lower().strip()
    state = (profile.get("state", "") or "").lower().strip()

    passed = []
    for s in schemes:
        # 1. Revenue cap
        max_rev = s.get("max_revenue_inr")
        if max_rev and revenue > max_rev:
            continue

        # 2. Entity type
        eligible_raw = s.get("eligible_types", "[]")
        try:
            eligible = json.loads(eligible_raw) if isinstance(eligible_raw, str) else eligible_raw
        except (json.JSONDecodeError, TypeError):
            eligible = []
        if eligible:
            normalized = [e.lower().strip() for e in eligible if isinstance(e, str)]
            if entity_type and entity_type not in normalized:
                continue

        passed.append(s)

    return passed


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI LLM SCORING — 4-dimension scoring via Gemini 2.0 Flash
# ═══════════════════════════════════════════════════════════════════════════════

async def _gemini_score(
    session_id: str,
    schemes: List[Dict],
    profile: Dict,
) -> List[Dict]:
    """
    Call Gemini to score each scheme on 4 dimensions and rank top 5.

    Dimensions:
    - Eligibility (0-40): Hard criteria match
    - Relevance (0-30): Sector/purpose alignment
    - Benefit (0-20): Grant value vs business needs
    - Ease (0-10): Application simplicity
    """
    prompt = f"""You are a grant eligibility expert for Indian businesses.
Score and rank these government schemes for this business profile.

BUSINESS PROFILE:
- Name: {profile.get('name', 'Unknown')}
- Type: {profile.get('type', 'Unknown')}
- Sector: {profile.get('sector', 'Unknown')}
- State: {profile.get('state', 'Unknown')}, City: {profile.get('city', '')}
- Team: {profile.get('team_size', 0)} employees
- Revenue: INR {profile.get('revenue_inr', 0):,}
- Funding Purpose: {profile.get('funding_purpose', 'general')}

SCHEMES TO EVALUATE:
{json.dumps(schemes, indent=2)}

SCORING RUBRIC (0-100 composite):
- Eligibility (0-40): Does the business meet ALL hard criteria?
- Relevance (0-30): How well does sector/purpose match the scheme goals?
- Benefit (0-20): How valuable is the grant amount relative to business size?
- Ease (0-10): How simple is the application process?

INSTRUCTIONS:
1. Score each scheme on all 4 dimensions
2. Compute composite = eligibility + relevance + benefit + ease
3. Select TOP 5 by composite score
4. Assign rank 1 (highest score) through 5
5. Calculate urgency_score (0.0-1.0): 1.0 if deadline within 14 days, 0.8 if within 30 days, 0.5 if within 60 days, 0.3 otherwise

Return ONLY a valid JSON array. No markdown fences, no explanation. Each object:
{{"scheme_name":"string","match_score":85,"rank":1,"reason":"1-2 sentence rationale","urgency_score":0.8,"composite_rank":1,"portal_url":"https://...","deadline":"2026-09-30","grant_amount":"Up to Rs 50 lakhs"}}"""

    logger.info("[%s] Calling Gemini for scheme scoring (%d schemes)...", session_id, len(schemes))

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

        # Validate and cap scores
        for r in ranked:
            r["match_score"] = max(0, min(100, r.get("match_score", 50)))
            r["urgency_score"] = max(0.0, min(1.0, r.get("urgency_score", 0.5)))
            r["composite_rank"] = r.get("composite_rank", r.get("rank", 1))

        logger.info("[%s] Gemini scored %d schemes successfully", session_id, len(ranked))
        return ranked[:5]  # Enforce top-5 limit

    except Exception as e:
        logger.error("[%s] Gemini scoring failed: %s", session_id, str(e))
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_json_array(text: str) -> List[Dict]:
    """Extract JSON array from LLM response, handling markdown fences."""
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
    return []


def _normalize_scheme_name(name: str) -> str:
    name = (name or "").strip().lower()
    return re.sub(r"\s+", " ", name)


def _is_generic_reason(reason: str) -> bool:
    if not reason:
        return True
    text = reason.strip().lower()
    if len(text) < 20:
        return True
    if "matches business profile" in text:
        return True
    return False


def _build_reason(scheme: Dict[str, Any], profile: Dict[str, Any]) -> str:
    """Create a concise, scheme-specific reason string."""
    parts = []

    entity_type = (profile.get("type") or profile.get("entity_type") or "").strip().lower()
    sector = (profile.get("sector") or "").replace("_", " ").strip()
    revenue = profile.get("revenue_inr") or 0

    eligible_raw = scheme.get("eligible_types", "[]")
    try:
        eligible_types = json.loads(eligible_raw) if isinstance(eligible_raw, str) else eligible_raw
    except (json.JSONDecodeError, TypeError):
        eligible_types = []

    eligible_types = [e.lower().strip() for e in eligible_types if isinstance(e, str)]

    if entity_type and (not eligible_types or entity_type in eligible_types):
        parts.append(f"Eligible for {entity_type.replace('_', ' ')} entities")

    if sector:
        parts.append(f"Sector match: {sector}")

    max_rev = scheme.get("max_revenue_inr")
    if max_rev:
        parts.append(f"Revenue cap up to Rs {int(max_rev):,}")
    elif revenue:
        parts.append(f"Revenue considered: Rs {int(revenue):,}")

    grant_amount = scheme.get("grant_amount")
    if grant_amount:
        parts.append(f"Grant: {grant_amount}")

    criteria = (scheme.get("criteria_text") or "").strip()
    if criteria:
        snippet = criteria.replace("\n", " ").strip()
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        parts.append(f"Criteria: {snippet}")

    if not parts:
        return "Eligible based on profile and scheme criteria."

    # Keep it to two short sentences
    first = "; ".join(parts[:3])
    second = parts[3] if len(parts) > 3 else ""
    if second:
        return f"{first}. {second}"
    return f"{first}."


def _enrich_ranked_reasons(
    ranked: List[Dict[str, Any]],
    filtered: List[Dict[str, Any]],
    raw_schemes: List[Dict[str, Any]],
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Replace generic reasons with scheme-specific context."""
    filtered_map = {
        _normalize_scheme_name(s.get("scheme_name")): s for s in filtered
    }
    raw_map = {
        _normalize_scheme_name(s.get("scheme_name")): s for s in raw_schemes
    }

    for r in ranked:
        reason = r.get("reason", "")
        if not _is_generic_reason(reason):
            continue
        name_key = _normalize_scheme_name(r.get("scheme_name"))
        scheme = filtered_map.get(name_key) or raw_map.get(name_key) or {}
        r["reason"] = _build_reason(scheme, profile)

    return ranked


def _normalize_scheme_name(name: str) -> str:
    """Normalize scheme names for deduplication."""
    name = (name or "").strip().lower()
    return re.sub(r"\s+", " ", name)


def _dedupe_and_fill(
    ranked: List[Dict],
    fallback_pool: List[Dict],
    target_count: int = 5,
) -> List[Dict]:
    """
    Remove duplicate scheme names and backfill with unique schemes
    from the fallback pool to reach target_count.
    """
    seen: set[str] = set()
    unique: List[Dict] = []

    for item in ranked:
        name = _normalize_scheme_name(item.get("scheme_name"))
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(item)

    if len(unique) >= target_count:
        return unique[:target_count]

    min_score = min((int(r.get("match_score", 50)) for r in unique), default=50)
    next_score = max(0, min_score - 5)

    for s in fallback_pool:
        if len(unique) >= target_count:
            break
        name = _normalize_scheme_name(s.get("scheme_name"))
        if not name or name in seen:
            continue
        unique.append({
            "scheme_name": s.get("scheme_name"),
            "match_score": int(next_score),
            "rank": 0,
            "reason": "Matches business profile based on sector and eligibility criteria.",
            "urgency_score": 0.5,
            "composite_rank": 0,
            "portal_url": s.get("source_url", ""),
            "deadline": s.get("deadline"),
            "grant_amount": "Check portal for details",
        })
        seen.add(name)
        next_score = max(0, next_score - 5)

    return unique


def _reindex_ranks(ranked: List[Dict]) -> List[Dict]:
    """Normalize rank fields and clamp scores for UI safety."""
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
        r["composite_rank"] = i + 1
        r["match_score"] = max(0, min(100, int(r.get("match_score", 50))))
        r["urgency_score"] = max(0.0, min(1.0, float(r.get("urgency_score", 0.5))))
        r.setdefault("reason", "Matches business profile based on sector and eligibility criteria.")
        r.setdefault("portal_url", "")
        r.setdefault("deadline", None)
        r.setdefault("grant_amount", "Check portal for details")
    return ranked


def _fallback_rank(schemes: List[Dict]) -> List[Dict]:
    """Simple deterministic ranking when Gemini is unavailable."""
    ranked = []
    for i, s in enumerate(schemes[:5]):
        ranked.append({
            "scheme_name": s["scheme_name"],
            "match_score": 80 - (i * 10),
            "rank": i + 1,
            "reason": "Matches business profile based on sector and eligibility criteria.",
            "urgency_score": 0.5,
            "composite_rank": i + 1,
            "portal_url": s.get("source_url", ""),
            "deadline": s.get("deadline"),
            "grant_amount": "Check portal for details",
        })
    return ranked
