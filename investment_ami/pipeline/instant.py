"""Run catalog instant engines with legacy-compatible results."""

from __future__ import annotations

from typing import Any

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.asset_allocation import get_asset_allocation_engine
from investment_ami.engines.diversification import get_diversification_engine
from investment_ami.engines.etf_overlap import get_etf_overlap_engine
from investment_ami.engines.macroeconomic import get_macroeconomic_engine
from investment_ami.engines.portfolio_concentration import get_portfolio_concentration_engine
from investment_ami.engines.portfolio_risk import get_portfolio_risk_engine

from investment_ami.engines.education import get_education_engine
from investment_ami.engines.behavioral_finance import get_behavioral_finance_engine
from investment_ami.engines.scenario_stress import get_scenario_stress_engine
from investment_ami.engines.valuation import get_valuation_engine
from investment_ami.engines.allocation_advisor import get_allocation_advisor_engine
from investment_ami.engines.cash_reserve_advisor import get_cash_reserve_advisor_engine

_concentration_engine = get_portfolio_concentration_engine()
_risk_engine = get_portfolio_risk_engine()
_allocation_engine = get_asset_allocation_engine()
_etf_overlap_engine = get_etf_overlap_engine()
_valuation_engine = get_valuation_engine()
_scenario_stress_engine = get_scenario_stress_engine()
_education_engine = get_education_engine()
_behavioral_finance_engine = get_behavioral_finance_engine()

INSTANT_ENGINE_REGISTRY: dict[str, Any] = {
    "diversification": get_diversification_engine(),
    "portfolio_concentration": _concentration_engine,
    "portfolio_analysis": _concentration_engine,
    "portfolio_risk": _risk_engine,
    "risk_analysis": _risk_engine,
    "allocation_recommendation": _allocation_engine,
    "asset_allocation": _allocation_engine,
    "etf_overlap": _etf_overlap_engine,
    "valuation": _valuation_engine,
    "scenario_stress": _scenario_stress_engine,
    "education": _education_engine,
    "investment_coach": _education_engine,
    "behavioral_finance": _behavioral_finance_engine,
    "risk_reduction": _behavioral_finance_engine,
    "macro_rates": get_macroeconomic_engine("macro_rates"),
    "macro_recession": get_macroeconomic_engine("macro_recession"),
    "macro_inflation": get_macroeconomic_engine("macro_inflation"),
    "allocation_advisor": get_allocation_advisor_engine(),
    "cash_reserve_advisor": get_cash_reserve_advisor_engine(),
}


def run_instant_engine(
    engine_id: str,
    context: dict[str, Any],
    *,
    beginner: bool,
    question: str = "",
) -> Any:
    """
    Execute a registered instant engine and return ``InvestmentSolverResult``.

    Unknown engine ids raise ``KeyError`` (programmer error during migration).
    """
    engine = INSTANT_ENGINE_REGISTRY[str(engine_id).strip()]
    request = InstantEngineRequest(
        context=dict(context or {}),
        beginner=beginner,
        question=str(question or ""),
    )
    return engine.solve(request)
