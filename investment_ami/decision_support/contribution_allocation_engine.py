"""Pure contribution-allocation engine (new-money-only mode).

Deterministic, session-free math: given current market values, explicit target
weights, and a contribution amount, allocate dollars to holdings without sales.

Does not fetch prices, read DEFAULT_HOLDINGS, or mutate ledgers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ContributionMode = Literal["new_money_only"]

# Status codes for callers / UI / AMI.
STATUS_OK = "ok"
STATUS_ZERO_CONTRIBUTION = "zero_contribution"
STATUS_NO_HOLDINGS = "no_holdings"
STATUS_INVALID_TARGETS = "invalid_targets"
STATUS_EMPTY_PORTFOLIO = "empty_portfolio"

REASON_FILL_UNDERWEIGHT = "fill_underweight"
REASON_PRO_RATA_TARGET = "pro_rata_target"
REASON_ALREADY_AT_TARGET = "already_at_target"
REASON_OVERWEIGHT_SKIP = "overweight_skip_new_money"
REASON_NO_ALLOCATION = "no_allocation"
REASON_ROUNDING = "rounding_residual"

WEIGHT_SUM_TOLERANCE = 0.02  # fraction (±2 pp)
DOLLAR_SUM_TOLERANCE = 0.02  # cents-level for float noise
BALANCED_DRIFT_TOLERANCE = 0.005  # |w - t| < 0.5 pp → treat as balanced for narrative


@dataclass(frozen=True)
class HoldingContributionRow:
    ticker: str
    current_value: float
    current_weight: float
    target_weight: float
    drift: float  # current_weight - target_weight (fraction)
    recommended_add: float
    projected_value: float
    projected_weight: float
    remaining_drift: float  # projected_weight - target_weight
    reason_code: str


@dataclass(frozen=True)
class ContributionAllocationResult:
    ok: bool
    status: str
    mode: ContributionMode
    contribution_amount: float
    portfolio_value_before: float
    portfolio_value_after: float
    aggregate_drift_before: float
    aggregate_drift_after: float
    rows: tuple[HoldingContributionRow, ...] = ()
    explanation: str = ""
    assumptions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    target_source: str = ""
    warnings: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "mode": self.mode,
            "contribution_amount": self.contribution_amount,
            "portfolio_value_before": self.portfolio_value_before,
            "portfolio_value_after": self.portfolio_value_after,
            "aggregate_drift_before": self.aggregate_drift_before,
            "aggregate_drift_after": self.aggregate_drift_after,
            "explanation": self.explanation,
            "assumptions": list(self.assumptions),
            "reason_codes": list(self.reason_codes),
            "target_source": self.target_source,
            "warnings": list(self.warnings),
            "rows": [
                {
                    "ticker": r.ticker,
                    "current_value": r.current_value,
                    "current_weight": r.current_weight,
                    "target_weight": r.target_weight,
                    "drift": r.drift,
                    "recommended_add": r.recommended_add,
                    "projected_value": r.projected_value,
                    "projected_weight": r.projected_weight,
                    "remaining_drift": r.remaining_drift,
                    "reason_code": r.reason_code,
                }
                for r in self.rows
            ],
            "meta": dict(self.meta),
        }


def _normalize_target_weights(raw: dict[str, float]) -> dict[str, float] | None:
    cleaned: dict[str, float] = {}
    for k, v in raw.items():
        sym = str(k or "").strip().upper()
        if not sym:
            continue
        try:
            w = float(v)
        except (TypeError, ValueError):
            continue
        if w < 0:
            return None
        # Accept percent points (e.g. 50) or fractions (0.50).
        if w > 1.0 + 1e-9:
            w = w / 100.0
        cleaned[sym] = cleaned.get(sym, 0.0) + w
    total = sum(cleaned.values())
    if total <= 0:
        return None
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        # Soft-normalize if close enough to be user percent entry noise.
        if abs(total - 1.0) <= 0.15:
            return {k: v / total for k, v in cleaned.items()}
        return None
    return {k: v / total for k, v in cleaned.items()}


def _aggregate_abs_drift(weights: dict[str, float], targets: dict[str, float]) -> float:
    keys = set(weights) | set(targets)
    return sum(abs(weights.get(k, 0.0) - targets.get(k, 0.0)) for k in keys)


def _build_explanation(
    rows: list[HoldingContributionRow],
    *,
    contribution: float,
    already_balanced: bool,
    filled_then_prorata: bool,
) -> str:
    if contribution <= 0:
        return "Enter a positive contribution amount to see a new-money allocation."
    adds = sorted(rows, key=lambda r: -r.recommended_add)
    top = [r for r in adds if r.recommended_add > 0.005]
    if already_balanced:
        bits = ", ".join(f"{r.ticker} (${r.recommended_add:,.0f})" for r in top[:4]) or "target weights"
        return (
            f"Your portfolio is already close to the selected target, so this "
            f"${contribution:,.0f} is distributed approximately by target weights"
            + (f" ({bits})." if bits else ".")
            + " No sales are required."
        )
    if not top:
        return (
            f"No new-money allocation was computed for ${contribution:,.0f}. "
            "Check holdings, targets, and data quality."
        )
    primary = top[0]
    under_bits = ", ".join(
        f"{r.ticker} (underweight by {abs(r.drift) * 100:.1f} pp → ${r.recommended_add:,.0f})"
        for r in top[:3]
        if r.reason_code == REASON_FILL_UNDERWEIGHT or r.drift < -BALANCED_DRIFT_TOLERANCE
    )
    if filled_then_prorata:
        return (
            f"Most of this ${contribution:,.0f} first corrects underweight positions"
            + (f" ({under_bits})" if under_bits else f" (led by {primary.ticker})")
            + ". After those deficits are filled, the remaining dollars follow the "
            "target weights so the contribution does not create a new distortion. "
            "Overweight holdings are not sold in new-money-only mode."
        )
    if primary.reason_code == REASON_FILL_UNDERWEIGHT or primary.drift < -BALANCED_DRIFT_TOLERANCE:
        return (
            f"Most of this ${contribution:,.0f} is directed toward **{primary.ticker}** "
            f"(${primary.recommended_add:,.0f}) because it is the most underweight relative "
            f"to your selected target"
            + (f" ({under_bits})." if under_bits and primary.ticker not in under_bits else ".")
            + " Existing overweight holdings receive $0 new money while underweights can "
            "absorb the contribution. No sales are recommended in this mode."
        )
    return (
        f"This ${contribution:,.0f} is allocated according to your selected target "
        f"(led by {primary.ticker} at ${primary.recommended_add:,.0f}). "
        "New-money-only mode does not sell existing holdings."
    )


def allocate_contribution_new_money_only(
    *,
    current_values: dict[str, float],
    target_weights: dict[str, float],
    contribution: float,
    target_source: str = "explicit",
    assumptions: tuple[str, ...] | None = None,
    warnings: tuple[str, ...] | None = None,
) -> ContributionAllocationResult:
    """
    Allocate ``contribution`` dollars using new money only (no sales).

    Algorithm
    ---------
    1. Let V = sum(current_values), V' = V + C, target dollars T_i = t_i * V'.
    2. Underweight set U = {i : current_weight_i < target_weight_i}.
    3. For i in U, need_i = max(0, T_i - v_i); overweight / at-target get need 0.
    4. If sum(need) >= C: allocate C proportional to needs (overweights stay at $0).
    5. Else: fill all needs, then allocate remainder R proportional to t_i (large-C case).
    6. If nothing is underweight, distribute C by target weights (already-balanced case).
    """
    base_assumptions = list(
        assumptions
        or (
            "New-money-only mode: recommendations add cash to holdings; they do not sell.",
            "Decision support only — not a trade order or guaranteed advice.",
        )
    )
    warn = list(warnings or ())

    try:
        c = float(contribution)
    except (TypeError, ValueError):
        c = 0.0
    if c < 0:
        c = 0.0

    values: dict[str, float] = {}
    for k, v in current_values.items():
        sym = str(k or "").strip().upper()
        if not sym:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv < 0:
            fv = 0.0
        values[sym] = values.get(sym, 0.0) + fv

    targets = _normalize_target_weights(target_weights)
    if targets is None:
        return ContributionAllocationResult(
            ok=False,
            status=STATUS_INVALID_TARGETS,
            mode="new_money_only",
            contribution_amount=c,
            portfolio_value_before=sum(values.values()),
            portfolio_value_after=sum(values.values()),
            aggregate_drift_before=0.0,
            aggregate_drift_after=0.0,
            explanation="A valid target allocation is required (weights must be non-negative and sum near 100%).",
            assumptions=tuple(base_assumptions),
            reason_codes=("target_invalid",),
            target_source=target_source,
            warnings=tuple(warn),
        )

    # Universe: current holdings plus any target-only names (0 current value).
    tickers = sorted(set(values) | set(targets))
    if not tickers:
        return ContributionAllocationResult(
            ok=False,
            status=STATUS_NO_HOLDINGS,
            mode="new_money_only",
            contribution_amount=c,
            portfolio_value_before=0.0,
            portfolio_value_after=0.0,
            aggregate_drift_before=0.0,
            aggregate_drift_after=0.0,
            explanation="No holdings available for contribution allocation.",
            assumptions=tuple(base_assumptions),
            reason_codes=("no_holdings",),
            target_source=target_source,
            warnings=tuple(warn),
        )

    for t in tickers:
        values.setdefault(t, 0.0)
        targets.setdefault(t, 0.0)

    v_total = sum(values.values())
    if v_total <= 0 and c <= 0:
        return ContributionAllocationResult(
            ok=False,
            status=STATUS_EMPTY_PORTFOLIO,
            mode="new_money_only",
            contribution_amount=c,
            portfolio_value_before=0.0,
            portfolio_value_after=0.0,
            aggregate_drift_before=0.0,
            aggregate_drift_after=0.0,
            explanation="Portfolio market value is zero; add holdings or a contribution amount.",
            assumptions=tuple(base_assumptions),
            reason_codes=("empty_portfolio",),
            target_source=target_source,
            warnings=tuple(warn),
        )

    current_w = {t: (values[t] / v_total if v_total > 0 else 0.0) for t in tickers}
    drift_before = {t: current_w[t] - targets[t] for t in tickers}
    agg_before = _aggregate_abs_drift(current_w, targets)
    already_balanced = agg_before <= 2 * BALANCED_DRIFT_TOLERANCE * max(1, len(tickers)) / 2

    if c <= 0:
        rows = [
            HoldingContributionRow(
                ticker=t,
                current_value=values[t],
                current_weight=current_w[t],
                target_weight=targets[t],
                drift=drift_before[t],
                recommended_add=0.0,
                projected_value=values[t],
                projected_weight=current_w[t],
                remaining_drift=drift_before[t],
                reason_code=REASON_NO_ALLOCATION,
            )
            for t in tickers
        ]
        return ContributionAllocationResult(
            ok=True,
            status=STATUS_ZERO_CONTRIBUTION,
            mode="new_money_only",
            contribution_amount=0.0,
            portfolio_value_before=v_total,
            portfolio_value_after=v_total,
            aggregate_drift_before=agg_before,
            aggregate_drift_after=agg_before,
            rows=tuple(rows),
            explanation=_build_explanation(rows, contribution=0.0, already_balanced=already_balanced, filled_then_prorata=False),
            assumptions=tuple(base_assumptions),
            reason_codes=(REASON_NO_ALLOCATION,),
            target_source=target_source,
            warnings=tuple(warn),
        )

    v_after = v_total + c
    target_dollars = {t: targets[t] * v_after for t in tickers}
    # Weight-overweight names get $0 while underweights can absorb the contribution.
    # (Dollar gap alone would still give pie-expansion buys to slight overweights.)
    underweight = {t for t in tickers if current_w[t] < targets[t] - 1e-12}
    pos_gaps = {
        t: (max(0.0, target_dollars[t] - values[t]) if t in underweight else 0.0) for t in tickers
    }
    total_pos_gap = sum(pos_gaps.values())

    adds = {t: 0.0 for t in tickers}
    reason = {t: REASON_OVERWEIGHT_SKIP for t in tickers}
    filled_then_prorata = False

    if not underweight or total_pos_gap <= 1e-9:
        # Already at/above target weights — distribute by target.
        for t in tickers:
            adds[t] = c * targets[t]
            reason[t] = REASON_ALREADY_AT_TARGET if already_balanced else REASON_PRO_RATA_TARGET
    elif total_pos_gap >= c - 1e-9:
        for t in tickers:
            if pos_gaps[t] > 0:
                adds[t] = c * (pos_gaps[t] / total_pos_gap)
                reason[t] = REASON_FILL_UNDERWEIGHT
            else:
                adds[t] = 0.0
                reason[t] = REASON_OVERWEIGHT_SKIP
    else:
        filled_then_prorata = True
        for t in tickers:
            if pos_gaps[t] > 0:
                adds[t] = pos_gaps[t]
                reason[t] = REASON_FILL_UNDERWEIGHT
            else:
                adds[t] = 0.0
                reason[t] = REASON_OVERWEIGHT_SKIP
        remainder = c - total_pos_gap
        for t in tickers:
            extra = remainder * targets[t]
            if extra > 0:
                adds[t] += extra
                if reason[t] == REASON_OVERWEIGHT_SKIP and extra > 1e-9:
                    reason[t] = REASON_PRO_RATA_TARGET
                elif reason[t] == REASON_FILL_UNDERWEIGHT and extra > 1e-9:
                    reason[t] = REASON_FILL_UNDERWEIGHT  # keep primary story

    # Fix float drift so adds sum exactly to c (give residual to largest underweight / add).
    add_sum = sum(adds.values())
    residual = c - add_sum
    if abs(residual) > 1e-9 and tickers:
        prefer = sorted(tickers, key=lambda t: (-adds[t], drift_before[t], t))
        sink = prefer[0]
        adds[sink] = max(0.0, adds[sink] + residual)
        if abs(residual) >= 0.005:
            reason[sink] = REASON_ROUNDING if reason[sink] == REASON_OVERWEIGHT_SKIP else reason[sink]

    # Guard: no negatives in new-money-only.
    for t in tickers:
        if adds[t] < 0:
            adds[t] = 0.0

    # Re-normalize tiny float error if needed.
    add_sum = sum(adds.values())
    if add_sum > 0 and abs(add_sum - c) > DOLLAR_SUM_TOLERANCE:
        scale = c / add_sum
        adds = {t: adds[t] * scale for t in tickers}

    rows: list[HoldingContributionRow] = []
    projected_w: dict[str, float] = {}
    for t in tickers:
        proj_v = values[t] + adds[t]
        proj_w = proj_v / v_after if v_after > 0 else 0.0
        projected_w[t] = proj_w
        rows.append(
            HoldingContributionRow(
                ticker=t,
                current_value=round(values[t], 6),
                current_weight=current_w[t],
                target_weight=targets[t],
                drift=drift_before[t],
                recommended_add=round(adds[t], 6),
                projected_value=round(proj_v, 6),
                projected_weight=proj_w,
                remaining_drift=proj_w - targets[t],
                reason_code=reason[t],
            )
        )

    agg_after = _aggregate_abs_drift(projected_w, targets)
    codes = tuple(dict.fromkeys(r.reason_code for r in rows if r.recommended_add > 0.005))
    explanation = _build_explanation(
        rows,
        contribution=c,
        already_balanced=already_balanced,
        filled_then_prorata=filled_then_prorata,
    )

    return ContributionAllocationResult(
        ok=True,
        status=STATUS_OK,
        mode="new_money_only",
        contribution_amount=round(c, 6),
        portfolio_value_before=round(v_total, 6),
        portfolio_value_after=round(v_after, 6),
        aggregate_drift_before=agg_before,
        aggregate_drift_after=agg_after,
        rows=tuple(rows),
        explanation=explanation,
        assumptions=tuple(base_assumptions),
        reason_codes=codes or (REASON_NO_ALLOCATION,),
        target_source=target_source,
        warnings=tuple(warn),
        meta={
            "filled_then_prorata": filled_then_prorata,
            "already_balanced": already_balanced,
            "total_positive_gap": total_pos_gap,
        },
    )
