"""Contribution Advisor — real-portfolio gates + target resolution over the pure engine.

Ownership
---------
- Pure math: ``contribution_allocation_engine.allocate_contribution_new_money_only``
- This module: require a real ledger snapshot, explicit target source, and usable
  market data before calling the engine.

Does **not** silently use DEFAULT_HOLDINGS, demo portfolios, optimizer weights,
or model ``holdings_df`` as the user's personal target.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from investment_ami.decision_support.contribution_allocation_engine import (
    ContributionAllocationResult,
    allocate_contribution_new_money_only,
)
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_recommendation_rules import (
    STALE_QUOTE_AGE_SECONDS,
)

TargetSourceChoice = Literal[
    "user_explicit",
    "stated_objective_recommended",
    "current_mix",
]

STATUS_NO_REAL_PORTFOLIO = "no_real_portfolio"
STATUS_TARGET_NOT_DEFINED = "target_not_defined"
STATUS_MISSING_PRICES = "missing_or_incomplete_prices"
STATUS_STALE_PRICES = "stale_prices"
STATUS_BLOCKED = "blocked"


def _blocked(
    status: str,
    *,
    contribution: float,
    explanation: str,
    target_source: str = "",
    warnings: tuple[str, ...] = (),
    assumptions: tuple[str, ...] = (),
) -> ContributionAllocationResult:
    return ContributionAllocationResult(
        ok=False,
        status=status,
        mode="new_money_only",
        contribution_amount=float(contribution or 0.0),
        portfolio_value_before=0.0,
        portfolio_value_after=0.0,
        aggregate_drift_before=0.0,
        aggregate_drift_after=0.0,
        explanation=explanation,
        assumptions=assumptions
        or (
            "Real Portfolio ledger is authoritative for holdings and market values.",
            "Decision support only — not a trade order.",
        ),
        reason_codes=(status,),
        target_source=target_source,
        warnings=warnings,
    )


def _holding_values_from_snapshot(
    snapshot: RealPortfolioSnapshot,
    *,
    include_cash: bool = True,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for h in snapshot.holdings:
        sym = str(h.ticker or "").strip().upper()
        if not sym or sym in ("$CASH", "CASH"):
            continue
        # Skip unpriced names from the investable set (value is 0 by snapshot policy).
        if h.current_price is None or "missing_price" in (h.data_quality_flags or ()):
            continue
        values[sym] = values.get(sym, 0.0) + float(h.current_value or 0.0)
    if include_cash and float(snapshot.cash or 0.0) > 0:
        values["$CASH"] = float(snapshot.cash)
    return values


def _current_mix_targets(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in values.items()}


def _objective_bucket_targets(health_objective: str | None) -> dict[str, float]:
    from portfolio_core import OBJECTIVE_ALLOCATIONS

    key = str(health_objective or "").strip().lower() or "balanced growth"
    mix = OBJECTIVE_ALLOCATIONS.get(key, OBJECTIVE_ALLOCATIONS["balanced growth"])
    return {
        "Equity": float(mix["equity"]),
        "Bonds": float(mix["bonds"]),
        "Cash_and_TBills": float(mix["tbills"]),
    }


def _holding_class(snapshot: RealPortfolioSnapshot, ticker: str) -> str:
    sym = str(ticker or "").strip().upper()
    if sym in ("$CASH", "CASH"):
        return "Cash"
    for h in snapshot.holdings:
        if str(h.ticker).strip().upper() == sym:
            return str(h.asset_class or "Other")
    return "Other"


def _objective_class(ledger_class: str) -> str:
    if ledger_class in ("Stocks", "ETFs"):
        return "Equity"
    if ledger_class == "Bonds":
        return "Bonds"
    if ledger_class == "Cash":
        return "Cash_and_TBills"
    return "Other"


def holding_targets_from_stated_objective(
    snapshot: RealPortfolioSnapshot,
    values: dict[str, float],
    health_objective: str | None,
) -> tuple[dict[str, float], tuple[str, ...]]:
    """
    Map OBJECTIVE_ALLOCATIONS → holding weights by pro-rating within economic sleeves.

    Labeled as **recommended / stated-objective**, not a user-saved personal target.
    """
    limitations: list[str] = []
    buckets = _objective_bucket_targets(health_objective)
    by_obj: dict[str, list[str]] = {"Equity": [], "Bonds": [], "Cash_and_TBills": [], "Other": []}
    for sym in values:
        oc = _objective_class(_holding_class(snapshot, sym))
        by_obj.setdefault(oc, []).append(sym)

    targets: dict[str, float] = {sym: 0.0 for sym in values}
    for bucket, bt in buckets.items():
        members = by_obj.get(bucket) or []
        if not members:
            if bt > 1e-9:
                limitations.append(
                    f"Stated-objective sleeve '{bucket}' ({bt * 100:.0f}%) has no priced ledger holdings to receive it."
                )
            continue
        sleeve_value = sum(values[m] for m in members)
        if sleeve_value <= 0:
            # Equal split if all zero within sleeve (shouldn't happen for priced).
            share = bt / len(members)
            for m in members:
                targets[m] += share
        else:
            for m in members:
                targets[m] += bt * (values[m] / sleeve_value)

    # If Other holdings exist with value, keep them at current mix share so weights remain coherent.
    other_members = by_obj.get("Other") or []
    other_value = sum(values[m] for m in other_members)
    total_v = sum(values.values())
    if other_members and total_v > 0 and other_value > 0:
        other_share = other_value / total_v
        # Scale objective sleeves into (1 - other_share) then add other at current mix.
        scale = max(0.0, 1.0 - other_share)
        for m in targets:
            if m in other_members:
                targets[m] = values[m] / total_v
            else:
                targets[m] *= scale
        limitations.append(
            "Other-classified holdings keep their current weight share; objective sleeves are scaled into the remainder."
        )

    s = sum(targets.values())
    if s <= 0:
        return {}, tuple(limitations + ["Could not derive holding targets from stated objective."])
    targets = {k: v / s for k, v in targets.items()}
    return targets, tuple(limitations)


def assess_market_data_for_contribution(
    snapshot: RealPortfolioSnapshot,
) -> tuple[str | None, tuple[str, ...]]:
    """
    Return (blocking_status_or_None, warnings).

    Missing/incomplete prices block precise recommendations.
    Stale cached quotes block by default (caller may surface warning-only later).
    """
    from investment_ami.decision_support.real_portfolio_snapshot import unpriced_holding_tickers

    warnings: list[str] = []
    missing = unpriced_holding_tickers(snapshot)
    if missing or snapshot.unpriced_holdings_count > 0 or snapshot.market_data_status in ("partial", "unavailable"):
        named = ", ".join(missing) if missing else "one or more holdings"
        return (
            STATUS_MISSING_PRICES,
            (
                f"Missing current market prices for: {named}. "
                "The Real Portfolio Dashboard may still show a cost-basis estimate for these names, "
                "but Contribution Advisor will not invent a tradeable mark. "
                "Refresh market data (or fix non-quotable tickers such as CASH / US TREASURY) "
                "before treating this as a precise new-money recommendation.",
            ),
        )
    age = snapshot.market_data_age_seconds
    status = str(snapshot.market_data_status or "")
    if status == "cached" and age is not None and age > STALE_QUOTE_AGE_SECONDS:
        return (
            STATUS_STALE_PRICES,
            (
                f"Market quotes look stale (age ≈ {int(age)}s). "
                "Refresh market data before treating this as a current trading recommendation.",
            ),
        )
    if status == "cached":
        warnings.append("Using cached market quotes — refresh if you need the latest marks.")
    return None, tuple(warnings)


def resolve_contribution_targets(
    *,
    snapshot: RealPortfolioSnapshot,
    values: dict[str, float],
    target_source: TargetSourceChoice,
    explicit_holding_targets: Mapping[str, float] | None,
    health_objective: str | None,
) -> tuple[dict[str, float] | None, str, tuple[str, ...], str | None]:
    """
    Returns (targets, label, limitations, block_status).

    ``user_explicit`` requires ``explicit_holding_targets`` — never invents them.
    """
    if target_source == "user_explicit":
        if not explicit_holding_targets:
            return (
                None,
                "user_explicit",
                (),
                STATUS_TARGET_NOT_DEFINED,
            )
        return dict(explicit_holding_targets), "user_explicit", (), None

    if target_source == "current_mix":
        targets = _current_mix_targets(values)
        if not targets:
            return None, "current_mix", (), STATUS_TARGET_NOT_DEFINED
        return (
            targets,
            "current_mix",
            ("Target is the portfolio's current mix (treat as already on-strategy).",),
            None,
        )

    if target_source == "stated_objective_recommended":
        obj = health_objective or snapshot.health_objective
        if not str(obj or "").strip():
            return (
                None,
                "stated_objective_recommended",
                (),
                STATUS_TARGET_NOT_DEFINED,
            )
        targets, limitations = holding_targets_from_stated_objective(snapshot, values, obj)
        if not targets:
            return None, "stated_objective_recommended", limitations, STATUS_TARGET_NOT_DEFINED
        note = (
            f"Target derived from stated objective '{obj}' (recommended / inferred sleeve mix "
            "pro-rated onto priced ledger holdings — not a user-saved personal target)."
        )
        return targets, "stated_objective_recommended", (note,) + tuple(limitations), None

    return None, str(target_source), (), STATUS_TARGET_NOT_DEFINED


def recommend_contribution_allocation(
    *,
    snapshot: RealPortfolioSnapshot | None,
    contribution_amount: float,
    target_source: TargetSourceChoice = "user_explicit",
    explicit_holding_targets: Mapping[str, float] | None = None,
    health_objective: str | None = None,
    include_cash: bool = True,
    failure_code: str | None = None,
) -> ContributionAllocationResult:
    """
    Gate real-portfolio contribution placement, then run the pure new-money engine.

    Parameters
    ----------
    snapshot:
        Ledger-backed snapshot from ``build_real_portfolio_snapshot``. ``None`` /
        no-ledger failures must be passed explicitly (do not substitute demo data).
    failure_code:
        Optional snapshot build failure code (e.g. ``no_real_ledger``).
    target_source:
        ``user_explicit`` | ``stated_objective_recommended`` | ``current_mix``.
    """
    c = float(contribution_amount or 0.0)

    if snapshot is None or failure_code == "no_real_ledger":
        return _blocked(
            STATUS_NO_REAL_PORTFOLIO,
            contribution=c,
            explanation=(
                "No real portfolio ledger is available. Record transactions in Real Portfolio "
                "before asking where new money should go. Demo or default model holdings are "
                "not used for real-money recommendations."
            ),
        )

    block, md_warnings = assess_market_data_for_contribution(snapshot)
    if block:
        return _blocked(
            block,
            contribution=c,
            explanation=md_warnings[0] if md_warnings else "Market data is insufficient for a precise recommendation.",
            warnings=md_warnings,
            target_source=target_source,
        )

    values = _holding_values_from_snapshot(snapshot, include_cash=include_cash)
    if not values:
        return _blocked(
            STATUS_NO_REAL_PORTFOLIO,
            contribution=c,
            explanation="The real portfolio has no priced holdings (and no cash) to allocate toward.",
            target_source=target_source,
            warnings=md_warnings,
        )

    targets, source_label, limitations, target_block = resolve_contribution_targets(
        snapshot=snapshot,
        values=values,
        target_source=target_source,
        explicit_holding_targets=explicit_holding_targets,
        health_objective=health_objective,
    )
    if target_block or targets is None:
        return _blocked(
            STATUS_TARGET_NOT_DEFINED,
            contribution=c,
            explanation=(
                "Select a legitimate target source before allocating new money. "
                "Options: your explicit holding targets, the stated-objective recommended mix "
                "(clearly labeled, not a saved personal target), or the current mix. "
                "Portfolio Health / optimizer weights are not silently applied."
            ),
            target_source=target_source,
            warnings=md_warnings + tuple(limitations),
        )

    assumptions = (
        "New-money-only mode: adds contribution dollars; does not sell overweight holdings.",
        "Real transaction ledger + current marks are authoritative for holdings and values.",
        "Deposits increase contributed capital / assets — they are not investment profit.",
        "Decision support only — not a brokerage order.",
    ) + tuple(limitations)

    return allocate_contribution_new_money_only(
        current_values=values,
        target_weights=targets,
        contribution=c,
        target_source=source_label,
        assumptions=assumptions,
        warnings=md_warnings,
    )


def recommend_contribution_allocation_from_session(
    session_state: Any,
    *,
    contribution_amount: float,
    target_source: TargetSourceChoice = "user_explicit",
    explicit_holding_targets: Mapping[str, float] | None = None,
    include_cash: bool = True,
) -> ContributionAllocationResult:
    """Build snapshot from session and run the advisor (UI / AMI entry)."""
    from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot

    result = build_real_portfolio_snapshot(session_state)
    health_objective = None
    try:
        health_objective = session_state.get("health_objective")  # type: ignore[union-attr]
    except Exception:
        health_objective = None
    if result.snapshot is None:
        code = result.failure.code if result.failure else "no_real_ledger"
        return recommend_contribution_allocation(
            snapshot=None,
            contribution_amount=contribution_amount,
            target_source=target_source,
            explicit_holding_targets=explicit_holding_targets,
            health_objective=str(health_objective or "") or None,
            include_cash=include_cash,
            failure_code=str(code),
        )
    return recommend_contribution_allocation(
        snapshot=result.snapshot,
        contribution_amount=contribution_amount,
        target_source=target_source,
        explicit_holding_targets=explicit_holding_targets,
        health_objective=str(health_objective or result.snapshot.health_objective or "") or None,
        include_cash=include_cash,
    )
