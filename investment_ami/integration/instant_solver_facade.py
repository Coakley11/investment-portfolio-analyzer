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
    from investment_ami_instant_solver import _solve_instant_investment_insight_core

    pair = _solve_instant_investment_insight_core(question, context)
    if pair is None:
        return None
    route, result = pair
    attach_routing_metadata(result, routed)
    computed = dict(getattr(result, "computed", None) or {})
    engine_id = str(computed.get("ami_engine_id") or "").strip()
    if engine_id and routed:
        computed.setdefault("ami_pipeline_step", "instant_engine")
    try:
        result.computed = computed
    except AttributeError:
        pass
    return route, result
