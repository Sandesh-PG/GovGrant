"""
PlannerService — Real Gemini-powered report generation (Agent 4).

Data flow:
1. Reads UserProfile + RankedSchemes from DB (written by Agents 1 & 3)
2. Calls Gemini 2.0 Flash to generate:
   - Consolidated documents checklist (10-15 items, deduped)
   - Per-scheme action cards (steps, tips, portal links)
   - 150-word persuasive cover summary
3. Persists to grant_reports table
4. Returns report dict for SSE emission as report_ready event

This agent owns the `grant_reports` database table.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import google.genai as genai
from sqlmodel import Session, select

from config import settings
from db.models import GrantReport, RankedScheme, UserProfile as DBUserProfile

logger = logging.getLogger("govgrant.planner")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT — called by pipeline in routes.py
# ═══════════════════════════════════════════════════════════════════════════════

async def run_planner(
    session_id: str,
    profile_data: Dict[str, Any],
    db: Session,
) -> Dict[str, Any]:
    """
    Run Agent 4: generate full GrantReport from ranked schemes, persist to DB.

    Args:
        session_id: Current session UUID
        profile_data: User profile dict from Agent 1
        db: SQLModel session for DB reads/writes

    Returns:
        Report dict with documents, action_cards, cover_summary for SSE
    """
    logger.info("[%s] === PLANNER START ===", session_id)

    # ── Step 1: Read ranked schemes from DB (Agent 3 output) ──────────
    ranked_rows = db.exec(
        select(RankedScheme).where(RankedScheme.session_id == session_id)
        .order_by(RankedScheme.composite_rank)
    ).all()

    if not ranked_rows:
        logger.warning("[%s] No ranked_schemes found -- using fallback report", session_id)
        report = _fallback_report(profile_data)
        _persist_report(session_id, report, db)
        return report

    ranked_schemes = [
        {
            "scheme_name": r.scheme_name,
            "match_score": r.match_score,
            "rank": r.rank,
            "reason": r.reason,
            "portal_url": r.portal_url or "",
            "deadline": r.deadline,
            "grant_amount": r.grant_amount or "Check portal",
        }
        for r in ranked_rows
    ]

    logger.info("[%s] Generating report for %d ranked schemes", session_id, len(ranked_schemes))

    # ── Step 2: Call Gemini to generate report ─────────────────────────
    report = await _gemini_generate(session_id, profile_data, ranked_schemes)

    if not report:
        logger.warning("[%s] Gemini planner failed -- using fallback", session_id)
        report = _fallback_report(profile_data)

    # ── Step 3: Persist to grant_reports table ─────────────────────────
    _persist_report(session_id, report, db)

    logger.info("[%s] === PLANNER DONE === report persisted", session_id)
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# DB PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def _persist_report(session_id: str, report: Dict, db: Session) -> None:
    """Write the report to grant_reports table (upsert)."""
    existing = db.exec(
        select(GrantReport).where(GrantReport.session_id == session_id)
    ).first()
    if existing:
        db.delete(existing)
        db.commit()

    db.add(GrantReport(
        session_id=session_id,
        documents_json=json.dumps(report.get("documents", [])),
        action_cards_json=json.dumps(report.get("action_cards", [])),
        cover_summary=report.get("cover_summary", ""),
    ))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

async def _gemini_generate(
    session_id: str,
    profile: Dict[str, Any],
    schemes: List[Dict],
) -> Optional[Dict]:
    """Call Gemini 2.0 Flash to generate the full grant report."""

    prompt = f"""You are GovGrant's report generator for Indian businesses.
Create a complete, actionable grant report.

BUSINESS PROFILE:
- Name: {profile.get('name', 'Unknown')}
- Type: {profile.get('type', 'Unknown')}
- Sector: {profile.get('sector', 'Unknown')}
- Location: {profile.get('city', '')}, {profile.get('state', 'India')}
- Team: {profile.get('team_size', 0)} employees
- Revenue: INR {profile.get('revenue_inr', 0):,}
- Funding Purpose: {profile.get('funding_purpose', 'general')}

TOP MATCHED SCHEMES:
{json.dumps(schemes, indent=2)}

Generate a JSON object with EXACTLY these 3 keys:

1. "documents" - Array of 10-15 document objects, each with:
   {{"name": "string", "mandatory": true/false, "description": "what's needed"}}

   Always include: Aadhaar/PAN, incorporation cert, bank statements (6mo),
   ITR (2yr), GST cert, MSME/Udyam, business plan, audited financials.
   Add scheme-specific documents for the schemes above.

2. "action_cards" - Array of one object per scheme, each with:
   {{"scheme_name": "string", "portal_url": "string", "deadline": "string",
     "steps": ["step1", ...], "estimated_days": number, "tips": ["tip1", ...]}}
   Include 5-6 steps per scheme and 2-3 practical tips.

