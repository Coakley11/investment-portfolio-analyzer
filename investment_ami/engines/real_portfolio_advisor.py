"""Real Portfolio Advisor — deterministic instant engine."""

from __future__ import annotations

from investment_ami.decision_support.modules import MODULE_REAL_PORTFOLIO
from investment_ami.decision_support.real_portfolio_advisor import run_real_portfolio_advisor
from investment_ami.engines.base import InstantEngineRequest
from investment_ami_instant_solver import InvestmentSolverResult


class RealPortfolioAdvisorEngine:
    engine_id = MODULE_REAL_PORTFOLIO

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        _resp, payload = run_real_portfolio_advisor(
            dict(request.context or {}),
            question=str(request.question or ""),
        )
        return InvestmentSolverResult(
            short_answer=payload["short_answer"],
            math_idea=payload.get("math_idea", ""),
            problem_type=MODULE_REAL_PORTFOLIO,
            model_name="Real Portfolio Advisor",
            confidence_pct=payload.get("confidence_pct"),
            computed=payload.get("computed"),
            analyst_sections=payload.get("analyst_sections"),
        )


def get_real_portfolio_advisor_engine() -> RealPortfolioAdvisorEngine:
    return RealPortfolioAdvisorEngine()
