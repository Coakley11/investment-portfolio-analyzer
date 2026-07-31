"""Orchestrate ledger-backed real portfolio analysis for AMI (Phase D)."""

from __future__ import annotations

from typing import Any

from investment_ami.decision_support.models import DecisionSupportResponse
from investment_ami.decision_support.modules import MODULE_REAL_PORTFOLIO
from investment_ami.decision_support.real_portfolio_concentration import analyze_real_portfolio_concentration
from investment_ami.decision_support.real_portfolio_drift import analyze_real_portfolio_drift
from investment_ami.decision_support.real_portfolio_performance import analyze_real_portfolio_performance
from investment_ami.decision_support.real_portfolio_presentation import (
    build_no_ledger_presentation,
    build_real_portfolio_presentation,
    presentation_to_decision_support_response,
    real_portfolio_to_solver_payload,
    render_real_portfolio_analyst_sections,
)
from investment_ami.decision_support.real_portfolio_recommendation_rules import build_real_portfolio_recommendations
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot
from investment_ami.decision_support.question_topics import is_real_portfolio_question


def _session_from_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    ss = dict(context)
    if "portfolio_transactions" not in ss and context.get("session_state"):
        try:
            raw = context["session_state"]
            if isinstance(raw, dict):
                ss = {**raw, **ss}
        except Exception:
            pass
    return ss


def _security_metadata_from_context(context: dict[str, Any] | None) -> dict[str, dict[str, str]] | None:
    if not context:
        return None
    meta = context.get("security_metadata") or context.get("real_portfolio_security_metadata")
    if isinstance(meta, dict):
        return {str(k).upper(): dict(v) if isinstance(v, dict) else {} for k, v in meta.items()}
    return None


def run_real_portfolio_advisor(
    context: dict[str, Any] | None,
    *,
    question: str,
) -> tuple[DecisionSupportResponse, dict[str, Any]]:
    """
    Build snapshot → analyses → recommendations → presentation.

    Does not mutate context or session state.
    """
    q = str(question or "").strip()
    ss = _session_from_context(context)
    prices = None
    if context:
        raw_prices = context.get("_real_portfolio_prices") or context.get("real_portfolio_prices")
        if isinstance(raw_prices, dict):
            prices = {str(k).upper(): float(v) for k, v in raw_prices.items()}
    build = build_real_portfolio_snapshot(ss, context=context, prices=prices)

    ask_placement = is_real_portfolio_question(q) and any(
        p in q.lower() for p in ("contribution", "next contribution", "where should")
    )

    if not build.ok or build.snapshot is None:
        pres = build_no_ledger_presentation(question=q)
        resp = presentation_to_decision_support_response(pres, question=q)
        sections = render_real_portfolio_analyst_sections(pres, question=q)
        payload = {
            "short_answer": resp.assessment,
            "math_idea": "",
            "confidence_pct": resp.confidence_pct,
            "computed": {
                "ami_engine_id": MODULE_REAL_PORTFOLIO,
                "insights_layout": "real_portfolio_advisor",
                "real_portfolio": {"no_ledger": True},
            },
            "analyst_sections": sections,
        }
        return resp, payload

    snap = build.snapshot
    perf = analyze_real_portfolio_performance(snap)
    meta = _security_metadata_from_context(context)
    conc = analyze_real_portfolio_concentration(snap, security_metadata=meta)
    drift = analyze_real_portfolio_drift(
        snap,
        health_objective=snap.health_objective or None,
    )
    recs = build_real_portfolio_recommendations(
        snap,
        perf,
        conc,
        drift,
        ask_contribution_placement=ask_placement,
    )
    pres = build_real_portfolio_presentation(
        question=q,
        snapshot=snap,
        performance=perf,
        concentration=conc,
        drift=drift,
        recommendations=recs,
    )
    resp = presentation_to_decision_support_response(pres, question=q, recommendations=recs)
    payload = real_portfolio_to_solver_payload(pres, resp, recommendations=recs)
    return resp, payload
