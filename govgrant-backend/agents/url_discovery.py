"""
url_discovery.py — Gemini-powered URL discovery for Agent 2

Given a user profile, Gemini generates a ranked list of URLs to scrape
(scheme listing pages, not individual scheme detail pages — those come
from parsing the listing HTML).

Exported:
  discover_urls(profile: dict, api_key: str, model: str) -> list[str]
"""

import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_DISCOVERY_SYSTEM = """You are a researcher specializing in Indian government grant and scheme portals.
Given a business profile, return a JSON array of URLs that are most likely to list
relevant government schemes for this business.

Rules:
- Return ONLY a JSON array of strings (URLs), no markdown, no explanation.
- Include 8-15 URLs maximum.
- Prioritize official government portals (.gov.in, .nic.in) and well-known scheme aggregators.
- Include both central government and state-specific portals based on the user's state.
- Focus on LISTING pages (pages that show multiple schemes), not individual scheme pages.
- For sector-specific portals, tailor by sector.
- Always include: schemes.msme.gov.in, startupindia.gov.in, myscheme.gov.in

Example output (do NOT copy verbatim, generate for the actual profile):
["https://schemes.msme.gov.in/Schemes.aspx", "https://startupindia.gov.in/content/sih/en/government-schemes.html"]
"""

_DISCOVERY_USER = """Business Profile:
- Sector: {sector}
- State: {state}
- Entity Type: {entity_type}
- Annual Revenue (INR): {revenue}
- Team Size: {team_size}
- Funding Purpose: {purpose}

Generate the best URLs to find government grant schemes for this business.
Return ONLY a JSON array of URLs."""


# ── Known reliable scheme listing URLs (fallback corpus) ─────────────────────
# Ensures we always have something even if Gemini fails

_BASELINE_URLS = [
    "https://schemes.msme.gov.in/Schemes.aspx",
    "https://msme.gov.in/schemes",
    "https://startupindia.gov.in/content/sih/en/government-schemes.html",
    "https://www.myscheme.gov.in/search",
    "https://www.sidbi.in/en/schemes",
    "https://www.nabard.org/content1.aspx?catid=23&mid=530",
    "https://www.mudra.org.in/ProductsSchemes",
    "https://cgtmse.in/products",
]

_STATE_PORTALS: dict[str, list[str]] = {
    "maharashtra": [
        "https://udyog.mahaonline.gov.in/En/Scheme/SchemeListing",
        "https://mahadbt.maharashtra.gov.in/SchemeData/pdf/schemes_list.pdf",
    ],
    "karnataka": [
        "https://www.karnataka.gov.in/industries",
        "https://kiadb.in/incentives/",
    ],
    "tamil nadu": [
        "https://www.tnidb.com/incentives.html",
        "https://msme.tn.gov.in/schemes.html",
    ],
    "gujarat": [
        "https://ic.gujarat.gov.in/incentives-overview.htm",
        "https://www.gidcgujarat.com/incentives/",
    ],
    "delhi": [
        "https://delhiindustrialpark.com/incentive-scheme/",
        "https://dtte.delhi.gov.in/dtte/schemes",
    ],
    "telangana": [
        "https://www.tsiic.telangana.gov.in/investor-services/incentives/",
        "https://industries.telangana.gov.in/Schemes.html",
    ],
    "andhra pradesh": [
        "https://www.apindustries.gov.in/APIndus/UserInterface/Schemes/listschemes.aspx",
    ],
    "rajasthan": [
        "https://rajsico.rajasthan.gov.in/schemes.aspx",
        "https://industries.rajasthan.gov.in/content/industries/en/govt-of-rajasthan0/scheme.html",
    ],
    "west bengal": [
        "https://msme.wb.gov.in/",
        "https://wbidc.com/incentives-and-schemes/",
    ],
    "uttar pradesh": [
        "https://msme.up.gov.in/en/schemes",
        "https://invest.up.gov.in/incentives-and-concessions/",
    ],
}

