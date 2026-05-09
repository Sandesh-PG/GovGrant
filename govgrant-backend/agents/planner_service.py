"""
PlannerService — Quota-efficient Gemini-powered report generation (Agent 4).

REFACTORED: Consolidates multiple extraction calls into ONE SINGLE Gemini call
to prevent 429 Resource Exhausted errors on the free tier.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import google.genai as genai
from sqlmodel import Session, select

from config import settings
from db.models import GrantReport, RankedScheme

logger = logging.getLogger("govgrant.planner")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def run_planner(
    session_id: str,
    profile_data: Dict[str, Any],
    db: Session,
) -> Dict[str, Any]:
    """
    Run Agent 4: generate full GrantReport using ONE Gemini call.
    """
    logger.info("[%s] === PLANNER START (QUOTA-EFFICIENT) ===", session_id)

    # ── Step 1: Read ranked schemes from DB ──────────────────────────
    ranked_rows = db.exec(
        select(RankedScheme).where(RankedScheme.session_id == session_id)
        .order_by(RankedScheme.composite_rank)
    ).all()

    if not ranked_rows:
        logger.warning("[%s] No ranked_schemes found -- using fallback", session_id)
        report = _fallback_report(profile_data)
        _persist_report(session_id, report, db)
        return report

    # Enrich schemes with context for the single prompt
    schemes_for_ai = [
        {
            "scheme_name": r.scheme_name,
            "match_score": r.match_score,
            "rank": r.rank,
            "reason": r.reason,
            "portal_url": r.portal_url or "",
            "deadline": r.deadline or "Check portal",
            "grant_amount": r.grant_amount or "Check portal",
            "context_from_research": r.reason, # Contains the scraped text snippets
            "scraped_documents": r.documents_json,
            "scraped_steps": r.steps_json,
        }
        for r in ranked_rows
    ]

    # ── Step 2: SINGLE Gemini Call for everything ────────────────────
    report = await _gemini_generate_full_report(session_id, profile_data, schemes_for_ai)

    if not report:
        logger.warning("[%s] Gemini planner failed -- using fallback", session_id)
        report = _fallback_report(profile_data)

    # ── Step 3: Persist and Return ────────────────────────────────────
    _persist_report(session_id, report, db)
    logger.info("[%s] === PLANNER DONE === report persisted", session_id)
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONSOLIDATED AI CALL
# ═══════════════════════════════════════════════════════════════════════════════

async def _gemini_generate_full_report(
    session_id: str,
    profile: Dict[str, Any],
    schemes: List[Dict],
) -> Optional[Dict]:
    """Generates the entire report in ONE call to save quota."""
    
    prompt = f"""You are GovGrant's high-precision report generator for Indian businesses.
Your goal is to create a tailored, research-driven grant report in ONE shot.

BUSINESS PROFILE:
- Name: {profile.get('name', 'Unknown')}
- Sector: {profile.get('sector', 'Unknown')}
- Revenue: INR {profile.get('revenue_inr', 0):,}
- Location: {profile.get('state', 'India')}

RANKED SCHEMES & RESEARCH CONTEXT:
{json.dumps(schemes, indent=2)}

TASK:
Return a JSON object with EXACTLY these 3 keys:

1. "documents_by_scheme": Array of objects (one per scheme).
   Each object: {{"scheme_name": "...", "documents": [ {{"name": "...", "mandatory": true, "description": "..."}} ]}}
   CRITICAL: Use the 'scraped_documents' field if it contains data. If empty, use 'context_from_research'. 
   If both are sparse, include standard MSME docs: PAN, Aadhaar, ITR, GST, MSME Cert, Bank Stmt.

2. "action_cards": Array of objects (one per scheme).
   Each object: {{"scheme_name": "...", "portal_url": "...", "steps": ["...", ...], "estimated_days": 45, "tips": ["...", ...]}}
   CRITICAL: Use the 'scraped_steps' field if it contains data. If empty, create 5-7 HIGHLY SPECIFIC application steps based on 'context_from_research'.

3. "cover_summary": A ~150-word formal narrative ("We/Our") introducing the business and highlighting why these grants are a match.

Return ONLY valid JSON. No markdown fences, no text outside JSON."""

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
        text = response.text or ""
        report = _parse_json_object(text)
        
        if report:
            # Add a global documents key for backward compatibility
            all_docs = []
            for item in report.get("documents_by_scheme", []):
                all_docs.extend(item.get("documents", []))
            report["documents"] = _dedupe_docs(all_docs)
            return report
            
        return None
    except Exception as e:
        logger.error("[%s] Gemini full report generation failed: %s", session_id, str(e))
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACKS & HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _fallback_report(profile: Dict[str, Any]) -> Dict[str, Any]:
    name = profile.get("name", "Your Business")
    sector = profile.get("sector", "general")
    state = profile.get("state", "India")
    
    docs = _static_documents(profile)
    
    return {
        "documents": docs,
        "documents_by_scheme": [
            {"scheme_name": "General Eligibility", "documents": docs},
        ],
        "action_cards": [
            {
                "scheme_name": "General Grant Application Roadmap",
                "portal_url": "https://www.india.gov.in/",
                "steps": [
                    "Step 1: Obtain MSME / Udyam Registration",
                    "Step 2: Prepare 3-year projected financial statements",
                    "Step 3: Register on the relevant department portal",
                    "Step 4: Upload KYC and business documents",
                    "Step 5: Submit application and track status",
                ],
                "estimated_days": 45,
                "tips": ["Keep all documents digitised", "Ensure GST returns are up to date"]
            }
        ],
        "cover_summary": f"We are {name}, a business in the {sector} sector based in {state}. We are seeking government support to scale our operations and contribute to the regional economy."
    }

def _static_documents(profile: Dict[str, Any]) -> List[Dict]:
    return [
        {"name": "Aadhaar/PAN of Promoters", "mandatory": True, "description": "KYC for all directors"},
        {"name": "Udyam Registration", "mandatory": True, "description": "MSME Certificate"},
        {"name": "GST Certificate", "mandatory": True, "description": "Registration for tax compliance"},
        {"name": "ITR & Audit Reports", "mandatory": True, "description": "Last 2-3 years financials"},
        {"name": "Business Plan", "mandatory": True, "description": "Detailed project report"},
    ]

def _dedupe_docs(docs: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for d in docs:
        name = d.get("name", "").lower().strip()
        if name not in seen:
            seen.add(name)
            unique.append(d)
    return unique

def _parse_json_object(text: str) -> Optional[Dict]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None

def _persist_report(session_id: str, report: Dict, db: Session) -> None:
    existing = db.exec(select(GrantReport).where(GrantReport.session_id == session_id)).first()
    if existing:
        db.delete(existing)
        db.commit()

    db.add(GrantReport(
        session_id=session_id,
        documents_json=json.dumps(report.get("documents_by_scheme", report.get("documents", []))),
        action_cards_json=json.dumps(report.get("action_cards", [])),
        cover_summary=report.get("cover_summary", ""),
    ))
    db.commit()
