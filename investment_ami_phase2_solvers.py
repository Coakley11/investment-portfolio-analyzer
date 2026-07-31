"""Phase 2 Investment AMI solvers — thin wrappers and phase-2 orchestration."""

from __future__ import annotations

from typing import Any

from investment_ami_instant_solver import InvestmentSolverResult, InvestmentSolverRoute, _route_for_intent


def structured_concentration_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    """Thin wrapper — concentration logic lives in ``investment_ami.engines.portfolio_concentration``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("portfolio_concentration", ctx, beginner=beginner)


def structured_portfolio_risk_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    """Thin wrapper — portfolio risk logic lives in ``investment_ami.engines.portfolio_risk``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("portfolio_risk", ctx, beginner=beginner)


def etf_overlap_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Thin wrapper — ETF overlap logic lives in ``investment_ami.engines.etf_overlap``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("etf_overlap", ctx, beginner=beginner, question=question)


def diversification_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    """Thin wrapper — diversification logic lives in ``investment_ami.engines.diversification``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("diversification", ctx, beginner=beginner)


def valuation_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Thin wrapper — valuation logic lives in ``investment_ami.engines.valuation``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("valuation", ctx, beginner=beginner, question=question)


def scenario_stress_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Thin wrapper — scenario stress logic lives in ``investment_ami.engines.scenario_stress``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("scenario_stress", ctx, beginner=beginner, question=question)


def education_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Thin wrapper — investment education logic lives in ``investment_ami.engines.education``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("education", ctx, beginner=beginner, question=question)


def coach_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Backward-compatible alias for ``education_answer``."""
    return education_answer(ctx, beginner=beginner, question=question)


def behavioral_finance_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Thin wrapper — behavioral finance logic lives in ``investment_ami.engines.behavioral_finance``."""
    from investment_ami.pipeline.instant import run_instant_engine

    return run_instant_engine("behavioral_finance", ctx, beginner=beginner, question=question)


def risk_reduction_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    """Backward-compatible alias for ``behavioral_finance_answer``."""
    return behavioral_finance_answer(ctx, beginner=beginner, question=question)


def solve_phase2_or_structured(
    intent: str,
    ctx: dict[str, Any],
    *,
    beginner: bool,
    question: str = "",
) -> tuple[InvestmentSolverRoute, InvestmentSolverResult] | None:
    if intent == "portfolio_concentration":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("portfolio_concentration", ctx, beginner=beginner, question=question)
    elif intent == "portfolio_risk":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("portfolio_risk", ctx, beginner=beginner, question=question)
    elif intent == "etf_overlap":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("etf_overlap", ctx, beginner=beginner, question=question)
    elif intent == "diversification":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("diversification", ctx, beginner=beginner, question=question)
    elif intent == "scenario_stress":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("scenario_stress", ctx, beginner=beginner, question=question)
    elif intent == "macro_rates":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("macro_rates", ctx, beginner=beginner, question=question)
    elif intent == "macro_recession":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("macro_recession", ctx, beginner=beginner, question=question)
    elif intent == "macro_inflation":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("macro_inflation", ctx, beginner=beginner, question=question)
    elif intent == "allocation_recommendation":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine(
            "allocation_recommendation",
            ctx,
            beginner=beginner,
            question=question,
        )
    elif intent == "valuation":
        result = valuation_answer(ctx, beginner=beginner, question=question)
    elif intent == "investment_coach":
        result = education_answer(ctx, beginner=beginner, question=question)
    elif intent == "risk_reduction":
        result = behavioral_finance_answer(ctx, beginner=beginner, question=question)
    elif intent == "allocation_advisor":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("allocation_advisor", ctx, beginner=beginner, question=question)
    elif intent == "cash_reserve_advisor":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("cash_reserve_advisor", ctx, beginner=beginner, question=question)
    elif intent == "real_portfolio_advisor":
        from investment_ami.pipeline.instant import run_instant_engine

        result = run_instant_engine("real_portfolio_advisor", ctx, beginner=beginner, question=question)
    else:
        return None
    route = _route_for_intent(intent)
    result.problem_type = route.problem_type
    result.model_name = route.model_name
    return route, result
