"""Pure contribution-allocation engine (new-money-only mode).

Deterministic, session-free math: given current market values, explicit target
weights, and a contribution amount, allocate dollars to holdings without sales.

Does not fetch prices, read DEFAULT_HOLDINGS, or mutate ledgers.

Core rule
---------
Solve against the **post-contribution** portfolio value ``V' = V + C``:

    need_i = target_weight_i * V' - current_value_i

When every ``need_i >= 0``, ``sum(need_i) == C`` and allocating ``need_i`` reaches
target exactly. Pre-contribution weight underweights must **not** gate which
names may receive dollars — a name that is slightly overweight today can still
need a positive buy to stay on-target after the pie expands.
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
REASON_REACH_TARGET = "reach_post_contribution_target"

WEIGHT_SUM_TOLERANCE = 0.02  # fraction (±2 pp)
DOLLAR_SUM_TOLERANCE = 0.02  # cents-level for float noise
BALANCED_DRIFT_TOLERANCE = 0.005  # |w - t| < 0.5 pp → treat as balanced for narrative
NEED_EPS = 1e-9  # treat tiny negative needs as zero (float noise)


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


def _round_cents(amount: float) -> float:
    return round(float(amount) + 0.0, 2)


def _allocate_cents(raw: dict[str, float], total: float, tickers: list[str]) -> dict[str, float]:
    """
    Deterministic cent rounding so allocations sum exactly to ``total`` (2 dp).

    Largest-remainder method on the fractional cents, tie-broken by ticker.
    """
    total_cents = int(round(_round_cents(total) * 100))
    if total_cents <= 0 or not tickers:
        return {t: 0.0 for t in tickers}

    raw_sum = sum(max(0.0, float(raw.get(t, 0.0))) for t in tickers)
    if raw_sum <= NEED_EPS:
        # Degenerate: dump into first ticker by sort order.
        out = {t: 0.0 for t in tickers}
        out[tickers[0]] = total_cents / 100.0
        return out

    scaled = {t: max(0.0, float(raw.get(t, 0.0))) / raw_sum * total_cents for t in tickers}
    floors = {t: int(scaled[t]) for t in tickers}
    assigned = sum(floors.values())
    remainder = total_cents - assigned
    fracs = sorted(
        ((scaled[t] - floors[t], t) for t in tickers),
        key=lambda x: (-x[0], x[1]),
    )
    for i in range(max(0, remainder)):
        floors[fracs[i % len(fracs)][1]] += 1
    return {t: floors[t] / 100.0 for t in tickers}


def _build_explanation(
    rows: list[HoldingContributionRow],
    *,
    contribution: float,
    already_balanced: bool,
    reached_target: bool,
    infeasible_without_sales: bool,
) -> str:
    if contribution <= 0:
        return "Enter a positive contribution amount to see a new-money allocation."
    adds = sorted(rows, key=lambda r: -r.recommended_add)
    top = [r for r in adds if r.recommended_add > 0.005]
    if reached_target:
        bits = ", ".join(f"{r.ticker} (${r.recommended_add:,.2f})" for r in top[:4]) or "target weights"
        return (
            f"This ${contribution:,.0f} is enough to bring every holding to your selected "
            f"target on the post-contribution portfolio ({bits}). "
            "No sales are required."
        )
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
    if infeasible_without_sales:
        under_bits = ", ".join(
            f"{r.ticker} (+${r.recommended_add:,.0f})"
            for r in top[:3]
        )
        return (
            f"This ${contribution:,.0f} is allocated to holdings that still need buys to "
            f"approach your post-contribution targets"
            + (f" ({under_bits})" if under_bits else f" (led by {primary.ticker})")
            + ". Some holdings are already above their target share of the larger portfolio, "
            "so new-money-only mode cannot remove all drift without sales. "
            "Those overweight names receive $0."
        )
    if primary.reason_code == REASON_FILL_UNDERWEIGHT or primary.drift < -BALANCED_DRIFT_TOLERANCE:
        return (
            f"Most of this ${contribution:,.0f} is directed toward **{primary.ticker}** "
            f"(${primary.recommended_add:,.0f}) because it needs the most new money to reach "
            f"its target share of the post-contribution portfolio. "
            "Holdings already above that post-contribution target receive $0. "
            "No sales are recommended in this mode."
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
    1. Let ``V = sum(current_values)``, ``V' = V + C``.
    2. ``need_i = target_weight_i * V' - current_value_i`` (post-contribution dollar gap).
    3. If every ``need_i >= 0``: allocate exactly ``need_i`` (reaches target; sum equals C).
    4. If some ``need_i < 0``: those names are already above target dollars after the
       contribution — they get $0. Distribute C across positive-need names in proportion
       to ``need_i`` (best feasible buy-only allocation; remaining drift is unavoidable).
    5. Already-at-target portfolios yield ``need_i = t_i * C`` (pro-rata by target).
    6. Cent-round so recommended adds sum to C.
    """
    base_assumptions = list(
        assumptions
        or (
            "New-money-only mode: recommendations add cash to holdings; they do not sell.",
            "Allocations are solved against post-contribution portfolio value (V + contribution).",
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
    c = _round_cents(c)

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
            explanation=_build_explanation(
                rows,
                contribution=0.0,
                already_balanced=already_balanced,
                reached_target=False,
                infeasible_without_sales=False,
            ),
            assumptions=tuple(base_assumptions),
            reason_codes=(REASON_NO_ALLOCATION,),
            target_source=target_source,
            warnings=tuple(warn),
        )

    v_after = v_total + c
    # Post-contribution dollar targets — the only gap that matters for buys.
    need = {t: targets[t] * v_after - values[t] for t in tickers}
    # Clamp microscopic float noise so "exact reach" is recognized.
    need = {t: (0.0 if abs(need[t]) <= NEED_EPS else need[t]) for t in tickers}

    positive_need = {t: max(0.0, need[t]) for t in tickers}
    total_positive = sum(positive_need.values())
    min_need = min(need.values()) if need else 0.0
    # Exact reachability: no name is already above its post-contribution target dollar.
    exact_reach = min_need >= -NEED_EPS and abs(total_positive - c) <= max(0.02, 1e-6 * max(c, 1.0))
    infeasible_without_sales = min_need < -NEED_EPS

    raw_adds: dict[str, float] = {t: 0.0 for t in tickers}
    reason = {t: REASON_OVERWEIGHT_SKIP for t in tickers}
    reached_target = False

    if exact_reach:
        reached_target = True
        for t in tickers:
            raw_adds[t] = positive_need[t]
            if positive_need[t] > NEED_EPS:
                reason[t] = (
                    REASON_ALREADY_AT_TARGET
                    if already_balanced
                    else REASON_REACH_TARGET
                )
            else:
                reason[t] = REASON_ALREADY_AT_TARGET if already_balanced else REASON_OVERWEIGHT_SKIP
    elif total_positive <= NEED_EPS:
        # No positive post-contribution gaps (degenerate / all zero targets) — fall back.
        for t in tickers:
            raw_adds[t] = c * targets[t]
            reason[t] = REASON_ALREADY_AT_TARGET if already_balanced else REASON_PRO_RATA_TARGET
        reached_target = already_balanced
    else:
        # Best feasible buy-only: give all new money to names with positive post-C need.
        for t in tickers:
            if positive_need[t] > NEED_EPS:
                raw_adds[t] = c * (positive_need[t] / total_positive)
                reason[t] = REASON_FILL_UNDERWEIGHT
            else:
                raw_adds[t] = 0.0
                reason[t] = REASON_OVERWEIGHT_SKIP

    adds = _allocate_cents(raw_adds, c, tickers)
    for t in tickers:
        if adds[t] <= 0 and reason[t] not in (REASON_OVERWEIGHT_SKIP, REASON_ALREADY_AT_TARGET):
            reason[t] = REASON_OVERWEIGHT_SKIP
        if abs(adds[t] - raw_adds[t]) >= 0.005 and adds[t] > 0:
            # Cent residual applied; keep semantic reason unless it was a pure skip.
            if reason[t] == REASON_OVERWEIGHT_SKIP:
                reason[t] = REASON_ROUNDING

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
                recommended_add=adds[t],
                projected_value=round(proj_v, 6),
                projected_weight=proj_w,
                remaining_drift=proj_w - targets[t],
                reason_code=reason[t],
            )
        )

    agg_after = _aggregate_abs_drift(projected_w, targets)
    # After cent rounding, treat near-zero remaining drift as reached.
    if exact_reach and agg_after <= 2e-4:
        reached_target = True
    codes = tuple(dict.fromkeys(r.reason_code for r in rows if r.recommended_add > 0.005))
    explanation = _build_explanation(
        rows,
        contribution=c,
        already_balanced=already_balanced,
        reached_target=reached_target,
        infeasible_without_sales=infeasible_without_sales,
    )

    return ContributionAllocationResult(
        ok=True,
        status=STATUS_OK,
        mode="new_money_only",
        contribution_amount=c,
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
            "exact_reach": exact_reach,
            "reached_target": reached_target,
            "infeasible_without_sales": infeasible_without_sales,
            "already_balanced": already_balanced,
            "total_positive_need": total_positive,
            # Backward-compatible key (old fill-then-prorata path removed).
            "filled_then_prorata": False,
        },
    )
