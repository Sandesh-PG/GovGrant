"""
research_service.py — Agent 2: Research Pipeline (REWRITTEN)

Full pipeline:
  1. URL Discovery   — Gemini generates target portal URLs for this profile
  2. Web Scraping    — httpx (fast) → Playwright fallback (JS-heavy pages)
  3. HTML Extraction — Gemini parses raw HTML → structured scheme records
  4. Deduplication   — merge across pages, remove exact duplicates
  5. ChromaDB Index  — index new schemes for future RAG retrieval
  6. RAG Merge       — pull additional matches from existing ChromaDB index
  7. Persist         — write final schemes to raw_schemes DB table

Fallback at every stage: if Gemini / scraping fails, uses curated schemes.
"""

import asyncio
import json
import logging
import os
from typing import Any

from sqlmodel import Session

from db.database import engine
from db.models import RawScheme

from .url_discovery import discover_urls
from .scraper import scrape_urls
from .html_extractor import extract_schemes_from_html, deduplicate_schemes
from .chroma_indexer import index_schemes, rag_search

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Max pages to scrape per session (balance thoroughness vs latency)
MAX_SCRAPE_URLS = 10

# Minimum schemes before we stop (quality gate)
MIN_SCHEMES_TARGET = 10

# ── Curated fallback schemes ──────────────────────────────────────────────────

