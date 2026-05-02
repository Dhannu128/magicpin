# Final report — magicpin Vera AI Challenge

**Team**: Pro Bro &nbsp; · &nbsp; **Author**: Dhannu Ram Meena &nbsp; · &nbsp; **Email**: dhannumeena281229111@gmail.com

## 🌐 Public bot URL

**`https://vera-bot-8reg.onrender.com`**

| Endpoint | Verified | Notes |
|---|---|---|
| `GET  /v1/healthz` | ✅ | returns `{status, uptime_seconds, contexts_loaded:{category,merchant,customer,trigger}}` |
| `GET  /v1/metadata` | ✅ | team=Pro Bro, model=anthropic/claude-opus-4.7, version=1.0.0 |
| `POST /v1/context` | ✅ | idempotent on (scope, context_id, version); 409 on stale; 400 on invalid scope |
| `POST /v1/tick` | ✅ | returns `{actions:[...]}`, ≤6 per tick, all required fields, no URLs in body |
| `POST /v1/reply` | ✅ | `send` / `wait` / `end` per the rubric |

## 📊 Scores against `judge_simulator.py` (all runs against the public URL)

**Real un-truncated mean: 40.31/50** (81%, "EXCELLENT" tier per the simulator's own banding).
The judge_simulator's printed "AVERAGE SCORE" integer-truncates per dimension, displaying "38/50 (76%) GOOD" — but the real per-message arithmetic mean is 40.31.

Per-dimension averages on the public URL:
- Specificity:   8.23/10 (min 6, max 9)
- Category Fit:  7.92/10 (min 6, max 10)
- Merchant Fit:  7.62/10 (min 6, max 9)
- Decision Quality: 8.54/10 (min 7, max 9)
- Engagement:    8.00/10 (min 7, max 9)

**Best single message**: 44/50 (review_theme for SK Pizza Junction — verbatim quote + contrast lever + draft offer).

**Replay scenarios**:
- ✅ Auto-reply hell — 1-prompt → 24h-wait → end (now also escalates across new conversation_ids per merchant)
- ✅ Intent transition — switches to ACTION mode, no re-qualifying
- ✅ Hostile — immediate `end` + 30-day merchant suppression
- ✅ Curveball — polite decline + redirect to original trigger

## 📋 Submission checklist (paste into the form)

| Field | Value |
|---|---|
| Public URL | `https://vera-bot-8reg.onrender.com` |
| Team name | Pro Bro |
| Author | Dhannu Ram Meena |
| Contact email | dhannumeena281229111@gmail.com |
| Model | anthropic/claude-opus-4.7 (primary) + anthropic/claude-haiku-4.5 (fast fallback) via TokenRouter |
| Version | 1.0.0 |
| GitHub repo (if portal asks) | https://github.com/Dhannu128/magicpin |
| Approach (one-liner) | Per-trigger-kind prompt routing with structured facts-pack guardrails, post-LLM validator (no URL / no taboo / single CTA / language honored / no repeat), voice packs from CategoryContext, stateful idempotent context store, replay-aware reply router (auto-reply 3-strike / hostile / intent / curveball / wait), per-kind deterministic fallbacks. |

## 🔑 Operating notes for the harness window

**Render free tier spins down after 15 min of inactivity** with ~30-50s cold start.
Two options before the test window opens:

1. **Recommended**: upgrade Render to Starter ($7/month) for the test window — eliminates cold start, stable warm machine.
2. **Workaround for free tier**: open https://uptimerobot.com (free), add an HTTP monitor on
   `https://vera-bot-8reg.onrender.com/v1/healthz` with 5-minute interval. Keeps the bot warm.
   Add the monitor at least 1 hour before the test window starts.

**LLM cost**: ~$0.02 per full 25-trigger sweep (Opus 4.7 ≈ $0.000255 per call). The 60-min harness will be well under $1.

## 🛠 Repo layout

```
bot/
  main.py              FastAPI app (5 endpoints)
  composer.py          facts-pack builder + LLM call + post-LLM validator
  reply_router.py      7 detectors in priority order
  tick_planner.py      rank by urgency × merchant_fit, parallel compose under budget
  state.py             ContextStore (idempotent), ConversationStore, Suppressor
  llm.py               TokenRouter via OpenAI SDK, async, deterministic
  templates/fallback.py  24 per-kind deterministic templates
  prompts/
    system_base.md     system prompt with all hard rules
    voice/{dentists,salons,restaurants,gyms,pharmacies}.md
    kind_packs.py      24 trigger-kind packs with format scaffolds
deploy/
  DEPLOY.md, render.yaml, fly.toml
tests/
  22 passing tests (idempotency, fallbacks, replay scenarios + cross-conversation auto-reply)
Dockerfile, requirements.txt, README.md, SUBMISSION_CHECKLIST.md, submission.jsonl
run_judge.py, parse_scores.py, build_submission_jsonl.py, inspect_actions.py
```

## 🎯 What the bot does that production Vera doesn't

1. **Cross-conversation auto-reply detection** — escalates 1-prompt → wait → end even when the harness opens a new `conversation_id` per turn.
2. **Per-kind compulsion-lever routing** — 24 trigger kinds each have explicit format scaffolds and lever guidance instead of a single generic prompt.
3. **Post-LLM fact validator** — every source citation (JIDA, DCI, CDSCO, ...) and batch number in the body must appear in the facts pack; URL/taboo/repeat checks block bad outputs.
4. **De-jargon pre-pass** — `delivery_late` → `delivery delays`, `kids_yoga` → `kids yoga`, etc., before the prompt sees the data, so the LLM never quotes raw payload keys.
5. **Pre-computed derivations** — `merchant.derived` exposes `peer_avg_ctr_pct`, `calls_vs_peer_pct`, `weeks_since_last_visit`, `estimated_views_post_verification` so the LLM reaches for ready-made comparison numbers.
6. **Customer vs merchant salutation** — for `send_as=merchant_on_behalf` the body opens with the customer's name (or parent name for minors, or "Namaste {name} ji" for seniors), never the merchant owner's name.
7. **Contrarian-operator advice on triggers like IPL** — "Saturday IPL = -12% covers, skip the match-night promo, push your existing BOGO as delivery-special" — case-study #5 behaviour out of the box.

## 🔁 To redeploy with changes

```powershell
cd D:\personal\AI-ML\hackathon\Magicpin\magicpin-ai-challenge
git add .
git commit -m "describe change"
git push
```

Render auto-rebuilds on every push to `main` (~2-3 min).
