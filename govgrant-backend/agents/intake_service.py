"""
IntakeService — Gemini-powered 10-step structured JSON intake.

Gemini is instructed to ALWAYS return a JSON envelope:
  { step, message, input_type, options, field, collected }

This lets the frontend render option pills, confirm buttons, profile
summaries and scheme cards rather than raw chat bubbles.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import google.genai as genai
from config import settings

logger = logging.getLogger("govgrant.intake")

# ─── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional Government Funding Intake Agent for India. Your job is to collect essential information from a client step-by-step to assess their eligibility for central and state government funding schemes.

---

## RESPONSE FORMAT (CRITICAL — ALWAYS FOLLOW)

You must ALWAYS respond in the following strict JSON format. Never respond with plain text.

{
  "step": <number from 1 to 10, or "summary", or "schemes">,
  "message": "<your conversational message to the client>",
  "input_type": "<one of: options | text | confirm | none>",
  "options": ["<option 1>", "<option 2>", ...],
  "field": "<the data field being collected>",
  "collected": {
    "<field_name>": "<value collected so far>"
  }
}

### Field descriptions:
- "step": Current step number (1–10). Use "summary" when presenting the final profile. Use "schemes" when listing eligible schemes.
- "message": What the agent says to the client. Keep it to 2–4 sentences max.
- "input_type":
    - "options" → show clickable buttons to the user
    - "text" → show a free-text input box
    - "confirm" → show Yes / No buttons
    - "none" → no input needed (informational message only)
- "options": Array of button labels. Only populate when input_type is "options" or "confirm".
- "field": The name of the data field currently being collected.
- "collected": A running object of all fields collected so far in this conversation.

---

## BEHAVIOUR RULES

- Ask only ONE question per turn.
- Always acknowledge the previous answer briefly before asking the next question.
- Keep tone professional yet warm — like a government liaison officer.
- If the answer is vague, set input_type to "options" again with the same options and add a clarification note in "message".
- Never skip a step.
- Do not recommend schemes until all 10 steps are complete and the client confirms.
- Never return plain text — always return valid JSON.

---

## INTAKE STEPS

Step 1 — field: "name_and_org"
Ask for full name and business/organisation name.
input_type: text
options: []

Step 2 — field: "state"
Ask which state they operate from. Mention it helps identify state-level schemes.
input_type: options
options: ["Karnataka", "Maharashtra", "Tamil Nadu", "Delhi", "Telangana", "Gujarat", "Punjab", "Rajasthan", "Uttar Pradesh", "Kerala", "Other"]

Step 3 — field: "sector"
Ask the primary business sector.
input_type: options
options: ["Agritech / Agriculture", "Manufacturing", "IT / Software", "Healthcare", "Clean Energy", "Retail / Commerce", "Education / Edtech", "Other"]

Step 4 — field: "business_stage"
Ask the current stage of the business.
input_type: options
options: ["Idea / Pre-revenue", "Early stage (< 1 year)", "Growth stage (1–3 years)", "Established (3+ years)"]

Step 5 — field: "annual_turnover"
Ask approximate annual turnover. Mention PMEGP / MSME thresholds.
input_type: options
options: ["Not yet generating revenue", "Under ₹10 lakhs", "₹10–₹50 lakhs", "₹50 lakhs–₹1 crore", "Above ₹1 crore"]

Step 6 — field: "employee_count"
Ask current number of employees.
input_type: options
options: ["Just myself (solo)", "2–10", "11–50", "51–200", "200+"]

Step 7 — field: "funding_type"
Ask what type of funding they are seeking.
input_type: options
options: ["Grant (non-repayable)", "Subsidised loan", "Equity / Seed funding", "Tax benefits / exemptions", "Infrastructure support", "Not sure — show me options"]

Step 8 — field: "funding_purpose"
Ask the primary purpose of the funding.
input_type: options
options: ["Research & development", "Equipment / machinery", "Working capital", "Export promotion", "Hiring & training", "Digital transformation", "Other"]

Step 9 — field: "legal_registration"
Ask if they are registered and what type.
input_type: options
options: ["Sole proprietorship", "Partnership / LLP", "Private Limited", "Public Limited", "NGO / Trust / Society", "Not yet registered"]

Step 10 — field: "certifications"
Ask about existing certifications. Briefly explain Udyam and DPIIT if needed.
input_type: options
options: ["Udyam / MSME registration", "DPIIT Startup recognition", "ISO certification", "FSSAI / BIS / other regulatory", "None of the above"]

---

## AFTER STEP 10 — SUMMARY

Set step to "summary". Present the full collected profile in the message field as a readable summary. Then ask for confirmation to proceed.

input_type: confirm
options: ["Yes, show me eligible schemes", "I want to edit my answers"]

---

## AFTER CONFIRMATION — SCHEMES

Set step to "schemes". List the top 3–5 most relevant central and state government schemes in the message field. For each scheme include:
- Scheme name
- Administering body
- Why eligible (based on collected data)
- How to apply (1 line)

input_type: none
options: []

---

## OPENING MESSAGE (first response — no user input yet)

{
  "step": 1,
  "message": "Hello! Welcome. I'm your Government Funding Intake Assistant. I'm here to help you identify and apply for central and state government funding schemes that best fit your business.\\n\\nThis will just take a few minutes. Could you please share your full name and the name of your business or organisation?",
  "input_type": "text",
  "options": [],
  "field": "name_and_org",
  "collected": {}
}
"""

