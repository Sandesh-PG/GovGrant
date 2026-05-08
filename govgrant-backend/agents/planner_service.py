"""
PlannerService — Real Gemini-powered report generation (Agent 4).

Data flow:
1. Reads UserProfile + RankedSchemes from DB
2. Calls Gemini to generate:
   - Consolidated documents checklist
   - Per-scheme action cards (steps, tips, portal links)
   - 150-word persuasive cover summary
3. Persists to grant_reports table
4. Returns report dict for SSE emission
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


async def run_planner(
    session_id: str,
    profile_data: Dict[str, Any],
    db: Session,
) -> Dict[str, Any]:
    """
    Run Agent 4: generate full GrantReport from ranked schemes, persist to DB.
    Returns report dict for SSE emission.
    """
    logger.info("[%s] === PLANNER START ===", session_id)

    # Read ranked schemes from DB
    ranked_rows = db.exec(
        select(RankedScheme).where(RankedScheme.session_id == session_id)
        .order_by(RankedScheme.composite_rank)
    ).all()

    if not ranked_rows:
        logger.warning("[%s] No ranked_schemes found — using fallback report", session_id)
        return _fallback_report(profile_data)

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

    # Call Gemini
    report = await _gemini_generate(session_id, profile_data, ranked_schemes)

    if not report:
        logger.warning("[%s] Gemini planner failed — using fallback", session_id)
        report = _fallback_report(profile_data)

    # Persist to grant_reports (upsert)
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
    logger.info("[%s] === PLANNER DONE — report persisted ===", session_id)
    return report


async def _gemini_generate(
    session_id: str,
    profile: Dict[str, Any],
    schemes: List[Dict],
) -> Optional[Dict]:
    """Call Gemini to generate the full grant report."""

    prompt = f"""You are GovGrant's report generator. Create a complete grant report for this business.

BUSINESS PROFILE:
- Name: {profile.get('name')}
- Type: {profile.get('type')}
- Sector: {profile.get('sector')}
- Location: {profile.get('city', '')}, {profile.get('state')}
- Team: {profile.get('team_size')} employees
- Revenue: INR {profile.get('revenue_inr')}
- Funding Purpose: {profile.get('funding_purpose')}

TOP MATCHED SCHEMES:
{json.dumps(schemes, indent=2)}

Generate a JSON object with EXACTLY these three keys:

1. "documents" - Array of document objects, each with:
   - "name": string (document name)
   - "mandatory": boolean
   - "notes": string (brief note on what's needed)
   
   Always include: Aadhaar/PAN, incorporation certificate, bank statements (6 months), ITR (2 years), GST certificate, MSME/Udyam registration, business plan.
   Add scheme-specific documents based on the schemes above.

2. "action_cards" - Array of one object per scheme, each with:
   - "scheme_name": string
   - "portal_url": string  
   - "deadline": string (or "Rolling / Check Portal")
   - "grant_amount": string
   - "steps": array of 5-6 strings (ordered application steps)
   - "estimated_days": number (realistic working days)
   - "tips": array of 2-3 strings (insider tips)

3. "cover_summary" - Exactly 150 words. Persuasive first-person paragraph that:
   - Introduces the business (sector, state, type)
   - Mentions team size and revenue
   - States the funding purpose and alignment with government objectives
   - Ends with a confident request for consideration
   Write as "We/Our business..."

Return ONLY the JSON object. No markdown, no explanation."""

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


def _parse_json_object(text: str) -> Optional[Dict]:
    """Extract JSON object from LLM response."""
    # Try markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _fallback_report(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Curated fallback report when Gemini fails."""
    name = profile.get("name", "Your Business")
    sector = profile.get("sector", "general")
    state = profile.get("state", "India")
    purpose = profile.get("funding_purpose", "business expansion")
    revenue = profile.get("revenue_inr", 0)
    team = profile.get("team_size", 1)
    entity = profile.get("type", "business")

    return {
        "documents": [
            {"name": "Aadhaar Card (Promoters)", "mandatory": True, "notes": "Self-attested copy of all promoters"},
            {"name": "PAN Card (Business + Promoters)", "mandatory": True, "notes": "Both business entity PAN and individual PANs"},
            {"name": "Certificate of Incorporation / Registration", "mandatory": True, "notes": "MOA, AOA for private limited; partnership deed for partnerships"},
            {"name": "GST Registration Certificate", "mandatory": True, "notes": "Required if turnover exceeds Rs 20L"},
            {"name": "MSME / Udyam Registration", "mandatory": True, "notes": "Register at udyamregistration.gov.in if not done"},
            {"name": "Bank Account Statements", "mandatory": True, "notes": "Last 6-12 months, all business accounts"},
            {"name": "Income Tax Returns (ITR)", "mandatory": True, "notes": "Last 2-3 financial years with CA certification"},
            {"name": "Audited Financial Statements", "mandatory": revenue > 4000000, "notes": "Balance sheet, P&L — required if turnover > Rs 40L"},
            {"name": "Business Plan / Project Report", "mandatory": True, "notes": "Detailed plan covering market, financials, and funding utilisation"},
            {"name": "Photographs of Business Premises", "mandatory": False, "notes": "Exterior and interior, for physical verification"},
        ],
        "action_cards": [
            {
                "scheme_name": "CGTMSE Credit Guarantee",
                "portal_url": "https://www.cgtmse.in/",
                "deadline": "Rolling",
                "grant_amount": "Guarantee on loans up to Rs 5 Cr",
                "steps": [
                    "Register on the CGTMSE portal at cgtmse.in",
                    "Approach your bank with your business plan and loan application",
                    "Bank submits proposal to CGTMSE on your behalf",
                    "CGTMSE reviews and issues guarantee certificate",
                    "Bank disburses the collateral-free loan",
                    "Maintain repayment schedule to preserve guarantee status",
                ],
                "estimated_days": 45,
                "tips": [
                    "PSU banks (SBI, PNB) have faster CGTMSE processing than private banks",
                    "Ensure Udyam registration is complete before applying — it speeds up verification",
                    "Prepare a crisp 2-page executive summary of your business plan for the bank manager",
                ],
            },
            {
                "scheme_name": "Startup India Seed Fund",
                "portal_url": "https://seedfund.startupindia.gov.in/",
                "deadline": "Rolling — quarterly cohorts",
                "grant_amount": "Up to Rs 50 lakhs",
                "steps": [
                    "Register on startupindia.gov.in and get DPIIT recognition",
                    "Find an incubator in your state on the Seed Fund portal",
                    "Submit application through the incubator's portal",
                    "Present business plan and demo to incubator committee",
                    "Sign grant agreement and receive first tranche",
                    "Submit utilisation certificates as per schedule",
                ],
                "estimated_days": 90,
                "tips": [
                    "DPIIT recognition is mandatory — apply at least 2 weeks before the incubator deadline",
                    "Choose an incubator that specialises in your sector for better mentorship",
                    "The grant is milestone-based — prepare quarterly progress reports in advance",
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
