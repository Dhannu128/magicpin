# Submission checklist — Pro Bro / Vera bot

## Identity (for the form)
- **Team name**: Pro Bro
- **Author**: Dhannu Ram Meena
- **Contact email**: dhannumeena281229111@gmail.com
- **Model**: anthropic/claude-opus-4.7 (primary) + anthropic/claude-haiku-4.5 (fast fallback) — both via TokenRouter (OpenAI-compatible at https://api.tokenrouter.com/v1)
- **Approach (one-liner)**: per-trigger-kind prompt routing with structured facts-pack guardrails, deterministic post-LLM validator (no URL / no taboo / single CTA / language honored), voice packs derived from CategoryContext, stateful idempotent context store, replay-aware reply router (auto-reply 3-strike / hostile / intent-transition / curveball / wait detectors), deterministic per-kind fallback templates.
- **Bot version**: 1.0.0

## Local validation done
- [x] All 21 contract + scenario tests green (`pytest -q`)
- [x] All 5 endpoints implemented per `examples/api-call-examples.md` schemas
- [x] `/v1/context` is idempotent on `(scope, context_id, version)`; same-or-lower → 409 with `current_version`
- [x] `/v1/tick` returns `{"actions": []}` rather than time out under any LLM failure
- [x] `/v1/reply` covers auto-reply (1-prompt → 24h-wait → end), hostile (immediate end + 30d cooldown), intent-transition (action mode, no re-qualifying), curveball (polite redirect), wait, engaged (honor + advance)
- [x] Anti-fabrication: source tokens (JIDA/DCI/CDSCO/JAMA/...) and batch numbers are validated against the facts pack
- [x] Anti-jargon: snake_case payload keys are humanized before being shown to the LLM ("delivery_late" → "delivery delays")
- [x] Customer-facing salutation correctly addresses customer/parent (not merchant owner) when send_as=merchant_on_behalf
- [x] Hindi-English code-mix honored when `identity.languages` contains "hi" or `customer.language_pref` contains "hi"
- [x] Determinism: temperature=0, top_p=1, sorted JSON keys, stable conversation_id, stable suppression_key

## judge_simulator.py results (5 full runs, mean across 13 messages each)
- Run 1: 39.0/50  (78%, "GOOD") — baseline
- Run 2: 39.2/50  (78%, "GOOD") — after de-jargon + customer-name fixes
- Run 3: 38.9/50  (78%, "GOOD") — after looser numeric validator
- Run 4: 39.0/50  (78%, "GOOD") — after kind_pack scaffolds (one outlier 23/50 from a fabrication-flagged planning intent)
- Run 5: **40.3/50** (81%, "EXCELLENT" tier) — after derived-facts pre-computation, **best run**
- Run 6: 39.4/50  (79%, "GOOD") — confirms ~40 plateau, judge variance ±1.5

Judge variance: stdev ~3 per message (judge runs at temp=0.2). Best message **44/50**; floor **31-36** on planning-intent outliers; mode **40-43**.

## Deliverables
- [x] **`bot.py` equivalent** → `bot/main.py` + `bot/composer.py` + `bot/reply_router.py` + `bot/tick_planner.py` + `bot/state.py` + `bot/llm.py` + `bot/templates/fallback.py` + `bot/prompts/{system_base.md, voice/*.md, kind_packs.py}`
- [x] **`submission.jsonl`** — 24 rows, one per (merchant, trigger) pair from the seed dataset, full `body`/`cta`/`rationale` populated
- [x] **`README.md`** — approach + tradeoffs + what additional context would have helped
- [x] **`Dockerfile`** + `requirements.txt` for one-click deploy
- [x] **`deploy/`** — Render blueprint, Fly.io blueprint, ngrok+local instructions

## Pre-flight before clicking "Submit"
- [ ] Public URL is reachable: `curl https://<your-host>/v1/healthz` returns 200 with status=ok
- [ ] `curl https://<your-host>/v1/metadata` returns the team/version/model JSON above
- [ ] Re-run `python run_judge.py full_evaluation` with `BOT_URL=https://<public-host>` and confirm parity with local (~39-40 mean)
- [ ] Submission portal: paste the public URL + email + team name above
- [ ] Optional artifacts to attach if portal allows: `submission.jsonl`, `README.md`

## Operating notes for the harness
- Tick budget: 13s (well under the 30s harness limit; LLM call ≈ 4-5s, repair pass + buffer fits)
- LLM cost per full 25-trigger sweep: ~$0.02 (Opus 4.7 at $0.000255 per short call)
- Failure modes:
  - LLM timeout → falls back to deterministic per-kind template (still uses facts pack; no URL, single CTA, voice-correct)
  - Validator fails twice → same fallback path
  - Hostile signal → 30-day merchant suppression + immediate `end`
  - Auto-reply 3 times → `wait` 24h on strike 2, `end` on strike 3
  - Bot restart → contexts cleared but harness re-pushes the base dataset on warmup, so it self-recovers
