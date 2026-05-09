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
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import google.genai as genai
import httpx
from bs4 import BeautifulSoup
from sqlmodel import Session, select

from config import settings
from db.models import GrantReport, RankedScheme
from .scraper import scrape_url

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

    # ── Step 2: Build documents checklist from portals (and web search) ─
    documents_by_scheme = await _build_documents_by_scheme(ranked_schemes, profile_data)

    # ── Step 3: Build action cards per scheme from portals (and web search) ─
    action_cards = await _build_action_cards(ranked_schemes, profile_data)

    # ── Step 4: Call Gemini to generate cover summary ────────────────
    report = await _gemini_generate(session_id, profile_data, ranked_schemes)

    if not report:
        logger.warning("[%s] Gemini planner failed -- using fallback", session_id)
        report = _fallback_report(profile_data)

    report["action_cards"] = action_cards
    report.setdefault("cover_summary", "")
    report["documents_by_scheme"] = documents_by_scheme
    report["documents"] = _merge_documents(documents_by_scheme)

    # ── Step 5: Persist to grant_reports table ─────────────────────────
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

    documents_payload = report.get("documents_by_scheme")
    if documents_payload is None:
        documents_payload = report.get("documents", [])

    db.add(GrantReport(
        session_id=session_id,
        documents_json=json.dumps(documents_payload),
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


def _parse_json_array(text: str) -> List[Dict]:
    """Extract JSON array from LLM response, handling markdown fences."""
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return []


def _normalize_action_card(card: Dict[str, Any], scheme: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ensure action card has required fields and reasonable values."""
    if not isinstance(card, dict):
        return None

    steps = [str(s).strip() for s in card.get("steps", []) if str(s).strip()]
    tips = [str(t).strip() for t in card.get("tips", []) if str(t).strip()]

    if len(steps) < 3:
        return None

    try:
        estimated_days = int(card.get("estimated_days", 45))
    except (TypeError, ValueError):
        estimated_days = 45

    estimated_days = max(7, min(180, estimated_days))

    return {
        "scheme_name": scheme.get("scheme_name", "Unknown Scheme"),
        "portal_url": scheme.get("portal_url") or scheme.get("source_url") or "",
        "deadline": scheme.get("deadline"),
        "steps": steps,
        "estimated_days": estimated_days,
        "tips": tips[:5],
    }


def _normalize_doc_name(name: str) -> str:
    name = (name or "").strip().lower()
    return re.sub(r"\s+", " ", name)


def _normalize_documents(docs: List[Dict]) -> List[Dict]:
    """Clean and dedupe document list."""
    seen: dict[str, Dict] = {}
    for d in docs:
        if not isinstance(d, dict):
            continue
        name = (d.get("name") or "").strip()
        if not name:
            continue
        key = _normalize_doc_name(name)
        item = {
            "name": name,
            "mandatory": bool(d.get("mandatory", False)),
            "description": (d.get("description") or "Required document for this scheme.").strip(),
        }
        if key not in seen:
            seen[key] = item
        else:
            existing = seen[key]
            if item["mandatory"]:
                existing["mandatory"] = True
            if len(item["description"]) > len(existing.get("description", "")):
                existing["description"] = item["description"]
    return list(seen.values())


def _merge_documents(documents_by_scheme: List[Dict]) -> List[Dict]:
    """Merge per-scheme document lists into a single deduped list."""
    merged: List[Dict] = []
    for item in documents_by_scheme:
        merged.extend(item.get("documents", []))
    return _normalize_documents(merged)


def _clean_text_from_html(html: str) -> str:
    """Strip noisy HTML and return readable text for extraction."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup([
        "script", "style", "nav", "footer", "header", "aside",
        "noscript", "svg", "img", "figure", "iframe", "form",
        "button", "input", "select",
    ]):
        tag.decompose()

    main = (
        soup.find("main")
        or soup.find(id=re.compile(r"(content|main|scheme|grant|document)", re.I))
        or soup.find(class_=re.compile(r"(content|main|scheme|grant|document|listing)", re.I))
        or soup.body
        or soup
    )

    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    words = text.split()
    if len(words) > 4000:
        text = " ".join(words[:4000]) + "\n[... truncated ...]"

    return text


async def _extract_documents_from_text(
    scheme_name: str,
    source_url: str,
    text: str,
) -> List[Dict]:
    """Use Gemini to extract required documents from text."""
    system_prompt = (
        "You extract required documents for a government scheme. "
        "Return ONLY a JSON array of objects with keys: "
        "name (string), mandatory (true/false), description (short note). "
        "Only include documents explicitly mentioned. "
        "If no document list is found, return [] and nothing else."
    )

    user_prompt = (
        f"Scheme: {scheme_name}\n"
        f"Source URL: {source_url}\n\n"
        "Page text:\n---\n"
        f"{text}\n"
        "---\n\n"
        "Extract the required documents list for this scheme."
    )

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=user_prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
        raw = response.text or ""
        docs = _parse_json_array(raw)
        return _normalize_documents(docs)
    except Exception as e:
        logger.warning("[planner] Document extraction failed: %s", str(e))
        return []


async def _extract_documents_from_url(
    scheme_name: str,
    url: str,
) -> List[Dict]:
    if not url:
        return []
    html = await scrape_url(url)
    if not html:
        return []
    text = _clean_text_from_html(html)
    if len(text) < 200:
        return []
    return await _extract_documents_from_text(scheme_name, url, text)


async def _extract_action_card_from_text(
    scheme: Dict[str, Any],
    text: str,
    profile: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Use Gemini to extract a step-by-step action plan from text."""
    system_prompt = (
        "You create step-by-step application roadmaps for Indian government schemes. "
        "Return ONLY a JSON object with keys: steps (array of 5-7 strings), "
        "estimated_days (integer), tips (array of 2-3 strings). "
        "Only use information present in the text; if unclear, infer a cautious generic step and "
        "advise checking the official portal within the steps or tips."
    )

    user_prompt = (
        f"Scheme: {scheme.get('scheme_name', 'Unknown Scheme')}\n"
        f"Portal URL: {scheme.get('portal_url') or scheme.get('source_url') or ''}\n"
        f"Deadline: {scheme.get('deadline', 'Rolling')}\n\n"
        "Business profile summary:\n"
        f"- Sector: {profile.get('sector', 'general')}\n"
        f"- Entity Type: {profile.get('type', 'msme')}\n"
        f"- State: {profile.get('state', 'India')}\n"
        f"- Purpose: {profile.get('funding_purpose', 'general')}\n\n"
        "Page text:\n---\n"
        f"{text}\n"
        "---\n\n"
        "Create a clear, realistic roadmap to apply for this scheme."
    )

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=user_prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )
        raw = response.text or ""
        card = _parse_json_object(raw)
        return _normalize_action_card(card, scheme)
    except Exception as e:
        logger.warning("[planner] Action card extraction failed: %s", str(e))
        return None


def _unwrap_ddg_url(url: str) -> str:
    if not url:
        return ""
    if "duckduckgo.com/l/" in url:
        parsed = urlparse(url)
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return unquote(uddg[0])
    return url


async def _search_document_urls(query: str, max_results: int = 5) -> List[str]:
    """Use DuckDuckGo HTML search to find candidate pages."""
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            resp = await client.get(search_url)
            if resp.status_code != 200:
                return []
    except Exception as e:
        logger.warning("[planner] Web search failed: %s", str(e))
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    urls: List[str] = []
    for a in soup.select("a.result__a"):
        href = _unwrap_ddg_url(a.get("href", ""))
        if href.startswith("http"):
            urls.append(href)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
        if len(unique) >= max_results:
            break

    return unique


async def _documents_for_scheme(
    scheme: Dict[str, Any],
) -> List[Dict]:
    scheme_name = scheme.get("scheme_name", "Unknown Scheme")
    portal_url = scheme.get("portal_url") or scheme.get("source_url") or ""

    # 1) Try scheme portal first
    docs = await _extract_documents_from_url(scheme_name, portal_url)
    if docs:
        logger.info("[planner] Documents found on portal for %s", scheme_name)
        return docs

    # 2) Fallback to web search
    query = f"{scheme_name} required documents for application"
    search_urls = await _search_document_urls(query, max_results=5)
    for url in search_urls:
        docs = await _extract_documents_from_url(scheme_name, url)
        if docs:
            logger.info("[planner] Documents found via web search for %s", scheme_name)
            return docs

    return []


def _fallback_action_card(scheme: Dict[str, Any]) -> Dict[str, Any]:
    """Generic action card when extraction fails."""
    return {
        "scheme_name": scheme.get("scheme_name", "Unknown Scheme"),
        "portal_url": scheme.get("portal_url") or scheme.get("source_url") or "",
        "deadline": scheme.get("deadline"),
        "steps": [
            "Review eligibility criteria on the official portal",
            "Create or update required business registrations (GST/MSME/DPIIT as applicable)",
            "Prepare core documents and project summary for the application",
            "Register on the scheme portal and fill the online application",
            "Upload documents and submit the application",
            "Track application status and respond to any queries from the authority",
        ],
        "estimated_days": 45,
        "tips": [
            "Keep scanned documents in a single folder to speed up submission",
            "Use the official portal checklist as the source of truth",
        ],
    }


async def _action_card_for_scheme(
    scheme: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    scheme_name = scheme.get("scheme_name", "Unknown Scheme")
    portal_url = scheme.get("portal_url") or scheme.get("source_url") or ""

    # 1) Try scheme portal first
    if portal_url:
        html = await scrape_url(portal_url)
        if html:
            text = _clean_text_from_html(html)
            if len(text) >= 200:
                card = await _extract_action_card_from_text(scheme, text, profile)
                if card:
                    logger.info("[planner] Action card built from portal for %s", scheme_name)
                    return card

    # 2) Fallback to web search
    query = f"{scheme_name} application steps how to apply"
    search_urls = await _search_document_urls(query, max_results=5)
    for url in search_urls:
        html = await scrape_url(url)
        if not html:
            continue
        text = _clean_text_from_html(html)
        if len(text) < 200:
            continue
        card = await _extract_action_card_from_text(scheme, text, profile)
        if card:
            logger.info("[planner] Action card built from web search for %s", scheme_name)
            return card

    return _fallback_action_card(scheme)


async def _build_documents_by_scheme(
    ranked_schemes: List[Dict[str, Any]],
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build per-scheme document lists with portal + web search fallback."""
    results: List[Dict[str, Any]] = []

    for scheme in ranked_schemes:
        docs = await _documents_for_scheme(scheme)
        if not docs:
            docs = _static_documents(profile)
            logger.info("[planner] Using static documents for %s", scheme.get("scheme_name"))
        results.append({
            "scheme_name": scheme.get("scheme_name", "Unknown Scheme"),
            "documents": docs,
        })

    return results


async def _build_action_cards(
    ranked_schemes: List[Dict[str, Any]],
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build action cards for each scheme."""
    cards: List[Dict[str, Any]] = []
    for scheme in ranked_schemes:
        cards.append(await _action_card_for_scheme(scheme, profile))
    return cards


def _fallback_report(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Curated fallback report when Gemini is unavailable."""
    name = profile.get("name", "Your Business")
    sector = profile.get("sector", "general")
    state = profile.get("state", "India")
    purpose = profile.get("funding_purpose", "business expansion")
    revenue = profile.get("revenue_inr", 0)
    team = profile.get("team_size", 1)
    entity = profile.get("type", "business")

    documents = _static_documents(profile)

    return {
        "documents": documents,
        "documents_by_scheme": [
            {"scheme_name": "General", "documents": documents},
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


def _static_documents(profile: Dict[str, Any]) -> List[Dict]:
    """Default checklist used when no portal/search docs are found."""
    revenue = profile.get("revenue_inr", 0)
    return [
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
    ]
