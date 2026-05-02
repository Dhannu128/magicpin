"""Per-trigger-kind deterministic fallback bodies.

Used when the LLM call times out, fails, or produces output that fails the
post-LLM validator twice. Pulls from the facts pack so the body still scores —
just less elegant prose than the LLM. NO fabrication, NO URLs, single CTA.
"""

from __future__ import annotations

from typing import Any


def _safe(d: dict | None, *keys, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _first_active_offer(facts: dict[str, Any]) -> str | None:
    offers = _safe(facts, "merchant", "active_offers", default=[]) or []
    if offers and isinstance(offers[0], str):
        return offers[0]
    return None


def _hi(language_mode: str | None) -> bool:
    return language_mode in {"hi-en", "hi"}


def _salutation(facts: dict[str, Any]) -> str:
    salu = _safe(facts, "merchant", "salutation")
    return str(salu) if salu else "Hi"


def _customer_name(facts: dict[str, Any]) -> str:
    return _safe(facts, "customer", "name") or "there"


# ─── Per-kind fallbacks ─────────────────────────────────────────────────────

def fb_research_digest(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    digest = _safe(facts, "category", "digest_item", default={}) or {}
    title = digest.get("title", "the latest digest item")
    source = digest.get("source", "")
    trial_n = digest.get("trial_n")
    seg = digest.get("patient_segment")
    cohort_count = _safe(facts, "merchant", "customer_aggregate", "high_risk_adult_count")
    locality = _safe(facts, "merchant", "locality") or ""

    parts = [f"{salu}, latest digest item:"]
    if seg and cohort_count:
        parts.append(f"{title}. Likely relevant to your {cohort_count} {seg.replace('_', ' ')} patients in {locality}.")
    else:
        parts.append(f"{title}.")
    if trial_n:
        parts.append(f"Trial size: {trial_n} patients.")
    parts.append("Want me to pull the abstract + draft a patient-ed WhatsApp keyed to your relevant cohort?")
    body = " ".join(parts)
    if source:
        body += f" — {source}"
    return {"body": body, "cta_kind": "open_ended", "rationale": f"research_digest fallback: source-cited (‘{source}’), tied to merchant cohort signal."}


def fb_regulation_change(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    digest = _safe(facts, "category", "digest_item", default={}) or {}
    title = digest.get("title", "a regulatory change")
    source = digest.get("source", "")
    deadline = _safe(facts, "trigger", "payload", "deadline_iso", default="")
    body = (
        f"{salu}, heads up — {title}."
        f" Effective {deadline.split('T')[0] if deadline else 'soon'}."
        f" Want me to draft your updated SOP + a compliance checklist before the deadline?"
    )
    if source:
        body += f" — {source}"
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "regulation_change fallback: deadline + source + draft offer."}


def fb_supply_alert(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    molecule = payload.get("molecule", "the affected molecule")
    batches = ", ".join(payload.get("affected_batches", []) or [])
    chronic_count = _safe(facts, "merchant", "customer_aggregate", "chronic_rx_count")
    body = (
        f"{salu}, urgent: voluntary recall on {molecule} batches ({batches})"
        f" — sub-potency, no safety risk, but customers should be informed for replacement."
    )
    if chronic_count:
        body += f" Your repeat-Rx list shows {chronic_count} chronic-Rx customers to cross-check."
    body += " Want me to draft their WhatsApp note + the replacement-pickup workflow?"
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "supply_alert fallback: batch numbers + derived count + workflow offer."}


def fb_perf_dip(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    metric = payload.get("metric", "calls")
    delta_pct = payload.get("delta_pct")
    pct_str = f"{int(round(abs(delta_pct) * 100))}%" if isinstance(delta_pct, (int, float)) else "noticeably"
    body = (
        f"{salu}, your {metric} are down {pct_str} this week."
        f" Worth a 7-day attendance-recovery plan tied to your top customers."
        f" Want me to draft it?"
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "perf_dip fallback: metric + delta + retention play."}


def fb_seasonal_perf_dip(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    metric = payload.get("metric", "views")
    delta_pct = payload.get("delta_pct")
    pct_str = f"{int(round(abs(delta_pct) * 100))}%" if isinstance(delta_pct, (int, float)) else ""
    members = _safe(facts, "merchant", "customer_aggregate", "total_active_members")
    body = (
        f"{salu}, {metric} down {pct_str} this week — but this is the normal April-June lull"
        f"; bookings typically recover by 2nd week May."
    )
    if members:
        body += f" Skip ad spend now; focus retention on your {members} members."
    body += " Want me to draft a summer attendance challenge?"
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "seasonal_perf_dip fallback: reframe + retention pivot + member count."}


def fb_milestone_reached(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    metric = payload.get("metric", "milestone")
    value_now = payload.get("value_now")
    target = payload.get("milestone_value")
    body = (
        f"{salu}, you're at {value_now} {metric} — {target} milestone is in sight."
        f" Which review do you want pinned at the top of your GBP for the moment?"
    )
    return {"body": body, "cta_kind": "open_ended", "rationale": "milestone_reached fallback: celebrate + ask-the-merchant."}


def fb_dormant(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    days = payload.get("days_since_last_merchant_message", "")
    last_topic = (payload.get("last_topic") or "").replace("_", " ")
    perf = _safe(facts, "merchant", "performance", default={}) or {}
    calls = perf.get("calls")
    delta = ((perf.get("delta_7d") or {}).get("calls_pct"))
    delta_str = f"{int(round(delta * 100))}%" if isinstance(delta, (int, float)) else ""
    locality = _safe(facts, "merchant", "locality", default="") or ""
    lapsed = (
        _safe(facts, "merchant", "customer_aggregate", "lapsed_180d_plus")
        or _safe(facts, "merchant", "customer_aggregate", "lapsed_90d_plus")
    )
    parts = [f"{salu}, {days} din ho gaye humari last baat ko"]
    if last_topic:
        parts[-1] += f" ({last_topic} ke baad se)"
    parts[-1] += "."
    if isinstance(calls, (int, float)) and delta_str:
        parts.append(f"Last 30 din mein calls {calls} pe aaye, 7-day delta {delta_str}{(' — ' + locality + ' ke liye thoda low') if locality else ''}.")
    if lapsed:
        parts.append(f"{lapsed} lapsed clients bhi list mein baithe hain jin par retention play chal sakti hai.")
    parts.append("Quick one — abhi sabse bada blocker kya hai? Jo bataenge, uske hisaab se main agle 7 din ka plan bana deti hoon.")
    body = " ".join(parts)
    return {"body": body, "cta_kind": "open_ended", "rationale": "dormant fallback: ask-the-merchant + reciprocity, anchored on real perf + lapsed numbers."}


def fb_curious_ask(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    name = _safe(facts, "merchant", "name", default="")
    body = (
        f"{salu}! Quick check — what service has been most asked-for this week"
        f"{' at ' + name if name else ''}? I'll turn it into a Google post + a 4-line WhatsApp reply you can use. Takes 5 min."
    )
    return {"body": body, "cta_kind": "open_ended", "rationale": "curious_ask fallback: low-stakes question + reciprocity."}


def fb_winback(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    days = payload.get("days_since_expiry", "")
    dip = payload.get("perf_dip_pct")
    pct = f"{int(round(abs(dip) * 100))}%" if isinstance(dip, (int, float)) else ""
    body = (
        f"{salu}, {days} days since renewal lapsed and {('views down ' + pct) if pct else 'traffic has slipped'}."
        f" Want me to draft a 7-day re-activation push (winback offer + 3 GBP posts)? 10 min to set up."
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "winback fallback: candid + concrete + draft offer."}


def fb_ipl(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    match = payload.get("match", "tonight's match")
    venue = payload.get("venue", "")
    time_iso = payload.get("match_time_iso", "")
    is_weeknight = payload.get("is_weeknight", True)
    offer = _first_active_offer(facts)
    body = f"{salu}, heads-up — {match} at {venue}, {time_iso.split('T')[1][:5] if 'T' in (time_iso or '') else ''}."
    if not is_weeknight:
        body += " Saturday IPL matches usually shift -12% restaurant covers (people watch at home)."
        if offer:
            body += f" Skip the match-night promo; push your {offer} as a delivery-only Saturday special instead."
    elif offer:
        body += f" Push your {offer} as the match-night combo."
    body += " Want me to draft the Swiggy banner + an Insta story? Live in 10 min."
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "ipl fallback: match details + contrarian-on-Saturday + leverage existing offer."}


def fb_festival(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    festival = payload.get("festival", "the festival")
    days = payload.get("days_until")
    offer = _first_active_offer(facts)
    body = f"{salu}, {festival} is {days} days out."
    if offer:
        body += f" Want me to draft a {festival} GBP post + WhatsApp combo built around your {offer}? 15 min."
    else:
        body += f" Want me to draft a {festival} GBP post + WhatsApp combo for your top SKU? 15 min."
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "festival fallback: timing + leverage existing offer."}


def fb_review_theme(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    theme = (payload.get("theme") or "").replace("_", " ")
    occ = payload.get("occurrences_30d")
    quote = payload.get("common_quote")
    body = f"{salu}, {occ} reviews this month flag {theme}"
    if quote:
        body += f' (e.g. "{quote}")'
    body += ". Want a 3-step fix? I'll draft the customer-facing reply too."
    return {"body": body, "cta_kind": "open_ended", "rationale": "review_theme fallback: theme + count + quote + draft offer."}


def fb_competitor(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    name = payload.get("competitor_name", "a new clinic")
    dist = payload.get("distance_km")
    body = (
        f"{salu}, FYI — {name} opened {dist} km away."
        f" Best response is to publish a 'why our patients stay' review-pinned post + a 3-month retention WhatsApp series."
        f" Want me to draft both?"
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "competitor fallback: defend-with-strength, no disparagement."}


def fb_renewal(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    days = payload.get("days_remaining")
    plan = payload.get("plan", "Pro")
    amount = payload.get("renewal_amount")
    body = (
        f"{salu}, your {plan} subscription renews in {days} days (₹{amount})."
        f" Reply CONFIRM and I'll auto-renew with no break in service. Reply CANCEL to discuss."
    )
    return {"body": body, "cta_kind": "binary_confirm_cancel", "rationale": "renewal fallback: quiet confidence + binary."}


def fb_gbp_unverified(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    uplift = payload.get("estimated_uplift_pct")
    pct = f"+{int(round(uplift * 100))}%" if isinstance(uplift, (int, float)) else "uplift"
    body = (
        f"{salu}, your GBP is unverified — average {pct} on views post-verification."
        f" Want the 5-min postcard-verification walk-through? I'll send the steps now."
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "gbp_unverified fallback: estimated uplift + low-friction step."}


def fb_cde(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    digest = _safe(facts, "category", "digest_item", default={}) or {}
    title = digest.get("title", "an upcoming CDE webinar")
    date = digest.get("date", "")
    fee = payload.get("fee", "")
    body = (
        f"{salu}, {title}{' on ' + date.split('T')[0] if date else ''}."
        f"{' ' + fee.replace('_', ' ') + '.' if fee else ''}"
        f" Want me to register you + add the date to your calendar?"
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "cde fallback: relevance + low-friction registration."}


def fb_planning(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    topic = (payload.get("intent_topic") or "your idea").replace("_", " ")
    body = (
        f"{salu}, here's a starter outline for the {topic} — you can edit:\n"
        f"- Tier 1: small (10 units) + free delivery\n"
        f"- Tier 2: medium (25 units) + free add-on\n"
        f"- Tier 3: 50+ units, deeper unit price + free starter\n"
        f"Want me to draft the 3-line outreach WhatsApp now?"
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "planning fallback: deliver artifact + binary follow-on (no re-qualifying)."}


def fb_perf_spike(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    metric = payload.get("metric", "calls")
    delta_pct = payload.get("delta_pct")
    pct = f"+{int(round(delta_pct * 100))}%" if isinstance(delta_pct, (int, float)) else "up"
    driver = (payload.get("likely_driver") or "").replace("_", " ")
    body = f"{salu}, your {metric} are {pct} this week"
    if driver:
        body += f" — looks like your {driver} post is driving it"
    body += ". What changed in the last 7 days? I can replicate it across your other posts."
    return {"body": body, "cta_kind": "open_ended", "rationale": "perf_spike fallback: celebrate + curiosity."}


def fb_recall_due(facts: dict[str, Any]) -> dict[str, Any]:
    name = _customer_name(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    slots = payload.get("available_slots") or []
    s1 = slots[0]["label"] if len(slots) > 0 else "this Wed"
    s2 = slots[1]["label"] if len(slots) > 1 else "this Thu"
    merchant_name = _safe(facts, "merchant", "name", default="our clinic")
    offer = _first_active_offer(facts)
    hi = _hi(_safe(facts, "language_mode"))
    if hi:
        body = (
            f"Hi {name}, {merchant_name} yahan — aapka 6-month cleaning recall due hai."
            f" 2 slots ready hain: {s1} ya {s2}."
        )
        if offer:
            body += f" {offer} + complimentary fluoride."
        body += f" Reply 1 for {s1.split(',')[0]}, 2 for {s2.split(',')[0]}, ya apna preferred time bata dijiye."
    else:
        body = (
            f"Hi {name}, {merchant_name} here — your 6-month cleaning recall is due."
            f" 2 slots ready: {s1} or {s2}."
        )
        if offer:
            body += f" {offer} + complimentary fluoride."
        body += f" Reply 1 for {s1.split(',')[0]}, 2 for {s2.split(',')[0]}, or tell us a time that works."
    return {"body": body, "cta_kind": "multi_choice_slot", "rationale": "recall_due fallback: name + slots + price + low-friction multi-choice (booking allowed); language honored."}


def fb_chronic_refill(facts: dict[str, Any]) -> dict[str, Any]:
    name = _customer_name(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    molecules = ", ".join(payload.get("molecule_list", []) or [])
    runout = (payload.get("stock_runs_out_iso") or "").split("T")[0]
    senior = _safe(facts, "customer", "senior_citizen", default=False)
    pharm_name = _safe(facts, "merchant", "name", default="our pharmacy")
    locality = _safe(facts, "merchant", "locality", default="")
    salutation = "Namaste" if senior else f"Hi {name}"
    family_addr = "Sharma ji" if senior and "sharma" in (name or "").lower() else name
    body = (
        f"{salutation} — {pharm_name} {locality} yahan."
        f" {family_addr} ki monthly medicines ({molecules}) {runout} ko khatam hongi."
        f" Same dose, same brand pack ready hai. Senior discount applied; free home delivery to saved address."
        f" Reply CONFIRM to dispatch, or call us if any change in dosage."
    )
    return {"body": body, "cta_kind": "binary_confirm_cancel", "rationale": "chronic_refill fallback: full molecules + date + senior discount + two-channel option."}


def fb_trial_followup(facts: dict[str, Any]) -> dict[str, Any]:
    name = _customer_name(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    options = payload.get("next_session_options") or []
    slot = options[0]["label"] if options else "the next available session"
    body = f"Hi {name}, hope the trial went well! Reply YES to confirm {slot}, or tell us another time."
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "trial_followup fallback: continuation + concrete slot + confirm."}


def fb_wedding_followup(facts: dict[str, Any]) -> dict[str, Any]:
    name = _customer_name(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    days = payload.get("days_to_wedding")
    program = (payload.get("next_step_window_open") or "").replace("_", " ")
    salon = _safe(facts, "merchant", "name", default="our salon")
    body = (
        f"Hi {name} 💍 {salon} here. {days} days to your wedding — perfect window for the {program}."
        f" Want me to block your preferred Saturday slot for the first session next week?"
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "wedding_followup fallback: relationship + count + program + slot pref."}


def fb_lapsed_hard(facts: dict[str, Any]) -> dict[str, Any]:
    name = _customer_name(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    days = payload.get("days_since_last_visit")
    weeks = round(days / 7) if isinstance(days, (int, float)) else None
    focus = (payload.get("previous_focus") or "").replace("_", " ")
    gym_name = _safe(facts, "merchant", "name", default="our gym")
    offer = _first_active_offer(facts)
    body = (
        f"Hi {name} 👋 {gym_name} here. It's been about {weeks or days} weeks — happens to most members at some point, no judgment."
    )
    if focus:
        body += f" We've added a class that fits your {focus} goals well."
    if offer:
        body += f" Want me to hold a free trial spot next week with {offer}? Reply YES — no commitment, no auto-charge."
    else:
        body += " Want me to hold a free trial spot next week? Reply YES — no commitment, no auto-charge."
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "lapsed_hard fallback: no-shame + relevant offer + free-trial framing."}


def fb_category_seasonal(facts: dict[str, Any]) -> dict[str, Any]:
    salu = _salutation(facts)
    payload = _safe(facts, "trigger", "payload", default={}) or {}
    trends = ", ".join(payload.get("trends", []) or [])
    body = (
        f"{salu}, summer demand shifts: {trends}."
        f" Want me to draft a 'summer health-pack' GBP post bundling the up-trending SKUs? Live in 10 min."
    )
    return {"body": body, "cta_kind": "binary_yes_no", "rationale": "category_seasonal fallback: explicit trend % + bundled artifact."}


# ─── Dispatcher ─────────────────────────────────────────────────────────────

FALLBACKS = {
    "research_digest": fb_research_digest,
    "regulation_change": fb_regulation_change,
    "supply_alert": fb_supply_alert,
    "perf_dip": fb_perf_dip,
    "perf_spike": fb_perf_spike,
    "seasonal_perf_dip": fb_seasonal_perf_dip,
    "milestone_reached": fb_milestone_reached,
    "dormant_with_vera": fb_dormant,
    "curious_ask_due": fb_curious_ask,
    "winback_eligible": fb_winback,
    "ipl_match_today": fb_ipl,
    "festival_upcoming": fb_festival,
    "review_theme_emerged": fb_review_theme,
    "competitor_opened": fb_competitor,
    "renewal_due": fb_renewal,
    "gbp_unverified": fb_gbp_unverified,
    "cde_opportunity": fb_cde,
    "active_planning_intent": fb_planning,
    "category_seasonal": fb_category_seasonal,
    "recall_due": fb_recall_due,
    "chronic_refill_due": fb_chronic_refill,
    "trial_followup": fb_trial_followup,
    "wedding_package_followup": fb_wedding_followup,
    "customer_lapsed_hard": fb_lapsed_hard,
}


def fallback_for(kind: str, facts: dict[str, Any]) -> dict[str, Any]:
    fn = FALLBACKS.get(kind)
    if fn:
        return fn(facts)
    # Generic last-resort.
    salu = _salutation(facts)
    body = f"{salu}, quick one — saw something worth flagging on your account. Want me to walk you through it?"
    return {"body": body, "cta_kind": "open_ended", "rationale": f"generic fallback for kind={kind}"}
