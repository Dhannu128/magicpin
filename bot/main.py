"""Vera bot — FastAPI app exposing the 5 challenge endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

from .composer import Composer
from .llm import LLM
from .reply_router import ReplyRouter
from .state import AppState
from .tick_planner import TickPlanner

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("vera.main")

# ─── App + globals ──────────────────────────────────────────────────────────

app = FastAPI(title="Vera — magicpin AI Challenge bot", version=os.getenv("BOT_VERSION", "1.0.0"))

state = AppState()
llm = LLM()
composer = Composer(llm)
tick_planner = TickPlanner(composer, state)
reply_router = ReplyRouter(composer, state)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ─── Pydantic models for inbound requests ───────────────────────────────────

class ContextBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str | None = None


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str = "merchant"
    message: str
    received_at: str | None = None
    turn_number: int = 1


# ─── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int((datetime.now(timezone.utc) - state.started_at).total_seconds()),
        "contexts_loaded": state.contexts.counts(),
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": os.getenv("TEAM_NAME", "Pro Bro"),
        "team_members": [m.strip() for m in os.getenv("TEAM_MEMBERS", "Dhannu Ram Meena").split(",") if m.strip()],
        "model": llm.primary,
        "approach": (
            "Per-trigger-kind prompt routing with structured facts-pack guardrails, "
            "deterministic post-LLM validator (no URL / no taboo / no fabricated numbers / single CTA / language honored / no repeat), "
            "voice packs derived from CategoryContext, stateful idempotent context store, "
            "replay-aware reply router (auto-reply / hostile / intent-transition / curveball / wait detectors), "
            "deterministic per-kind fallback templates if the LLM call times out or fails validation twice."
        ),
        "contact_email": os.getenv("CONTACT_EMAIL", "dhannumeena281229111@gmail.com"),
        "version": os.getenv("BOT_VERSION", "1.0.0"),
        "submitted_at": _utcnow_iso(),
    }


@app.post("/v1/context")
async def push_context(body: ContextBody):
    accepted, extras = state.contexts.put(body.scope, body.context_id, body.version, body.payload)
    if not accepted:
        if extras.get("reason") == "stale_version":
            return JSONResponse(status_code=409, content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": extras.get("current_version"),
            })
        return JSONResponse(status_code=400, content={
            "accepted": False,
            "reason": extras.get("reason", "invalid"),
            "details": extras.get("details", ""),
        })
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": extras.get("stored_at", _utcnow_iso()),
    }


@app.post("/v1/tick")
async def tick(body: TickBody):
    try:
        actions = await tick_planner.plan(body.now, body.available_triggers or [])
    except Exception as e:
        logger.exception("tick failed: %s", e)
        actions = []
    return {"actions": actions}


@app.post("/v1/reply")
async def reply(body: ReplyRequest):
    merchant_id = body.merchant_id or ""
    try:
        decision = await reply_router.route(
            conv_id=body.conversation_id,
            merchant_id=merchant_id,
            message=body.message,
            turn_number=body.turn_number,
            customer_id=body.customer_id,
        )
    except Exception as e:
        logger.exception("reply route failed: %s", e)
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Internal error during reply routing; backing off 30 min for safety.",
        }

    if decision.action == "send":
        return {"action": "send", "body": decision.body, "cta": decision.cta, "rationale": decision.rationale}
    if decision.action == "wait":
        return {"action": "wait", "wait_seconds": decision.wait_seconds, "rationale": decision.rationale}
    if decision.action == "end":
        return {"action": "end", "rationale": decision.rationale}
    # Defensive default
    return {"action": "wait", "wait_seconds": 1800, "rationale": "Unrecognized decision; default wait."}


# ─── Optional: teardown for the testing brief §11 ──────────────────────────

@app.post("/v1/teardown")
async def teardown():
    state.contexts._store.clear()
    state.conversations._convs.clear()
    state.suppressor._sent.clear()
    state.suppressor._merchant_cooldown.clear()
    state.suppressor._merchant_auto_reply_strikes.clear()
    return {"accepted": True, "wiped_at": _utcnow_iso()}


# ─── uvicorn entry ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")), reload=False)