3. "cover_summary" - Exactly ~150 words. First-person ("We/Our"), formal English.
   Introduce the business, highlight strengths, state funding purpose,
   show alignment with government objectives, end with a request.

Return ONLY valid JSON. No markdown fences, no explanation."""

    logger.info("[%s] Calling Gemini for report generation...", session_id)

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=8192,
            ),
        )
        text = response.text or ""
        report = _parse_json_object(text)
        if report:
            logger.info("[%s] Gemini report generated successfully", session_id)
        return report
    except Exception as e:
        logger.error("[%s] Gemini planner failed: %s", session_id, str(e))
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_json_object(text: str) -> Optional[Dict]:
    """Extract JSON object from LLM response, handling markdown fences."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _fallback_report(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Curated fallback report when Gemini is unavailable."""
    name = profile.get("name", "Your Business")
    sector = profile.get("sector", "general")
    state = profile.get("state", "India")
    purpose = profile.get("funding_purpose", "business expansion")
    revenue = profile.get("revenue_inr", 0)
    team = profile.get("team_size", 1)
    entity = profile.get("type", "business")

    return {
        "documents": [
            {"name": "Aadhaar Card (Promoters)", "mandatory": True, "description": "Self-attested copy of all promoters"},
            {"name": "PAN Card (Business + Promoters)", "mandatory": True, "description": "Both entity PAN and individual PANs"},
            {"name": "Certificate of Incorporation", "mandatory": True, "description": "MOA/AOA for Pvt Ltd; partnership deed for partnerships"},
            {"name": "GST Registration Certificate", "mandatory": True, "description": "Required if turnover exceeds Rs 20 lakhs"},
            {"name": "MSME / Udyam Registration", "mandatory": True, "description": "Register at udyamregistration.gov.in"},
            {"name": "Bank Account Statements", "mandatory": True, "description": "Last 6-12 months, all business accounts"},
            {"name": "Income Tax Returns (ITR)", "mandatory": True, "description": "Last 2-3 financial years with CA certification"},
            {"name": "Audited Financial Statements", "mandatory": revenue > 4000000, "description": "Balance sheet and P&L, required if turnover > Rs 40L"},
            {"name": "Business Plan / Project Report", "mandatory": True, "description": "Market analysis, financials, and fund utilisation plan"},
            {"name": "Photographs of Business Premises", "mandatory": False, "description": "Exterior and interior for physical verification"},
        ],
        "action_cards": [
            {
                "scheme_name": "CGTMSE Credit Guarantee",
                "portal_url": "https://www.cgtmse.in/",
                "deadline": "Rolling",
                "steps": [
                    "Register on the CGTMSE portal at cgtmse.in",
                    "Approach your bank with business plan and loan application",
                    "Bank submits proposal to CGTMSE on your behalf",
                    "CGTMSE reviews and issues guarantee certificate",
                    "Bank disburses the collateral-free loan",
                    "Maintain repayment schedule to preserve guarantee",
                ],
                "estimated_days": 45,
                "tips": [
                    "PSU banks (SBI, PNB) process CGTMSE faster than private banks",
                    "Ensure Udyam registration is complete before applying",
                ],
            },
            {
                "scheme_name": "Startup India Seed Fund",
                "portal_url": "https://seedfund.startupindia.gov.in/",
                "deadline": "Rolling (quarterly cohorts)",
                "steps": [
                    "Get DPIIT recognition on startupindia.gov.in",
                    "Find an incubator in your state on the Seed Fund portal",
                    "Submit application through the incubator",
                    "Present business plan to incubator committee",
                    "Sign grant agreement and receive first tranche",
                    "Submit utilisation certificates per schedule",
                ],
                "estimated_days": 90,
                "tips": [
                    "DPIIT recognition is mandatory - apply 2 weeks before incubator deadline",
                    "Choose an incubator specialising in your sector",
                ],
            },
        ],
        "cover_summary": (
            f"We are {name}, a {entity} operating in the {sector} sector, based in {state}. "
            f"Our dedicated team of {team} professionals has built a sustainable business with "
            f"an annual revenue of INR {revenue:,}, reflecting consistent growth and market confidence. "
            f"We are seeking funding to support {purpose}, which will directly enhance our operational "
            f"capacity and create meaningful employment opportunities in our region. "
            f"Our growth trajectory aligns with the Government of India's vision of strengthening "
            f"the MSME ecosystem and promoting indigenous enterprise. We maintain full statutory "
            f"compliance, including GST and Udyam registration. With the right financial support, "
            f"we are confident of doubling our capacity within 18 months and contributing significantly "
            f"to India's economic development. We respectfully request consideration for the government "
            f"schemes identified in this report."
        ),
    }