FALLBACK_SCHEMES = [
    {
        "scheme_name": "CGTMSE — Credit Guarantee Fund Trust for Micro and Small Enterprises",
        "criteria_text": "Collateral-free credit up to ₹5 crore for MSMEs. No third-party guarantee required.",
        "deadline": None,
        "max_revenue_inr": 25_00_00_000,
        "eligible_types": ["msme", "startup", "proprietorship", "private_limited", "partnership", "llp"],
        "grant_amount": "Up to ₹5 crore (credit guarantee)",
        "portal_url": "https://cgtmse.in/",
        "source_type": "offline",
    },
    {
        "scheme_name": "PM Mudra Yojana — Shishu / Kishore / Tarun",
        "criteria_text": "Loans for non-farm income generating activities up to ₹10 lakh. For micro enterprises.",
        "deadline": None,
        "max_revenue_inr": None,
        "eligible_types": ["proprietorship", "msme", "partnership"],
        "grant_amount": "Up to ₹10 lakh",
        "portal_url": "https://www.mudra.org.in/",
        "source_type": "offline",
    },
    {
        "scheme_name": "Stand Up India — SC/ST and Women Entrepreneurs",
        "criteria_text": "Bank loans between ₹10 lakh and ₹1 crore for SC/ST and women entrepreneurs for greenfield enterprises.",
        "deadline": None,
        "max_revenue_inr": None,
        "eligible_types": ["proprietorship", "private_limited", "partnership", "llp"],
        "grant_amount": "₹10 lakh to ₹1 crore",
        "portal_url": "https://www.standupmitra.in/",
        "source_type": "offline",
    },
    {
        "scheme_name": "PM Employment Generation Programme (PMEGP)",
        "criteria_text": "Subsidy 15-35% of project cost for setting up new micro-enterprises in manufacturing/service sectors.",
        "deadline": None,
        "max_revenue_inr": None,
        "eligible_types": ["proprietorship", "msme", "cooperative", "ngo", "partnership"],
        "grant_amount": "15-35% subsidy on project cost",
        "portal_url": "https://www.kviconline.gov.in/pmegpeportal/pmegphome/index.jsp",
        "source_type": "offline",
    },
    {
        "scheme_name": "Startup India Seed Fund Scheme (SISFS)",
        "criteria_text": "Grants/soft loans for DPIIT-recognised startups at ideation/POC/prototype stage.",
        "deadline": None,
        "max_revenue_inr": None,
        "eligible_types": ["startup", "private_limited", "llp"],
        "grant_amount": "Up to ₹20 lakh (grant) + ₹50 lakh (convertible debentures)",
        "portal_url": "https://seedfund.startupindia.gov.in/",
        "source_type": "offline",
    },
]


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run_research_pipeline(profile: dict[str, Any], session_id: str) -> list[dict]:
    """
    Full research pipeline for Agent 2.

    Args:
        profile: User profile dict from user_profiles table
        session_id: Current session UUID

    Returns:
        List of raw scheme dicts persisted to raw_schemes table
    """
    logger.info(f"[research] Starting research pipeline for session {session_id}")
    logger.info(f"[research] Profile: sector={profile.get('sector')}, state={profile.get('state')}, "
                f"entity={profile.get('entity_type')}, revenue={profile.get('annual_revenue_inr')}")

    all_schemes: list[dict] = []

    # ── STEP 1: Check ChromaDB for existing indexed schemes (RAG) ─────────────
    rag_query = _build_rag_query(profile)
    existing_rag = await _safe_rag_search(rag_query)
    if existing_rag:
        logger.info(f"[research] RAG returned {len(existing_rag)} existing schemes from index")
        all_schemes.extend(existing_rag)

    # ── STEP 2: Discover URLs to scrape ──────────────────────────────────────
    target_urls = []
    try:
        target_urls = await discover_urls(profile, GOOGLE_API_KEY, GEMINI_MODEL)
        logger.info(f"[research] Discovered {len(target_urls)} URLs to scrape")
    except Exception as e:
        logger.error(f"[research] URL discovery failed: {e}")

    # Limit to MAX_SCRAPE_URLS
    target_urls = target_urls[:MAX_SCRAPE_URLS]

    # ── STEP 3: Scrape all URLs ───────────────────────────────────────────────
    scraped_html: dict[str, str | None] = {}
    if target_urls:
        try:
            scraped_html = await scrape_urls(target_urls, concurrency=3)
            successful = sum(1 for v in scraped_html.values() if v)
            logger.info(f"[research] Scraped {successful}/{len(target_urls)} URLs successfully")
        except Exception as e:
            logger.error(f"[research] Scraping failed: {e}")

    # ── STEP 4: Extract schemes from each scraped page ────────────────────────
    newly_scraped: list[dict] = []
    extraction_tasks = []

    for url, html in scraped_html.items():
        if html:
            extraction_tasks.append(
                extract_schemes_from_html(html, url, profile, GOOGLE_API_KEY, GEMINI_MODEL)
            )

    if extraction_tasks:
        results = await asyncio.gather(*extraction_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"[research] Extraction task failed: {result}")
            elif isinstance(result, list):
                newly_scraped.extend(result)

        logger.info(f"[research] Extracted {len(newly_scraped)} schemes from scraped pages")

    # ── STEP 5: Deduplicate newly scraped schemes ─────────────────────────────
    if newly_scraped:
        newly_scraped = deduplicate_schemes(newly_scraped)

        # ── STEP 6: Index new schemes into ChromaDB ───────────────────────────
        try:
            indexed = await index_schemes(newly_scraped, GOOGLE_API_KEY)
            logger.info(f"[research] Indexed {indexed} new schemes into ChromaDB")
        except Exception as e:
            logger.error(f"[research] ChromaDB indexing failed: {e}")

        all_schemes.extend(newly_scraped)

    # ── STEP 7: Final dedup across RAG + newly scraped ───────────────────────
    all_schemes = deduplicate_schemes(all_schemes)
    logger.info(f"[research] Total unique schemes after merge: {len(all_schemes)}")

    # ── STEP 8: Fallback if we have too few results ───────────────────────────
    if len(all_schemes) < 5:
        logger.warning(f"[research] Only {len(all_schemes)} schemes found, adding fallback schemes")
        all_schemes.extend(FALLBACK_SCHEMES)
        all_schemes = deduplicate_schemes(all_schemes)

    # ── STEP 9: Persist to raw_schemes table ─────────────────────────────────
    persisted = _persist_raw_schemes(all_schemes, session_id)
    logger.info(f"[research] Persisted {len(persisted)} schemes to raw_schemes table")

    return persisted


