"""Parse judge_run_*.log and print real (un-truncated) average scores."""

from __future__ import annotations
import re
import sys
import statistics

DIMS = ("Specificity", "Category Fit", "Merchant Fit", "Decision Quality", "Engagement")


def parse(path: str) -> None:
    # Try utf-16 first (Windows Tee-Object default), fall back to utf-8.
    try:
        raw = open(path, encoding="utf-16", errors="replace").read()
        if "Message:" not in raw:
            raise ValueError("no msgs in utf-16")
    except Exception:
        raw = open(path, encoding="utf-8", errors="replace").read()
    # Strip ANSI
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    # Iterate "Message:" blocks
    blocks = re.split(r"(?=Message:)", raw)
    per_msg = []
    msg_idx = 0
    for b in blocks:
        scores = {}
        for d in DIMS:
            m = re.search(rf"{re.escape(d)}\s+\[.*?\]\s+(\d+)/10", b)
            if m:
                scores[d] = int(m.group(1))
        if len(scores) == 5:
            msg_idx += 1
            preview = (re.search(r'Message:\s+"([^"]+)"', b) or [None, "?"])[1][:40]
            total = sum(scores.values())
            per_msg.append((msg_idx, total, scores, preview))
    if not per_msg:
        print("no messages parsed from", path)
        return
    print(f"\n=== {path} ===")
    print(f"{'#':>3}  {'TOTAL':>5}  {'Spec':>4}  {'Cat':>3}  {'Mer':>3}  {'Dec':>3}  {'Eng':>3}  Preview")
    for i, t, s, p in per_msg:
        print(f"{i:>3}  {t:>5}  {s['Specificity']:>4}  {s['Category Fit']:>3}  {s['Merchant Fit']:>3}  "
              f"{s['Decision Quality']:>3}  {s['Engagement']:>3}  {p}")
    totals = [t for _, t, _, _ in per_msg]
    print(f"\nN={len(totals)}  mean={statistics.mean(totals):.2f}/50  median={statistics.median(totals)}  "
          f"min={min(totals)}  max={max(totals)}  stdev={statistics.stdev(totals) if len(totals)>1 else 0:.2f}")
    for d in DIMS:
        vals = [s[d] for _, _, s, _ in per_msg]
        print(f"  Avg {d:18}: {statistics.mean(vals):.2f}/10  (min {min(vals)}, max {max(vals)})")


if __name__ == "__main__":
    for p in sys.argv[1:] or ["judge_run_3.log"]:
        parse(p)
