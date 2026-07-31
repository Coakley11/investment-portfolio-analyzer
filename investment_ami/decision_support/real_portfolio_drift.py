"""Target resolution and allocation drift analysis for the real portfolio (Phase C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot

TargetSource = Literal[
    "user_defined_target",
    "saved_objective_target",
    "inferred_risk_profile_target",
    "unavailable",
]

TargetQuality = Literal["explicit", "sufficient", "limited", "invalid"]

DriftSeverity = Literal["immaterial", "modest", "material", "substantial"]

DriftStatus = Literal[
    "aligned",
    "immaterial_drift",
    "modest_drift",
    "material_drift",
    "target_unavailable",
    "partial_data",
    "invalid_target",
]

# Product decision-support thresholds (documented; not universal financial rules).
DRIFT_IMMATERIAL_PP = 2.0
DRIFT_MODEST_MIN_PP = 2.0
DRIFT_MATERIAL_MIN_PP = 5.0
DRIFT_SUBSTANTIAL_MIN_PP = 10.0
TARGET_WEIGHT_SUM_TOLERANCE_PP = 3.0
COMBINED_MODEST_DRIFT_COUNT = 2
COMBINED_MODEST_DRIFT_SUM_PP = 8.0

LEDGER_ASSET_CLASSES: frozenset[str] = frozenset({"Stocks", "ETFs", "Cash", "Other"})
OBJECTIVE_BUCKETS: frozenset[str] = frozenset({"Equity", "Bonds", "Cash_and_TBills"})
OBJECTIVE_ALIASES: dict[str, str] = {
    "equity": "Equity",
    "bonds": "Bonds",
    "tbills": "Cash_and_TBills",
    "t-bills": "Cash_and_TBills",
    "cash": "Cash_and_TBills",
    "cash_and_tbills": "Cash_and_TBills",
}


@dataclass(frozen=True)
class DriftObservation:
    code: str
    asset_class: str
    current_weight: float
    target_weight: float
    drift_percentage_points: float
    severity: DriftSeverity
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RealPortfolioDriftAnalysis:
    target_source: TargetSource
    target_allocation: dict[str, float]
    current_allocation: dict[str, float]
    drift_by_asset_class: dict[str, float]
    absolute_drift_by_asset_class: dict[str, float]
    largest_overweight: DriftObservation | None
    largest_underweight: DriftObservation | None
    total_absolute_drift: float
    drift_status: DriftStatus
    rebalance_triggered: bool
    target_quality: TargetQuality
    observations: tuple[DriftObservation, ...]
    data_quality_flags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


def _severity(abs_drift: float) -> DriftSeverity:
    if abs_drift < DRIFT_IMMATERIAL_PP:
        return "immaterial"
    if abs_drift < DRIFT_MATERIAL_MIN_PP:
        return "modest"
    if abs_drift < DRIFT_SUBSTANTIAL_MIN_PP:
        return "material"
    return "substantial"


def _current_ledger_allocation(snapshot: RealPortfolioSnapshot) -> dict[str, float]:
    ac = dict(snapshot.allocation_by_asset_class or {})
    cash = float(ac.get("Cash", 0.0))
    if cash <= 0.0:
        cash = float(snapshot.allocation_by_holding.get("$CASH", 0.0))
    return {
        "Stocks": float(ac.get("Stocks", 0.0)),
        "ETFs": float(ac.get("ETFs", 0.0)),
        "Cash": cash,
        "Other": float(ac.get("Other", 0.0)),
    }


def _current_objective_allocation(snapshot: RealPortfolioSnapshot) -> dict[str, float]:
    ledger = _current_ledger_allocation(snapshot)
    return {
        "Equity": ledger["Stocks"] + ledger["ETFs"],
        "Bonds": ledger["Other"],
        "Cash_and_TBills": ledger["Cash"],
    }


def _normalize_target_keys(raw: dict[str, float]) -> dict[str, float]:
    canonical_ledger = {"stocks": "Stocks", "etfs": "ETFs", "cash": "Cash", "other": "Other"}
    out: dict[str, float] = {}
    for k, v in raw.items():
        key = str(k).strip()
        low = key.lower().replace(" ", "_")
        if key in LEDGER_ASSET_CLASSES or key in OBJECTIVE_BUCKETS:
            pass
        elif low in canonical_ledger:
            key = canonical_ledger[low]
        elif low in OBJECTIVE_ALIASES:
            key = OBJECTIVE_ALIASES[low]
        try:
            out[key] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _target_sum_ok(target: dict[str, float]) -> bool:
    if not target:
        return False
    total = sum(target.values())
    return abs(total - 100.0) <= TARGET_WEIGHT_SUM_TOLERANCE_PP


def _aggregate_ticker_targets(
    snapshot: RealPortfolioSnapshot,
    ticker_targets: dict[str, float],
) -> tuple[dict[str, float], TargetQuality, tuple[str, ...]]:
    limitations: list[str] = []
    by_class: dict[str, float] = {k: 0.0 for k in LEDGER_ASSET_CLASSES}
    ticker_to_class = {h.ticker.upper(): h.asset_class for h in snapshot.holdings}
    unmapped: list[str] = []
    for tick, wt in ticker_targets.items():
        sym = str(tick).strip().upper()
        if sym in ("$CASH", "CASH"):
            by_class["Cash"] += float(wt)
            continue
        cls = ticker_to_class.get(sym)
        if cls in LEDGER_ASSET_CLASSES:
            by_class[cls] += float(wt)
        else:
            unmapped.append(sym)
    if unmapped:
        limitations.append(
            f"Target tickers not in ledger were excluded from asset-class aggregation: {', '.join(unmapped[:6])}."
        )
    total = sum(by_class.values())
    if total <= 0:
        return {}, "invalid", tuple(limitations)
    if abs(total - 100.0) > TARGET_WEIGHT_SUM_TOLERANCE_PP:
        limitations.append(
            f"Aggregated ticker targets sum to {total:.1f}% (tolerance ±{TARGET_WEIGHT_SUM_TOLERANCE_PP:.0f} pp)."
        )
        return by_class, "limited", tuple(limitations)
    return by_class, "explicit", tuple(limitations)


def _objective_targets_from_health(health_objective: str) -> dict[str, float]:
    from portfolio_core import OBJECTIVE_ALLOCATIONS

    key = str(health_objective or "").strip().lower()
    mix = OBJECTIVE_ALLOCATIONS.get(key, OBJECTIVE_ALLOCATIONS["balanced growth"])
    return {
        "Equity": float(mix["equity"]) * 100.0,
        "Bonds": float(mix["bonds"]) * 100.0,
        "Cash_and_TBills": float(mix["tbills"]) * 100.0,
    }


def _resolve_target(
    snapshot: RealPortfolioSnapshot,
    *,
    user_asset_class_targets: dict[str, float] | None,
    saved_objective_target: dict[str, float] | None,
    health_objective: str | None,
) -> tuple[TargetSource, dict[str, float], TargetQuality, tuple[str, ...]]:
    limitations: list[str] = []

    if user_asset_class_targets:
        norm = _normalize_target_keys(user_asset_class_targets)
        keys = set(norm.keys())
        if keys <= LEDGER_ASSET_CLASSES and _target_sum_ok(norm):
            return "user_defined_target", norm, "explicit", tuple(limitations)
        if keys <= OBJECTIVE_BUCKETS and _target_sum_ok(norm):
            return "user_defined_target", norm, "explicit", tuple(limitations)
        limitations.append("User-defined target failed validation (keys or weight sum).")

    if saved_objective_target:
        norm = _normalize_target_keys(saved_objective_target)
        if set(norm.keys()) <= OBJECTIVE_BUCKETS and _target_sum_ok(norm):
            return "saved_objective_target", norm, "sufficient", tuple(limitations)

    if snapshot.target_allocation:
        raw = _normalize_target_keys(snapshot.target_allocation)
        keys = set(raw.keys())
        if keys <= LEDGER_ASSET_CLASSES and _target_sum_ok(raw):
            return "user_defined_target", raw, "explicit", tuple(limitations)
        if keys <= OBJECTIVE_BUCKETS and _target_sum_ok(raw):
            return "user_defined_target", raw, "explicit", tuple(limitations)
        agg, quality, lims = _aggregate_ticker_targets(snapshot, raw)
        limitations.extend(lims)
        if agg and quality in ("explicit", "limited"):
            src: TargetSource = "user_defined_target"
            return src, agg, quality, tuple(limitations)

    if health_objective:
        obj = _objective_targets_from_health(health_objective)
        limitations.append(
            "Target derived from Portfolio Health objective mapping (OBJECTIVE_ALLOCATIONS); "
            "ledger Other weight is treated as Bonds for comparison."
        )
        return "inferred_risk_profile_target", obj, "sufficient", tuple(limitations)

    if snapshot.risk_tolerance:
        obj = _objective_targets_from_health(snapshot.risk_tolerance)
        limitations.append(
            "Target inferred from plan risk label using the same objective mapping as Portfolio Health."
        )
        return "inferred_risk_profile_target", obj, "limited", tuple(limitations)

    return "unavailable", {}, "invalid", tuple(limitations)


def _align_current_to_target_space(
    target: dict[str, float],
    snapshot: RealPortfolioSnapshot,
) -> dict[str, float]:
    keys = set(target.keys())
    if keys <= OBJECTIVE_BUCKETS:
        return _current_objective_allocation(snapshot)
    return _current_ledger_allocation(snapshot)


def _compute_drift(
    current: dict[str, float],
    target: dict[str, float],
) -> tuple[dict[str, float], dict[str, float], tuple[DriftObservation, ...]]:
    classes = sorted(set(current.keys()) | set(target.keys()))
    drift: dict[str, float] = {}
    abs_drift: dict[str, float] = {}
    observations: list[DriftObservation] = []
    for cls in classes:
        cur = float(current.get(cls, 0.0))
        tgt = float(target.get(cls, 0.0))
        d = cur - tgt
        drift[cls] = d
        abs_drift[cls] = abs(d)
        observations.append(
            DriftObservation(
                code="asset_class_drift",
                asset_class=cls,
                current_weight=cur,
                target_weight=tgt,
                drift_percentage_points=d,
                severity=_severity(abs(d)),
                evidence={"overweight": d > 0, "underweight": d < 0},
            )
        )
    return drift, abs_drift, tuple(observations)


def _pick_extreme(
    observations: tuple[DriftObservation, ...],
    *,
    overweight: bool,
) -> DriftObservation | None:
    candidates = [
        o
        for o in observations
        if o.severity != "immaterial" and ((o.drift_percentage_points > 0) if overweight else (o.drift_percentage_points < 0))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda o: abs(o.drift_percentage_points))


def _rebalance_triggered(
    observations: tuple[DriftObservation, ...],
    *,
    target_quality: TargetQuality,
    pricing_ok: bool,
) -> bool:
    if target_quality not in ("explicit", "sufficient"):
        return False
    if not pricing_ok:
        return False
    material = [o for o in observations if o.severity in ("material", "substantial")]
    if material:
        return True
    modest = [o for o in observations if o.severity == "modest"]
    if len(modest) >= COMBINED_MODEST_DRIFT_COUNT:
        if sum(abs(o.drift_percentage_points) for o in modest) >= COMBINED_MODEST_DRIFT_SUM_PP:
            return True
    return False


def analyze_real_portfolio_drift(
    snapshot: RealPortfolioSnapshot,
    *,
    user_asset_class_targets: dict[str, float] | None = None,
    saved_objective_target: dict[str, float] | None = None,
    health_objective: str | None = None,
) -> RealPortfolioDriftAnalysis:
    """Pure drift analysis from snapshot marks and validated targets only."""
    flags = list(snapshot.data_quality_flags)
    limitations: list[str] = []

    if snapshot.unpriced_holdings_count > 0:
        if "missing_prices" not in flags:
            flags.append("missing_prices")
        if "partial_market_value" not in flags:
            flags.append("partial_market_value")

    pricing_ok = snapshot.unpriced_holdings_count == 0 and snapshot.market_data_status != "unavailable"

    source, target, quality, resolve_lims = _resolve_target(
        snapshot,
        user_asset_class_targets=user_asset_class_targets,
        saved_objective_target=saved_objective_target,
        health_objective=health_objective,
    )
    limitations.extend(resolve_lims)

    if source == "unavailable" or not target:
        return RealPortfolioDriftAnalysis(
            target_source="unavailable",
            target_allocation={},
            current_allocation=_current_ledger_allocation(snapshot),
            drift_by_asset_class={},
            absolute_drift_by_asset_class={},
            largest_overweight=None,
            largest_underweight=None,
            total_absolute_drift=0.0,
            drift_status="target_unavailable",
            rebalance_triggered=False,
            target_quality="invalid",
            observations=(),
            data_quality_flags=tuple(dict.fromkeys(flags)),
            limitations=tuple(limitations),
        )

    current = _align_current_to_target_space(target, snapshot)
    if set(target.keys()) != set(current.keys()):
        limitations.append("Target and current allocation buckets could not be aligned reliably.")
        quality = "limited"

    drift, abs_drift, observations = _compute_drift(current, target)
    total_abs = sum(abs_drift.values())

    largest_over = _pick_extreme(observations, overweight=True)
    largest_under = _pick_extreme(observations, overweight=False)

    status: DriftStatus
    if not pricing_ok:
        status = "partial_data"
    elif quality == "invalid":
        status = "invalid_target"
    elif any(o.severity in ("material", "substantial") for o in observations):
        status = "material_drift"
    elif any(o.severity == "modest" for o in observations):
        status = "modest_drift"
    elif total_abs < DRIFT_IMMATERIAL_PP:
        status = "aligned"
    else:
        status = "immaterial_drift"

    triggered = _rebalance_triggered(observations, target_quality=quality, pricing_ok=pricing_ok)

    return RealPortfolioDriftAnalysis(
        target_source=source,
        target_allocation=dict(target),
        current_allocation=dict(current),
        drift_by_asset_class=drift,
        absolute_drift_by_asset_class=abs_drift,
        largest_overweight=largest_over,
        largest_underweight=largest_under,
        total_absolute_drift=round(total_abs, 4),
        drift_status=status,
        rebalance_triggered=triggered,
        target_quality=quality,
        observations=observations,
        data_quality_flags=tuple(dict.fromkeys(flags)),
        limitations=tuple(limitations),
    )
