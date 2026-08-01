"""Separate portfolio cash, protected reserves, and target allocation cash (Real Portfolio Advisor)."""

from __future__ import annotations

from dataclasses import dataclass

from investment_ami.decision_support.real_portfolio_drift import RealPortfolioDriftAnalysis
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot


@dataclass(frozen=True)
class RealPortfolioCashClassification:
    """Ledger cash split for liquidity vs allocation reasoning."""

    portfolio_cash: float
    protected_cash_target: float
    protected_shortfall: float
    investable_cash: float | None
    reserves_fully_funded: bool
    cash_purpose_known: bool
    portfolio_cash_weight_pct: float
    target_portfolio_cash_allocation_pct: float | None


def classify_real_portfolio_cash(
    snapshot: RealPortfolioSnapshot,
    drift: RealPortfolioDriftAnalysis | None = None,
) -> RealPortfolioCashClassification:
    """
    A. portfolio_cash — cash in the transaction ledger.
    B. protected_cash_target — emergency + near-term (+ optional plan expenses when present).
    C. target_portfolio_cash_allocation_pct — from saved/inferred target, not reserve needs.
    """
    cash = float(snapshot.cash or 0.0)
    tmv = max(float(snapshot.total_market_value or 0.0), 1.0)
    reserves = snapshot.reserves or {}
    emergency = float(reserves.get("emergency", 0.0))
    near = float(snapshot.near_term_needs or 0.0)
    expenses = float(reserves.get("plan_expenses", 0.0))
    protected_target = emergency + near + expenses
    purpose_known = protected_target > 0.0

    shortfall = max(0.0, protected_target - cash) if purpose_known else 0.0
    fully_funded = purpose_known and shortfall <= 0.0
    investable: float | None
    if not purpose_known:
        investable = None
    else:
        investable = max(0.0, cash - protected_target)

    target_cash_pct: float | None = None
    if drift is not None and drift.target_allocation:
        for key in ("Cash", "Cash_and_TBills", "cash"):
            if key in drift.target_allocation:
                try:
                    target_cash_pct = float(drift.target_allocation[key])
                    break
                except (TypeError, ValueError):
                    pass
        if target_cash_pct is None:
            for key, val in drift.target_allocation.items():
                if str(key).lower().replace(" ", "_") in ("cash", "cash_and_tbills"):
                    try:
                        target_cash_pct = float(val)
                        break
                    except (TypeError, ValueError):
                        pass

    return RealPortfolioCashClassification(
        portfolio_cash=cash,
        protected_cash_target=protected_target,
        protected_shortfall=shortfall,
        investable_cash=investable,
        reserves_fully_funded=fully_funded,
        cash_purpose_known=purpose_known,
        portfolio_cash_weight_pct=cash / tmv * 100.0,
        target_portfolio_cash_allocation_pct=target_cash_pct,
    )
