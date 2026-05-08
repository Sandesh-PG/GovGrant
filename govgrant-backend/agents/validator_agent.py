"""
ValidatorAgent — Agent 3: Filters and scores schemes against the UserProfile.

Pipeline:
1. Hard-filter: Remove schemes where revenue, entity_type, or state is ineligible
2. LLM-score: Score remaining schemes 0-100 on 4 dimensions
3. Rank and return top 5 RankedScheme objects
4. Persist results to ranked_schemes table

This agent owns the `ranked_schemes` database table.
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
    Removes schemes where the user clearly doesn't qualify.

    Checks:
    - Revenue cap: user revenue must be <= scheme max_revenue_inr
    - Entity type: user entity must be in scheme's eligible list
    - State: user state must match (empty = pan-India, all allowed)
    - Team size: user team must be <= scheme max_team_size

    Args:
        schemes_json: JSON string of raw scheme objects from Agent 2
        profile_json: JSON string of UserProfile from Agent 1

    Returns:
        Filtered list of scheme dicts that pass all hard checks
    """
    schemes: List[Dict] = json.loads(schemes_json)
    profile: Dict = json.loads(profile_json)

    revenue = profile.get("annual_revenue_inr", 0) or profile.get("revenue_inr", 0) or 0
    entity_type = (profile.get("entity_type", "") or profile.get("type", "")).lower().strip()
    state = (profile.get("state", "") or "").lower().strip()
    team_size = profile.get("team_size", 0) or 0

    passed = []
    for s in schemes:
        # 1. Revenue cap check
        max_rev = s.get("max_revenue_inr")
        if max_rev and revenue > max_rev:
            continue

        # 2. Entity type check
        eligible_entities = s.get("eligible_entity_types", [])
        if isinstance(eligible_entities, str):
            try:
                eligible_entities = json.loads(eligible_entities)
            except json.JSONDecodeError:
                eligible_entities = []
        if eligible_entities:
            normalized = [e.lower().strip() for e in eligible_entities]
            if entity_type and entity_type not in normalized:
                continue

        # 3. State check (empty list = pan-India = all allowed)
        eligible_states = s.get("eligible_states", [])
        if isinstance(eligible_states, str):
            try:
                eligible_states = json.loads(eligible_states)
            except json.JSONDecodeError:
                eligible_states = []
        if eligible_states:
            normalized_states = [st.lower().strip() for st in eligible_states]
            if state and state not in normalized_states and "pan_india" not in normalized_states:
                continue

        # 4. Team size check
        max_team = s.get("max_team_size")
        if max_team and team_size > max_team:
            continue

        passed.append(s)

    return passed


hard_filter_tool = FunctionTool(func=hard_filter_schemes)


# ─── System Prompt ─────────────────────────────────────────────────────────────

VALIDATOR_SYSTEM_PROMPT = """You are GovGrant's eligibility validator and scoring engine.

INPUTS (in session state):
- `user_profile`: Structured UserProfile JSON
- `raw_schemes`: List of 15-25 raw scheme objects from ResearchAgent

YOUR TASK:
1. Call `hard_filter_schemes` with the raw schemes and user profile as JSON strings
2. Score each remaining scheme on 4 dimensions (0-100 composite):
   - Eligibility (0-40): How perfectly does the business meet hard criteria?
   - Relevance (0-30): How well does sector/purpose match the scheme?
   - Benefit (0-20): How valuable is the grant amount relative to business needs?
   - Ease (0-10): How easy is the application process?
3. Select the TOP 5 schemes by composite score
4. Return a JSON array of exactly 5 RankedScheme objects

SCORING RULES:
- Be strict: eligibility should be 40 only if ALL criteria match perfectly
- Prefer schemes with higher grant amounts for the user's stated purpose
- Women-led bonus: +5 to relevance if is_women_led AND scheme has women preference
- SC/ST bonus: +5 to relevance if is_sc_st_led AND scheme targets SC/ST founders
- Deadline urgency: schemes with deadlines within 30 days get urgency_score > 0.7
- Never include a scheme with composite score < 30

OUTPUT FORMAT: JSON array of 5 RankedScheme objects, ordered rank 1 (best) to 5.
Each object must have:
{
  "scheme_name": "string",
  "match_score": 85,
  "rank": 1,
  "reason": "1-2 sentence rationale",
  "urgency_score": 0.8,
  "composite_rank": 1,
  "portal_url": "https://...",
  "deadline": "2026-09-30",
  "grant_amount": "Up to Rs 50 lakhs"
}"""


# ─── Agent Factory ─────────────────────────────────────────────────────────────

def create_validator_agent(model: str = "gemini-2.0-flash") -> LlmAgent:
    """Create and return the configured ValidatorAgent."""
    return LlmAgent(
        name="validator_agent",
        model=model,
        description=(
            "Filters schemes by hard eligibility criteria (revenue cap, entity type, "
            "state, team size), then LLM-scores remaining schemes on 4 dimensions "
            "(eligibility, relevance, benefit, ease) to select and rank the top 5."
        ),
        instruction=VALIDATOR_SYSTEM_PROMPT,
        tools=[hard_filter_tool],
        output_key="ranked_schemes",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
