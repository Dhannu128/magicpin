"""Replay-test contract: auto-reply hell, intent transition, hostile, curveball."""

from __future__ import annotations


def _push_seed(client, dataset):
    for slug, cat in dataset["categories"].items():
        client.post("/v1/context", json={"scope": "category", "context_id": slug, "version": 1, "payload": cat,
                                         "delivered_at": "2026-04-26T00:00:00Z"})
    for mid, m in dataset["merchants"].items():
        client.post("/v1/context", json={"scope": "merchant", "context_id": mid, "version": 1, "payload": m,
                                         "delivered_at": "2026-04-26T00:00:00Z"})
    for cid, c in dataset["customers"].items():
        client.post("/v1/context", json={"scope": "customer", "context_id": cid, "version": 1, "payload": c,
                                         "delivered_at": "2026-04-26T00:00:00Z"})
    for tid, t in dataset["triggers"].items():
        client.post("/v1/context", json={"scope": "trigger", "context_id": tid, "version": 1, "payload": t,
                                         "delivered_at": "2026-04-26T00:00:00Z"})


def test_auto_reply_three_strike(client, dataset):
    _push_seed(client, dataset)
    conv = "conv_auto_replay_001"
    mid = "m_001_drmeera_dentist_delhi"

    auto = "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly."

    r1 = client.post("/v1/reply", json={"conversation_id": conv, "merchant_id": mid, "from_role": "merchant",
                                        "message": auto, "received_at": "2026-04-26T10:00:00Z", "turn_number": 2})
    assert r1.status_code == 200
    assert r1.json()["action"] == "send"  # one explicit prompt

    r2 = client.post("/v1/reply", json={"conversation_id": conv, "merchant_id": mid, "from_role": "merchant",
                                        "message": auto, "received_at": "2026-04-26T10:01:00Z", "turn_number": 3})
    assert r2.json()["action"] == "wait"
    assert r2.json()["wait_seconds"] >= 3600

    r3 = client.post("/v1/reply", json={"conversation_id": conv, "merchant_id": mid, "from_role": "merchant",
                                        "message": auto, "received_at": "2026-04-26T10:02:00Z", "turn_number": 4})
    assert r3.json()["action"] == "end"


def test_auto_reply_cross_conversation_escalates(client, dataset):
    """Judge harness sometimes opens a NEW conversation_id per turn while sending the same canned text.
    Bot must still escalate via merchant-level strike tracking."""
    _push_seed(client, dataset)
    mid = "m_001_drmeera_dentist_delhi"
    auto = "Thank you for contacting us! Our team will respond shortly."
    actions = []
    for i in range(1, 5):
        r = client.post("/v1/reply", json={
            "conversation_id": f"conv_auto_x{i}", "merchant_id": mid, "from_role": "merchant",
            "message": auto, "received_at": "2026-04-26T10:00:00Z", "turn_number": i + 1,
        })
        assert r.status_code == 200
        actions.append(r.json()["action"])

    # Turn 1: one polite send. Turn 2: wait. Turn 3+: end.
    assert actions[0] == "send"
    assert actions[1] == "wait"
    assert actions[2] == "end"


def test_intent_transition_no_requalifying(client, dataset):
    _push_seed(client, dataset)
    conv = "conv_intent_001"
    mid = "m_001_drmeera_dentist_delhi"

    r = client.post("/v1/reply", json={"conversation_id": conv, "merchant_id": mid, "from_role": "merchant",
                                       "message": "Ok let's do it. What's next?", "received_at": "2026-04-26T10:00:00Z",
                                       "turn_number": 3})
    assert r.status_code == 200
    j = r.json()
    assert j["action"] == "send", j
    body_l = j["body"].lower()
    qualifying_phrases = ["would you say", "tell me more about", "can you tell me", "first question", "to plan well"]
    assert not any(q in body_l for q in qualifying_phrases), f"bot is still qualifying: {j['body']}"


def test_hostile_immediate_end(client, dataset):
    _push_seed(client, dataset)
    conv = "conv_hostile_001"
    mid = "m_001_drmeera_dentist_delhi"

    r = client.post("/v1/reply", json={"conversation_id": conv, "merchant_id": mid, "from_role": "merchant",
                                       "message": "Stop messaging me. This is useless spam.",
                                       "received_at": "2026-04-26T10:00:00Z", "turn_number": 2})
    assert r.status_code == 200
    assert r.json()["action"] == "end"


def test_curveball_redirects(client, dataset):
    _push_seed(client, dataset)
    conv = "conv_curve_001"
    mid = "m_001_drmeera_dentist_delhi"

    r = client.post("/v1/reply", json={"conversation_id": conv, "merchant_id": mid, "from_role": "merchant",
                                       "message": "Btw can you also help me with my GST filing this month?",
                                       "received_at": "2026-04-26T10:00:00Z", "turn_number": 2})
    assert r.status_code == 200
    j = r.json()
    assert j["action"] == "send"
    assert "ca" in j["body"].lower() or "outside" in j["body"].lower() or "specialist" in j["body"].lower()


def test_wait_signal(client, dataset):
    _push_seed(client, dataset)
    r = client.post("/v1/reply", json={"conversation_id": "conv_wait_001", "merchant_id": "m_001_drmeera_dentist_delhi",
                                       "from_role": "merchant", "message": "I'm busy now, call me tomorrow",
                                       "received_at": "2026-04-26T10:00:00Z", "turn_number": 2})
    assert r.status_code == 200
    assert r.json()["action"] == "wait"


def test_tick_returns_actions(client, dataset):
    _push_seed(client, dataset)
    r = client.post("/v1/tick", json={"now": "2026-04-26T10:35:00Z",
                                       "available_triggers": ["trg_001_research_digest_dentists",
                                                              "trg_010_ipl_match_delhi",
                                                              "trg_018_supply_atorvastatin_recall"]})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert isinstance(actions, list)
    # We expect at least one action because all 3 triggers are valid for distinct merchants.
    assert len(actions) >= 1
    for a in actions:
        for key in ("conversation_id", "merchant_id", "send_as", "trigger_id", "template_name",
                    "template_params", "body", "cta", "suppression_key", "rationale"):
            assert key in a, f"missing key {key} in action {a}"
        assert a["body"]
        assert "http" not in a["body"].lower()


def test_tick_empty_when_no_triggers(client, dataset):
    _push_seed(client, dataset)
    r = client.post("/v1/tick", json={"now": "2026-04-26T10:35:00Z", "available_triggers": []})
    assert r.status_code == 200
    assert r.json() == {"actions": []}


def test_hostile_then_blocked_for_subsequent_ticks(client, dataset):
    _push_seed(client, dataset)
    mid = "m_001_drmeera_dentist_delhi"
    client.post("/v1/reply", json={"conversation_id": "conv_block_001", "merchant_id": mid, "from_role": "merchant",
                                   "message": "stop, do not message me", "received_at": "2026-04-26T10:00:00Z",
                                   "turn_number": 2})
    # Now a tick that would otherwise generate an action for this merchant must skip them.
    r = client.post("/v1/tick", json={"now": "2026-04-26T11:00:00Z",
                                       "available_triggers": ["trg_001_research_digest_dentists"]})
    assert r.status_code == 200
    for a in r.json()["actions"]:
        assert a["merchant_id"] != mid, "merchant should be cooldown-blocked after hostile signal"
