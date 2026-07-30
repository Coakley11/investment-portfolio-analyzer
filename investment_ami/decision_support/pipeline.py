"""Orchestrate decision-support modules."""

from __future__ import annotations

from typing import Any

from investment_ami.decision_support.analysis import build_decision_support_response, run_financial_analysis
from investment_ami.decision_support.explanation import DECISION_SUPPORT_VERSION, format_decision_support_markdown
from investment_ami.decision_support.models import DecisionSupportResponse
from investment_ami.decision_support.snapshot import build_financial_snapshot

# Ensure built-in rules are registered
from investment_ami.decision_support.rules import builtin as _builtin  # noqa: F401


def run_decision_support_module(
    module_id: str,
    context: dict[str, Any] | None,
    *,
    question: str,
) -> DecisionSupportResponse:
    snapshot = build_financial_snapshot(context, question=question)
    findings = run_financial_analysis(module_id, snapshot, question)
    return build_decision_support_response(module_id, snapshot, question, findings)


def decision_support_to_solver_payload(response: DecisionSupportResponse) -> dict[str, Any]:
    md = format_decision_support_markdown(response)
    return {
        "short_answer": md,
        "math_idea": "Rule-based decision support from financial snapshot + extensible reasoning rules.",
        "confidence_pct": 72 if response.confidence != "placeholder" else 65,
        "computed": {
            "ami_engine_id": response.module_id,
            "decision_support_version": DECISION_SUPPORT_VERSION,
            "applied_rule_ids": list(response.applied_rule_ids),
            "decision_support": {
                "facts": response.facts,
                "observations": response.observations,
                "concerns": response.concerns,
                "suggested_actions": response.suggested_actions,
                "trade_offs": response.trade_offs,
                "confidence": response.confidence,
            },
        },
        "analyst_sections": {
            "facts": "\n".join(f"- {x}" for x in response.facts),
            "observations": "\n".join(f"- {x}" for x in response.observations),
            "concerns": "\n".join(f"- {x}" for x in response.concerns),
            "suggested_actions": "\n".join(f"- {x}" for x in response.suggested_actions),
            "trade_offs": "\n".join(f"- {x}" for x in response.trade_offs),
        },
    }
