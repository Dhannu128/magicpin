"""Stateful in-memory stores: contexts, conversations, suppression.

Survives across requests (single uvicorn process); lost on restart — the brief
explicitly permits this.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger("vera.state")


# ─── Context store ──────────────────────────────────────────────────────────

@dataclass
class StoredContext:
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    stored_at: str  # iso8601


class ContextStore:
    """Idempotent on (scope, context_id, version). Higher version replaces atomically."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: dict[tuple[str, str], StoredContext] = {}

    def put(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Returns (accepted, response_extras)."""
        if scope not in {"category", "merchant", "customer", "trigger"}:
            return False, {"reason": "invalid_scope", "details": f"scope must be one of category/merchant/customer/trigger, got {scope!r}"}

        key = (scope, context_id)
        with self._lock:
            existing = self._store.get(key)
            if existing and existing.version >= version:
                return False, {"reason": "stale_version", "current_version": existing.version}
            stored = StoredContext(
                scope=scope,
                context_id=context_id,
                version=version,
                payload=payload,
                stored_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            self._store[key] = stored
        logger.info("ctx put %s/%s v%d", scope, context_id, version)
        return True, {"stored_at": stored.stored_at}

    def get(self, scope: str, context_id: str) -> dict[str, Any] | None:
        with self._lock:
            v = self._store.get((scope, context_id))
            return v.payload if v else None

    def get_version(self, scope: str, context_id: str) -> int | None:
        with self._lock:
            v = self._store.get((scope, context_id))
            return v.version if v else None

    def all_of_scope(self, scope: str) -> Iterable[dict[str, Any]]:
        with self._lock:
            return [v.payload for (s, _), v in self._store.items() if s == scope]

    def counts(self) -> dict[str, int]:
        out = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (s, _), _ in self._store.items():
                out[s] = out.get(s, 0) + 1
        return out

    def find_merchant_for_trigger(self, trigger_payload: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve trigger.merchant_id → MerchantContext payload, if present."""
        mid = trigger_payload.get("merchant_id")
        if not mid:
            return None
        return self.get("merchant", mid)

    def find_category_for_merchant(self, merchant_payload: dict[str, Any]) -> dict[str, Any] | None:
        slug = merchant_payload.get("category_slug")
        if not slug:
            return None
        return self.get("category", slug)

    def find_customer(self, customer_id: str | None) -> dict[str, Any] | None:
        if not customer_id:
            return None
        return self.get("customer", customer_id)


# ─── Conversation store ─────────────────────────────────────────────────────

@dataclass
class ConversationTurn:
    role: str  # "vera" | "merchant" | "customer" | "merchant_on_behalf"
    body: str
    cta: str
    ts: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Conversation:
    conversation_id: str
    merchant_id: str
    customer_id: str | None
    trigger_id: str | None
    send_as: str
    turns: list[ConversationTurn] = field(default_factory=list)
    auto_reply_strikes: int = 0
    ended: bool = False
    end_reason: str | None = None
    last_inbound_lang: str | None = None  # language signal from latest merchant reply
    last_bot_message: str | None = None
    waiting_until_ts: str | None = None


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._convs: dict[str, Conversation] = {}

    def get(self, conv_id: str) -> Conversation | None:
        with self._lock:
            return self._convs.get(conv_id)

    def get_or_create(
        self,
        conv_id: str,
        merchant_id: str,
        customer_id: str | None = None,
        trigger_id: str | None = None,
        send_as: str = "vera",
    ) -> Conversation:
        with self._lock:
            c = self._convs.get(conv_id)
            if c is None:
                c = Conversation(
                    conversation_id=conv_id,
                    merchant_id=merchant_id,
                    customer_id=customer_id,
                    trigger_id=trigger_id,
                    send_as=send_as,
                )
                self._convs[conv_id] = c
            return c

    def append_turn(self, conv_id: str, role: str, body: str, cta: str = "", **meta: Any) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            c = self._convs.get(conv_id)
            if c is None:
                logger.warning("append_turn on unknown conv %s — creating bare", conv_id)
                c = Conversation(conversation_id=conv_id, merchant_id="", customer_id=None, trigger_id=None, send_as="vera")
                self._convs[conv_id] = c
            c.turns.append(ConversationTurn(role=role, body=body, cta=cta, ts=ts, meta=meta))
            if role in {"vera", "merchant_on_behalf"}:
                c.last_bot_message = body

    def end(self, conv_id: str, reason: str) -> None:
        with self._lock:
            c = self._convs.get(conv_id)
            if c:
                c.ended = True
                c.end_reason = reason

    def is_ended(self, conv_id: str) -> bool:
        with self._lock:
            c = self._convs.get(conv_id)
            return bool(c and c.ended)

    def prior_bodies(self, conv_id: str) -> list[str]:
        with self._lock:
            c = self._convs.get(conv_id)
            if not c:
                return []
            return [t.body for t in c.turns if t.role in {"vera", "merchant_on_behalf"}]


# ─── Suppression / dedup ────────────────────────────────────────────────────

KIND_DEFAULT_TTL_SECONDS = {
    "research_digest": 7 * 24 * 3600,            # 1 week
    "regulation_change": 14 * 24 * 3600,         # 2 weeks (deadline-driven anyway)
    "supply_alert": 24 * 3600,                   # 1 day per merchant per molecule
    "perf_spike": 7 * 24 * 3600,
    "perf_dip": 7 * 24 * 3600,
    "seasonal_perf_dip": 30 * 24 * 3600,
    "milestone_reached": 30 * 24 * 3600,
    "dormant_with_vera": 14 * 24 * 3600,
    "curious_ask_due": 7 * 24 * 3600,
    "winback_eligible": 14 * 24 * 3600,
    "ipl_match_today": 24 * 3600,
    "festival_upcoming": 7 * 24 * 3600,
    "weather_heatwave": 24 * 3600,
    "review_theme_emerged": 14 * 24 * 3600,
    "competitor_opened": 30 * 24 * 3600,
    "renewal_due": 7 * 24 * 3600,
    "gbp_unverified": 14 * 24 * 3600,
    "cde_opportunity": 7 * 24 * 3600,
    "active_planning_intent": 24 * 3600,
    "category_seasonal": 14 * 24 * 3600,
    "recall_due": 6 * 30 * 24 * 3600,            # 6 months
    "chronic_refill_due": 30 * 24 * 3600,
    "trial_followup": 14 * 24 * 3600,
    "wedding_package_followup": 14 * 24 * 3600,
    "customer_lapsed_hard": 60 * 24 * 3600,      # 60 days; one shot
}
DEFAULT_TTL_SECONDS = 7 * 24 * 3600
HOSTILE_MERCHANT_SUPPRESS_DAYS = 30


class Suppressor:
    """Tracks which (suppression_key) we've sent and when, plus per-merchant cooldowns."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sent: dict[str, datetime] = {}  # suppression_key -> last_sent_utc
        self._merchant_cooldown: dict[str, datetime] = {}  # merchant_id -> blocked_until_utc

    def should_skip(self, suppression_key: str | None, kind: str) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            last = self._sent.get(suppression_key)
            if last is None:
                return False
            ttl_s = KIND_DEFAULT_TTL_SECONDS.get(kind, DEFAULT_TTL_SECONDS)
            return (datetime.now(timezone.utc) - last) < timedelta(seconds=ttl_s)

    def mark(self, suppression_key: str | None) -> None:
        if not suppression_key:
            return
        with self._lock:
            self._sent[suppression_key] = datetime.now(timezone.utc)

    def merchant_blocked(self, merchant_id: str) -> bool:
        if not merchant_id:
            return False
        with self._lock:
            until = self._merchant_cooldown.get(merchant_id)
            if not until:
                return False
            return datetime.now(timezone.utc) < until

    def block_merchant(self, merchant_id: str, days: int = HOSTILE_MERCHANT_SUPPRESS_DAYS) -> None:
        with self._lock:
            self._merchant_cooldown[merchant_id] = datetime.now(timezone.utc) + timedelta(days=days)
            logger.info("blocking merchant %s for %d days", merchant_id, days)


# ─── A single global instance bag (held by main.py) ─────────────────────────

@dataclass
class AppState:
    contexts: ContextStore = field(default_factory=ContextStore)
    conversations: ConversationStore = field(default_factory=ConversationStore)
    suppressor: Suppressor = field(default_factory=Suppressor)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
