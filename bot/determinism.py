"""Determinism + canonicalization helpers.

Same input → same output. We hash the canonical facts pack to derive a stable
cache key per (merchant, trigger, version, conversation_state) tuple.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def canonical_json(obj: Any) -> str:
    """Stable JSON: sorted keys, no whitespace, ensure_ascii=False so ₹/Hindi survive."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(obj: Any, length: int = 12) -> str:
    """Hex hash of canonical JSON. Deterministic across runs and OSes."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:length]


_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]+")


def short_id(s: str, length: int = 10) -> str:
    """Short, URL-safe slug from arbitrary string."""
    return _NON_ALNUM.sub("_", s)[:length].strip("_") or "x"


def conversation_id_for(merchant_id: str, trigger_kind: str, suppression_key: str) -> str:
    """Decodable, resumable conversation_id."""
    sk = short_id(suppression_key, 24)
    return f"conv_{short_id(merchant_id, 32)}_{short_id(trigger_kind, 16)}_{sk}"


def render_template_params(body: str, slots: list[str] | None = None) -> list[str]:
    """Return ordered template_params used to render body. We use the body itself
    as the single param when no explicit slots are provided. Keeps things simple
    while staying schema-compliant."""
    return slots if slots else [body]
