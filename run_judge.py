"""Run judge_simulator.py against our local bot, with the judge LLM routed
through TokenRouter (OpenAI-compatible).

Usage (PowerShell):
  $env:LLM_API_KEY = "<key>"
  python run_judge.py            # full default ("all" scenario)
  python run_judge.py phase2_short
  python run_judge.py auto_reply_hell
  python run_judge.py full_evaluation
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# --- Pre-empt judge_simulator.py CONFIG -------------------------------------
# We patch the constants by mutating the imported module BEFORE main() runs.

import importlib.util

spec = importlib.util.spec_from_file_location("judge_simulator", str(ROOT / "judge_simulator.py"))
js = importlib.util.module_from_spec(spec)


def _override_openai_provider_url():
    """Patch the OpenAIProvider class to hit TokenRouter instead of openai.com."""
    OriginalOpenAIProvider = js.OpenAIProvider

    class TokenRouterProvider(OriginalOpenAIProvider):
        def name(self):
            return f"TokenRouter-OpenAI-compat ({self.model})"

        def complete(self, prompt: str, system: str = None) -> str:
            import json
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            body = json.dumps({
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1500,
            }).encode("utf-8")

            url = os.environ.get("LLM_BASE_URL", "https://api.tokenrouter.com/v1").rstrip("/") + "/chat/completions"
            req = urlrequest.Request(
                url,
                data=body,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
            resp = urlrequest.urlopen(req, timeout=js.TIMEOUT_LLM)
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    js.OpenAIProvider = TokenRouterProvider


def main():
    spec.loader.exec_module(js)
    _override_openai_provider_url()

    # Inject our settings
    js.BOT_URL = os.environ.get("BOT_URL", "http://localhost:8080")
    js.LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # routed via TokenRouter
    js.LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    js.LLM_MODEL = os.environ.get("JUDGE_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    js.TEST_SCENARIO = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TEST_SCENARIO", "all")

    if not js.LLM_API_KEY:
        print("ERROR: LLM_API_KEY env var is required.")
        sys.exit(1)

    js.main()


if __name__ == "__main__":
    main()
