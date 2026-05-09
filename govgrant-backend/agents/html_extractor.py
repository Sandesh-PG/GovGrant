"""
html_extractor.py — Gemini-powered scheme extraction from raw HTML

Given raw HTML from a scraped government portal, Gemini identifies and
extracts all grant/scheme mentions as structured JSON records.

Exported:
  extract_schemes_from_html(html, source_url, profile, api_key, model) -> list[dict]
"""

import json
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── HTML pre-processing ───────────────────────────────────────────────────────

def _clean_html(html: str) -> str:
    """
    Strip navigation, scripts, styles, footers.
    Keep main content text to reduce token usage before sending to Gemini.
    Target: < 8000 words of clean text.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise tags
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "noscript", "svg", "img", "figure",
                     "iframe", "form", "button", "input", "select"]):
        tag.decompose()

    # Try to find the main content container
    main = (
        soup.find("main")
        or soup.find(id=re.compile(r"(content|main|scheme|grant)", re.I))
        or soup.find(class_=re.compile(r"(content|main|scheme|grant|listing)", re.I))
        or soup.body
        or soup
    )

    text = main.get_text(separator="\n", strip=True)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Limit to ~8000 words
    words = text.split()
    if len(words) > 8000:
        text = " ".join(words[:8000]) + "\n[... truncated ...]"

    return text


# ── Gemini extraction prompt ──────────────────────────────────────────────────

_EXTRACT_SYSTEM = """You are an expert at extracting Indian government grant and scheme information
from web page text. Extract every scheme, grant, loan, subsidy, or incentive mentioned.

Return ONLY a valid JSON array. Each element must have these fields:
{
  "scheme_name": "Official full name of the scheme",
  "criteria_text": "Eligibility criteria, who can apply, sector/state/revenue restrictions",
  "deadline": "YYYY-MM-DD if mentioned, else null",
  "max_revenue_inr": integer rupee value if revenue cap mentioned else null,
  "eligible_types": ["startup", "msme", "private_limited", ...],
  "grant_amount": "e.g. Up to ₹10 lakh or null",
  "portal_url": "Direct application URL if found else null",
  "required_documents": ["list", "of", "docs", "if", "found", "else", "[]"],
  "application_steps": ["step 1", "step 2", "if", "found", "else", "[]"],
  "source_type": "live"
}

Rules:
- Extract ALL schemes mentioned, even briefly.
- If a field is unknown, use null (not empty string).
- eligible_types must use these exact values: startup, msme, proprietorship, private_limited,
  partnership, llp, cooperative, public_limited, ngo, farmer
- Do NOT include schemes that are clearly not government grants (e.g. commercial loans).
- Return [] if no schemes found — never return non-JSON.
- No markdown fences, no explanation, only the JSON array."""

_EXTRACT_USER = """Source URL: {url}

Business looking for schemes with profile:
- Sector: {sector}
- State: {state}
- Entity Type: {entity_type}

Page content:
---
{content}
---

Extract all grant/scheme information as a JSON array."""


# ── Main extraction function ──────────────────────────────────────────────────

async def extract_schemes_from_html(
    html: str,
    source_url: str,
    profile: dict[str, Any],
    api_key: str,
    model: str = "gemini-2.0-flash",
) -> list[dict]:
    """
    Extract structured scheme records from raw HTML.
    
    Args:
        html: Raw HTML from scraper
        source_url: The URL this HTML came from (for attribution)
        profile: User profile dict
        api_key: Google API key
        model: Gemini model name
    
    Returns:
        List of raw scheme dicts (may have duplicates across pages)
    """
    if not html or len(html.strip()) < 200:
        logger.warning(f"[extractor] HTML too short to extract from {source_url}")
        return []

    # Pre-process HTML to clean text
    clean_text = _clean_html(html)

    if len(clean_text.strip()) < 100:
        logger.warning(f"[extractor] Cleaned text too short for {source_url}")
        return []

    user_msg = _EXTRACT_USER.format(
        url=source_url,
        sector=profile.get("sector", "general"),
        state=profile.get("state", "India"),
        entity_type=profile.get("entity_type", "msme"),
        content=clean_text,
    )

    payload = {
        "model": model,
        "system_instruction": {"parts": [{"text": _EXTRACT_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Strip markdown fences
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text, flags=re.MULTILINE)
        raw_text = re.sub(r"\n?```$", "", raw_text, flags=re.MULTILINE)

        schemes = json.loads(raw_text)
        if not isinstance(schemes, list):
            logger.warning(f"[extractor] Non-list response for {source_url}")
            return []

        # Attach source URL if scheme doesn't have a portal_url
        for s in schemes:
            if not s.get("portal_url"):
                s["portal_url"] = source_url
            if not s.get("source_type"):
                s["source_type"] = "live"

        logger.info(f"[extractor] Extracted {len(schemes)} schemes from {source_url}")
        return schemes

    except json.JSONDecodeError as e:
        logger.error(f"[extractor] JSON parse error for {source_url}: {e}")
        return []
    except Exception as e:
        logger.error(f"[extractor] Gemini extraction failed for {source_url}: {e}")
        return []


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate_schemes(schemes: list[dict]) -> list[dict]:
    """
    Remove duplicate schemes by scheme_name (case-insensitive, normalized).
    When duplicates exist, prefer the one with more non-null fields.
    """
    seen: dict[str, dict] = {}

    for scheme in schemes:
        name = scheme.get("scheme_name", "").strip().lower()
        name = re.sub(r"\s+", " ", name)

        if not name or name == "unknown":
            continue

        if name not in seen:
            seen[name] = scheme
        else:
            # Keep whichever has more populated fields
            existing = seen[name]
            existing_score = sum(1 for v in existing.values() if v is not None)
            new_score = sum(1 for v in scheme.values() if v is not None)
            if new_score > existing_score:
                seen[name] = scheme

    deduped = list(seen.values())
    logger.info(f"[dedup] {len(schemes)} → {len(deduped)} schemes after deduplication")
    return deduped
