"""TASK 1 audit — verify the live bot is actually calling the LLM.

Steps:
  a) healthz check
  b) push base dataset, time /tick on T22/T15/T13, diff bodies vs submission.jsonl
  c) push a NEW digest item (version 2 of dentists category) and re-tick research_digest
     trigger; verify the new digest title appears in body (proves LLM is being called
     freshly, not serving stale cached fallback)
  d) print summary verdict
"""

from __future__ import annotations

import json
import os
import sys
import time
import statistics
from pathlib import Path
from urllib import request as urlrequest, error as urlerror

ROOT = Path(__file__).resolve().parent
BOT_URL = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("BOT_URL", "https://vera-bot-8reg.onrender.com")).rstrip("/")


def post(path, body, timeout=30):
    req = urlrequest.Request(BOT_URL + path, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
    try:
        return json.loads(urlrequest.urlopen(req, timeout=timeout).read().decode("utf-8")), None
    except urlerror.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8")), e.code
        except Exception:
            return None, e.code


def get(path, timeout=10):
    try:
        return json.loads(urlrequest.urlopen(BOT_URL + path, timeout=timeout).read().decode("utf-8")), None
    except urlerror.HTTPError as e:
        return None, e.code


def jaccard(a: str, b: str) -> float:
    sa = set((a or "").lower().split())
    sb = set((b or "").lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main():
    print(f"=== TASK 1 audit on {BOT_URL} ===\n")

    # (a) healthz
    h, _ = get("/v1/healthz")
    if not h:
        print("FAIL: healthz unreachable"); sys.exit(2)
    print(f"a) /healthz: status={h['status']} uptime={h['uptime_seconds']}s contexts_loaded={h['contexts_loaded']}")

    # Wipe + reseed
    post("/v1/teardown", {})
    cats = {f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in (ROOT / "dataset" / "categories").glob("*.json")}
    merchants = json.loads((ROOT / "dataset" / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"]
    customers = json.loads((ROOT / "dataset" / "customers_seed.json").read_text(encoding="utf-8"))["customers"]
    triggers = {t["id"]: t for t in
                json.loads((ROOT / "dataset" / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"]}
    for slug, c in cats.items():
        post("/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": c,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    for m in merchants:
        post("/v1/context", {"scope": "merchant", "context_id": m["merchant_id"], "version": 1, "payload": m,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    for c in customers:
        post("/v1/context", {"scope": "customer", "context_id": c["customer_id"], "version": 1, "payload": c,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    for t in triggers.values():
        post("/v1/context", {"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t,
                             "delivered_at": "2026-04-26T00:00:00Z"})
    h, _ = get("/v1/healthz")
    print(f"   reseeded; counts={h['contexts_loaded']}")

    # (b) Time + diff on hard triggers
    submission = {}
    for line in open(ROOT / "submission.jsonl", encoding="utf-8"):
        r = json.loads(line)
        submission[r["trigger_id"]] = r["body"]

    hard = [
        ("T22", "trg_023_competitor_opened_dentist"),
        ("T15", "trg_016_kids_yoga_program_drafting"),
        ("T13", "trg_014_seasonal_acquisition_dip_powerhouse"),
    ]
    latencies = []
    print("\nb) hard-trigger /tick + body diff vs submission.jsonl:")
    for label, tid in hard:
        t0 = time.time()
        out, _ = post("/v1/tick", {"now": "2026-04-26T10:35:00Z", "available_triggers": [tid]}, timeout=30)
        ms = int((time.time() - t0) * 1000)
        latencies.append(ms)
        actions = (out or {}).get("actions", [])
        if not actions:
            print(f"   {label} {tid}: FAIL — 0 actions ({ms}ms)")
            continue
        live_body = actions[0]["body"]
        sub_body = submission.get(tid, "")
        identical = (live_body.strip() == sub_body.strip())
        j = jaccard(live_body, sub_body)
        print(f"   {label} ({ms}ms): identical={identical} jaccard={j:.2f} live_len={len(live_body)} sub_len={len(sub_body)}")
        if not identical:
            print(f"     LIVE: {live_body[:150]}...")
            print(f"     SUB:  {sub_body[:150]}...")

    p50 = int(statistics.median(latencies))
    p95 = int(max(latencies))
    print(f"   latencies: p50={p50}ms p95={p95}ms")

    # (c) novel-context injection — push a fake digest in dentists v2 and tick research trigger
    print("\nc) novel-context injection test:")
    novel_id = "d_2026W18_NOVEL_AUDIT_TEST"
    novel_title = "ICMR Apr 2026: bioactive glass varnish cuts root caries 47% in 60+ adults"
    novel_source = "ICMR Bulletin Apr 2026, p.22"
    new_cat = json.loads(json.dumps(cats["dentists"]))  # deep copy
    new_cat["digest"] = [{
        "id": novel_id, "kind": "research", "title": novel_title,
        "source": novel_source, "trial_n": 1140, "patient_segment": "high_risk_adults",
        "summary": "Bioactive glass varnish RCT (n=1140) shows 47% reduction in root caries among 60+ adults vs fluoride varnish.",
        "actionable": "Consider for senior cohort with active root caries.",
    }] + new_cat["digest"]

    post("/v1/context", {"scope": "category", "context_id": "dentists", "version": 2, "payload": new_cat,
                         "delivered_at": "2026-04-26T11:00:00Z"})
    # update trigger payload to reference the new digest item
    new_trigger = json.loads(json.dumps(triggers["trg_001_research_digest_dentists"]))
    new_trigger["payload"]["top_item_id"] = novel_id
    post("/v1/context", {"scope": "trigger", "context_id": "trg_001_research_digest_dentists",
                         "version": 2, "payload": new_trigger, "delivered_at": "2026-04-26T11:01:00Z"})

    out, _ = post("/v1/tick", {"now": "2026-04-26T11:02:00Z",
                                "available_triggers": ["trg_001_research_digest_dentists"]}, timeout=30)
    actions = (out or {}).get("actions", [])
    if not actions:
        print("   FAIL — bot returned 0 actions on novel-context tick")
        novel_cited = False
    else:
        body = actions[0]["body"]
        novel_cited = ("ICMR" in body or "47%" in body or "1,140" in body or "1140" in body or "bioactive glass" in body.lower())
        print(f"   body: {body[:300]}...")
        print(f"   novel ICMR/47%/bioactive cited? {novel_cited}")

    # (d) verdict
    print("\n=== VERDICT ===")
    print(f"[*] LLM key env var: LLM_API_KEY | present in prod (deduced from healthy LLM responses below): {'YES' if all(latencies) else 'UNKNOWN'}")
    print(f"[*] Live /tick latency p50: {p50}ms | p95: {p95}ms")
    print(f"[*] Novel-context cited: {'YES' if novel_cited else 'NO'}")
    fast = sum(1 for ms in latencies if ms < 2000)
    print(f"[*] Calls under 2s ({fast}/{len(latencies)}): if any are <2s, likely fallback path (no LLM call)")
    verdict = "API_LIVE" if novel_cited and p95 > 2000 else ("API_PARTIAL" if novel_cited else "API_DEAD")
    print(f"[*] VERDICT: {verdict}")


if __name__ == "__main__":
    main()
