"""Test fixtures.

We test against the in-memory app via FastAPI's TestClient — no live LLM calls.
For composer tests we force_fallback=True so we hit the deterministic templates,
which are what's verified for facts-pack adherence + anti-fabrication.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force-disable the LLM in unit tests so we never hit the network.
os.environ.setdefault("LLM_API_KEY", "")


@pytest.fixture(scope="session")
def dataset() -> dict:
    cats = {}
    for f in (ROOT / "dataset" / "categories").glob("*.json"):
        cats[f.stem] = json.loads(f.read_text(encoding="utf-8"))

    merchants_raw = json.loads((ROOT / "dataset" / "merchants_seed.json").read_text(encoding="utf-8"))
    merchants = {m["merchant_id"]: m for m in merchants_raw["merchants"]}

    customers_raw = json.loads((ROOT / "dataset" / "customers_seed.json").read_text(encoding="utf-8"))
    customers = {c["customer_id"]: c for c in customers_raw["customers"]}

    triggers_raw = json.loads((ROOT / "dataset" / "triggers_seed.json").read_text(encoding="utf-8"))
    triggers = {t["id"]: t for t in triggers_raw["triggers"]}

    return {"categories": cats, "merchants": merchants, "customers": customers, "triggers": triggers}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from bot.main import app, state
    # Wipe state between tests
    state.contexts._store.clear()
    state.conversations._convs.clear()
    state.suppressor._sent.clear()
    state.suppressor._merchant_cooldown.clear()
    return TestClient(app)
