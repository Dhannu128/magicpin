# Vera — magicpin AI Challenge submission

**Team:** Pro Bro &nbsp; · &nbsp; **Author:** Dhannu Ram Meena &nbsp; · &nbsp; **Contact:** dhannumeena281229111@gmail.com
**Model:** `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` (primary) · `anthropic/claude-haiku-4.5` (safety-net fallback) — both via TokenRouter (OpenAI-compatible). Pipeline is model-agnostic; the deterministic validator + per-kind fallback templates absorb most of the quality delta vs. larger models.

## Approach

A FastAPI bot that exposes the 5 challenge endpoints (`/v1/healthz`, `/v1/metadata`, `/v1/context`, `/v1/tick`, `/v1/reply`) and composes every WhatsApp body through a single LLM pipeline structured to maximize the 5-dimension judge score.

**The composer pipeline** (the part that wins):

1. **Build a structured `facts` pack** from the 4 contexts (CategoryContext + MerchantContext + TriggerContext + optional CustomerContext) — only verifiable values: numbers, dates, source citations, active offers, signals, peer-stats, customer aggregates. *No* text not derivable from those four objects.
2. **Pick a voice pack** (one per category — `dentists`, `salons`, `restaurants`, `gyms`, `pharmacies`) and a **kind pack** (one per trigger.kind — `research_digest`, `recall_due`, `ipl_match_today`, `supply_alert`, `seasonal_perf_dip`, `active_planning_intent`, `intent_handoff`, …). The kind pack tells the LLM *which compulsion levers to lead with*.
3. **Call the primary model** with `temperature=0`, `top_p=1` (deterministic), strict JSON output: `{body, cta_kind, rationale}`.
4. **Run the post-LLM validator** against the body:
   - no URL (Meta would reject; -3)
   - no taboo vocab (per CategoryContext.voice.vocab_taboo)
   - every numeric/percentage/₹/source/batch in the body must appear as a substring of the facts pack (anti-fabrication)
   - exactly one CTA, in the last sentence
   - owner first-name salutation present (or customer name for customer-facing)
   - language preference honored (hi-en mix → Hindi-English mix detected)
   - not byte-identical to a prior body in the conversation
5. **Repair pass** if validation fails: re-prompt the model once with the failure reasons.
6. **Deterministic per-kind fallback template** if the LLM still fails — keeps us above floor under any failure mode.

**Reply router** runs detectors in priority order: `hostile → end (+ 30-day merchant suppression)` · `auto-reply (3-strike: prompt-once → wait-24h → end)` · `intent-transition → switch to ACTION mode (deliver concrete artifact + binary CONFIRM, NEVER re-qualify)` · `curveball → polite decline + redirect to original trigger` · `wait signal → wait 1h` · `engaged → honor + advance one step`. Mid-stream context updates always honored — every reply re-reads the live context store.

**Tick planner** filters expired/suppressed triggers, scores each `(merchant, trigger)` pair on `urgency × merchant_fit_score` (e.g., a `research_digest` about high-risk-adults only fits a merchant whose signals include `high_risk_adult_cohort`), takes top-K with one action per merchant per tick, composes in parallel under a 9-second budget. Returns `{actions: []}` rather than time out.

**Determinism:** `temperature=0`, `top_p=1`, sorted JSON keys throughout, stable `conversation_id` (`conv_{merchant_id}_{kind}_{suppression_key_short}`), stable `suppression_key` from trigger or derived as `{kind}:{merchant_id}:{date}`.

**Stateful:** in-memory `ContextStore` keyed by `(scope, context_id)`, idempotent on `(scope, context_id, version)` — re-pushing same/lower version returns 409. Higher version replaces atomically. `ConversationStore` and `Suppressor` survive across calls.

## Tradeoffs

- **Single LLM pipeline > rules-only**: the rubric rewards judgement (Case Study 5: contrarian "skip the IPL promo on Saturday" advice). Templated bots cap at ~35/50.
- **TokenRouter over going direct to Anthropic**: lets us swap models without changing code. Adds one network hop (~50 ms) — well within the 9 s tick budget.
- **In-memory state**: brief permits it; spares us a DB. Lost on restart, but the harness pushes the base dataset on warmup so we recover.
- **Deterministic fallback bodies**: less elegant than the LLM but they still hit ≥7/dim because they pull from the same facts pack.

## What additional context would have helped

1. **Slot/inventory APIs** — for `recall_due` and `chronic_refill_due` we currently echo the slots in the trigger payload. A live calendar would let us propose the *actual* next-available evening slot per Priya's preference.
2. **Last-N-messages-the-customer-saw** — for `customer_lapsed_hard` the body shape changes if we know whether they saw a winback recently from another merchant.
3. **Locality demographic data** — would sharpen claims like "3 dentists in your locality did Y this month" with a real peer-cohort count rather than the category-wide `peer_stats`.

## Run locally

```bash
pip install -r requirements.txt
cp bot/.env.example bot/.env   # edit LLM_API_KEY
uvicorn bot.main:app --host 0.0.0.0 --port 8080
```

```bash
# Configure judge_simulator.py:
#   BOT_URL = "http://localhost:8080"
#   LLM_PROVIDER = "openai"   (TokenRouter uses OpenAI-compatible shape)
#   LLM_API_KEY = "<your TokenRouter key>"
#   LLM_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
# Edit the OpenAIProvider URL inside judge_simulator.py to https://api.tokenrouter.com/v1
# (or use ANTHROPIC_PROVIDER directly if you have an Anthropic key.)
python judge_simulator.py
```

## Deploy (Render)

1. Push this repo to GitHub.
2. Render → New → Web Service → connect repo → Dockerfile auto-detected.
3. Set env vars (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_PRIMARY`, `LLM_MODEL_FAST`, `TEAM_NAME`, `CONTACT_EMAIL`, `BOT_VERSION`).
4. Click Deploy — public URL appears in 2–3 min.

(Fly.io: `flyctl launch && flyctl secrets set LLM_API_KEY=...` — same Dockerfile.)

## Tests

```bash
pytest -q
```

- `test_idempotency.py` — `/v1/context` is idempotent on `(scope, context_id, version)`; higher version replaces atomically; same/lower version → 409.
- `test_composer_facts_only.py` — golden tests against the 10 case studies: each composed body scores ≥9 on judgement criteria via the validator, AND has Jaccard < 0.5 against the case-study body (no plagiarism).
- `test_replay_scenarios.py` — auto-reply hell (3 strikes → end), intent transition (no re-qualifying), hostile (immediate end + 30-day suppression).

## License

MIT. Synthetic dataset; no real merchant/customer data.
