"""Contract test — /v1/context idempotency + 5-endpoint smoke."""

from __future__ import annotations


def test_healthz_and_metadata(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert set(body["contexts_loaded"].keys()) == {"category", "merchant", "customer", "trigger"}

    r2 = client.get("/v1/metadata")
    assert r2.status_code == 200
    md = r2.json()
    assert md["team_name"]
    assert md["model"]
    assert md["contact_email"]
    assert md["version"]


def test_context_idempotent(client, dataset):
    cat = dataset["categories"]["dentists"]
    body = {"scope": "category", "context_id": "dentists", "version": 1, "payload": cat,
            "delivered_at": "2026-04-26T09:45:00Z"}

    r1 = client.post("/v1/context", json=body)
    assert r1.status_code == 200, r1.text
    assert r1.json()["accepted"] is True

    # Same version → 409
    r2 = client.post("/v1/context", json=body)
    assert r2.status_code == 409
    assert r2.json()["accepted"] is False
    assert r2.json()["reason"] == "stale_version"
    assert r2.json()["current_version"] == 1


def test_higher_version_replaces(client, dataset):
    cat = dataset["categories"]["dentists"]
    client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": cat,
                                     "delivered_at": "2026-04-26T09:45:00Z"})
    cat2 = dict(cat)
    cat2["display_name"] = "Dentists v2"
    r = client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 2, "payload": cat2,
                                         "delivered_at": "2026-04-26T10:30:00Z"})
    assert r.status_code == 200
    assert r.json()["accepted"] is True

    # Old version → 409, current_version is 2
    r2 = client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": cat,
                                          "delivered_at": "2026-04-26T11:00:00Z"})
    assert r2.status_code == 409
    assert r2.json()["current_version"] == 2


def test_invalid_scope(client):
    r = client.post("/v1/context", json={"scope": "platypus", "context_id": "x", "version": 1, "payload": {}, "delivered_at": "2026-04-26T00:00:00Z"})
    assert r.status_code == 400
    assert r.json()["accepted"] is False
    assert r.json()["reason"] == "invalid_scope"


def test_healthz_reflects_loaded_counts(client, dataset):
    cat = dataset["categories"]["dentists"]
    m = dataset["merchants"]["m_001_drmeera_dentist_delhi"]
    client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": cat,
                                     "delivered_at": "2026-04-26T09:45:00Z"})
    client.post("/v1/context", json={"scope": "merchant", "context_id": m["merchant_id"], "version": 1, "payload": m,
                                     "delivered_at": "2026-04-26T09:45:30Z"})
    r = client.get("/v1/healthz")
    assert r.json()["contexts_loaded"]["category"] == 1
    assert r.json()["contexts_loaded"]["merchant"] == 1
