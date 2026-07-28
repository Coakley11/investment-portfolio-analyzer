"""Investment education / coach instant reasoning engine (P2)."""

from __future__ import annotations

from typing import Any

from investment_ami_instant_solver import InvestmentSolverResult, _ctx_value

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.support.education_content import (
    format_advanced_coach_snapshot,
    format_beginner_coach_snapshot,
)


def _education_solve(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    _ = question  # reserved for future topic-specific education routing
    objective = str(_ctx_value(ctx, "objective", default="")).strip() or "your goal"
    if beginner:
        text = format_beginner_coach_snapshot(objective)
    else:
        text = format_advanced_coach_snapshot(objective)
    return InvestmentSolverResult(
        short_answer=text,
        math_idea="Educational portfolio construction framing.",
        problem_type="investment_coach",
        model_name="Investment coach",
        confidence_pct=74,
        computed={"ami_engine_id": "education"},
    )


class EducationEngine:
    engine_id = "education"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        return _education_solve(
            dict(request.context or {}),
            beginner=bool(request.beginner),
            question=str(request.question or ""),
        )


_DEFAULT_ENGINE = EducationEngine()


def get_education_engine() -> EducationEngine:
    return _DEFAULT_ENGINE
