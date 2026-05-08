"""
research_agent.py — Agent 2: ResearchAgent (Google ADK definition)

ADK agent that wraps the full scrape pipeline as callable tools.
In the ADK sequential pipeline, this agent:
  1. Receives the user_profile from Agent 1 (IntakeAgent)
  2. Calls scrape_and_extract_schemes tool
  3. Returns structured raw_schemes list

The actual heavy lifting is in research_service.py.
"""

import asyncio
import json
import logging
from typing import Any

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


# ── Tool: scrape_and_extract_schemes ─────────────────────────────────────────

async def scrape_and_extract_schemes(
    sector: str,
    state: str,
    entity_type: str,
    annual_revenue_inr: int,
    team_size: int,
    purpose: str,
    session_id: str,
) -> dict[str, Any]:
    """
    Full research pipeline: discover URLs → scrape → extract → index → return.

    Args:
        sector: Business sector (e.g. food_processing, it_tech)
        state: Indian state (e.g. Maharashtra, Karnataka)
        entity_type: Entity type (e.g. startup, msme, private_limited)
        annual_revenue_inr: Annual revenue in INR (0 for pre-revenue)
        team_size: Number of employees
        purpose: Funding purpose (e.g. technology_upgrade, working_capital)
        session_id: Current session UUID

    Returns:
        {"schemes": [...], "count": int, "status": "ok"|"fallback"}
    """
    from .research_service import run_research_pipeline

    profile = {
        "sector": sector,
        "state": state,
        "entity_type": entity_type,
        "annual_revenue_inr": annual_revenue_inr,
        "team_size": team_size,
        "purpose": purpose,
    }

    try:
        schemes = await run_research_pipeline(profile, session_id)
        return {
            "schemes": schemes,
            "count": len(schemes),
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"[research_agent] Pipeline failed: {e}")
        from .research_service import FALLBACK_SCHEMES
        return {
            "schemes": FALLBACK_SCHEMES,
            "count": len(FALLBACK_SCHEMES),
            "status": "fallback",
            "error": str(e),
        }


# ── Tool: rag_lookup ──────────────────────────────────────────────────────────

async def rag_lookup(query: str) -> dict[str, Any]:
    """
    Search the ChromaDB index for relevant schemes matching a query.
    Useful when you want to find schemes without re-scraping.

    Args:
        query: Natural language query (e.g. "food processing MSME Maharashtra")

    Returns:
        {"schemes": [...], "count": int}
    """
    from .chroma_indexer import rag_search, get_collection_stats
    import os

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    try:
        stats = get_collection_stats()
        logger.info(f"[research_agent] ChromaDB has {stats.get('total_schemes', 0)} schemes indexed")

        schemes = await rag_search(query, api_key, n_results=15)
        return {"schemes": schemes, "count": len(schemes)}
    except Exception as e:
        logger.error(f"[research_agent] RAG lookup failed: {e}")
        return {"schemes": [], "count": 0, "error": str(e)}


# ── ADK Agent Definition ──────────────────────────────────────────────────────

_RESEARCH_INSTRUCTION = """You are the Research Agent for GovGrant, an AI platform that
discovers government grant schemes for Indian businesses.

Your job is to find the most relevant government grant schemes for the business
described in the user_profile from the previous step.

WORKFLOW:
1. Extract the business profile fields from the context (sector, state, entity_type,
   annual_revenue_inr, team_size, purpose, session_id).
2. Call scrape_and_extract_schemes with these exact fields.
3. If scrape_and_extract_schemes returns status="fallback", also call rag_lookup
   with a query built from the sector + state + entity type.
4. Return the combined list of schemes as the output key "raw_schemes".

IMPORTANT:
- Always pass session_id from the context to scrape_and_extract_schemes.
- Do not hallucinate or invent schemes.
- Do not modify scheme data returned by the tools.
- If both tools fail, return an empty list with a note.

OUTPUT FORMAT:
Return a JSON object:
{
  "raw_schemes": [ /* array of scheme objects from tool */ ],
  "total_found": <integer>,
  "research_method": "scraped" | "rag" | "fallback"
}
"""

research_agent = Agent(
    name="ResearchAgent",
    model="gemini-2.0-flash",
    description=(
        "Discovers relevant Indian government grant schemes by scraping official portals, "
        "extracting structured data, and searching the ChromaDB vector index."
    ),
    instruction=_RESEARCH_INSTRUCTION,
    tools=[
        FunctionTool(scrape_and_extract_schemes),
        FunctionTool(rag_lookup),
    ],
    output_key="raw_schemes",
)
