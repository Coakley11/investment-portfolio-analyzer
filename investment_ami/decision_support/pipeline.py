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
    from investment_ami.decision_support.presentation import finalize_decision_support_response

    return finalize_decision_support_response(module_id, snapshot, question, findings)


def decision_support_to_solver_payload(response: DecisionSupportResponse) -> dict[str, Any]:
    from investment_ami.decision_support.presentation import render_user_analyst_sections

    sections = render_user_analyst_sections(response)
    return {
        "short_answer": response.assessment,
        "math_idea": "",
        "confidence_pct": response.confidence_pct,
        "computed": {
            "ami_engine_id": response.module_id,
            "decision_support_version": DECISION_SUPPORT_VERSION,
            "insights_layout": "decision_support",
            "applied_rule_ids": list(response.applied_rule_ids),
            "insights_layout": "decision_support",
            "decision_support": {
                "facts": response.facts,
                "observations": response.observations,
                "suggested_actions": response.suggested_actions,
                "trade_offs": response.trade_offs,
                "confidence": response.confidence,
                "confidence_pct": response.confidence_pct,
            },
        },
        "analyst_sections": sections,
    }