# ─── Helpers ───────────────────────────────────────────────────────────────────


def _build_messages(history: List[Dict], user_message: str) -> list:
    """Build Gemini message list from chat history."""
    messages = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", msg.get("text", ""))
        if role == "assistant":
            role = "model"
        messages.append({"role": role, "parts": [{"text": content}]})
    messages.append({"role": "user", "parts": [{"text": user_message}]})
    return messages


def _parse_agent_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract and parse the JSON object from agent response text."""
    if not text:
        return None

    # Direct parse
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Markdown code block
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # Bare JSON object anywhere in text
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _map_profile_to_legacy(agent_json: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
    """
    Convert the structured collected fields to the legacy DB profile format
    so the downstream pipeline (research → validator → planner) can work.
    """
    collected = agent_json.get("collected", {})
    if not collected:
        return None

    # Turnover → revenue_inr
    turnover_map = {
        "not yet generating revenue": 0,
        "under ₹10 lakhs": 900_000,
        "₹10–₹50 lakhs": 3_000_000,
        "₹50 lakhs–₹1 crore": 7_500_000,
        "above ₹1 crore": 15_000_000,
    }
    turnover_str = (collected.get("annual_turnover") or "").lower()
    revenue_inr = 0
    for key, val in turnover_map.items():
        if key in turnover_str:
            revenue_inr = val
            break

    # Employee count → team_size
    employee_map = {
        "just myself": 1, "solo": 1,
        "2–10": 6, "2-10": 6,
        "11–50": 30, "11-50": 30,
        "51–200": 125, "51-200": 125,
        "200+": 250,
    }
    emp_str = (collected.get("employee_count") or "").lower()
    team_size = 1
    for key, val in employee_map.items():
        if key in emp_str:
            team_size = val
            break

    # Sector
    sector_map = {
        "agritech": "agriculture", "agriculture": "agriculture",
        "manufacturing": "manufacturing",
        "it": "it_tech", "software": "it_tech",
        "healthcare": "healthcare",
        "clean energy": "renewable_energy",
        "retail": "retail", "commerce": "retail",
        "education": "education", "edtech": "education",
    }
    sector_str = (collected.get("sector") or "").lower()
    sector = "other"
    for key, val in sector_map.items():
        if key in sector_str:
            sector = val
            break

    # Registration type → entity type
    reg_map = {
        "sole proprietorship": "proprietorship",
        "partnership": "partnership", "llp": "llp",
        "private limited": "private_limited",
        "public limited": "public_limited",
        "ngo": "ngo", "trust": "ngo", "society": "ngo",
        "not yet registered": "startup",
    }
    reg_str = (collected.get("legal_registration") or "").lower()
    entity_type = "other"
    for key, val in reg_map.items():
        if key in reg_str:
            entity_type = val
            break

    # Funding purpose
    purpose_map = {
        "research": "r_and_d",
        "equipment": "technology_upgrade", "machinery": "technology_upgrade",
        "working capital": "working_capital",
        "export": "export_promotion",
        "hiring": "hiring", "training": "hiring",
        "digital": "technology_upgrade",
    }
    purpose_str = (collected.get("funding_purpose") or "").lower()
    funding_purpose = "other"
    for key, val in purpose_map.items():
        if key in purpose_str:
            funding_purpose = val
            break

    name_and_org = collected.get("name_and_org", "")
    parts = [p.strip() for p in name_and_org.split(",") if p.strip()]
    full_name = parts[0] if parts else name_and_org
    business_name = parts[1] if len(parts) > 1 else name_and_org

    return {
        "full_name": full_name,
        "name": business_name,
        "type": entity_type,
        "sector": sector,
        "state": collected.get("state", ""),
        "city": "",
        "business_stage": collected.get("business_stage", ""),
        "annual_turnover": collected.get("annual_turnover", ""),
        "employee_count": collected.get("employee_count", ""),
        "funding_type": collected.get("funding_type", ""),
        "funding_purpose": collected.get("funding_purpose", ""),
        "registration_type": collected.get("legal_registration", ""),
        "certifications": collected.get("certifications", ""),
        "team_size": team_size,
        "revenue_inr": revenue_inr,
        "session_id": session_id,
    }


# ─── Main service ──────────────────────────────────────────────────────────────


async def process_intake_message(
    session_id: str,
    message: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Send user message to Gemini for structured JSON intake.

    Returns:
        {
            "reply": str,             # plain text from message field
            "intake_complete": bool,  # True when step == "schemes"
            "profile": dict | None,   # legacy profile for DB persistence
            "fields_collected": int,
            "total_fields": 10,
            "agent_response": dict    # full structured JSON from agent
        }
    """
    logger.info("[%s] Intake message: %.100s", session_id, message)

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    contents = _build_messages(history, message)

    reply_text = ""
    # Call Gemini — the system prompt enforces JSON output
    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=2048,
            ),
        )
        reply_text = response.text or ""
    except Exception as e:
        logger.error("[%s] Gemini call failed: %s", session_id, str(e))
        raise

    # Parse structured JSON
    agent_json = _parse_agent_json(reply_text)

    if agent_json:
        step = agent_json.get("step")
        collected = agent_json.get("collected") or {}
        message_text = agent_json.get("message", "")

        # Pipeline kicks off when the agent presents eligible schemes
        intake_complete = step == "schemes"
        profile = None
        if intake_complete:
            profile = _map_profile_to_legacy(agent_json, session_id)
            logger.info(
                "[%s] INTAKE COMPLETE — profile: %s",
                session_id, json.dumps(profile or {}),
            )

        fields_collected = len([v for v in collected.values() if v])

        logger.info(
            "[%s] Structured step=%s fields=%d/10",
            session_id, step, fields_collected,
        )
        return {
            "reply": message_text,
            "intake_complete": intake_complete,
            "profile": profile,
            "fields_collected": fields_collected,
            "total_fields": 10,
            "agent_response": agent_json,
        }

    # Fallback: agent returned plain text
    logger.warning("[%s] Agent returned non-JSON, using plain text fallback", session_id)
    user_msgs = len([m for m in history if m.get("role") == "user"]) + 1
    estimated = min(user_msgs, 9)

    fallback_json = {
        "step": estimated,
        "message": reply_text,
        "input_type": "text",
        "options": [],
        "field": "",
        "collected": {},
    }
    return {
        "reply": reply_text,
        "intake_complete": False,
        "profile": None,
        "fields_collected": estimated,
        "total_fields": 10,
        "agent_response": fallback_json,
    }
