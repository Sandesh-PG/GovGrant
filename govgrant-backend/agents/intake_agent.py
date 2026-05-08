"""
IntakeAgent — Conversational agent that collects 6 business profile fields
and returns a structured UserProfile JSON.

Uses Gemini 2.0 Flash to drive multi-turn conversation, detecting when
all required fields are collected and outputting structured JSON.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from schemas import UserProfile, Sector, EntityType, PurposeType

# ─── System Prompt ─────────────────────────────────────────────────────────────

INTAKE_SYSTEM_PROMPT = """You are GovGrant's intake specialist — a warm, professional assistant 
that helps Indian businesses find government grants and schemes.

Your task: Collect the following 6 fields through natural conversation:
1. **sector** — Business sector (agriculture, manufacturing, IT/tech, healthcare, education, 
   food_processing, textile, renewable_energy, fintech, retail, logistics, other)
2. **state** — Indian state of incorporation (use standard state names)
3. **annual_revenue_inr** — Annual revenue in INR (0 for pre-revenue startups)
4. **entity_type** — Legal entity (startup, msme, proprietorship, partnership, 
   private_limited, public_limited, ngo, other)
5. **team_size** — Number of full-time employees
6. **purpose** — Primary use of funds (working_capital, capex, r_and_d, export, hiring,
   technology_upgrade, market_expansion, sustainability, other)

ADDITIONAL fields to collect if mentioned:
- years_in_operation (years since incorporation)
- is_women_led (boolean — women-led enterprise?)
- is_sc_st_led (boolean — SC/ST founder?)
- has_existing_loans (boolean)

RULES:
- Be conversational — don't present as a form. Ask 1-2 questions at a time.
- Infer from context. e.g. "we make organic pickles" → sector: food_processing
- If user provides all info in one message, extract immediately
- When you have all 6 required fields, call the `finalize_profile` tool
- Speak in simple English, avoid jargon
- If the user writes in Hinglish or regional language, respond naturally but extract English values

Start: Greet the user and ask about their business."""


# ─── Tools ────────────────────────────────────────────────────────────────────

def finalize_profile(
    session_id: str,
    sector: str,
    state: str,
    annual_revenue_inr: float,
    entity_type: str,
    team_size: int,
    purpose: str,
    raw_description: str,
    years_in_operation: Optional[int] = None,
    is_women_led: bool = False,
    is_sc_st_led: bool = False,
    has_existing_loans: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Called by the agent when all required profile fields have been collected.
    Validates and returns a structured UserProfile.
    """
    profile = UserProfile(
        session_id=session_id,
        sector=Sector(sector.lower().replace(" ", "_").replace("/", "_")),
        state=state.title(),
        annual_revenue_inr=annual_revenue_inr,
        entity_type=EntityType(entity_type.lower().replace(" ", "_")),
        team_size=team_size,
        purpose=PurposeType(purpose.lower().replace(" ", "_")),
        raw_description=raw_description,
        years_in_operation=years_in_operation,
        is_women_led=is_women_led,
        is_sc_st_led=is_sc_st_led,
        has_existing_loans=has_existing_loans,
    )
    return profile.model_dump()


finalize_profile_tool = FunctionTool(func=finalize_profile)


# ─── Agent Factory ─────────────────────────────────────────────────────────────

def create_intake_agent(model: str = "gemini-2.0-flash") -> LlmAgent:
    """Create and return the configured IntakeAgent."""
    return LlmAgent(
        name="intake_agent",
        model=model,
        description=(
            "Conversational agent that collects business profile information "
            "through natural dialogue and outputs a structured UserProfile JSON."
        ),
        instruction=INTAKE_SYSTEM_PROMPT,
        tools=[finalize_profile_tool],
        output_key="user_profile",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1024,
        ),
    )


# ─── Standalone runner (for testing) ──────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    async def test_intake():
        session_service = InMemorySessionService()
        agent = create_intake_agent()
        runner = Runner(
            agent=agent,
            app_name="govgrant_intake_test",
            session_service=session_service,
        )
        session = await session_service.create_session(
            app_name="govgrant_intake_test",
            user_id="test_user",
        )
        messages = [
            "Hi! I run a small organic food processing unit in Maharashtra. "
            "We're a private limited company, 3 years old, team of 12 people, "
            "annual revenue around 80 lakhs. Looking for capital to upgrade our packaging machinery.",
        ]
        for msg in messages:
            print(f"\nUser: {msg}")
            content = types.Content(role="user", parts=[types.Part(text=msg)])
            async for event in runner.run_async(
                user_id="test_user",
                session_id=session.id,
                new_message=content,
            ):
                if event.is_final_response():
                    print(f"Agent: {event.content.parts[0].text}")

    asyncio.run(test_intake())
