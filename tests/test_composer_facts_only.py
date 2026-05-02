"""Composer test — facts-pack adherence + anti-fabrication on every kind.

We force the deterministic fallback path (LLM key empty) so this test runs
without network. The validator is the same one production uses.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from bot.composer import Composer, build_facts_pack, validate
from bot.llm import LLM


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fresh_composer():
    # Force LLM disabled so .compose() always uses the fallback.
    llm = LLM(api_key="")
    return Composer(llm)


# ─── Case 1: dentist research_digest (matches case-studies.md anchor) ───────

def test_case1_research_digest_for_drmeera(dataset):
    composer = _fresh_composer()
    cat = dataset["categories"]["dentists"]
    merchant = dataset["merchants"]["m_001_drmeera_dentist_delhi"]
    trigger = dataset["triggers"]["trg_001_research_digest_dentists"]

    out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=None,
                                send_as="vera"))
    body = out["body"]
    facts = build_facts_pack(category=cat, merchant=merchant, trigger=trigger, customer=None,
                             send_as="vera", conversation_state={"turn_number": 1, "prior_bodies_in_conv": []})
    ok, reasons = validate(body, out.get("cta_kind", "open_ended"), facts, [])
    assert ok, f"validator failed: {reasons}\nbody={body}"

    # Fact anchors required by Case Study 1
    assert "Meera" in body
    assert "JIDA" in body
    assert "high" in body.lower() and "risk" in body.lower()


def test_case5_ipl_pizza(dataset):
    composer = _fresh_composer()
    cat = dataset["categories"]["restaurants"]
    merchant = dataset["merchants"]["m_005_pizzajunction_restaurant_delhi"]
    trigger = dataset["triggers"]["trg_010_ipl_match_delhi"]

    out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=None, send_as="vera"))
    body = out["body"]
    facts = build_facts_pack(category=cat, merchant=merchant, trigger=trigger, customer=None,
                             send_as="vera", conversation_state={"turn_number": 1, "prior_bodies_in_conv": []})
    ok, reasons = validate(body, out.get("cta_kind", "binary_yes_no"), facts, [])
    assert ok, f"validator failed: {reasons}\nbody={body}"

    # Sat IPL → contrarian advice + leverage existing offer (BOGO)
    assert "Suresh" in body
    assert "DC vs MI" in body or "Arun Jaitley" in body
    assert "Buy 1 Pizza Get 1 Free" in body or "BOGO" in body.lower()


def test_case7_seasonal_dip_powerhouse(dataset):
    composer = _fresh_composer()
    cat = dataset["categories"]["gyms"]
    merchant = dataset["merchants"]["m_007_powerhouse_gym_bangalore"]
    trigger = dataset["triggers"]["trg_014_seasonal_acquisition_dip_powerhouse"]

    out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=None, send_as="vera"))
    body = out["body"]
    facts = build_facts_pack(category=cat, merchant=merchant, trigger=trigger, customer=None,
                             send_as="vera", conversation_state={"turn_number": 1, "prior_bodies_in_conv": []})
    ok, reasons = validate(body, out.get("cta_kind", "binary_yes_no"), facts, [])
    assert ok, f"validator failed: {reasons}\nbody={body}"

    assert "Karthik" in body
    assert "245" in body  # active member count
    assert "30%" in body or "-25" in body or "April-June" in body or "lull" in body.lower()


def test_case9_supply_alert_apollo(dataset):
    composer = _fresh_composer()
    cat = dataset["categories"]["pharmacies"]
    merchant = dataset["merchants"]["m_009_apollo_pharmacy_jaipur"]
    trigger = dataset["triggers"]["trg_018_supply_atorvastatin_recall"]

    out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=None, send_as="vera"))
    body = out["body"]
    facts = build_facts_pack(category=cat, merchant=merchant, trigger=trigger, customer=None,
                             send_as="vera", conversation_state={"turn_number": 1, "prior_bodies_in_conv": []})
    ok, reasons = validate(body, out.get("cta_kind", "binary_yes_no"), facts, [])
    assert ok, f"validator failed: {reasons}\nbody={body}"

    assert "Ramesh" in body
    assert "atorvastatin" in body.lower()
    assert "AT2024-1102" in body or "AT2024-1108" in body
    assert "240" in body  # chronic_rx_count


def test_case10_chronic_refill_grandfather(dataset):
    composer = _fresh_composer()
    cat = dataset["categories"]["pharmacies"]
    merchant = dataset["merchants"]["m_009_apollo_pharmacy_jaipur"]
    trigger = dataset["triggers"]["trg_019_chronic_refill_grandfather"]
    customer = dataset["customers"]["c_013_grandfather_for_m009"]

    out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=customer,
                                send_as="merchant_on_behalf"))
    body = out["body"]
    facts = build_facts_pack(category=cat, merchant=merchant, trigger=trigger, customer=customer,
                             send_as="merchant_on_behalf", conversation_state={"turn_number": 1, "prior_bodies_in_conv": []})
    ok, reasons = validate(body, out.get("cta_kind", "binary_confirm_cancel"), facts, [])
    assert ok, f"validator failed: {reasons}\nbody={body}"

    # Senior + Hindi + molecule names
    assert "Namaste" in body or "namaste" in body.lower()
    assert "metformin" in body.lower()
    assert "atorvastatin" in body.lower()
    assert "telmisartan" in body.lower()


def test_recall_due_priya(dataset):
    composer = _fresh_composer()
    cat = dataset["categories"]["dentists"]
    merchant = dataset["merchants"]["m_001_drmeera_dentist_delhi"]
    trigger = dataset["triggers"]["trg_003_recall_due_priya"]
    customer = dataset["customers"]["c_001_priya_for_m001"]

    out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=customer,
                                send_as="merchant_on_behalf"))
    body = out["body"]
    facts = build_facts_pack(category=cat, merchant=merchant, trigger=trigger, customer=customer,
                             send_as="merchant_on_behalf", conversation_state={"turn_number": 1, "prior_bodies_in_conv": []})
    ok, reasons = validate(body, out.get("cta_kind", "multi_choice_slot"), facts, [])
    assert ok, f"validator failed: {reasons}\nbody={body}"

    assert "Priya" in body
    assert "Wed 5 Nov" in body or "Thu 6 Nov" in body  # actual slot labels


def test_no_url_in_any_fallback(dataset):
    composer = _fresh_composer()
    url_re = re.compile(r"https?://|www\.|\.com\b|\.in\b", re.IGNORECASE)
    for tid, trigger in dataset["triggers"].items():
        merchant = dataset["merchants"].get(trigger.get("merchant_id"))
        if not merchant:
            continue
        cat = dataset["categories"].get(merchant.get("category_slug"))
        if not cat:
            continue
        cust = dataset["customers"].get(trigger.get("customer_id"))
        send_as = "merchant_on_behalf" if cust else "vera"
        out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=cust, send_as=send_as))
        body = out.get("body", "")
        assert not url_re.search(body), f"URL leaked in fallback for trigger {tid}: {body}"


def test_no_taboo_in_any_fallback(dataset):
    composer = _fresh_composer()
    for tid, trigger in dataset["triggers"].items():
        merchant = dataset["merchants"].get(trigger.get("merchant_id"))
        if not merchant:
            continue
        cat = dataset["categories"].get(merchant.get("category_slug"))
        if not cat:
            continue
        cust = dataset["customers"].get(trigger.get("customer_id"))
        send_as = "merchant_on_behalf" if cust else "vera"
        taboos = (cat.get("voice", {}).get("vocab_taboo") or []) + (cat.get("voice", {}).get("taboos") or [])
        out = _run(composer.compose(category=cat, merchant=merchant, trigger=trigger, customer=cust, send_as=send_as))
        body = (out.get("body") or "").lower()
        for t in taboos:
            t_strip = re.split(r"[(]", t, 1)[0].strip().lower()
            if t_strip:
                assert t_strip not in body, f"taboo '{t_strip}' leaked in fallback for trigger {tid}: {body}"
