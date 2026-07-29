"""Minimal OpenAI Chat Completions client (stdlib HTTP — no extra dependency)."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from investment_ami.integration.synthesis_config import openai_api_key

_OPENAI_SESSION_CACHE_ENV = "INVESTMENT_AMI_OPENAI_SESSION_CACHE"
_SESSION_CACHE_KEY = "_inv_ami_openai_completion_cache_v1"


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


def _openai_session_cache_enabled() -> bool:
    raw = str(os.environ.get(_OPENAI_SESSION_CACHE_ENV) or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _completion_cache_key(*, model: str, messages: list[dict[str, str]], temperature: float) -> str:
    blob = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _get_cached_completion(cache_key: str) -> ChatCompletionResult | None:
    try:
        import streamlit as st

        bucket = st.session_state.get(_SESSION_CACHE_KEY)
        if not isinstance(bucket, dict):
            return None
        raw = bucket.get(cache_key)
        if not isinstance(raw, dict):
            return None
        return ChatCompletionResult(
            content=str(raw.get("content") or ""),
            model=str(raw.get("model") or ""),
            prompt_tokens=_int_or_none(raw.get("prompt_tokens")),
            completion_tokens=_int_or_none(raw.get("completion_tokens")),
            total_tokens=_int_or_none(raw.get("total_tokens")),
            raw_response=dict(raw.get("raw_response") or {}),
        )
    except Exception:
        return None


def _store_cached_completion(cache_key: str, result: ChatCompletionResult) -> None:
    try:
        import streamlit as st

        bucket = st.session_state.get(_SESSION_CACHE_KEY)
        if not isinstance(bucket, dict):
            bucket = {}
        bucket[cache_key] = {
            "content": result.content,
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "raw_response": dict(result.raw_response or {}),
        }
        if len(bucket) > 12:
            for old_key in list(bucket.keys())[:-12]:
                bucket.pop(old_key, None)
        st.session_state[_SESSION_CACHE_KEY] = bucket
    except Exception:
        pass


def chat_completion_json(
    *,
    messages: list[dict[str, str]],
    model: str,
    timeout_sec: int = 90,
    temperature: float = 0.35,
    max_tokens: int | None = None,
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

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None and max_tokens > 0:
        body["max_tokens"] = int(max_tokens)
    if _openai_session_cache_enabled():
        cache_key = _completion_cache_key(model=model, messages=messages, temperature=temperature)
        cached = _get_cached_completion(cache_key)
        if cached is not None and cached.content:
            return cached

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
    result = ChatCompletionResult(
        content=content,
        model=str(raw.get("model") or model),
        prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
        completion_tokens=_int_or_none(usage.get("completion_tokens")),
        total_tokens=_int_or_none(usage.get("total_tokens")),
        raw_response=raw,
    )
    if _openai_session_cache_enabled():
        cache_key = _completion_cache_key(model=model, messages=messages, temperature=temperature)
        _store_cached_completion(cache_key, result)
    return result


def _int_or_none(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _mock_json_response(messages: list[dict[str, str]]) -> str:
    user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    q = user[:120].replace('"', "'")
    payload = {
        "investment_thesis": (
            "Mock thesis: a 55/45 VOO/BND barbell expresses belief in US large-cap earnings "
            "with bond ballast under stable rates and moderate inflation."
        ),
        "answer_markdown": (
            f"**Mock analytical synthesis** (INVESTMENT_AMI_SYNTHESIS_MOCK=1).\n\n"
            f"Question received: {q}…\n\n"
            "## Investment Thesis\n"
            "Mock CIO through-line linking VOO equity beta, BND rate sensitivity, and macro regime.\n\n"
            "## Executive Summary\n"
            "Mock IC memo — enable live model for full institutional synthesis.\n\n"
            "## Investment Committee View\n"
            "Committee would debate concentration vs simplicity trade-off.\n"
        ),
        "report_meta": {
            "portfolio_grade": "B",
            "overall_assessment": "Mock assessment for pipeline tests.",
        },
        "citations": [{"fact_id": "concentration.summary", "excerpt": "concentration summary from brief"}],
        "uncertainties": ["Mock mode — not a live model response."],
        "alternative_viewpoints": ["A more defensive posture would raise bonds at the cost of expected return."],
        "missing_information": ["Tax and liquidity needs not in brief (mock)."],
        "priority_recommendations": {
            "highest_priority": "Mock: review largest weight (test).",
            "greatest_impact": "Mock.",
            "least_effort": "Mock.",
            "implement_now": "Mock.",
            "monitor_only": "Mock.",
        },
        "self_critique": "Mock self-critique.",
    }
    return json.dumps(payload)
