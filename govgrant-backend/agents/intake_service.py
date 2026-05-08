"""
IntakeService - Real Gemini-powered conversational intake.

Calls Gemini 2.0 Flash directly to:
1. Have a natural conversation collecting 6 business fields
2. Detect when all fields are collected
3. Return structured JSON profile

No ADK dependency - just clean Gemini API calls.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import google.genai as genai
from config import settings

logger = logging.getLogger("govgrant.intake")

SYSTEM_PROMPT = """You are GovGrant's intake assistant. You help Indian businesses find government grants.

Your job: Collect these 6 fields through natural conversation:
1. name - Business name
2. type - Entity type (startup, msme, proprietorship, partnership, private_limited, public_limited, ngo, other)
3. sector - Business sector (agriculture, manufacturing, it_tech, healthcare, education, food_processing, textile, renewable_energy, fintech, retail, logistics, other)
4. state - Indian state (and city if mentioned)
5. team_size - Number of employees (integer)
6. revenue_and_purpose - Annual revenue in INR + what they need funding for

RULES:
- Be warm, conversational. Ask 1-2 questions at a time.
- If the user gives multiple fields in one message, accept them all.
- When you have ALL 6 fields, respond with EXACTLY this format at the END of your message:

|||PROFILE_COMPLETE|||
{"name": "...", "type": "...", "sector": "...", "state": "...", "city": "...", "team_size": N, "revenue_inr": N, "funding_purpose": "..."}
|||END|||

- revenue_inr should be a number (e.g. 8000000 for 80 lakhs)
- Do NOT output the PROFILE_COMPLETE block until you have all 6 fields.
- If user says something unclear, ask for clarification.
- Keep responses short (2-3 sentences max).
"""


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


async def process_intake_message(
    session_id: str,
    message: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Send user message to Gemini for conversational intake.

    Returns:
        {
            "reply": str,
            "intake_complete": bool,
            "profile": dict | None,
            "fields_collected": int,
            "total_fields": 6
        }
    """
    logger.info("[%s] Intake message: %.100s", session_id, message)

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    # Build conversation
    contents = _build_messages(history, message)

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )
        reply_text = response.text or ""
    except Exception as e:
        logger.error("[%s] Gemini API error: %s", session_id, str(e))
        raise

    # Check if profile is complete
    profile_data = _extract_profile(reply_text, session_id)

    if profile_data:
        # Strip the PROFILE_COMPLETE block from the visible reply
        clean_reply = re.split(r"\|\|\|PROFILE_COMPLETE\|\|\|", reply_text)[0].strip()
        if not clean_reply:
            clean_reply = "Perfect! I have all the details I need. Starting grant search now..."

        logger.info(
            "[%s] INTAKE COMPLETE - Profile: %s",
            session_id, json.dumps(profile_data),
        )
        return {
            "reply": clean_reply,
            "intake_complete": True,
            "profile": profile_data,
            "fields_collected": 6,
            "total_fields": 6,
        }

    # Estimate fields collected from conversation length
    user_msgs = len([m for m in history if m.get("role") == "user"]) + 1
    estimated = min(user_msgs, 5)

    logger.info(
        "[%s] Intake continuing - estimated %d/6 fields, reply: %.100s",
        session_id, estimated, reply_text,
    )
    return {
        "reply": reply_text,
        "intake_complete": False,
        "profile": None,
        "fields_collected": estimated,
        "total_fields": 6,
    }


def _extract_profile(text: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Extract profile JSON from the PROFILE_COMPLETE block if present."""
    match = re.search(
        r"\|\|\|PROFILE_COMPLETE\|\|\|\s*(\{.*?\})\s*\|\|\|END\|\|\|",
        text,
        re.DOTALL,
    )
    if not match:
        return None

    try:
        profile = json.loads(match.group(1))
        # Validate required fields
        required = ["name", "type", "sector", "state", "team_size", "revenue_inr"]
        missing = [f for f in required if f not in profile or profile[f] is None]
        if missing:
            logger.warning("[%s] Profile missing fields: %s", session_id, missing)
            return None

        # Ensure numeric types
        profile["team_size"] = int(profile["team_size"])
        profile["revenue_inr"] = int(profile["revenue_inr"])
        profile.setdefault("city", "")
        profile.setdefault("funding_purpose", "general")
        profile["session_id"] = session_id

        return profile
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error("[%s] Failed to parse profile JSON: %s", session_id, str(e))
        return None
