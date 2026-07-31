"""Unrealized performance analysis from RealPortfolioSnapshot (Phase B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot, RealPortfolioSnapshot

METRIC_LABEL_UNREALIZED = "Unrealized gain or loss since purchase (cost basis)"

PerformanceStatus = Literal[
    "positive_unrealized_gain",
    "negative_unrealized_loss",
    "approximately_flat",
    "partial_data",
    "unavailable",
]

FLAT_RETURN_THRESHOLD_PCT = 0.5


@dataclass(frozen=True)
class HoldingPerformanceContribution:
    ticker: str
    name: str
    asset_class: str
    current_value: float
    total_cost_basis: float
    gain_loss_dollars: float | None
    gain_loss_pct: float | None
    portfolio_weight: float
    contribution_to_total_gain_loss_dollars: float | None
    contribution_to_portfolio_return_pct: float | None
    price_available: bool
    data_quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RealPortfolioPerformanceAnalysis:
    total_market_value: float
    total_cost_basis: float
    total_gain_loss_dollars: float | None
    total_gain_loss_pct: float | None
    priced_holdings_gain_loss_pct: float | None
    priced_holdings_count: int
    unpriced_holdings_count: int
    positive_contributors: tuple[HoldingPerformanceContribution, ...]
    negative_contributors: tuple[HoldingPerformanceContribution, ...]
    largest_positive_contributor: HoldingPerformanceContribution | None
    largest_negative_contributor: HoldingPerformanceContribution | None
    performance_status: PerformanceStatus
    metric_label: str
    data_quality_flags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


def _security_holdings(snapshot: RealPortfolioSnapshot) -> tuple[RealHoldingSnapshot, ...]:
    return snapshot.holdings


def _contribution_row(
    holding: RealHoldingSnapshot,
    *,
    total_cost_basis: float,
    priced_cost_basis: float,
    complete_pricing: bool,
) -> HoldingPerformanceContribution | None:
    priced = holding.current_price is not None and holding.current_price > 0
    if not priced or holding.gain_loss_dollars is None:
        flags = tuple(holding.data_quality_flags) or ("missing_price",)
        return HoldingPerformanceContribution(
            ticker=holding.ticker,
            name=holding.name,
            asset_class=holding.asset_class,
            current_value=holding.current_value,
            total_cost_basis=holding.total_cost_basis,
            gain_loss_dollars=None,
            gain_loss_pct=None,
            portfolio_weight=holding.current_weight,
            contribution_to_total_gain_loss_dollars=None,
            contribution_to_portfolio_return_pct=None,
            price_available=False,
            data_quality_flags=flags,
        )
    contrib_d = float(holding.gain_loss_dollars)
    contrib_pct: float | None = None
    if complete_pricing and total_cost_basis > 0:
        contrib_pct = contrib_d / total_cost_basis * 100.0
    elif priced_cost_basis > 0:
        contrib_pct = contrib_d / priced_cost_basis * 100.0
    return HoldingPerformanceContribution(
        ticker=holding.ticker,
        name=holding.name,
        asset_class=holding.asset_class,
        current_value=holding.current_value,
        total_cost_basis=holding.total_cost_basis,
        gain_loss_dollars=contrib_d,
        gain_loss_pct=holding.gain_loss_pct,
        portfolio_weight=holding.current_weight,
        contribution_to_total_gain_loss_dollars=contrib_d,
        contribution_to_portfolio_return_pct=contrib_pct,
        price_available=True,
        data_quality_flags=tuple(holding.data_quality_flags),
    )


def analyze_real_portfolio_performance(snapshot: RealPortfolioSnapshot) -> RealPortfolioPerformanceAnalysis:
    """
    Pure unrealized performance facts from a Phase A snapshot.

    Does not read session state, alternate model-portfolio views, or sidebar portfolio value.
    """
    flags: list[str] = list(snapshot.data_quality_flags)
    limitations: list[str] = []
    holdings = _security_holdings(snapshot)

    priced = [h for h in holdings if h.current_price is not None and h.current_price > 0]
    unpriced = [h for h in holdings if h not in priced]
    if unpriced:
        if "missing_prices" not in flags:
            flags.append("missing_prices")
        if "partial_market_value" not in flags:
            flags.append("partial_market_value")
    if snapshot.holdings_df_mismatch_warning:
        flags.append("holdings_df_mismatch")
    if snapshot.cash < -1e-6 and "negative_cash_balance" not in flags:
        flags.append("negative_cash_balance")

    total_cost = snapshot.total_cost_basis
    priced_cost = sum(h.total_cost_basis for h in priced)
    complete = len(unpriced) == 0 and total_cost > 0

    total_gain_d = snapshot.total_gain_loss_dollars
    total_gain_pct = snapshot.total_gain_loss_pct if complete else None
    priced_gain_pct = snapshot.priced_holdings_gain_loss_pct

    rows: list[HoldingPerformanceContribution] = []
    for h in holdings:
        row = _contribution_row(
            h,
            total_cost_basis=total_cost,
            priced_cost_basis=priced_cost,
            complete_pricing=complete,
        )
        if row is not None:
            rows.append(row)

    ranked = [r for r in rows if r.price_available and r.contribution_to_total_gain_loss_dollars is not None]
    positive = tuple(sorted([r for r in ranked if r.contribution_to_total_gain_loss_dollars > 0], key=lambda r: -r.contribution_to_total_gain_loss_dollars))
    negative = tuple(sorted([r for r in ranked if r.contribution_to_total_gain_loss_dollars < 0], key=lambda r: r.contribution_to_total_gain_loss_dollars))

    largest_pos = positive[0] if positive else None
    largest_neg = negative[0] if negative else None

    status: PerformanceStatus
    if not priced and total_cost <= 0:
        status = "unavailable"
        limitations.append("No priced holdings with cost basis are available.")
    elif unpriced:
        status = "partial_data"
        limitations.append(
            "Complete portfolio unrealized return is unavailable because one or more holdings lack current prices."
        )
        if priced_gain_pct is not None:
            limitations.append(
                "Priced-holdings unrealized return applies only to holdings with valid current prices."
            )
    elif total_gain_d is None:
        status = "unavailable"
    elif total_gain_pct is not None and abs(total_gain_pct) < FLAT_RETURN_THRESHOLD_PCT:
        status = "approximately_flat"
    elif total_gain_d is not None and total_gain_d > 0:
        status = "positive_unrealized_gain"
    elif total_gain_d is not None and total_gain_d < 0:
        status = "negative_unrealized_loss"
    else:
        status = "approximately_flat"

    return RealPortfolioPerformanceAnalysis(
        total_market_value=snapshot.total_market_value,
        total_cost_basis=total_cost,
        total_gain_loss_dollars=total_gain_d if complete or priced else total_gain_d,
        total_gain_loss_pct=total_gain_pct,
        priced_holdings_gain_loss_pct=priced_gain_pct,
        priced_holdings_count=len(priced),
        unpriced_holdings_count=len(unpriced),
        positive_contributors=positive,
        negative_contributors=negative,
        largest_positive_contributor=largest_pos,
        largest_negative_contributor=largest_neg,
        performance_status=status,
        metric_label=METRIC_LABEL_UNREALIZED,
        data_quality_flags=tuple(dict.fromkeys(flags)),
        limitations=tuple(limitations),
    )
