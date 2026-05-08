"""
ValidatorAgent — Filters and scores schemes against the UserProfile.

Pipeline:
1. Hard-filter: Remove schemes where revenue or entity_type is ineligible
2. LLM-score: Score remaining schemes 0–100 on 4 dimensions
3. Rank and return top 5 RankedScheme objects
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from schemas import (
    RankedScheme, Scheme, ScoreBreakdown, UserProfile,
    EntityType, PurposeType
)

# ─── Hard-filter logic ────────────────────────────────────────────────────────

def hard_filter_schemes(
    schemes_json: str,
    profile_json: str,
) -> List[Dict[str, Any]]:
    """
    Apply hard eligibility filters before LLM scoring.
    Returns filtered list of scheme dicts.
    """
    schemes: List[Dict] = json.loads(schemes_json)
    profile: Dict = json.loads(profile_json)

    revenue = profile.get("annual_revenue_inr", 0) or 0
    entity_type = profile.get("entity_type", "")
    state = profile.get("state", "")
    team_size = profile.get("team_size", 0)

    passed = []
    for s in schemes:
        # Revenue cap check
        if s.get("max_revenue_inr") and revenue > s["max_revenue_inr"]:
            continue
        # Entity type check
        eligible_entities = s.get("eligible_entity_types", [])
        if eligible_entities and entity_type not in eligible_entities:
            continue
        # State check (empty = pan-India)
        eligible_states = s.get("eligible_states", [])
        if eligible_states and state not in eligible_states and "pan_india" not in eligible_states:
            continue
        # Team size check
        if s.get("max_team_size") and team_size > s["max_team_size"]:
            continue
        passed.append(s)

    return passed


hard_filter_tool = FunctionTool(func=hard_filter_schemes)


# ─── System Prompt ─────────────────────────────────────────────────────────────

VALIDATOR_SYSTEM_PROMPT = """You are GovGrant's eligibility validator and scoring engine.

INPUTS (in session state):
- `user_profile`: Structured UserProfile JSON
- `raw_schemes`: List of 15–25 raw scheme objects from ResearchAgent

YOUR TASK:
1. Call `hard_filter_schemes` with the raw schemes and user profile as JSON strings
2. Score each remaining scheme on 4 dimensions (0–100 composite):
   - Eligibility (0–40): How perfectly does the business meet hard criteria?
   - Relevance (0–30): How well does sector/purpose match the scheme?
   - Benefit (0–20): How valuable is the grant amount relative to business needs?
   - Ease (0–10): How easy is the application process?
3. Select the TOP 5 schemes by composite score
4. Return a JSON array of exactly 5 RankedScheme objects

SCORING RULES:
- Be strict: eligibility should be 40 only if ALL criteria match perfectly
- Prefer schemes with higher grant amounts for the user's stated purpose
- Women-led bonus: +5 to relevance if is_women_led AND scheme has women preference
- SC/ST bonus: +5 to relevance if is_sc_st_led AND scheme targets SC/ST founders
- Never include a scheme with composite score < 30

OUTPUT: JSON array of 5 RankedScheme objects, ordered rank 1 (best) to 5."""


# ─── Agent Factory ─────────────────────────────────────────────────────────────

def create_validator_agent(model: str = "gemini-2.0-flash") -> LlmAgent:
    """Create and return the configured ValidatorAgent."""
    return LlmAgent(
        name="validator_agent",
        model=model,
        description=(
            "Filters schemes by hard eligibility criteria, then LLM-scores "
            "remaining schemes to select and rank the top 5."
        ),
        instruction=VALIDATOR_SYSTEM_PROMPT,
        tools=[hard_filter_tool],
        output_key="ranked_schemes",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
