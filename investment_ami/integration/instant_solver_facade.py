"""P1 instant solve entry — route via catalog, execute legacy solvers unchanged."""

from __future__ import annotations

from typing import Any

from investment_ami.assembly.legacy_adapter import attach_routing_metadata
from investment_ami.routing.router import route_instant_question


def solve_instant_insight(
    question: str,
    context: dict[str, Any] | None,
) -> tuple[Any, Any] | None:
    """
    Route through the P1 architecture, then delegate to legacy solver core.

    Returns the same ``(InvestmentSolverRoute, InvestmentSolverResult)`` tuple as before P1.
    """
    routed = route_instant_question(question, context)
    if routed is None:
        return None

    if routed.response_mode == "analytical_synthesis":
        from investment_ami.pipeline.analytical_synthesis import solve_analytical_synthesis_with_diagnostics
        from investment_ami.routing.mode_router import route_investment_response_mode

        mode = route_investment_response_mode(question, context)
        route, result, _synth_diag = solve_analytical_synthesis_with_diagnostics(question, context, mode)
    else:
        from investment_ami_instant_solver import _solve_instant_investment_insight_core

        pair = _solve_instant_investment_insight_core(question, context)
        if pair is None:
            return None
        route, result = pair
        try:
            from investment_ami.pipeline.portfolio_brief import attach_portfolio_analysis_brief

            attach_portfolio_analysis_brief(result, context, question=question)
        except Exception:
            pass

    attach_routing_metadata(result, routed)
    computed = dict(getattr(result, "computed", None) or {})
    computed.setdefault("ami_response_mode", routed.response_mode)
    if routed.question_tag:
        computed.setdefault("ami_question_tag", routed.question_tag)
    computed.setdefault("ami_mode_routing", dict(routed.mode_routing or {}))
    engine_id = str(computed.get("ami_engine_id") or "").strip()
    if engine_id:
        computed.setdefault("ami_pipeline_step", "instant_engine")
    elif routed.response_mode == "analytical_synthesis":
        step = str(computed.get("ami_pipeline_step") or "analytical_synthesis")
        computed["ami_pipeline_step"] = step
    try:
        result.computed = computed
    except AttributeError:
        pass
    return route, result
