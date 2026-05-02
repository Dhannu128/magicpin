"""TASK 4 — adaptive injection + idempotency stress.

Defends against the actual judge harness's mid-test context updates: new digests,
updated perf snapshots, new triggers, surprise customer contexts. The 30 canonical
pairs DON'T cover this — this is the post-submission injection differentiator.

The tests run against the LIVE bot (BOT_URL env var, defaults to public Render URL)
because we want to verify production behavior, not just unit-test logic. They also
work locally if you start `uvicorn bot.main:app --port 8080` first.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import request as urlrequest, error as urlerror

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOT_URL = os.getenv("BOT_URL", "http://127.0.0.1:8080").rstrip("/")
HARNESS_OFFLINE = os.getenv("SKIP_HARNESS_TESTS") == "1"


def _post(path: str, body: dict, timeout: int = 30):
    req = urlrequest.Request(BOT_URL + path, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
    try:
        return json.loads(urlrequest.urlopen(req, timeout=timeout).read().decode("utf-8")), None
    except urlerror.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8")), e.code
        except Exception:
            return None, e.code


def _get(path: str, timeout: int = 10):
    try:
        return json.loads(urlrequest.urlopen(BOT_URL + path, timeout=timeout).read().decode("utf-8")), None
    except urlerror.HTTPError as e:
        return None, e.code


def _bot_alive() -> bool:
    try:
        return _get("/v1/healthz", 4)[1] is None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(HARNESS_OFFLINE or not _bot_alive(),
                                 reason="live bot at $BOT_URL not reachable; set SKIP_HARNESS_TESTS=1 to silence")


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def seed_data():
    cats = {f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in (ROOT / "dataset" / "categories").glob("*.json")}
    merchants = {m["merchant_id"]: m for m in
                 json.loads((ROOT / "dataset" / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]}
    customers = {c["customer_id"]: c for c in
                 json.loads((ROOT / "dataset" / "customers_seed.json").read_text(encoding="utf-8"))["customers"]}
    triggers = {t["id"]: t for t in
                json.loads((ROOT / "dataset" / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]}
    return {"categories": cats, "merchants": merchants, "customers": customers, "triggers": triggers}


@pytest.fixture
def fresh_bot(seed_data):
    """Wipe + reseed before each test."""
    _post("/v1/teardown", {})
    for slug, c in seed_data["categories"].items():
        _post("/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": c,
                              "delivered_at": "2026-04-26T00:00:00Z"})
    for mid, m in seed_data["merchants"].items():
        _post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 1, "payload": m,
                              "delivered_at": "2026-04-26T00:00:00Z"})
    for cid, c in seed_data["customers"].items():
        _post("/v1/context", {"scope": "customer", "context_id": cid, "version": 1, "payload": c,
                              "delivered_at": "2026-04-26T00:00:00Z"})
    for tid, t in seed_data["triggers"].items():
        _post("/v1/context", {"scope": "trigger", "context_id": tid, "version": 1, "payload": t,
                              "delivered_at": "2026-04-26T00:00:00Z"})
    return seed_data


# ─── (a) New digest item is cited after version bump ─────────────────────────

def test_new_digest_item_picked_up(fresh_bot):
    cats = fresh_bot["categories"]
    triggers = fresh_bot["triggers"]

    novel_id = "d_2026W18_TASK4_NOVEL_DIGEST"
    novel_title = "ICMR Apr 2026: bioactive glass varnish cuts root caries 47% in 60+ adults"
    novel_source = "ICMR Bulletin Apr 2026, p.22"
    new_cat = json.loads(json.dumps(cats["dentists"]))
    new_cat["digest"] = [{
        "id": novel_id, "kind": "research", "title": novel_title, "source": novel_source,
        "trial_n": 1140, "patient_segment": "high_risk_adults",
        "summary": "Bioactive glass varnish RCT (n=1140) shows 47% reduction in root caries among 60+ adults vs fluoride varnish.",
        "actionable": "Consider for senior cohort with active root caries.",
    }] + new_cat["digest"]

    resp, code = _post("/v1/context", {"scope": "category", "context_id": "dentists", "version": 2,
                                        "payload": new_cat, "delivered_at": "2026-04-26T11:00:00Z"})
    assert code is None and resp.get("accepted") is True

    # Update trigger to point at new digest item.
    new_trigger = json.loads(json.dumps(triggers["trg_001_research_digest_dentists"]))
    new_trigger["payload"]["top_item_id"] = novel_id
    _post("/v1/context", {"scope": "trigger", "context_id": "trg_001_research_digest_dentists",
                          "version": 2, "payload": new_trigger, "delivered_at": "2026-04-26T11:01:00Z"})

    out, _ = _post("/v1/tick", {"now": "2026-04-26T11:02:00Z",
                                 "available_triggers": ["trg_001_research_digest_dentists"]})
    actions = out.get("actions", []) if out else []
    assert actions, "bot returned 0 actions on novel-digest tick"
    body = actions[0]["body"]
    assert ("ICMR" in body or "47%" in body or "1,140" in body or "1140" in body or "bioactive glass" in body.lower()), \
        f"new digest NOT cited; body: {body}"
    # And: old digest title (JIDA fluoride 38%) MUST NOT appear — atomic replace check.
    assert "JIDA" not in body, f"old (replaced) digest leaked into body: {body}"


# ─── (b) Doubled performance number is mentioned ─────────────────────────────

def test_perf_shift_picked_up(fresh_bot):
    """Bump merchant perf and confirm the new number flows into the next compose."""
    merchants = fresh_bot["merchants"]
    m = json.loads(json.dumps(merchants["m_001_drmeera_dentist_delhi"]))
    m["performance"]["views"] = 4820  # was 2410 — doubled
    m["performance"]["delta_7d"]["views_pct"] = 1.0  # +100%
    resp, code = _post("/v1/context", {"scope": "merchant", "context_id": m["merchant_id"], "version": 2,
                                        "payload": m, "delivered_at": "2026-04-26T11:10:00Z"})
    assert code is None and resp.get("accepted") is True

    # Tick a perf_spike-style trigger for that merchant.
    spike = {
        "id": "trg_TASK4_perf_spike_meera", "scope": "merchant", "kind": "perf_spike", "source": "internal",
        "merchant_id": "m_001_drmeera_dentist_delhi", "customer_id": None,
        "payload": {"metric": "views", "delta_pct": 1.0, "window": "7d", "vs_baseline": 2410},
        "urgency": 2, "suppression_key": "perf_spike:m_001:test:2026-W18",
        "expires_at": "2026-05-30T00:00:00Z",
    }
    _post("/v1/context", {"scope": "trigger", "context_id": spike["id"], "version": 1, "payload": spike,
                          "delivered_at": "2026-04-26T11:11:00Z"})
    out, _ = _post("/v1/tick", {"now": "2026-04-26T11:12:00Z", "available_triggers": [spike["id"]]})
    actions = out.get("actions", []) if out else []
    assert actions, "bot returned 0 actions on perf-shift tick"
    body = actions[0]["body"]
    # Must reference the new number OR the +100%/doubled phrasing — bot has access via merchant.derived
    assert ("4820" in body or "4,820" in body or "100%" in body or "doubled" in body.lower() or "double" in body.lower()), \
        f"new perf number NOT mentioned; body: {body}"


# ─── (c) Stale-version push returns 409 with current_version ─────────────────

def test_stale_version_push_409(fresh_bot):
    cats = fresh_bot["categories"]
    # We just pushed v1 in fresh_bot. Push v1 again → 409.
    resp, code = _post("/v1/context", {"scope": "category", "context_id": "dentists", "version": 1,
                                        "payload": cats["dentists"], "delivered_at": "2026-04-26T12:00:00Z"})
    assert code == 409
    assert resp["accepted"] is False
    assert resp["reason"] == "stale_version"
    assert resp["current_version"] == 1


# ─── (d) 20 context updates in 30s — idempotency stress ──────────────────────

def test_idempotency_under_burst(fresh_bot):
    cats = fresh_bot["categories"]
    base = cats["dentists"]
    start = time.time()
    accepted = 0
    rejected = 0
    # Push versions 2..21 in rapid succession, each with a small payload tweak.
    for v in range(2, 22):
        payload = json.loads(json.dumps(base))
        payload["display_name"] = f"Dentists v{v}"
        resp, code = _post("/v1/context", {"scope": "category", "context_id": "dentists", "version": v,
                                            "payload": payload, "delivered_at": "2026-04-26T13:00:00Z"})
        if code is None and resp.get("accepted"):
            accepted += 1
        else:
            rejected += 1
    elapsed = time.time() - start
    assert elapsed < 30, f"20 updates took {elapsed:.1f}s, > 30s budget"
    assert accepted == 20, f"expected all 20 to be accepted (monotonic versions), got {accepted}"
    # Now re-push v3 (lower than current 21) → 409.
    payload = json.loads(json.dumps(base))
    resp, code = _post("/v1/context", {"scope": "category", "context_id": "dentists", "version": 3,
                                        "payload": payload, "delivered_at": "2026-04-26T13:01:00Z"})
    assert code == 409
    assert resp["current_version"] == 21


# ─── (e) Surprise CustomerContext mid-test → recall_due fires correctly ──────

def test_surprise_customer_context_mid_test(fresh_bot):
    """Phase-3 simulation: a new customer context appears mid-test followed 2 min later by
    a recall_due trigger on that customer. Bot must compose with send_as=merchant_on_behalf,
    cite the merchant, address the customer, and use the active offer + slot labels."""
    surprise_customer = {
        "customer_id": "c_surprise_TASK4_001",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "identity": {"name": "Anita", "phone_redacted": "<phone>", "language_pref": "hi-en mix", "age_band": "30-40"},
        "relationship": {"first_visit": "2025-09-01", "last_visit": "2026-03-01", "visits_total": 3,
                         "services_received": ["cleaning", "cleaning", "scaling"], "lifetime_value": 1497},
        "state": "lapsed_soft",
        "preferences": {"preferred_slots": "weekday_evening", "channel": "whatsapp", "reminder_opt_in": True},
        "consent": {"opted_in_at": "2025-09-01", "scope": ["recall_reminders", "appointment_reminders"]},
    }
    _post("/v1/context", {"scope": "customer", "context_id": surprise_customer["customer_id"], "version": 1,
                          "payload": surprise_customer, "delivered_at": "2026-04-26T13:30:00Z"})

    surprise_trigger = {
        "id": "trg_TASK4_recall_due_anita", "scope": "customer", "kind": "recall_due", "source": "internal",
        "merchant_id": "m_001_drmeera_dentist_delhi", "customer_id": "c_surprise_TASK4_001",
        "payload": {"service_due": "6_month_cleaning", "last_service_date": "2026-03-01", "due_date": "2026-09-01",
                    "available_slots": [{"iso": "2026-09-03T18:00:00+05:30", "label": "Wed 3 Sep, 6pm"},
                                         {"iso": "2026-09-04T17:00:00+05:30", "label": "Thu 4 Sep, 5pm"}]},
        "urgency": 3, "suppression_key": "recall:c_surprise_TASK4_001:6mo",
        "expires_at": "2026-09-30T00:00:00Z",
    }
    _post("/v1/context", {"scope": "trigger", "context_id": surprise_trigger["id"], "version": 1,
                          "payload": surprise_trigger, "delivered_at": "2026-04-26T13:32:00Z"})

    out, _ = _post("/v1/tick", {"now": "2026-04-26T13:33:00Z",
                                 "available_triggers": [surprise_trigger["id"]]})
    actions = out.get("actions", []) if out else []
    assert actions, "bot returned 0 actions on surprise-customer tick"
    a = actions[0]
    assert a["customer_id"] == "c_surprise_TASK4_001"
    assert a["send_as"] == "merchant_on_behalf"
    body = a["body"]
    assert "Anita" in body, f"customer name missing; body: {body}"
    # Merchant signature anchor (T3 fix): name + locality must appear.
    assert ("Meera" in body or "Lajpat Nagar" in body), f"merchant signature missing; body: {body}"
    # At least one of the slots verbatim.
    assert ("Wed 3 Sep" in body or "Thu 4 Sep" in body), f"slot labels missing; body: {body}"
    # Active offer (Dental Cleaning @ ₹299) reference.
    assert ("299" in body or "cleaning" in body.lower()), f"offer / service missing; body: {body}"
