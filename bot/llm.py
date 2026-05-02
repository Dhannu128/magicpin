"""LLM client — OpenAI-compatible (TokenRouter), async, deterministic."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger("vera.llm")


class LLM:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        primary_model: str | None = None,
        fast_model: str | None = None,
        timeout: float | None = None,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.tokenrouter.com/v1")
        self.primary = primary_model or os.getenv("LLM_MODEL_PRIMARY", "anthropic/claude-opus-4.7")
        self.fast = fast_model or os.getenv("LLM_MODEL_FAST", "anthropic/claude-haiku-4.5")
        self.timeout = float(timeout if timeout is not None else os.getenv("LLM_TIMEOUT_SECONDS", "20"))

        if not self.api_key:
            logger.warning("LLM_API_KEY is empty — LLM calls will fail; bot will fall back to templates.")

        self.client = AsyncOpenAI(
            api_key=self.api_key or "no-key",
            base_url=self.base_url,
            timeout=self.timeout,
        )

    async def chat_json(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 700,
        retries: int = 1,
    ) -> dict[str, Any] | None:
        """Call the chat-completion endpoint, expect strict JSON, return parsed dict or None.

        Determinism: temperature=0, top_p=1. seed is sent when the upstream supports it.
        """
        chosen_model = model or self.primary
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await self.client.chat.completions.create(
                    model=chosen_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0,
                    top_p=1,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content or ""
                parsed = _parse_json_loose(content)
                if parsed is not None:
                    return parsed
                logger.warning("LLM returned unparseable JSON (attempt %d): %s", attempt, content[:200])
                last_err = ValueError("unparseable_json")
            except (APITimeoutError, RateLimitError, APIError, asyncio.TimeoutError) as e:
                last_err = e
                logger.warning("LLM call failed (attempt %d, model=%s): %s", attempt, chosen_model, e)
                # On retry, fall back to the fast model — better than failing the whole tick.
                chosen_model = self.fast
            except Exception as e:
                last_err = e
                logger.exception("LLM unexpected error (attempt %d): %s", attempt, e)
        logger.error("LLM gave up after %d attempts: %s", retries + 1, last_err)
        return None

    async def chat_text(self, system: str, user: str, model: str | None = None, max_tokens: int = 400) -> str | None:
        try:
            resp = await self.client.chat.completions.create(
                model=model or self.fast,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                top_p=1,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("LLM text call failed: %s", e)
            return None


def _parse_json_loose(content: str) -> dict[str, Any] | None:
    """Try strict JSON first; if that fails, extract the largest brace-balanced JSON object."""
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        pass

    # Strip code fences.
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        try:
            return json.loads(stripped)
        except Exception:
            pass

    # Find the longest balanced {...} block.
    start = content.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(content)):
            ch = content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = content[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
        start = content.find("{", start + 1)
    return None
