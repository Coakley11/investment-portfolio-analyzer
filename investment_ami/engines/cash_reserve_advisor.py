"""Cash Reserve Analysis — decision-support instant engine."""

from __future__ import annotations

from investment_ami.decision_support.modules import MODULE_CASH_RESERVE
from investment_ami.decision_support.pipeline import decision_support_to_solver_payload, run_decision_support_module
from investment_ami.engines.base import InstantEngineRequest
from investment_ami_instant_solver import InvestmentSolverResult


class CashReserveAdvisorEngine:
    engine_id = MODULE_CASH_RESERVE

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        response = run_decision_support_module(
            MODULE_CASH_RESERVE,
            dict(request.context or {}),
            question=str(request.question or ""),
        )
        payload = decision_support_to_solver_payload(response)
        return InvestmentSolverResult(
            short_answer=payload["short_answer"],
            math_idea=payload["math_idea"],
            problem_type=MODULE_CASH_RESERVE,
            model_name="Cash Reserve Analyst",
            confidence_pct=payload["confidence_pct"],
            computed=payload["computed"],
            analyst_sections=payload["analyst_sections"],
        )


def get_cash_reserve_advisor_engine() -> CashReserveAdvisorEngine:
    return CashReserveAdvisorEngine()
