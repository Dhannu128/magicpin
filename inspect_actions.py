"""Push all 25 triggers + all 10 merchants + 5 categories + 15 customers to a fresh bot,
issue /tick batches, and dump every action's full body + rationale. Use to debug what
the LLM is actually emitting (judge_simulator only shows 50-char previews).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parent
BOT_URL = os.getenv("BOT_URL", "http://127.0.0.1:8080").rstrip("/")


def post(path, body):
    from urllib import error as urlerror
    req = urlrequest.Request(
        BOT_URL + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urlrequest.urlopen(req, timeout=30)
        return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as e:
        if e.code == 409:
            return {"accepted": False, "reason": "stale_version"}
        raise


def main():
    cats = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (ROOT / "dataset" / "categories").glob("*.json")}
    merchants = json.loads((ROOT / "dataset" / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]
    customers = json.loads((ROOT / "dataset" / "customers_seed.json").read_text(encoding="utf-8"))["customers"]
    triggers = json.loads((ROOT / "dataset" / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]

    for slug, cat in cats.items():
        post("/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": cat, "delivered_at": "2026-04-26T00:00:00Z"})
    for m in merchants:
        post("/v1/context", {"scope": "merchant", "context_id": m["merchant_id"], "version": 1, "payload": m, "delivered_at": "2026-04-26T00:00:00Z"})
    for c in customers:
        post("/v1/context", {"scope": "customer", "context_id": c["customer_id"], "version": 1, "payload": c, "delivered_at": "2026-04-26T00:00:00Z"})
    for t in triggers:
        post("/v1/context", {"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t, "delivered_at": "2026-04-26T00:00:00Z"})

    # Group triggers by merchant for one-per-tick coverage.
    by_merchant = {}
    for t in triggers:
        by_merchant.setdefault(t.get("merchant_id"), []).append(t["id"])

    # Run one tick PER trigger so we get every body.
    actions = []
    for t in triggers:
        out = post("/v1/tick", {"now": "2026-04-26T10:35:00Z", "available_triggers": [t["id"]]})
        for a in out.get("actions", []):
            actions.append((t["id"], a))

    for tid, a in actions:
        print("=" * 80)
        print(f"TRIGGER: {tid}")
        print(f"merchant_id={a.get('merchant_id')}  customer_id={a.get('customer_id')}  send_as={a.get('send_as')}")
        print(f"cta={a.get('cta')}  template={a.get('template_name')}")
        print(f"BODY:\n{a.get('body')}")
        print(f"RATIONALE: {a.get('rationale')}")
    print("=" * 80)
    print(f"TOTAL ACTIONS: {len(actions)} / {len(triggers)} triggers")


if __name__ == "__main__":
    main()
