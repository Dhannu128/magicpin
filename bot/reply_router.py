"""Reply router — detectors A through G, in priority order.

A. Auto-reply detection
B. Hard opt-out / hostile
C. Intent transition  ← switch to ACTION
D. Off-topic / curveball
E. Engaged answer
F. Wait signals
G. (mid-stream context updates handled by always reading current store)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .composer import Composer, build_facts_pack
from .determinism import canonical_json
from .state import AppState, Conversation
from .templates.fallback import fallback_for

logger = logging.getLogger("vera.reply")


# ─── Pattern banks ──────────────────────────────────────────────────────────

AUTO_REPLY_PATTERNS = [
    r"thank you for contact",
    r"our team will respond",
    r"we will get back",
    r"i am an automated assistant",
    r"main ek automated assistant",
    r"aapki jaankari ke liye shukriya",
    r"automatic reply",
    r"auto.?reply",
    r"this is an out.?of.?office",
    r"we have received your message",
    r"hamari team aap se",
    r"team se baat kar",
    r"reply karenge",
    r"shortly\.?$",
]

HOSTILE_PATTERNS = [
    r"\bstop\b",
    r"not interested",
    r"do not message",
    r"don'?t message",
    r"remove me",
    r"unsubscribe",
    r"useless",
    r"bothering me",
    r"spam",
    r"\bf+u+c+k\b",
    r"\bshut up\b",
    r"madarchod|behenchod|bhosdi|chutiya|gandu",
    r"naraz|gussa",
    r"band karo",
    r"pareshan mat karo",
    r"mat bhejo",
]

INTENT_TRANSITION_PATTERNS = [
    r"\bok let'?s do it\b",
    r"\blet'?s do it\b",
    r"\bdo it\b",
    r"\byes go ahead\b",
    r"\bgo ahead\b",
    r"\bsend it\b",
    r"\bsend the\b",
    r"\bdraft it\b",
    r"\bproceed\b",
    r"\bconfirm\b",
    r"\baccepted\b",
    r"\bcarry on\b",
    r"\b(ok|okay)[,\s]+(do|go|send|draft)\b",
    r"\bhaan\b.*\b(kar|bhej|do)\b",
    r"\bkar do\b",
    r"\bkardo\b",
    r"\bmujhe.*\bjoin\b",
    r"\bmujhe.*\bjudna\b",
    r"\bmujhe.*\bjudrna\b",  # typo variants
    r"\bsahi hai\b.*\b(kar|bhej|do)\b",
    r"\bbilkul\b.*\b(kar|bhej|do)\b",
    r"\bchalo\b.*\b(kar|bhej|do)\b",
    r"\byes.*(send|draft|proceed|confirm)\b",
    r"\b(approved|approve)\b",
    r"\bship it\b",
    r"\bplease send\b",
]

WAIT_PATTERNS = [
    r"\bbusy\b",
    r"\blater\b",
    r"\btomorrow\b",
    r"\bnext week\b",
    r"\bthoda time\b",
    r"\bbaad mein\b",
    r"\bkal\b",
    r"\baaj nahi\b",
    r"\bcall me\b",
    r"\bin a meeting\b",
    r"\bafter \d+\b",
]

CURVEBALL_PATTERNS = [
    r"\bgst\b",
    r"\bincome tax\b",
    r"\bjoke\b",
    r"\bweather\b(?!.*(haircut|salon|gym))",
    r"\brecipe\b",
    r"\bcricket score\b",
    r"\bmovie\b",
    r"\bsong\b",
    r"\bpolitics\b",
    r"\bmodi\b|\bcongress\b|\bbjp\b",
    r"\bstock market\b",
    r"\bshare price\b",
    r"\baccount.*open\b",
    r"\bloan\b",
    r"\bcredit card\b",
]


def _matches_any(text: str, patterns: list[str]) -> str | None:
    tl = text.lower()
    for p in patterns:
        if re.search(p, tl):
            return p
    return None


# ─── Detection result ───────────────────────────────────────────────────────

@dataclass
class Decision:
    detector: str
    action: str  # "send" | "wait" | "end"
    body: str = ""
    cta: str = "open_ended"
    wait_seconds: int = 0
    rationale: str = ""


class ReplyRouter:
    def __init__(self, composer: Composer, state: AppState):
        self.composer = composer
        self.state = state

    async def route(self, conv_id: str, merchant_id: str, message: str, turn_number: int, customer_id: str | None = None) -> Decision:
        """Return the next action for this incoming reply."""
        msg = (message or "").strip()
        conv = self.state.conversations.get_or_create(conv_id, merchant_id, customer_id=customer_id)

        # Record inbound turn first.
        self.state.conversations.append_turn(conv_id, "merchant" if not customer_id else "customer", msg)

        if conv.ended:
            return Decision(detector="conversation_ended", action="end", rationale="Conversation already closed.")

        # Hostile takes precedence — always exit.
        hostile = _matches_any(msg, HOSTILE_PATTERNS)
        if hostile:
            self.state.suppressor.block_merchant(merchant_id, days=30)
            self.state.conversations.end(conv_id, reason="hostile")
            return Decision(
                detector="hostile",
                action="end",
                rationale=f"Hostile / opt-out signal ('{hostile}'). Suppressing all triggers for this merchant for 30 days.",
            )

        # Auto-reply — track strikes.
        if _matches_any(msg, AUTO_REPLY_PATTERNS) or self._is_repeat_inbound(conv_id, msg):
            conv.auto_reply_strikes += 1
            if conv.auto_reply_strikes == 1:
                # One brief polite prompt.
                body = "Looks like an auto-reply 😊 When the owner sees this, just reply 'Yes' to continue."
                self.state.conversations.append_turn(conv_id, "vera", body, cta="binary_yes_no")
                return Decision(detector="auto_reply_strike1", action="send", body=body, cta="binary_yes_no",
                                rationale="Detected auto-reply; one explicit prompt for the owner.")
            if conv.auto_reply_strikes == 2:
                return Decision(detector="auto_reply_strike2", action="wait", wait_seconds=86400,
                                rationale="Same auto-reply twice; backing off 24h for owner.")
            self.state.conversations.end(conv_id, reason="auto_reply_strike3")
            return Decision(detector="auto_reply_strike3", action="end",
                            rationale="Auto-reply 3x; zero engagement signal — closing.")

        # Intent transition — switch to ACTION; deliver concrete artifact, single binary CONFIRM.
        if _matches_any(msg, INTENT_TRANSITION_PATTERNS):
            decision = await self._compose_intent_handoff(conv, merchant_id, customer_id, turn_number)
            return decision

        # Curveball / off-topic.
        if _matches_any(msg, CURVEBALL_PATTERNS):
            redirect = await self._compose_curveball_redirect(conv, merchant_id, customer_id)
            return redirect

        # Wait signals.
        if _matches_any(msg, WAIT_PATTERNS):
            return Decision(detector="wait_signal", action="wait", wait_seconds=3600,
                            rationale="Merchant signalled later; backing off 1h.")

        # Engaged answer — honor + advance.
        return await self._compose_engaged_followup(conv, merchant_id, customer_id, turn_number, msg)

    # ─── helpers ────────────────────────────────────────────────────────────

    def _is_repeat_inbound(self, conv_id: str, msg: str) -> bool:
        """If the same merchant message has been received >= 2 times, treat as auto-reply."""
        conv = self.state.conversations.get(conv_id)
        if not conv:
            return False
        norm = re.sub(r"\s+", " ", msg.strip().lower())
        if not norm:
            return False
        seen = sum(1 for t in conv.turns if t.role in {"merchant", "customer"} and re.sub(r"\s+", " ", (t.body or "").strip().lower()) == norm)
        return seen >= 2

    async def _resolve_facts(self, conv: Conversation, merchant_id: str, customer_id: str | None) -> tuple[dict | None, dict | None, dict | None, dict | None]:
        """Always re-read context store (mid-stream updates honored)."""
        merchant = self.state.contexts.get("merchant", merchant_id) or {}
        category = self.state.contexts.find_category_for_merchant(merchant) or {}
        customer = self.state.contexts.get("customer", customer_id) if customer_id else None
        trigger = self.state.contexts.get("trigger", conv.trigger_id or "") if conv.trigger_id else None
        return merchant or None, category or None, customer, trigger

    async def _compose_intent_handoff(self, conv: Conversation, merchant_id: str, customer_id: str | None, turn_number: int) -> Decision:
        merchant, category, customer, trigger = await self._resolve_facts(conv, merchant_id, customer_id)
        # Use a synthetic trigger so the composer takes the intent_handoff path.
        synthetic_trigger = trigger or {"id": f"intent_handoff:{conv.conversation_id}", "kind": "intent_handoff", "payload": {}, "scope": "merchant", "source": "internal", "urgency": 4}
        if synthetic_trigger.get("kind") != "intent_handoff":
            # Override kind so kind_pack delivers the right guidance.
            synthetic_trigger = dict(synthetic_trigger)
            synthetic_trigger["kind"] = "intent_handoff"

        prior = self.state.conversations.prior_bodies(conv.conversation_id)
        if not (merchant and category):
            body = "Great — drafting now and will send a CONFIRM in this thread within 10 minutes. Reply CONFIRM to ship, or CANCEL to hold."
            self.state.conversations.append_turn(conv.conversation_id, "vera", body, cta="binary_confirm_cancel")
            return Decision(detector="intent_transition_unbacked", action="send", body=body, cta="binary_confirm_cancel",
                            rationale="Explicit intent committed; switching to action without further qualification (no merchant context).")

        out = await self.composer.compose(
            category=category, merchant=merchant, trigger=synthetic_trigger,
            customer=customer, send_as=("merchant_on_behalf" if customer else "vera"),
            conversation_state={"turn_number": turn_number, "prior_bodies_in_conv": prior},
        )
        body = out["body"]
        cta = out.get("cta_kind", "binary_confirm_cancel")
        self.state.conversations.append_turn(conv.conversation_id, "vera" if not customer else "merchant_on_behalf", body, cta=cta)
        return Decision(detector="intent_transition", action="send", body=body, cta=cta,
                        rationale=f"Explicit intent committed → action mode; concrete artifact + binary commit. ({out.get('rationale','')})")

    async def _compose_curveball_redirect(self, conv: Conversation, merchant_id: str, customer_id: str | None) -> Decision:
        merchant, category, customer, trigger = await self._resolve_facts(conv, merchant_id, customer_id)
        topic = (trigger or {}).get("kind", "the original thread").replace("_", " ")
        body = (
            f"That's outside what I can help with directly — better to ask your CA / specialist. "
            f"Coming back to the {topic} thread — want me to take the next step now, or hold?"
        )
        self.state.conversations.append_turn(conv.conversation_id, "vera" if not customer else "merchant_on_behalf", body, cta="open_ended")
        return Decision(detector="curveball_redirect", action="send", body=body, cta="open_ended",
                        rationale="Off-topic ask politely declined; re-anchored to original trigger in one sentence.")

    async def _compose_engaged_followup(self, conv: Conversation, merchant_id: str, customer_id: str | None, turn_number: int, inbound: str) -> Decision:
        merchant, category, customer, trigger = await self._resolve_facts(conv, merchant_id, customer_id)
        synthetic_trigger = trigger or {"id": f"engaged:{conv.conversation_id}", "kind": "engaged_followup", "payload": {"merchant_last_message": inbound}, "scope": "merchant", "source": "internal", "urgency": 2}
        if synthetic_trigger.get("kind") != "engaged_followup":
            synthetic_trigger = dict(synthetic_trigger)
            synthetic_trigger["kind"] = "engaged_followup"
            synthetic_trigger.setdefault("payload", {})
            synthetic_trigger["payload"]["merchant_last_message"] = inbound

        prior = self.state.conversations.prior_bodies(conv.conversation_id)
        if not (merchant and category):
            body = "Got it — let me act on that and come back with the concrete artifact in this thread. Want me to ship as soon as it's ready?"
            self.state.conversations.append_turn(conv.conversation_id, "vera", body, cta="binary_yes_no")
            return Decision(detector="engaged_unbacked", action="send", body=body, cta="binary_yes_no",
                            rationale="Engaged reply but merchant context not loaded; honoring + advancing.")

        out = await self.composer.compose(
            category=category, merchant=merchant, trigger=synthetic_trigger,
            customer=customer, send_as=("merchant_on_behalf" if customer else "vera"),
            conversation_state={"turn_number": turn_number, "prior_bodies_in_conv": prior, "inbound_message": inbound},
        )
        body = out["body"]
        cta = out.get("cta_kind", "binary_yes_no")
        self.state.conversations.append_turn(conv.conversation_id, "vera" if not customer else "merchant_on_behalf", body, cta=cta)
        return Decision(detector="engaged_followup", action="send", body=body, cta=cta,
                        rationale=f"Honoring engaged reply + advancing one step. ({out.get('rationale','')})")
