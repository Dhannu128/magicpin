"""Tick planner — picks which triggers to act on this tick, ranks them, composes in
parallel under the time budget, returns the action list."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .composer import Composer
from .determinism import conversation_id_for, render_template_params
from .state import AppState

logger = logging.getLogger("vera.tick")

TICK_BUDGET_SECONDS = float(os.getenv("TICK_TIME_BUDGET_SECONDS", "9"))
MAX_PARALLEL = int(os.getenv("LLM_MAX_PARALLEL", "4"))
MAX_ACTIONS = int(os.getenv("TICK_MAX_ACTIONS", "8"))


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _expired(trigger: dict, now: datetime) -> bool:
    expiry = _parse_iso(trigger.get("expires_at"))
    if not expiry:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return now > expiry


def _merchant_fit_score(merchant: dict, trigger: dict) -> float:
    """Heuristic: does this trigger actually match this merchant's signals/cohort?"""
    score = 1.0
    kind = trigger.get("kind", "")
    payload = trigger.get("payload") or {}
    signals = set(merchant.get("signals") or [])

    # Research about high-risk-adults → only fire if cohort signal present.
    if kind == "research_digest":
        seg = ((trigger.get("payload") or {}).get("patient_segment") or "")
        if seg == "high_risk_adults" and "high_risk_adult_cohort" not in signals:
            score *= 0.4

    # IPL only matters if locality is IPL-eligible.
    if kind == "ipl_match_today" and "ipl_eligible_locality" not in signals:
        # still useful, but lower
        score *= 0.7

    # Festival relevance for category.
    if kind == "festival_upcoming":
        relevance = payload.get("category_relevance") or []
        cat_slug = merchant.get("category_slug", "")
        if relevance and cat_slug not in relevance:
            score *= 0.3

    # GBP unverified only fires for unverified merchants.
    if kind == "gbp_unverified":
        if (merchant.get("identity") or {}).get("verified", True):
            score *= 0.1

    # Engaged-in-last-24h merchants get a small bump (they're warm).
    if "engaged_in_last_24h" in signals or "engaged_in_last_48h" in signals:
        score *= 1.2

    return score


