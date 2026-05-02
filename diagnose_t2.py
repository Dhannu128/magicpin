"""TASK 2 — build the per-dim matrix across all judge runs and diagnose the gap."""
from __future__ import annotations
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

DIMS = ("Specificity", "Category Fit", "Merchant Fit", "Decision Quality", "Engagement")
ROOT = Path(__file__).resolve().parent
LOGS = sorted(ROOT.glob("judge_run_*.log"))


def parse(path):
    try:
        raw = open(path, encoding="utf-16", errors="replace").read()
        if "Message:" not in raw:
            raise ValueError
    except Exception:
        raw = open(path, encoding="utf-8", errors="replace").read()
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    blocks = re.split(r"(?=Message:)", raw)
    rows = []
    for b in blocks:
        scores = {}
        for d in DIMS:
            m = re.search(rf"{re.escape(d)}\s+\[.*?\]\s+(\d+)/10", b)
            if m: scores[d] = int(m.group(1))
        if len(scores) == 5:
            preview = (re.search(r'Message:\s+"([^"]+)"', b) or [None, "?"])[1][:60]
            rows.append((scores, preview))
    return rows


# Aggregate every message across every run, keyed by msg-preview (rough id).
all_rows = []
for log in LOGS:
    for scores, preview in parse(log):
        all_rows.append({"log": log.name, "preview": preview, **scores, "total": sum(scores.values())})

if not all_rows:
    print("no data"); sys.exit(1)

# Per-dim stats across ALL messages (not just one run).
print(f"=== TASK 2 — per-dim stats across {len(all_rows)} message-evaluations from {len(LOGS)} runs ===\n")
for d in DIMS + ("total",):
    vals = [r[d] for r in all_rows] if d != "total" else [r["total"] for r in all_rows]
    target = 50 if d == "total" else 10
    print(f"  {d:18}: mean={statistics.mean(vals):.2f}/{target}  median={statistics.median(vals)}  "
          f"min={min(vals)}  max={max(vals)}  stdev={statistics.stdev(vals):.2f}")

# Bottom 5 messages overall (drag the average).
print("\n=== Bottom 8 message-evaluations (drag the average) ===")
all_rows.sort(key=lambda r: r["total"])
for r in all_rows[:8]:
    parts = " ".join(f"{d[:3]}={r[d]}" for d in DIMS)
    print(f"  total={r['total']:>2}  {parts}  | {r['preview']}")

# Group by trigger-kind heuristic (preview prefix tells you who's being addressed).
print("\n=== By message preview prefix (proxy for trigger.kind) — mean total ===")
buckets = defaultdict(list)
for r in all_rows:
    p = r["preview"].lower()
    if "kids yoga" in p: k = "kids_yoga (planning + trial_followup)"
    elif "smile studio" in p: k = "competitor_opened"
    elif "atorvastatin" in p or "cdsco" in p: k = "supply_alert"
    elif "dci" in p or "compliance" in p: k = "regulation_change"
    elif "bridal" in p or "kavya" in p: k = "wedding_followup"
    elif "anjali" in p and "humne" in p: k = "dormancy"
    elif "anjali" in p: k = "winback (Anjali)"
    elif "lapsed" in p or "rashmi" in p: k = "lapsed_hard"
    elif "review" in p: k = "review_theme"
    elif "milestone" in p or "145" in p or "150" in p: k = "milestone"
    elif "perf_dip" in p or "calls 4" in p or "calls last 7" in p or "bharat" in p: k = "perf_dip"
    elif "calls" in p and ("up" in p or "+15" in p or "spike" in p): k = "perf_spike"
    elif "padma" in p: k = "perf_spike (Padma)"
    elif "vikas" in p or "sunrise" in p or "google" in p: k = "gbp_unverified"
    elif "ramesh" in p: k = "supply_alert"
    elif "jida" in p or "research" in p or "fluoride" in p: k = "research_digest"
    elif "ipl" in p or "dc vs mi" in p: k = "ipl"
    elif "diwali" in p or "festival" in p: k = "festival"
    elif "summer" in p: k = "category_seasonal"
    elif "thali" in p or "indiranagar" in p: k = "active_planning"
    else: k = "other"
    buckets[k].append(r["total"])
for k, vals in sorted(buckets.items(), key=lambda kv: statistics.mean(kv[1])):
    print(f"  {k:42}  n={len(vals):>2}  mean={statistics.mean(vals):.1f}  range=[{min(vals)},{max(vals)}]")