def _build_rag_query(profile: dict) -> str:
    """Build a semantic search query from the profile."""
    parts = [
        profile.get("sector", ""),
        profile.get("entity_type", ""),
        profile.get("state", ""),
        "government grant scheme subsidy",
        profile.get("purpose", ""),
    ]
    return " ".join(p for p in parts if p)


async def _safe_rag_search(query: str) -> list[dict]:
    """RAG search with error handling."""
    try:
        results = await rag_search(query, GOOGLE_API_KEY, n_results=15)
        # Convert RAG metadata back to scheme dicts
        schemes = []
        for r in results:
            scheme = {
                "scheme_name": r.get("scheme_name", ""),
                "criteria_text": r.get("criteria_text", ""),
                "deadline": r.get("deadline") or None,
                "max_revenue_inr": r.get("max_revenue_inr") or None,
                "eligible_types": r.get("eligible_types", "").split(",") if r.get("eligible_types") else [],
                "grant_amount": r.get("grant_amount", ""),
                "portal_url": r.get("source_url", ""),
                "source_type": "live",
            }
            if scheme["scheme_name"]:
                schemes.append(scheme)
        return schemes
    except Exception as e:
        logger.warning(f"[research] RAG search failed silently: {e}")
        return []


def _persist_raw_schemes(schemes: list[dict], session_id: str) -> list[dict]:
    """Write scheme records to the raw_schemes table."""
    persisted = []

    with Session(engine) as db:
        for s in schemes:
            eligible = s.get("eligible_types", [])
            if isinstance(eligible, list):
                eligible_json = json.dumps(eligible)
            else:
                eligible_json = json.dumps([eligible]) if eligible else "[]"

            revenue = s.get("max_revenue_inr")
            try:
                revenue = int(revenue) if revenue is not None else None
            except (TypeError, ValueError):
                revenue = None

            deadline = s.get("deadline")
            if deadline and isinstance(deadline, str) and len(deadline) < 4:
                deadline = None

            record = RawScheme(
                session_id=session_id,
                scheme_name=s.get("scheme_name", "Unknown Scheme"),
                source_url=s.get("portal_url") or s.get("source_url") or "",
                source_type=s.get("source_type", "live"),
                criteria_text=s.get("criteria_text", ""),
                deadline=deadline,
                max_revenue_inr=revenue,
                eligible_types=eligible_json,
                documents_json=json.dumps(s.get("required_documents", [])),
                steps_json=json.dumps(s.get("application_steps", [])),
            )
            db.add(record)
            persisted.append(s)

        db.commit()

    return persisted


# ── Helpers for routes.py ────────────────────────────────────────────────────

def read_profile_from_db(session_id: str, db: Session) -> dict | None:
    """Read a UserProfile from the DB and return it as a dict (or None)."""
    from db.models import UserProfile
    from sqlmodel import select

    profile = db.exec(
        select(UserProfile).where(UserProfile.session_id == session_id)
    ).first()
    if not profile:
        return None

    return {
        "name": profile.name,
        "type": profile.type,
        "sector": profile.sector,
        "state": profile.state,
        "city": getattr(profile, "city", ""),
        "team_size": profile.team_size,
        "revenue_inr": profile.revenue_inr,
        "funding_purpose": getattr(profile, "funding_purpose", "general"),
        "entity_type": profile.type,
        "annual_revenue_inr": profile.revenue_inr,
        "purpose": getattr(profile, "funding_purpose", "general"),
        "session_id": session_id,
    }


async def run_research(
    session_id: str,
    profile_data: dict,
    db: Session,
) -> list[dict]:
    """
    Wrapper called by routes.py's pipeline endpoint.
    Delegates to the full research pipeline.
    """
    profile = {
        "sector": profile_data.get("sector", ""),
        "state": profile_data.get("state", ""),
        "entity_type": profile_data.get("entity_type") or profile_data.get("type", ""),
        "annual_revenue_inr": profile_data.get("annual_revenue_inr") or profile_data.get("revenue_inr", 0),
        "team_size": profile_data.get("team_size", 1),
        "purpose": profile_data.get("purpose") or profile_data.get("funding_purpose", "general"),
    }
    return await run_research_pipeline(profile, session_id)
