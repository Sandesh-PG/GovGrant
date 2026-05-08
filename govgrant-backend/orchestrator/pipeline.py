"""
GovGrant ADK Pipeline — SequentialAgent wiring all 4 agents.

Flow:  intake_agent → research_agent → validator_agent → planner_agent

Each agent reads from and writes to shared session state via output_key.
The pipeline streams SSE events at each agent completion boundary.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from agents import (
    create_intake_agent,
    research_agent,
    create_validator_agent,
    create_planner_agent,
)

# ─── App constants ─────────────────────────────────────────────────────────────

APP_NAME = "govgrant"
DB_URL = os.getenv("SQLITE_URL", "sqlite:///./data/govgrant.db")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


# ─── Pipeline factory ──────────────────────────────────────────────────────────

def create_pipeline() -> SequentialAgent:
    """Wire all 4 agents into a SequentialAgent pipeline."""
    return SequentialAgent(
        name="govgrant_pipeline",
        description="End-to-end grant discovery pipeline for Indian businesses.",
        sub_agents=[
            create_intake_agent(MODEL),
            research_agent,
            create_validator_agent(MODEL),
            create_planner_agent(MODEL),
        ],
    )


# ─── Runner factory ────────────────────────────────────────────────────────────

def create_runner() -> Runner:
    """Create the ADK Runner with persistent SQLite session service."""
    session_service = DatabaseSessionService(db_url=DB_URL)
    pipeline = create_pipeline()
    return Runner(
        agent=pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )


# ─── SSE event stream ──────────────────────────────────────────────────────────

AGENT_STAGE_MAP = {
    "intake_agent": {"stage": "intake", "label": "Collecting Business Profile", "step": 1},
    "research_agent": {"stage": "research", "label": "Searching Grant Schemes", "step": 2},
    "validator_agent": {"stage": "validation", "label": "Validating Eligibility", "step": 3},
    "planner_agent": {"stage": "planning", "label": "Building Your Report", "step": 4},
}


async def stream_pipeline(
    runner: Runner,
    user_id: str,
    session_id: str,
    message: str,
) -> AsyncGenerator[dict, None]:
    """
    Run the pipeline and yield SSE-ready dicts at each agent boundary.

    Yields events shaped as:
    {
        "type": "agent_start" | "agent_complete" | "chat" | "report" | "error",
        "stage": str,
        "label": str,
        "step": int,
        "data": any,
    }
    """
    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )

    current_agent = None

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            agent_name = getattr(event, "author", None)
            stage_info = AGENT_STAGE_MAP.get(agent_name, {})

            # Agent start
            if agent_name and agent_name != current_agent and stage_info:
                current_agent = agent_name
                yield {
                    "type": "agent_start",
                    "stage": stage_info["stage"],
                    "label": stage_info["label"],
                    "step": stage_info["step"],
                    "data": None,
                }

            # Intermediate chat responses from intake agent
            if (
                agent_name == "intake_agent"
                and event.content
                and not event.is_final_response()
            ):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        yield {
                            "type": "chat",
                            "stage": "intake",
                            "label": "GovGrant Assistant",
                            "step": 1,
                            "data": part.text,
                        }

            # Agent completion
            if event.is_final_response() and stage_info:
                # Final report from planner
                if agent_name == "planner_agent":
                    report_data = None
                    if event.content and event.content.parts:
                        report_data = event.content.parts[0].text
                    yield {
                        "type": "report",
                        "stage": "complete",
                        "label": "Report Ready",
                        "step": 4,
                        "data": report_data,
                    }
                else:
                    yield {
                        "type": "agent_complete",
                        "stage": stage_info["stage"],
                        "label": stage_info["label"],
                        "step": stage_info["step"],
                        "data": None,
                    }

    except Exception as exc:
        yield {
            "type": "error",
            "stage": "error",
            "label": "Pipeline Error",
            "step": 0,
            "data": str(exc),
        }
