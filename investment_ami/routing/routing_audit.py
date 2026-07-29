"""Collect routing decisions for evidence-driven router improvement."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from investment_ami.routing.mode_router import ModeRoutingDecision, mode_routing_diagnostics_dict

ROUTING_AUDIT_SESSION_KEY = "_ami_routing_audit_log_v1"
ROUTING_AUDIT_MAX_ENTRIES = 50


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_routing_audit_entry(st: Any, entry: dict[str, Any]) -> None:
    """Ring buffer in session state (dev / reasoning laboratory)."""
    try:
        ss = st.session_state
    except Exception:
        return
    log = ss.get(ROUTING_AUDIT_SESSION_KEY)
    if not isinstance(log, list):
        log = []
    log.append(dict(entry))
    ss[ROUTING_AUDIT_SESSION_KEY] = log[-ROUTING_AUDIT_MAX_ENTRIES:]

    if str(os.environ.get("INVESTMENT_ROUTING_AUDIT_PERSIST") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        _append_jsonl(entry)


def _append_jsonl(entry: dict[str, Any]) -> None:
    try:
        root = Path(__file__).resolve().parents[2]
        path = root / "docs" / "eval" / "routing_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def build_routing_audit_entry(
    *,
    question: str,
    routing_decision: ModeRoutingDecision,
    selected_engine: str,
    synthesis_invoked: bool,
    solver_build_id: str = "",
    latency_ms: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    synthesis_enabled: bool | None = None,
    prompt_version: str = "",
) -> dict[str, Any]:
    routing = mode_routing_diagnostics_dict(routing_decision)
    intent = dict(routing_decision.intent_classification or {})
    return {
        "timestamp_utc": _utc_now(),
        "question": str(question or "").strip(),
        "intent_primary": intent.get("primary"),
        "intent_classification": intent,
        "routing": routing,
        "matched_routing_rules": list(routing_decision.matched_rules),
        "selected_engine": selected_engine,
        "response_mode": routing_decision.response_mode,
        "question_tag": routing_decision.question_tag,
        "synthesis_invoked": synthesis_invoked,
        "synthesis_enabled": synthesis_enabled,
        "synthesis_prompt_version": prompt_version,
        "solver_build_id": solver_build_id,
        "latency_ms": dict(latency_ms or {}),
        "token_usage": dict(token_usage or {}),
    }


def record_investment_routing_audit(
    st: Any,
    *,
    question: str,
    routing_decision: ModeRoutingDecision,
    computed: dict[str, Any] | None,
    synthesis_diagnostics: dict[str, Any] | None,
    solver_build_id: str = "",
) -> dict[str, Any]:
    computed = dict(computed or {})
    synth = dict(synthesis_diagnostics or {})
    response_mode = str(computed.get("ami_response_mode") or routing_decision.response_mode)
    synthesis_invoked = response_mode == "analytical_synthesis" and bool(
        synth.get("synthesis_enabled")
    ) and not str(synth.get("error") or "").startswith("Analytical synthesis disabled")

    engine = "analytical_synthesis"
    if response_mode == "deterministic":
        engine = str(computed.get("ami_engine_id") or routing_decision.deterministic_intent or "deterministic")
    elif computed.get("ami_pipeline_step") == "analytical_placeholder":
        engine = "analytical_placeholder"

    entry = build_routing_audit_entry(
        question=question,
        routing_decision=routing_decision,
        selected_engine=engine,
        synthesis_invoked=synthesis_invoked,
        solver_build_id=solver_build_id,
        latency_ms=synth.get("timing_ms") if isinstance(synth.get("timing_ms"), dict) else {},
        token_usage=synth.get("token_usage") if isinstance(synth.get("token_usage"), dict) else {},
        synthesis_enabled=synth.get("synthesis_enabled"),
        prompt_version=str(synth.get("prompt_version") or ""),
    )
    append_routing_audit_entry(st, entry)
    return entry
