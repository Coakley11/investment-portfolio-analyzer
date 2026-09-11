"""Real Portfolio Dashboard insights — financial summary, drivers, strategy status.

Pure helpers over the authoritative ledger marks (positions + cash ledger).
Does not mutate transactions, strategy targets, or Contribution Advisor math.

Slices A–C only: no TWR / XIRR / benchmark / historical NAV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

StrategyStatusLabel = Literal["On Target", "Mild Drift", "Significant Drift", "No Strategy Target"]

# Explicit product thresholds (percentage points of portfolio weight).
# Boundary: |drift| < 2 → On Target; 2 ≤ |drift| < 5 → Mild; |drift| ≥ 5 → Significant.
STRATEGY_ON_TARGET_MAX_ABS_PP = 2.0
STRATEGY_MILD_DRIFT_MAX_ABS_PP = 5.0


@dataclass(frozen=True)
class HoldingDriverRow:
    ticker: str
    market_value: float
    cost_basis: float
    unrealized_gain_loss_dollar: float
    unrealized_gain_loss_pct: float
    weight_pct: float
    contribution_to_aggregate_unrealized_dollar: float


@dataclass(frozen=True)
class StrategyHoldingDriftRow:
    ticker: str
    target_weight_pct: float
    live_weight_pct: float
    drift_pp: float
    abs_drift_pp: float


@dataclass(frozen=True)
class StrategyStatusResult:
    ok: bool
    status: StrategyStatusLabel
    max_abs_drift_pp: float
    overall_abs_drift_sum_pp: float
    rows: tuple[StrategyHoldingDriftRow, ...] = ()
    saved_target_pct: dict[str, float] = field(default_factory=dict)
    live_allocation_pct: dict[str, float] = field(default_factory=dict)
    explanation: str = ""


@dataclass(frozen=True)
class FinancialPerformanceSnapshot:
    nav: float
    securities_market_value: float
    cash_balance: float
    net_external_contributions: float
    securities_cost_basis: float
    unrealized_gain_loss_dollar: float
    unrealized_gain_loss_pct: float
    num_holdings: int


def classify_strategy_status(max_abs_drift_pp: float) -> StrategyStatusLabel:
    """
    Map maximum absolute holding drift (percentage points) to a status label.

    Deterministic boundaries (unit-tested):
    - abs_drift < 2.0  → On Target
    - 2.0 ≤ abs_drift < 5.0 → Mild Drift
    - abs_drift ≥ 5.0 → Significant Drift
    """
    d = abs(float(max_abs_drift_pp))
    if d < STRATEGY_ON_TARGET_MAX_ABS_PP:
        return "On Target"
    if d < STRATEGY_MILD_DRIFT_MAX_ABS_PP:
        return "Mild Drift"
    return "Significant Drift"


def _as_pct_map(raw: Mapping[str, float] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not raw:
        return out
    for k, v in raw.items():
        sym = str(k or "").strip().upper()
        if not sym:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv < 0:
            continue
        out[sym] = out.get(sym, 0.0) + fv
    return out


def normalize_weight_map_to_percent(raw: Mapping[str, float] | None) -> dict[str, float]:
    """Accept percent (sum≈100) or fraction (sum≈1) maps; return percent weights."""
    cleaned = _as_pct_map(raw)
    if not cleaned:
        return {}
    total = sum(cleaned.values())
    if total <= 0:
        return {}
    if abs(total - 1.0) <= 0.02:
        return {k: v * 100.0 for k, v in cleaned.items()}
    return dict(cleaned)


def financial_performance_from_engine(
    *,
    total_portfolio_value: float,
    securities_market_value: float,
    cash_balance: float,
    net_external_contributions: float,
    securities_cost_basis: float,
    unrealized_gain_loss_dollar: float,
    num_holdings: int,
) -> FinancialPerformanceSnapshot:
    invested = float(securities_cost_basis or 0.0)
    gain = float(unrealized_gain_loss_dollar or 0.0)
    pct = (gain / invested * 100.0) if invested > 0 else 0.0
    return FinancialPerformanceSnapshot(
        nav=float(total_portfolio_value or 0.0),
        securities_market_value=float(securities_market_value or 0.0),
        cash_balance=float(cash_balance or 0.0),
        net_external_contributions=float(net_external_contributions or 0.0),
        securities_cost_basis=invested,
        unrealized_gain_loss_dollar=gain,
        unrealized_gain_loss_pct=pct,
        num_holdings=int(num_holdings or 0),
    )


def holding_performance_drivers(
    positions: Sequence[Any],
) -> tuple[HoldingDriverRow, ...]:
    """
    Build per-holding unrealized drivers.

    ``contribution_to_aggregate_unrealized_dollar`` equals the holding's unrealized
    G/L $ (sums to portfolio unrealized G/L when all positions are included).
    Ranking for best/worst must use this dollar field — not holding %.
    """
    rows: list[HoldingDriverRow] = []
    for p in positions:
        ticker = str(getattr(p, "ticker", "") or "").strip().upper()
        if not ticker:
            continue
        mv = float(getattr(p, "market_value", 0.0) or 0.0)
        shares = float(getattr(p, "shares_owned", 0.0) or 0.0)
        avg = float(getattr(p, "average_cost_basis", 0.0) or 0.0)
        cost = shares * avg
        # Prefer explicit position fields when present.
        gl = getattr(p, "gain_loss_dollar", None)
        if gl is None:
            gl = mv - cost
        gl = float(gl)
        gl_pct = getattr(p, "gain_loss_pct", None)
        if gl_pct is None:
            gl_pct = (gl / cost * 100.0) if cost > 0 else 0.0
        weight = float(getattr(p, "weight_pct", 0.0) or 0.0)
        rows.append(
            HoldingDriverRow(
                ticker=ticker,
                market_value=mv,
                cost_basis=cost,
                unrealized_gain_loss_dollar=gl,
                unrealized_gain_loss_pct=float(gl_pct),
                weight_pct=weight,
                contribution_to_aggregate_unrealized_dollar=gl,
            )
        )
    rows.sort(key=lambda r: (-r.contribution_to_aggregate_unrealized_dollar, r.ticker))
    return tuple(rows)


def best_and_worst_dollar_contributors(
    rows: Sequence[HoldingDriverRow],
) -> tuple[HoldingDriverRow | None, HoldingDriverRow | None]:
    if not rows:
        return None, None
    best = max(rows, key=lambda r: (r.contribution_to_aggregate_unrealized_dollar, r.ticker))
    worst = min(rows, key=lambda r: (r.contribution_to_aggregate_unrealized_dollar, r.ticker))
    return best, worst


def analyze_strategy_status(
    *,
    live_weights_pct: Mapping[str, float],
    saved_strategy_pct: Mapping[str, float] | None,
) -> StrategyStatusResult:
    """
    Compare live portfolio weights to the saved Current Strategy Target.

    Does not mutate or rewrite ``saved_strategy_pct``.
    Status uses max absolute holding drift vs the explicit thresholds.
    """
    live = normalize_weight_map_to_percent(live_weights_pct)
    saved = normalize_weight_map_to_percent(saved_strategy_pct)
    if not saved:
        return StrategyStatusResult(
            ok=False,
            status="No Strategy Target",
            max_abs_drift_pp=0.0,
            overall_abs_drift_sum_pp=0.0,
            live_allocation_pct=live,
            explanation=(
                "No saved strategy target yet. Establish one under Allocate New Money → "
                "Current strategy target. Live market weights are not used as a substitute."
            ),
        )

    tickers = sorted(set(live) | set(saved))
    rows: list[StrategyHoldingDriftRow] = []
    for t in tickers:
        tgt = float(saved.get(t, 0.0))
        cur = float(live.get(t, 0.0))
        drift = cur - tgt
        rows.append(
            StrategyHoldingDriftRow(
                ticker=t,
                target_weight_pct=tgt,
                live_weight_pct=cur,
                drift_pp=drift,
                abs_drift_pp=abs(drift),
            )
        )
    rows.sort(key=lambda r: (-r.abs_drift_pp, r.ticker))
    max_abs = max((r.abs_drift_pp for r in rows), default=0.0)
    sum_abs = sum(r.abs_drift_pp for r in rows)
    status = classify_strategy_status(max_abs)
    return StrategyStatusResult(
        ok=True,
        status=status,
        max_abs_drift_pp=max_abs,
        overall_abs_drift_sum_pp=sum_abs,
        rows=tuple(rows),
        saved_target_pct=dict(saved),
        live_allocation_pct=live,
        explanation=(
            f"Strategy status is based on max absolute holding drift "
            f"({max_abs:.2f} pp) versus the saved strategy target — "
            "not on whether investments are making or losing money."
        ),
    )