_SECTOR_PORTALS: dict[str, list[str]] = {
    "food_processing": [
        "https://mofpi.gov.in/Schemes/list-of-schemes",
        "https://pmfme.mofpi.gov.in/pmfme/",
        "https://www.apeda.gov.in/apedawebsite/SubHead_Products/Schemes.htm",
    ],
    "agriculture": [
        "https://agricoop.nic.in/en/schemes",
        "https://nabard.org/content1.aspx?catid=23&mid=530",
        "https://pmkisan.gov.in/",
    ],
    "it_tech": [
        "https://meity.gov.in/schemes",
        "https://startupindia.gov.in/content/sih/en/government-schemes.html",
        "https://nasscom.in/initiatives",
    ],
    "healthcare": [
        "https://mohfw.gov.in/schemes",
        "https://nhm.gov.in/index4.php?lang=1&level=0&linkid=445&lid=3465",
        "https://ayush.gov.in/about-the-systems/ayush/ayush-schemes",
    ],
    "manufacturing": [
        "https://dpiit.gov.in/schemes",
        "https://www.plischeme.com/",
        "https://schemes.msme.gov.in/Schemes.aspx",
    ],
    "textile": [
        "https://texmin.nic.in/schemes",
        "https://sitp.nic.in/",
        "https://tufs.nic.in/",
    ],
    "renewable_energy": [
        "https://mnre.gov.in/schemes",
        "https://seci.co.in/",
        "https://www.ireda.in/",
    ],
    "export": [
        "https://www.apeda.gov.in/apedawebsite/SubHead_Products/Schemes.htm",
        "https://www.ecgc.in/Portal/Products/ProductList.aspx",
        "https://www.eximbankindia.in/schemes",
    ],
}


async def discover_urls(profile: dict[str, Any], api_key: str, model: str = "gemini-2.0-flash") -> list[str]:
    """
    Generate a list of URLs to scrape for schemes relevant to the profile.
    
    Flow:
      1. Build baseline list from sector + state lookup tables
      2. Ask Gemini to suggest additional targeted URLs
      3. Merge, deduplicate, return
    """
    urls: list[str] = list(_BASELINE_URLS)

    # Add sector-specific portals
    sector = (profile.get("sector") or "").lower().replace(" ", "_")
    for key, portals in _SECTOR_PORTALS.items():
        if key in sector or sector in key:
            urls.extend(portals)
            break

    # Add state-specific portals
    state = (profile.get("state") or "").lower()
    for key, portals in _STATE_PORTALS.items():
        if key in state or state in key:
            urls.extend(portals)
            break

    # Ask Gemini for additional targeted URLs
    try:
        gemini_urls = await _gemini_discover(profile, api_key, model)
        urls.extend(gemini_urls)
        logger.info(f"[url_discovery] Gemini added {len(gemini_urls)} URLs")
    except Exception as e:
        logger.warning(f"[url_discovery] Gemini URL discovery failed: {e}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        u = u.strip().rstrip("/")
        if u and u not in seen and u.startswith("http"):
            seen.add(u)
            unique.append(u)

    logger.info(f"[url_discovery] Total unique URLs to scrape: {len(unique)}")
    return unique


async def _gemini_discover(profile: dict, api_key: str, model: str) -> list[str]:
    """Call Gemini API to get suggested URLs."""
    user_msg = _DISCOVERY_USER.format(
        sector=profile.get("sector", "general"),
        state=profile.get("state", "India"),
        entity_type=profile.get("entity_type", "msme"),
        revenue=profile.get("annual_revenue_inr", 0),
        team_size=profile.get("team_size", 0),
        purpose=profile.get("purpose", "growth"),
    )

    payload = {
        "model": model,
        "system_instruction": {"parts": [{"text": _DISCOVERY_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Strip markdown fences
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE)

    urls = json.loads(text)
    return [u for u in urls if isinstance(u, str) and u.startswith("http")]
