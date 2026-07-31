"""Concentration analysis from RealPortfolioSnapshot (Phase B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot, RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_security_types import (
    SecurityClassification,
    SecurityKind,
    classify_holding_security,
    classify_snapshot_holdings,
)

# Product decision-support thresholds (not universal financial rules).
SINGLE_EQUITY_NOTABLE_WEIGHT_PCT = 10.0
SINGLE_EQUITY_MATERIAL_WEIGHT_PCT = 20.0
LARGE_BROAD_FUND_REPORT_WEIGHT_PCT = 25.0

ConcentrationStatus = Literal[
    "well_diversified_by_weight",
    "notable_concentration",
    "material_concentration",
    "partial_data",
    "unknown_metadata",
]


@dataclass(frozen=True)
class RealPortfolioObservation:
    code: str
    ticker: str = ""
    value: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RealPortfolioConcentrationAnalysis:
    largest_holding: RealHoldingSnapshot | None
    largest_holding_weight: float
    top_three_weight: float
    top_five_weight: float
    hhi: float
    effective_number_of_positions: float | None
    security_count: int
    priced_security_count: int
    cash_weight: float
    asset_class_weights: dict[str, float]
    single_security_concentration_flags: tuple[str, ...]
    broad_fund_concentration_flags: tuple[str, ...]
    asset_class_concentration_flags: tuple[str, ...]
    concentration_status: ConcentrationStatus
    observations: tuple[RealPortfolioObservation, ...]
    data_quality_flags: tuple[str, ...] = ()
    security_classifications: dict[str, SecurityClassification] = field(default_factory=dict)


def _weights_for_concentration(snapshot: RealPortfolioSnapshot) -> list[tuple[RealHoldingSnapshot, float]]:
    total = snapshot.total_market_value
    if total <= 0:
        return []
    out: list[tuple[RealHoldingSnapshot, float]] = []
    for h in snapshot.holdings:
        if h.current_price is None or h.current_price <= 0:
            continue
        w = h.current_value / total * 100.0 if h.current_value > 0 else h.current_weight
        out.append((h, w))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _hhi(weights_pct: list[float]) -> float:
    fracs = [w / 100.0 for w in weights_pct if w > 0]
    return sum(f * f for f in fracs)


def _observations_for_holdings(
    weighted: list[tuple[RealHoldingSnapshot, float]],
    classifications: dict[str, SecurityClassification],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[RealPortfolioObservation, ...],
    ConcentrationStatus,
]:
    single_flags: list[str] = []
    broad_flags: list[str] = []
    asset_flags: list[str] = []
    observations: list[RealPortfolioObservation] = []
    unknown_count = 0

    for holding, weight in weighted:
        clf = classifications.get(holding.ticker)
        kind: SecurityKind = clf.kind if clf else "unknown"
        if clf and clf.confidence == "low" and kind == "unknown":
            unknown_count += 1

        if kind == "individual_equity":
            if weight >= SINGLE_EQUITY_MATERIAL_WEIGHT_PCT:
                single_flags.append(f"material_single_security:{holding.ticker}")
                observations.append(
                    RealPortfolioObservation(
                        code="material_single_security_weight",
                        ticker=holding.ticker,
                        value=weight,
                        evidence={"kind": kind, "threshold_pct": SINGLE_EQUITY_MATERIAL_WEIGHT_PCT},
                    )
                )
            elif weight >= SINGLE_EQUITY_NOTABLE_WEIGHT_PCT:
                single_flags.append(f"notable_single_security:{holding.ticker}")
                observations.append(
                    RealPortfolioObservation(
                        code="notable_single_security_weight",
                        ticker=holding.ticker,
                        value=weight,
                        evidence={"kind": kind, "threshold_pct": SINGLE_EQUITY_NOTABLE_WEIGHT_PCT},
                    )
                )
        elif kind == "broad_market_etf":
            if weight >= LARGE_BROAD_FUND_REPORT_WEIGHT_PCT:
                broad_flags.append(f"large_broad_fund_weight:{holding.ticker}")
            observations.append(
                RealPortfolioObservation(
                    code="broad_market_etf_weight",
                    ticker=holding.ticker,
                    value=weight,
                    evidence={
                        "note": "Broad-market ETF weight is not equivalent to single-company concentration.",
                    },
                )
            )
        elif kind == "narrow_or_thematic_etf":
            observations.append(
                RealPortfolioObservation(
                    code="narrow_or_thematic_etf_weight",
                    ticker=holding.ticker,
                    value=weight,
                    evidence={"kind": kind},
                )
            )
            if weight >= SINGLE_EQUITY_NOTABLE_WEIGHT_PCT:
                broad_flags.append(f"thematic_concentration:{holding.ticker}")
        elif kind == "unknown":
            observations.append(
                RealPortfolioObservation(
                    code="unknown_security_type",
                    ticker=holding.ticker,
                    value=weight,
                    evidence={"message": "Concentration interpretation is limited."},
                )
            )

    if weighted:
        top = weighted[0]
        observations.append(
            RealPortfolioObservation(
                code="largest_position_weight",
                ticker=top[0].ticker,
                value=top[1],
                evidence={},
            )
        )
        top3 = sum(w for _, w in weighted[:3])
        observations.append(
            RealPortfolioObservation(
                code="top_three_weight",
                value=top3,
                evidence={"count": min(3, len(weighted))},
            )
        )

    status: ConcentrationStatus = "well_diversified_by_weight"
    if any(f.startswith("material_single") for f in single_flags):
        status = "material_concentration"
    elif single_flags or any("thematic" in f for f in broad_flags):
        status = "notable_concentration"
    if unknown_count > 0 and status == "well_diversified_by_weight":
        status = "unknown_metadata"

    return (
        tuple(single_flags),
        tuple(broad_flags),
        tuple(asset_flags),
        tuple(observations),
        status,
    )


def analyze_real_portfolio_concentration(
    snapshot: RealPortfolioSnapshot,
    *,
    security_metadata: dict[str, dict[str, str]] | None = None,
) -> RealPortfolioConcentrationAnalysis:
    """Pure concentration metrics and factual observations — no buy/sell guidance."""
    flags = list(snapshot.data_quality_flags)
    if snapshot.unpriced_holdings_count > 0:
        if "missing_prices" not in flags:
            flags.append("missing_prices")
        if "partial_market_value" not in flags:
            flags.append("partial_market_value")

    cash_weight = float(snapshot.allocation_by_holding.get("$CASH", 0.0))
    asset_class_weights = dict(snapshot.allocation_by_asset_class)

    classifications = classify_snapshot_holdings(snapshot.holdings, security_metadata=security_metadata)
    weighted = _weights_for_concentration(snapshot)

    weights_pct = [w for _, w in weighted]
    hhi = _hhi(weights_pct)
    enp = (1.0 / hhi) if hhi > 1e-12 else None

    largest_h = weighted[0][0] if weighted else None
    largest_w = weighted[0][1] if weighted else 0.0
    top3 = sum(weights_pct[:3])
    top5 = sum(weights_pct[:5])

    single_f, broad_f, asset_f, observations, status = _observations_for_holdings(weighted, classifications)

    if snapshot.unpriced_holdings_count > 0 and status != "material_concentration":
        status = "partial_data"

    # Asset-class description only (no target judgment without plan targets).
    for cls, wt in asset_class_weights.items():
        if cls == "Cash":
            continue
        if wt >= 80.0:
            asset_f = (*asset_f, f"high_asset_class_weight:{cls}")
            obs_list = list(observations)
            obs_list.append(
                RealPortfolioObservation(
                    code="asset_class_weight",
                    value=wt,
                    evidence={"asset_class": cls, "note": "Descriptive only without target allocation context."},
                )
            )
            observations = tuple(obs_list)

    priced_count = sum(1 for h in snapshot.holdings if h.current_price is not None and h.current_price > 0)

    return RealPortfolioConcentrationAnalysis(
        largest_holding=largest_h,
        largest_holding_weight=largest_w,
        top_three_weight=top3,
        top_five_weight=top5,
        hhi=round(hhi, 6),
        effective_number_of_positions=round(enp, 4) if enp is not None else None,
        security_count=len(snapshot.holdings),
        priced_security_count=priced_count,
        cash_weight=cash_weight,
        asset_class_weights=asset_class_weights,
        single_security_concentration_flags=single_f,
        broad_fund_concentration_flags=broad_f,
        asset_class_concentration_flags=asset_f,
        concentration_status=status,
        observations=observations,
        data_quality_flags=tuple(dict.fromkeys(flags)),
        security_classifications=classifications,
    )
