"""Build submission.jsonl by hitting /v1/tick once per (merchant, trigger) pair from the seed,
extracting the action's body+rationale, and emitting one JSON line per pair (max 30).

Run: python build_submission_jsonl.py [BOT_URL]
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from urllib import request as urlrequest, error as urlerror

ROOT = Path(__file__).resolve().parent
BOT_URL = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("BOT_URL", "http://127.0.0.1:8080")).rstrip("/")


def post(path: str, body: dict) -> dict:
    req = urlrequest.Request(BOT_URL + path, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
    try:
        return json.loads(urlrequest.urlopen(req, timeout=30).read().decode("utf-8"))
    except urlerror.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": e.code}


def main():
    cats = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (ROOT / "dataset" / "categories").glob("*.json")}
    merchants = json.loads((ROOT / "dataset" / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]
    customers = json.loads((ROOT / "dataset" / "customers_seed.json").read_text(encoding="utf-8"))["customers"]
    triggers = json.loads((ROOT / "dataset" / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]

    # Wipe any leftover state from prior runs (suppressor, conversation memory).
    post("/v1/teardown", {})

    for slug, cat in cats.items():
        post("/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": cat,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    for m in merchants:
        post("/v1/context", {"scope": "merchant", "context_id": m["merchant_id"], "version": 1, "payload": m,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    for c in customers:
        post("/v1/context", {"scope": "customer", "context_id": c["customer_id"], "version": 1, "payload": c,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    for t in triggers:
        post("/v1/context", {"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t,
                             "delivered_at": "2026-04-26T00:00:00Z"})

    rows = []
    for t in triggers:
        out = post("/v1/tick", {"now": "2026-04-26T10:35:00Z", "available_triggers": [t["id"]]})
        for a in out.get("actions", []):
            rows.append({
                "test_id": f"T{len(rows)+1:02d}",
                "merchant_id": a.get("merchant_id"),
                "customer_id": a.get("customer_id"),
                "trigger_id": a.get("trigger_id"),
                "send_as": a.get("send_as"),
                "template_name": a.get("template_name"),
                "template_params": a.get("template_params"),
                "body": a.get("body"),
                "cta": a.get("cta"),
                "suppression_key": a.get("suppression_key"),
                "rationale": a.get("rationale"),
            })
        if len(rows) >= 30:
            break

    out_path = ROOT / "submission.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} lines to {out_path}")


if __name__ == "__main__":
    main()
