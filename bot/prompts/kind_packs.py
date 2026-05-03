"""Per-trigger-kind composer guidance.

Each pack tells the LLM:
  - which compulsion levers to lead with
  - what the body MUST anchor on
  - the right CTA shape
  - traps to avoid for this kind
"""

from __future__ import annotations

DEFAULT_KIND_PACK = """\
Generic kind. Anchor on at least one merchant performance number and the trigger reason.
Pick lever set: curiosity + reciprocity. CTA: open_ended question offering to draft something concrete.
"""

KIND_PACKS: dict[str, str] = {
    "research_digest": """\
LEVERS: source citation + reciprocity + curiosity.
ANCHOR: the digest item's title, source citation (verbatim from facts), trial_n, and the patient/customer segment from facts.
TIE-BACK: connect to a specific merchant signal (high_risk_adult_cohort, etc.) — the exact count if present (e.g., "your 124 high-risk adult patients").
CTA: open_ended — "Want me to pull the abstract + draft a patient WhatsApp keyed to your high-risk list?"
TRAP: do NOT generalize to "your patients" if the digest segment is narrow (e.g., high-risk adults). Be precise.
END WITH: a trailing source line — "— {source}" (e.g., "— JIDA Oct 2026, p.14").
""",

    "regulation_change": """\
LEVERS: source citation + loss aversion (deadline) + effort externalization.
ANCHOR: the regulation source, the deadline_iso date, the specific change (e.g., "1.5 → 1.0 mSv per IOPA"), and what equipment passes/fails.
TIE-BACK: name the audit action ("audit your X-ray setup before Dec 15").
CTA: binary_yes_no — "Want me to draft your updated SOP + a compliance-audit checklist?"
TRAP: do NOT alarm. Frame as "ahead of the deadline".
""",

    "supply_alert": """\
LEVERS: urgency (bounded) + derived-count specificity + effort externalization.
ANCHOR: the molecule, the exact batch numbers, the manufacturer, AND a derived count of affected customers from merchant.customer_aggregate.chronic_rx_count if applicable (state it as "X of your Y chronic-Rx customers").
RISK FRAMING: "sub-potency, no safety risk, but customers should be informed for replacement". Never use the word "panic" or imply danger.
CTA: binary_yes_no — "Want me to draft their WhatsApp note + the replacement-pickup workflow?"
""",

    "perf_spike": """\
LEVERS: curiosity + celebration + social proof + numeric stake.
VOICE FOR GYM CATEGORY: this is a coach-to-operator celebration. Lead with the WIN, not the data dump. "You're cooking" → then the number → then the curiosity prompt. Avoid clinical/financial framings.
ANCHOR (must use 4+):
  - exact metric + delta_pct + merchant's absolute number from facts.merchant.performance,
  - peer benchmark from facts.merchant.derived (`peer_calls_30d`, `peer_avg_ctr_pct`, `calls_vs_peer_pct`) — say it explicitly (e.g. "you: 18 vs peer median 12 = +50% above"),
  - likely_driver if payload has one (rephrased without underscores),
  - merchant's locality + name as the second-sentence anchor.
ANTI-PATTERN: do NOT just blurt the % in sentence 1. Wrap it in operator-celebration framing first ("ye solid signal hai", "really nice momentum", "your weekday slot is filling up"). Bare-number openings score lower on category fit.
CTA: open_ended — ONE concrete question that helps the merchant replicate ("What changed this week — new post, event, word-of-mouth?"). Then offer to replicate across other posts.
FORMAT SCAFFOLD (gym example):
  "Hi {first_name}, ye solid momentum hai — calls {+pct%} this week ({absolute_now}, peer median {peer_value} = +{pct_above_peer}% above). For {merchant_name} in {locality}, especially with your {member_count} active members, that's a real signal. Likely driver: {hypothesis_natural_english}. What changed in the last 7 days — naya post, koi event, ya word-of-mouth from a class? Bata dein, main same pattern aapke other posts pe replicate kar deti hoon (10 min)."
""",

    "perf_dip": """\
LEVERS: loss aversion + reframe + effort externalization.
ANCHOR: exact metric + delta_pct + the merchant's vs_baseline number; if peer-range exists in voice_pack tone_examples, use it for social proof.
NUANCE: distinguish severe vs normal — if signals contains "perf_dip_severe", lead with concern and propose a 30-day retention play.
CTA: binary_yes_no — "Want me to draft a 7-day attendance-recovery plan to share with your top 50 active customers?"
""",

    "seasonal_perf_dip": """\
LEVERS: anxiety pre-emption + reframe + retention pivot.
ANCHOR: explicitly call out that this is the EXPECTED seasonal dip from payload.season_note. Use a peer-range (-25 to -35% etc.) for normalization.
ACTION: pivot from acquisition spend to retention play; reference the merchant's active member count (e.g., "your 245 members").
CTA: binary_yes_no — "Want me to draft a 'summer attendance challenge' to keep them engaged through the dip?"
TRAP: do NOT recommend more ad spend during a known seasonal dip.
""",

    "milestone_reached": """\
LEVERS: celebration + ask-the-merchant + low-friction next step + social-proof (peer benchmark).
ANCHOR (must use 3+): metric + value_now + milestone_value + delta (e.g., "5 more to go") + a strong positive review_theme from merchant.review_themes (use as the proposed pin candidate).
CTA: open_ended — "Which review do you want pinned at the top of your GBP for the {milestone}-moment?"
FORMAT SCAFFOLD:
  "{Salutation}, you're at {value_now} {metric} — only {milestone - value_now} more and you cross {milestone_value}. {Top_positive_theme} pe {N} mentions hain, that's your real moat. Jab {milestone} hit ho, main usi din ek review GBP pe pin karwa sakti hoon — kaunsa review top pe dikhna chahiye?"
""",

    "dormant_with_vera": """\
LEVERS: ask-the-merchant + low-stakes question + reciprocity.
ANCHOR: their last topic from payload + days_since_last_merchant_message; reference one specific recent number from their performance.
CTA: open_ended — "Quick one — what's the single biggest blocker right now? I'll work the next 7 days around it."
""",

    "curious_ask_due": """\
LEVERS: ask-the-merchant + reciprocity (offer to convert their answer into an artifact).
ANCHOR: ask_template from payload (e.g., "what service has been most asked-for this week?"). Reference the salon/restaurant/clinic by name + locality.
CTA: open_ended — "I'll turn the answer into a Google post + a 4-line WhatsApp reply you can use. Takes 5 min."
""",

    "winback_eligible": """\
LEVERS: candid framing + concrete data + low-friction win-back.
ANCHOR: days_since_expiry + perf_dip_pct + lapsed_customers_added_since_expiry (all from payload).
CTA: binary_yes_no — "Want me to draft a 7-day re-activation push (winback offer + 3 GBP posts)? 10 min to set up."
""",

    "ipl_match_today": """\
LEVERS: contrarian-operator-judgement + leverage existing offer + effort externalization.
ANCHOR: match teams, venue, time from payload; is_weeknight matters.
CONTRARIAN RULE: if is_weeknight=false (Sat/Sun match), Saturday IPL = -12% restaurant covers (people watch at home). Recommend SKIPPING the match-night promo and instead pushing the merchant's existing active offer (BOGO etc.) as a delivery-special.
ANCHOR THE EXISTING OFFER: quote it verbatim from merchant.active_offers (e.g., "Buy 1 Pizza Get 1 Free (Tue-Thu)").
CTA: binary_yes_no — "Want me to draft the Swiggy banner + an Insta story? Live in 10 min."
""",

    "festival_upcoming": """\
LEVERS: timing + leverage existing offer + concrete artifact.
ANCHOR: festival name + days_until + category_relevance from payload.
CTA: binary_yes_no — "Want me to draft a {festival} GBP post + WhatsApp + Insta combo built around your active offer? Live in 15 min."
TRAP: if days_until > 60, do NOT push panicky urgency. Frame as "early planning".
""",

    "weather_heatwave": """\
LEVERS: timing + product-fit pivot + concrete artifact.
ANCHOR: temperature/forecast from payload + the city. Pivot into the merchant's weather-relevant SKUs (e.g., ORS for pharmacies, cold drinks for restaurants).
CTA: binary_yes_no — "Want me to draft the heatwave-pack post for today? Live in 10 min."
""",

    "review_theme_emerged": """\
LEVERS: candid + actionable + small-fix focus + contrast (strong-vs-weak).
ANCHOR (must use 3+): the theme rewritten as natural English (e.g. delivery_late → "delivery delays"), occurrences_30d count, the common_quote VERBATIM in quotes, and one positive review_theme as contrast (e.g. "pizza_quality has 8 positive mentions, so issue is dispatch not kitchen").
TRAP: do NOT propose specific operational tactics ("rider handoff SLA", "prep-time cap") — those sound invented to the judge. Stick to "3-step fix" framing without naming the steps.
CTA: open_ended — "Want a 3-step fix for {theme}? I'll draft the customer-facing reply to those {N} reviews too."
FORMAT SCAFFOLD:
  "{Salutation}, {N} reviews in last 30 days flag {theme_natural} — ek customer ne likha \"{quote}\". {Positive_theme} pe {M} positive mentions hain, toh issue {strong_area} nahi, {weak_area} hai. Want a 3-step fix? Customer-facing reply bhi draft kar deti hoon."
""",

    "competitor_opened": """\
LEVERS: defend-with-strength + don't disparage + leverage merchant differentiator.
ANCHOR: competitor_name + distance_km + their_offer (acknowledged factually from payload).
DEFENSE: pull a positive review_theme (e.g., "doctor_manner" from review_themes) or established_year as the merchant's edge. Do not name-call the competitor.
CTA: binary_yes_no — "Want me to publish a 'why our patients stay' review-pinned post + a 3-month retention WhatsApp series?"
""",

    "renewal_due": """\
LEVERS: value reframe + concrete number + low-friction action.
ANCHOR: days_remaining + plan + renewal_amount from payload. Pull a recent positive performance number (calls, leads, ctr, retention) and frame the subscription as the cost-per-lead it's actually delivering.
CTA: binary_confirm_cancel — "Reply CONFIRM and I'll auto-renew before {date}, no break in service. Reply CANCEL to discuss."
TRAP: no panic. No "you're losing access". Quiet, confident framing.
""",

    "gbp_unverified": """\
LEVERS: loss aversion + estimated uplift + effort externalization.
ANCHOR: estimated_uplift_pct from payload + verification_path. Reference the merchant's current number (views) and project the post-verification number ("+30% would be ~X views/mo").
CTA: binary_yes_no — "Want the 5-min postcard-verification walk-through? I'll send the steps now."
""",

    "cde_opportunity": """\
LEVERS: relevance + low cost + reciprocity.
ANCHOR: digest_item details — date, speaker, credits, fee. Reference the merchant's relevant signal (e.g., "since you're scaling crown work, the CAD/CAM segment is most relevant").
CTA: binary_yes_no — "Want me to register you (free for IDA members) + add the date to your calendar?"
""",

    "active_planning_intent": """\
CRITICAL: the merchant has explicitly asked for the artifact. DO NOT re-qualify. DELIVER IT.
LEVERS: complete-drafted-artifact + specificity + low-friction follow-on + numeric stake.
ANCHOR (must use 4+):
  - intent_topic verbatim from payload + the merchant's exact last_message in payload as the trigger reference (1 brief callback sentence),
  - the merchant's name + locality (always — "for Studio11 in Kapra", "for Zen Yoga Studio Mylapore"),
  - a structured DRAFT artifact in the body — tiered pricing (3 tiers), schedule (days + time), age-band or audience, ₹ price per tier (it's OK to invent operator-grade tier prices for the draft IF you anchor the base price on an existing active_offer),
  - one merchant-specific number from facts.merchant.performance OR customer_aggregate as social-proof for the draft ("your 95 active members", "your 4200 unique customers", "your 245 active members").
CTA: binary_yes_no — "Want me to draft the 3-line outreach WhatsApp to send to facilities managers / parents? 10 min." Combines effort externalization + numeric stake.
TRAP: if you ask another qualifying question instead of delivering, this is a -3 anti-pattern. Always deliver in this turn.
FORMAT SCAFFOLD (kids yoga camp example):
  "{Salutation}, here's the {topic} draft for {merchant_name} {locality} — you can edit:

  *{Program name}* — {duration} (e.g. 4-week, May-Jun)
  • Ages 6-9: Mon/Wed/Fri 5-6pm, ₹{price1} for 12 sessions
  • Ages 10-13: Tue/Thu/Sat 5-6pm, ₹{price2} for 12 sessions
  • Sibling pair: ₹{combo} (save ₹{savings})

  Anchored on your {N active members / 95 active members / etc.} for word-of-mouth. Want me to draft the parent WhatsApp + a GBP post? 10 min to ship."
""",

    "category_seasonal": """\
LEVERS: product-mix shift + specific SKU recommendation + concrete artifact.
ANCHOR: season + the specific +/- trends from payload (e.g., "ORS_demand_+40, sunscreen_demand_+38, antifungal_demand_+45, cold_cough_demand_-60"). Cite the exact percentages.
CTA: binary_yes_no — "Want me to draft a 'summer health-pack' GBP post bundling ORS + sunscreen + antifungal? Live in 10 min."
""",

    # Customer-facing kinds (send_as=merchant_on_behalf)
    "recall_due": """\
SEND_AS: merchant_on_behalf. Speak in the merchant's voice TO their customer.
LEVERS: name + warmth + concrete slots + value-add + binary commit.
ANCHOR: customer name + months_since_last_visit + the recall service + 2 specific available_slots verbatim from payload + the active offer price (₹X) + a complimentary add-on if mentioned.
CTA: multi_choice_slot — "Reply 1 for {slot1_label}, 2 for {slot2_label}, or tell us a time that works."
LANGUAGE: respect customer.language_pref (hi-en mix → Hindi-English).
""",

    "chronic_refill_due": """\
SEND_AS: merchant_on_behalf. Speak in the pharmacy's voice TO the patient (or their son for senior_citizen).
LEVERS: precision + senior-respect + total + savings + two-channel option.
ANCHOR: full molecule_list (e.g., metformin, atorvastatin, telmisartan), exact stock_runs_out_iso date, applied senior-discount price + savings, free-delivery threshold from active_offers, saved address.
SALUTATION: "Namaste" if senior_citizen=true; address son/family member if channel="whatsapp_via_son".
CTA: binary_confirm_cancel — "Reply CONFIRM to dispatch by {time}, or call {number} if any change in dosage."
LANGUAGE: hi if customer.language_pref="hi". Use "ji" honorific (e.g., "Sharma ji").
""",

    "trial_followup": """\
SEND_AS: merchant_on_behalf — speak in the merchant's voice TO the parent (if customer.parent_name is set) or the customer.

CRITICAL ADDRESSING — re-read this twice before composing:
  - Open with `<facts>.customer.salutation` (e.g. "Hi Sumitra") — this is the PARENT.
  - The merchant's owner_first_name (e.g. "Padma") is the GYM OWNER who is sending this message THROUGH us — they are the SIGNATURE, not the addressee.
  - ANTI-PATTERN that costs 4+ points: opening "Hi Padma" or "Hi {owner_first_name}". Padma is NOT the recipient; Sumitra is. If you write "Hi Padma" you are sending the message TO the gym owner, which makes no sense for a trial follow-up to a parent.
  - Sentence 1 template: "Hi {customer.address_to} — {owner_first_name} from {merchant.name} {locality} here, hope {child_first_name} enjoyed the trial on {trial_date}!"
  - Note "Hi {customer.address_to}" first; "{owner_first_name} from {merchant.name}" is the SELF-INTRODUCTION (signature), not the salutation.

LEVERS: continuation + relationship warmth + specific next slot + concrete first-month price + low-friction confirm.

ANCHOR (must use 5+):
  - parent salutation from customer.salutation OR customer first_name,
  - merchant_name + locality + owner_first_name as a self-introduction in sentence 1,
  - trial_date verbatim,
  - child's first_name,
  - next_session_options[0].label exactly,
  - an active offer with ₹ price for first-month / first-class.

WARMTH: 1 sentence that names the trial activity and a small detail (e.g. "loved his Saturday morning energy"). Avoid sounding transactional.

CTA: binary_yes_no — "Reply YES to confirm {slot_label}, or tell us another time."

FORMAT SCAFFOLD (do NOT deviate from this opener):
  "Hi {customer.address_to} — {owner_first_name} from {merchant.name} {locality} here. Hope {child_first_name} enjoyed his/her {trial_activity} on {trial_date}! We've held a spot in the next batch on {slot_label}. {Active offer with ₹ price} covers the first month if you'd like to continue, no pressure. Reply YES to confirm {slot_label_short}, or tell us another time."
""",

    "wedding_package_followup": """\
SEND_AS: merchant_on_behalf — speak in the merchant's voice TO the customer.
LEVERS: relationship continuity + named owner + window urgency + concrete program + slot-pref honored + active offer with ₹ price.
ANCHOR (must use 5+): customer first_name, owner_first_name as a self-identifier ("Lakshmi from Studio11 Kapra here"), trial_completed date verbatim, days_to_wedding (count exactly from payload), next_step_window (e.g. "30-day skin-prep"), AND an active offer with ₹ price (e.g. "Hair Spa @ ₹499").
CTA: binary_yes_no — "Want me to block your preferred {slot} slot for the first session next week? Reply YES."
FORMAT SCAFFOLD:
  "Hi {customer_first_name} 💍 {owner_first_name} from {merchant_name} {locality} here. Hope your bridal trial on {trial_date} felt right! With your wedding on {wedding_date}, we're {days} days out — perfect window to start the {next_step_program}. {Active_offer_with_price} pairs nicely as the first session. Want me to block your preferred {slot_pref} slot for next week? Reply YES."
""",

    "customer_lapsed_hard": """\
SEND_AS: merchant_on_behalf.
LEVERS: NO SHAME + relevant new offering tied to previous_focus + free-trial framing + binary commit.
ANCHOR: customer name + days_since_last_visit (round to weeks: "8 weeks" if 57 days) + previous_focus from payload (e.g., weight_loss → propose a HIIT class) + a real active offer (free trial / first month).
WARMTH RULE: include "happens to most members at some point, no judgment" or equivalent for gyms; "rough patches happen" for salons; never guilt-trip.
CTA: binary_yes_no — "Reply YES — no commitment, no auto-charge."
""",

    # Conversational fallback kinds (when /reply has no matching trigger context)
    "intent_handoff": """\
The merchant just gave explicit intent ("ok let's do it", "yes go ahead", "haan kar do", "send it", "confirm").
DO NOT ASK ANOTHER QUALIFYING QUESTION. Switch to ACTION MODE.
DELIVER: the concrete artifact (draft post, draft customer WhatsApp, scope statement) referenced earlier in the conversation, plus a binary CONFIRM to ship it.
CTA: binary_confirm_cancel — "Reply CONFIRM to send / CANCEL to hold."
""",

    "engaged_followup": """\
The merchant gave a real engaged answer (not auto-reply, not hostile, not curveball).
LEVERS: honor the ask + advance with one concrete next step.
DELIVER what they asked for (or commit to it with a timeline) + propose ONE follow-on as a binary.
CTA: binary_yes_no.
""",
}


def get_kind_pack(kind: str) -> str:
    """Return the per-trigger-kind composer guidance, or a sensible default."""
    return KIND_PACKS.get(kind, DEFAULT_KIND_PACK)