class TickPlanner:
    def __init__(self, composer: Composer, state: AppState):
        self.composer = composer
        self.state = state

    async def plan(self, now_iso: str, available_triggers: list[str]) -> list[dict[str, Any]]:
        now = _parse_iso(now_iso) or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Filter, score, rank.
        candidates: list[tuple[float, dict, dict, dict | None, dict]] = []
        for tid in available_triggers or []:
            trigger = self.state.contexts.get("trigger", tid)
            if not trigger:
                logger.debug("tick: no trigger context for %s", tid)
                continue
            if _expired(trigger, now):
                logger.debug("tick: trigger %s expired", tid)
                continue

            merchant = self.state.contexts.find_merchant_for_trigger(trigger)
            if not merchant:
                logger.debug("tick: no merchant context for %s", tid)
                continue

            merchant_id = merchant.get("merchant_id") or trigger.get("merchant_id") or ""
            if self.state.suppressor.merchant_blocked(merchant_id):
                logger.info("tick: merchant %s blocked (hostile cooldown); skipping", merchant_id)
                continue

            kind = trigger.get("kind", "")
            sk = trigger.get("suppression_key") or f"{kind}:{merchant_id}:{now.date().isoformat()}"
            if self.state.suppressor.should_skip(sk, kind):
                logger.info("tick: suppressed %s (key=%s)", tid, sk)
                continue

            category = self.state.contexts.find_category_for_merchant(merchant)
            if not category:
                logger.debug("tick: no category for merchant %s", merchant_id)
                continue

            customer = self.state.contexts.find_customer(trigger.get("customer_id"))

            urgency = float(trigger.get("urgency") or 1)
            fit = _merchant_fit_score(merchant, trigger)
            rank = urgency * fit

            # Per-merchant cap of 1 in this tick (the brief: one action per (merchant, conversation_id)).
            candidates.append((rank, trigger, merchant, customer, category))

        # Sort high → low rank, but keep at most one per merchant.
        candidates.sort(key=lambda x: -x[0])
        chosen: list[tuple[float, dict, dict, dict | None, dict]] = []
        seen_merchants: set[str] = set()
        for c in candidates:
            mid = c[2].get("merchant_id", "")
            if mid in seen_merchants:
                continue
            seen_merchants.add(mid)
            chosen.append(c)
            if len(chosen) >= MAX_ACTIONS:
                break

        if not chosen:
            return []

        # 2. Compose in parallel under time budget.
        semaphore = asyncio.Semaphore(MAX_PARALLEL)

        async def _one(rank, trigger, merchant, customer, category):
            async with semaphore:
                send_as = "merchant_on_behalf" if customer else "vera"
                conv_id = conversation_id_for(merchant.get("merchant_id", ""), trigger.get("kind", ""), trigger.get("suppression_key", ""))
                conv = self.state.conversations.get(conv_id)
                prior = self.state.conversations.prior_bodies(conv_id) if conv else []
                conv_state = {"turn_number": 1 if not conv else len(conv.turns) + 1, "prior_bodies_in_conv": prior}
                composed = await self.composer.compose(
                    category=category, merchant=merchant, trigger=trigger,
                    customer=customer, send_as=send_as, conversation_state=conv_state,
                )
                return rank, trigger, merchant, customer, category, conv_id, composed

        # Each LLM call has its own client-side timeout; gather lets the fast ones
        # return even if a slow one hits its individual timeout. We ALSO race the
        # whole gather against a hard budget so we never miss our /tick deadline:
        # any tasks not done by the budget contribute a fallback body.
        tasks = [asyncio.create_task(_one(*c)) for c in chosen]
        try:
            done, pending = await asyncio.wait(tasks, timeout=TICK_BUDGET_SECONDS)
        except Exception as e:
            logger.warning("tick gather failed: %s", e)
            for t in tasks:
                t.cancel()
            return []
        results: list[Any] = []
        for t in done:
            try:
                results.append(t.result())
            except Exception as e:
                logger.warning("tick task error: %s", e)
        for t in pending:
            t.cancel()
            logger.info("tick: cancelling slow task at budget")

        actions: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("tick compose error: %s", r)
                continue
            rank, trigger, merchant, customer, category, conv_id, composed = r
            body = (composed.get("body") or "").strip()
            if not body:
                continue
            kind = trigger.get("kind", "")
            sk = trigger.get("suppression_key") or f"{kind}:{merchant.get('merchant_id','')}:{now.date().isoformat()}"
            send_as = "merchant_on_behalf" if customer else "vera"
            template_name = (
                f"merchant_{kind}_v1" if send_as == "merchant_on_behalf" else f"vera_{kind}_v1"
            )

            self.state.suppressor.mark(sk)
            # Register conversation so /reply can find it.
            self.state.conversations.get_or_create(
                conv_id,
                merchant_id=merchant.get("merchant_id", ""),
                customer_id=(customer or {}).get("customer_id") if customer else None,
                trigger_id=trigger.get("id"),
                send_as=send_as,
            )
            self.state.conversations.append_turn(conv_id, send_as, body, cta=composed.get("cta_kind", "open_ended"))

            params = render_template_params(body)
            actions.append({
                "conversation_id": conv_id,
                "merchant_id": merchant.get("merchant_id", ""),
                "customer_id": (customer or {}).get("customer_id") if customer else None,
                "send_as": send_as,
                "trigger_id": trigger.get("id", ""),
                "template_name": template_name,
                "template_params": params,
                "body": body,
                "cta": composed.get("cta_kind", "open_ended"),
                "suppression_key": sk,
                "rationale": composed.get("rationale", "")[:600],
            })

        return actions
