"""Run a single tick on a specific trigger and dump the full body."""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from urllib import request as urlrequest, error as urlerror

ROOT = Path(__file__).resolve().parent
BOT_URL = os.getenv("BOT_URL", "http://127.0.0.1:8080").rstrip("/")
TRIGGER_ID = sys.argv[1] if len(sys.argv) > 1 else "trg_016_kids_yoga_program_drafting"


def post(path, body):
    req = urlrequest.Request(BOT_URL + path, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
    try:
        return json.loads(urlrequest.urlopen(req, timeout=30).read().decode("utf-8"))
    except urlerror.HTTPError as e:
        return {"error": e.code}


def main():
    cats = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (ROOT / "dataset" / "categories").glob("*.json")}
    merchants = json.loads((ROOT / "dataset" / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]
    customers = json.loads((ROOT / "dataset" / "customers_seed.json").read_text(encoding="utf-8"))["customers"]
    triggers = {t["id"]: t for t in json.loads((ROOT / "dataset" / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]}

    if TRIGGER_ID not in triggers:
        print(f"unknown trigger: {TRIGGER_ID}")
        sys.exit(2)

    for slug, cat in cats.items():
        post("/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": cat, "delivered_at": "2026-04-26T00:00:00Z"})
    for m in merchants:
        post("/v1/context", {"scope": "merchant", "context_id": m["merchant_id"], "version": 1, "payload": m, "delivered_at": "2026-04-26T00:00:00Z"})
    for c in customers:
        post("/v1/context", {"scope": "customer", "context_id": c["customer_id"], "version": 1, "payload": c, "delivered_at": "2026-04-26T00:00:00Z"})
    for t in triggers.values():
        post("/v1/context", {"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t, "delivered_at": "2026-04-26T00:00:00Z"})

    out = post("/v1/tick", {"now": "2026-04-26T10:35:00Z", "available_triggers": [TRIGGER_ID]})
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
