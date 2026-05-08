"""
GovGrant FastAPI Backend — Main Application
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestrator.pipeline import create_runner, stream_pipeline

# ─── Lifespan ──────────────────────────────────────────────────────────────────

_runner = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner
    os.makedirs("./data/chroma_db", exist_ok=True)
    os.makedirs("./data/scheme_pdfs", exist_ok=True)
    _runner = create_runner()
    print("✅ GovGrant pipeline runner initialized")
    yield
    print("🛑 GovGrant shutting down")


# ─── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="GovGrant API",
    description="AI grant discovery platform for Indian businesses",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:3000"),
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "govgrant-api"}


@app.post("/api/session", response_model=SessionResponse)
async def create_session():
    """Create a new chat session and return its ID."""
    session_id = str(uuid.uuid4())
    # Session is created lazily on first message in ADK
    return SessionResponse(session_id=session_id)


@app.post("/api/run")
async def run_pipeline(request: ChatRequest):
    """
    Main endpoint — streams SSE events as each agent completes.

    SSE event format:
        data: {"type": "agent_start"|"agent_complete"|"chat"|"report"|"error",
               "stage": str, "label": str, "step": int, "data": any}

    Client should listen with EventSource or fetch + ReadableStream.
    """
    if not _runner:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    user_id = request.user_id or f"user_{request.session_id[:8]}"

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in stream_pipeline(
            runner=_runner,
            user_id=user_id,
            session_id=request.session_id,
            message=request.message,
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/session/{session_id}/report")
async def get_report(session_id: str):
    """Retrieve a previously generated grant report for a session."""
    if not _runner:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    try:
        session = await _runner.session_service.get_session(
            app_name="govgrant",
            user_id=f"user_{session_id[:8]}",
            session_id=session_id,
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        report = session.state.get("grant_report")
        if not report:
            raise HTTPException(status_code=404, detail="Report not yet generated")
        return {"session_id": session_id, "report": report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Deadline Alert Webhook ────────────────────────────────────────────────────

class AlertRequest(BaseModel):
    email: str
    scheme_id: str
    scheme_name: str
    deadline: str  # ISO date string


@app.post("/api/alerts/subscribe")
async def subscribe_alert(request: AlertRequest):
    """
    Subscribe to deadline reminders for a specific scheme.
    Stores in SQLite; SendGrid cron job picks these up.
    """
    # TODO: Implement SQLite storage + SendGrid integration
    return {
        "status": "subscribed",
        "message": f"You'll receive a reminder 7 days before {request.deadline}",
        "scheme_id": request.scheme_id,
    }
