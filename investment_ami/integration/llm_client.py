"""Minimal OpenAI Chat Completions client (stdlib HTTP — no extra dependency)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from investment_ami.integration.synthesis_config import openai_api_key


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    raw_response: dict[str, Any]


class LlmClientError(RuntimeError):
    pass


def chat_completion_json(
    *,
    messages: list[dict[str, str]],
    model: str,
    timeout_sec: int = 90,
    temperature: float = 0.35,
) -> ChatCompletionResult:
    mock = str(os.environ.get("INVESTMENT_AMI_SYNTHESIS_MOCK") or "").strip().lower() in ("1", "true", "yes")
    if mock:
        return ChatCompletionResult(
            content=_mock_json_response(messages),
            model=f"mock:{model}",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            raw_response={"mock": True},
        )

    api_key = openai_api_key()
    if not api_key:
        raise LlmClientError("OPENAI_API_KEY not configured (env or st.secrets openai.api_key).")

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LlmClientError(f"OpenAI HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise LlmClientError(f"OpenAI request failed: {exc}") from exc

    choices = raw.get("choices") or []
    if not choices:
        raise LlmClientError("OpenAI returned no choices")
    content = str((choices[0].get("message") or {}).get("content") or "")
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    return ChatCompletionResult(
        content=content,
        model=str(raw.get("model") or model),
        prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
        completion_tokens=_int_or_none(usage.get("completion_tokens")),
        total_tokens=_int_or_none(usage.get("total_tokens")),
        raw_response=raw,
    )


def _int_or_none(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _mock_json_response(messages: list[dict[str, str]]) -> str:
    user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    q = user[:120].replace('"', "'")
    payload = {
        "answer_markdown": (
            f"**Mock analytical synthesis** (INVESTMENT_AMI_SYNTHESIS_MOCK=1).\n\n"
            f"Question received: {q}…\n\n"
            "This portfolio shows measurable concentration in the largest weights; "
            "any change should weigh liquidity, tax, and macro assumptions noted in the brief limitations."
        ),
        "citations": [{"fact_id": "concentration.summary", "excerpt": "concentration summary from brief"}],
        "uncertainties": ["Mock mode — not a live model response."],
        "alternative_viewpoints": ["A more defensive posture would raise bonds at the cost of expected return."],
    }
    return json.dumps(payload)
