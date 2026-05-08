"""
ResearchAgent — Hybrid RAG + Gemini web search agent.

Pipeline:
1. Queries ChromaDB (pre-indexed scheme PDFs) for relevant chunks
2. Uses Gemini's Google Search grounding for live scheme data
3. Merges, deduplicates, and returns 15–25 raw Scheme objects
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, google_search
from google.genai import types

from schemas import Scheme, UserProfile

# ─── ChromaDB Setup ────────────────────────────────────────────────────────────

CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
COLLECTION_NAME = "govgrant_schemes"


def _get_chroma_collection():
    """Lazy-load ChromaDB collection."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=os.environ["GOOGLE_API_KEY"],
        model_name="models/text-embedding-004",
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


# ─── RAG Tool ──────────────────────────────────────────────────────────────────

def rag_scheme_search(
    query: str,
    sector: str,
    state: str,
    entity_type: str,
    n_results: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search the ChromaDB vector store for relevant government schemes.
    Returns a list of raw scheme chunk metadata dicts.
    """
    collection = _get_chroma_collection()
    enriched_query = (
        f"Government grant scheme for {entity_type} in {sector} sector "
        f"in {state}, India. {query}"
    )
    results = collection.query(
        query_texts=[enriched_query],
        n_results=min(n_results, collection.count()),
        where={
            "$or": [
                {"sector": {"$in": [sector, "all"]}},
                {"state": {"$in": [state, "pan_india"]}},
            ]
        },
    )
    schemes = []
    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0])
    ):
        schemes.append({
            "scheme_id": meta.get("scheme_id", f"rag_{i}"),
            "name": meta.get("name", "Unknown Scheme"),
            "ministry": meta.get("ministry", ""),
            "portal_url": meta.get("portal_url", ""),
            "description": meta.get("description", doc[:200]),
            "eligible_sectors": meta.get("eligible_sectors", [sector]),
            "eligible_entity_types": meta.get("eligible_entity_types", []),
            "eligible_states": meta.get("eligible_states", []),
            "max_revenue_inr": meta.get("max_revenue_inr"),
            "max_team_size": meta.get("max_team_size"),
            "grant_amount_inr": meta.get("grant_amount_inr"),
            "deadline": meta.get("deadline"),
            "source": "rag",
            "raw_chunk": doc[:500],
        })
    return schemes


rag_search_tool = FunctionTool(func=rag_scheme_search)


# ─── System Prompt ─────────────────────────────────────────────────────────────

RESEARCH_SYSTEM_PROMPT = """You are GovGrant's research specialist. Given a UserProfile JSON,
your job is to find 15–25 relevant Indian government grant schemes and subsidies.

PROCESS:
1. Call `rag_scheme_search` with the user's sector, state, entity_type as parameters
2. Use Google Search to find additional current schemes — search for:
   - "{sector} government scheme India 2024 2025"
   - "{state} state government grant {entity_type}"
   - "Ministry of MSME scheme {purpose} India"
   - Women/SC-ST specific schemes if applicable
3. Merge results, removing duplicates (same scheme_id or portal_url)
4. Return a JSON array of Scheme objects

IMPORTANT:
- Only return real, verifiable schemes with actual portal URLs
- Mark source as 'rag' or 'web_search' accordingly
- Include both central (pan-India) and state-specific schemes
- Prioritize schemes with open application windows
- Aim for 15–25 results before deduplication

OUTPUT: Return a JSON array of scheme objects matching the Scheme schema."""


# ─── Agent Factory ─────────────────────────────────────────────────────────────

def create_research_agent(model: str = "gemini-2.0-flash") -> LlmAgent:
    """Create and return the configured ResearchAgent."""
    return LlmAgent(
        name="research_agent",
        model=model,
        description=(
            "Hybrid RAG + web-search agent that finds 15–25 relevant "
            "government grant schemes for a given business profile."
        ),
        instruction=RESEARCH_SYSTEM_PROMPT,
        tools=[rag_search_tool, google_search],
        output_key="raw_schemes",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )
