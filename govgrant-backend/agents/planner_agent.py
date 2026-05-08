"""
PlannerAgent — Agent 4: Generates the complete GrantReport.

Given top 5 RankedSchemes + UserProfile, produces:
1. Master documents checklist (consolidated, deduped across all 5 schemes)
2. Per-scheme action cards with steps, deadlines, portal links, tips
3. 150-word copy-ready cover summary for grant applications

This agent owns the `grant_reports` and `alerts` database tables.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types


# ─── Tool: persist report to DB ───────────────────────────────────────────────

def save_grant_report(
    session_id: str,
    documents_json: str,
    action_cards_json: str,
    cover_summary: str,
) -> str:
    """
    Persist the generated GrantReport to the grant_reports SQLite table.

    Args:
        session_id: UUID of the current session
        documents_json: JSON string of the documents checklist array
        action_cards_json: JSON string of the action cards array
        cover_summary: The 150-word cover summary text

    Returns:
        Confirmation message
    """
    # NOTE: In the ADK pipeline, this tool is declarative — the actual
    # DB persistence happens in planner_service.py which is called by
    # the routes.py pipeline endpoint. This tool exists so the LLM
    # knows the expected output shape.
    return f"Report saved for session {session_id}"


save_report_tool = FunctionTool(func=save_grant_report)


# ─── System Prompt ─────────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """You are GovGrant's action planner — the final step that turns
ranked schemes into an actionable grant report for Indian businesses.

INPUTS (in session state):
- `user_profile`: Structured UserProfile JSON
- `ranked_schemes`: Top 5 RankedScheme objects from ValidatorAgent

YOUR TASK: Generate a complete GrantReport JSON with EXACTLY 3 keys:

1. **"documents"** — A merged, deduplicated array of document objects.
   Each object: {"name": "string", "mandatory": true/false, "description": "brief note"}

   ALWAYS include these core documents:
   - Aadhaar Card of promoters (mandatory)
   - PAN Card — business + promoters (mandatory)
   - Certificate of Incorporation / Registration (mandatory)
   - GST Registration Certificate (mandatory if turnover > Rs 20L)
   - MSME / Udyam Registration Certificate (mandatory)
   - Bank Account Statements — last 6-12 months (mandatory)
   - Income Tax Returns — last 2-3 years (mandatory)
   - Business Plan / Project Report (mandatory)
   - Audited Financial Statements (if turnover > Rs 40L)

   Then ADD scheme-specific documents for each of the 5 schemes.
   Total: 10-15 documents, no duplicates.

2. **"action_cards"** — Array of EXACTLY one card per ranked scheme.
   Each object:
   {
     "scheme_name": "string",
     "portal_url": "string",
     "deadline": "string (ISO date or 'Rolling')",
     "steps": ["step 1", "step 2", ...],  // 5-7 ordered steps
     "estimated_days": number,  // realistic working days
     "tips": ["tip 1", "tip 2"]  // 2-3 insider tips
   }

3. **"cover_summary"** — Exactly ~150 words. A professional, persuasive paragraph:
   - First person ("We/Our business...")
   - Introduce the business (name, sector, state, entity type)
   - Highlight strengths (team size, revenue, years of operation)
   - State the specific funding purpose
   - Show alignment with government MSME/startup objectives
   - End with a confident request for consideration
   - Formal English, no bullet points

OUTPUT: Return ONLY a valid JSON object with keys: documents, action_cards, cover_summary.
No markdown fences, no explanation — just the JSON."""


# ─── Agent Factory ─────────────────────────────────────────────────────────────

def create_planner_agent(model: str = "gemini-2.0-flash") -> LlmAgent:
    """Create and return the configured PlannerAgent."""
    return LlmAgent(
        name="planner_agent",
        model=model,
        description=(
            "Generates the complete GrantReport: master documents checklist, "
            "per-scheme action cards with application steps and tips, and a "
            "150-word persuasive cover summary. Persists to grant_reports table."
        ),
        instruction=PLANNER_SYSTEM_PROMPT,
        tools=[save_report_tool],
        output_key="grant_report",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=8192,
        ),
    )
