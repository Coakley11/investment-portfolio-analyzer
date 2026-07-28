"""Behavioral finance / risk-reduction instant reasoning engine (P2)."""

from __future__ import annotations

from typing import Any

from investment_ami_instant_solver import InvestmentSolverResult, _ctx_value, _weight_rows

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.behavioral_finance_content import (
    build_advanced_risk_reduction_lines,
    build_beginner_risk_reduction_lines,
)


def _behavioral_finance_solve(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    _ = question
    rows = _weight_rows(ctx)
    if beginner:
        top_ticker: str | None = None
        top_pct: float | None = None
        if rows:
            top_ticker, top_pct = rows[0]
        lines = build_beginner_risk_reduction_lines(top_ticker=top_ticker, top_pct=top_pct)
    else:
        vol = str(_ctx_value(ctx, "volatility", default="")).strip()
        lines = build_advanced_risk_reduction_lines(volatility=vol)

    computed: dict[str, Any] = {"ami_engine_id": "behavioral_finance"}

    return InvestmentSolverResult(
        short_answer="\n".join(lines),
        math_idea="Defensive allocation + de-concentration reduce portfolio variance.",
        problem_type="risk_reduction",
        model_name="Investment risk coach",
        confidence_pct=79,
        computed=computed,
    )


class BehavioralFinanceEngine:
    engine_id = "behavioral_finance"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        return _behavioral_finance_solve(
            dict(request.context or {}),
            beginner=bool(request.beginner),
            question=str(request.question or ""),
        )


_DEFAULT_ENGINE = BehavioralFinanceEngine()


def get_behavioral_finance_engine() -> BehavioralFinanceEngine:
    return _DEFAULT_ENGINE
