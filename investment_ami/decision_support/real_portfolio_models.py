"""Typed models for ledger-backed real portfolio snapshots (Phase A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MarketDataStatus = Literal["fresh", "cached", "partial", "unavailable"]
RealPortfolioDataSource = Literal["real_portfolio_engine"]
SnapshotFailureCode = Literal["no_real_ledger"]

REAL_PORTFOLIO_DATA_SOURCE: RealPortfolioDataSource = "real_portfolio_engine"


@dataclass(frozen=True)
class RealHoldingSnapshot:
    ticker: str
    name: str
    shares: float
    average_cost: float
    total_cost_basis: float
    current_price: float | None
    current_value: float
    gain_loss_dollars: float | None
    gain_loss_pct: float | None
    current_weight: float
    target_weight: float | None
    asset_class: str
    price_source: str
    price_as_of: datetime | None
    data_quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RealPortfolioSnapshot:
    as_of: datetime
    market_data_status: MarketDataStatus
    market_data_age_seconds: int | None
    data_source: RealPortfolioDataSource
    total_market_value: float
    total_cost_basis: float
    total_gain_loss_dollars: float | None
    total_gain_loss_pct: float | None
    priced_holdings_gain_loss_pct: float | None
    cash: float
    holdings: tuple[RealHoldingSnapshot, ...]
    allocation_by_holding: dict[str, float]
    allocation_by_asset_class: dict[str, float]
    largest_positions: tuple[RealHoldingSnapshot, ...]
    concentration_metrics: dict[str, float]
    target_allocation: dict[str, float] | None = None
    allocation_drift: dict[str, float] | None = None
    recent_performance: dict[str, Any] | None = None
    benchmark_performance: dict[str, Any] | None = None
    risk_tolerance: str = ""
    investment_horizon: int | None = None
    monthly_contribution: float | None = None
    reserves: dict[str, float] | None = None
    near_term_needs: float | None = None
    health_objective: str = ""
    data_quality_flags: tuple[str, ...] = ()
    holdings_df_mismatch_warning: str | None = None
    known_marked_securities_value: float = 0.0
    unpriced_holdings_count: int = 0


@dataclass(frozen=True)
class RealPortfolioSnapshotBuildFailure:
    code: SnapshotFailureCode
    message: str


@dataclass(frozen=True)
class RealPortfolioSnapshotBuildResult:
    snapshot: RealPortfolioSnapshot | None = None
    failure: RealPortfolioSnapshotBuildFailure | None = None

    @property
    def ok(self) -> bool:
        return self.snapshot is not None
