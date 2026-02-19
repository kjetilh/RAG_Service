from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import json
import random
import time
import requests
from datetime import datetime
import os
import uuid

from app.settings import settings


@dataclass
class LLMMessage:
    role: str
    content: str


class LLMProvider:
    def chat(self, messages: List[LLMMessage]) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    """Minimal OpenAI-compatible /chat/completions client with robust 429 handling."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _post_with_retries(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        timeout_s: int = 60,
        max_attempts: int = 6,
        base_delay_s: float = 0.8,
        max_delay_s: float = 20.0,
    ) -> requests.Response:
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=timeout_s)

                # Success
                if r.status_code < 400:
                    return r

                # Retryable statuses (rate limits + transient upstream)
                if r.status_code in (408, 429, 500, 502, 503, 504):
                    # Try to extract error payload (helps debugging quota vs rate limits)
                    err_text = None
                    try:
                        err_text = r.text
                    except Exception:
                        err_text = None

                    retry_after = r.headers.get("Retry-After")
                    if retry_after:
                        try:
                            sleep_s = float(retry_after)
                        except Exception:
                            sleep_s = None
                    else:
                        sleep_s = None

                    if sleep_s is None:
                        # exponential backoff with jitter
                        expo = base_delay_s * (2 ** (attempt - 1))
                        jitter = random.uniform(0.0, 0.4)
                        sleep_s = min(max_delay_s, expo + jitter)

                    # Log once per attempt (lightweight; avoids dependency on logging config)
                    print(
                        f"[LLM] HTTP {r.status_code} on attempt {attempt}/{max_attempts}. "                        f"Sleeping {sleep_s:.2f}s. Response: {err_text[:400] if err_text else '<no body>'}"
                    )

                    time.sleep(sleep_s)
                    last_exc = requests.HTTPError(f"{r.status_code} {r.reason}", response=r)
                    continue

                # Non-retryable errors: raise immediately with detail
                r.raise_for_status()
                return r  # unreachable
            except requests.RequestException as e:
                # Network / DNS / timeout etc. Retry a few times.
                last_exc = e
                expo = base_delay_s * (2 ** (attempt - 1))
                jitter = random.uniform(0.0, 0.4)
                sleep_s = min(max_delay_s, expo + jitter)
                print(f"[LLM] RequestException on attempt {attempt}/{max_attempts}: {e}. Sleeping {sleep_s:.2f}s")
                time.sleep(sleep_s)

        # If we get here, retries are exhausted.
        raise last_exc if last_exc else RuntimeError("LLM request failed without exception")


    def chat(self, messages: List[LLMMessage]) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is empty. Set it in .env (LLM_API_KEY=...)")

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        _log_prompt(self.model, payload["messages"])
        r = self._post_with_retries(url, payload, headers, timeout_s=60)
        data = r.json()
        return data["choices"][0]["message"]["content"]


def default_provider() -> LLMProvider:
    if settings.llm_provider == "openai_compat":
        return OpenAICompatibleProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")

def _log_prompt(model: str, messages: list[dict]):
    log_dir = os.getenv("LLM_PROMPT_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    req_id = str(uuid.uuid4())
    ts = datetime.utcnow().isoformat()

    # Grovt token-estimat: 1 token ~ 4 chars (god nok for debugging)
    total_chars = sum(len(m.get("content", "")) for m in messages)
    est_tokens = total_chars // 4

    payload = {
        "request_id": req_id,
        "timestamp_utc": ts,
        "model": model,
        "estimated_tokens": est_tokens,
        "messages": messages,
    }

    path = os.path.join(log_dir, f"prompt_{req_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
