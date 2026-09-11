"""Contribution Advisor — real-portfolio gates + target resolution over the pure engine.

Ownership
---------
- Pure math: ``contribution_allocation_engine.allocate_contribution_new_money_only``
- This module: require a real ledger snapshot, explicit target source, and usable
  market data before calling the engine.

Does **not** silently use DEFAULT_HOLDINGS, demo portfolios, optimizer weights,
Health/Guided rebalance targets, or model ``holdings_df`` as the user's personal target.

Target sources (isolated)
-------------------------
- ``user_explicit`` — percentages the user typed for Contribution Advisor.
- ``stated_objective_recommended`` — ``OBJECTIVE_ALLOCATIONS`` for the stated
  ``health_objective``, mapped onto existing priced ledger holdings (labeled).
- ``current_strategy`` — durable user-accepted strategy target (not live drift).
  Legacy alias: ``current_mix``.
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

# Session / persistence key for the durable Contribution Advisor strategy target.
STRATEGY_TARGET_WEIGHTS_KEY = "real_portfolio_strategy_target_weights"

TargetSourceChoice = Literal[
    "user_explicit",
    "stated_objective_recommended",
    "current_strategy",
    "current_mix",  # legacy alias → current_strategy
]

STATUS_NO_REAL_PORTFOLIO = "no_real_portfolio"
STATUS_TARGET_NOT_DEFINED = "target_not_defined"
STATUS_MISSING_PRICES = "missing_or_incomplete_prices"
STATUS_STALE_PRICES = "stale_prices"
STATUS_BLOCKED = "blocked"

# Category → ledger asset_class mapping (explicit product assumption).
OBJECTIVE_SLEEVE_MAPPING_ASSUMPTION = (
    "Objective categories map to existing ledger holdings by asset class: "
    "Stocks/ETFs → Equity; Bonds → Bonds; Cash → Cash_and_TBills. "
    "Within a represented sleeve, category weight is pro-rated by current market value. "
    "No new ticker is invented for an unrepresented sleeve."
)


def normalize_target_source(target_source: str) -> str:
    """Map legacy UI/API aliases onto canonical target-source ids."""
    raw = str(target_source or "").strip()
    if raw == "current_mix":
        return "current_strategy"
    return raw


def canonical_stated_objective(health_objective: str | None) -> str | None:
    """Return OBJECTIVE_ALLOCATIONS key if ``health_objective`` is a valid stated objective."""
    from portfolio_core import OBJECTIVE_ALLOCATIONS

    key = str(health_objective or "").strip().lower()
    if not key:
        return None
    if key in OBJECTIVE_ALLOCATIONS:
        return key
    return None


def objective_category_targets(health_objective: str | None) -> dict[str, float] | None:
    """Labeled category mix for a valid stated objective — no silent balanced-growth fallback."""
    from portfolio_core import OBJECTIVE_ALLOCATIONS

    key = canonical_stated_objective(health_objective)
    if key is None:
        return None
    mix = OBJECTIVE_ALLOCATIONS[key]
    return {
        "Equity": float(mix["equity"]),
        "Bonds": float(mix["bonds"]),
        "Cash_and_TBills": float(mix["tbills"]),
    }


def _blocked(
    status: str,
    *,
    contribution: float,
    explanation: str,
    target_source: str = "",
    warnings: tuple[str, ...] = (),
    assumptions: tuple[str, ...] = (),
    meta: dict[str, Any] | None = None,
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
        meta=dict(meta or {}),
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


def weights_from_values_as_percent(values: Mapping[str, float]) -> dict[str, float]:
    """Stable percent map (0–100) from current dollar values — for establishing strategy."""
    cleaned: dict[str, float] = {}
    for k, v in values.items():
        sym = str(k or "").strip().upper()
        if not sym:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv < 0:
            fv = 0.0
        cleaned[sym] = cleaned.get(sym, 0.0) + fv
    total = sum(cleaned.values())
    if total <= 0:
        return {}
    return {k: (v / total) * 100.0 for k, v in cleaned.items()}


def parse_strategy_target_weights(raw: Any) -> dict[str, float] | None:
    """Parse persisted / session strategy target (percent or fraction). Empty → None."""
    if not isinstance(raw, Mapping):
        return None
    out: dict[str, float] = {}
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
        out[sym] = fv
    if not out or sum(out.values()) <= 0:
        return None
    return out


def strategy_targets_from_session(session_state: Any) -> dict[str, float] | None:
    """Load durable strategy target from session (and ledger meta fallback)."""
    if session_state is None:
        return None
    try:
        parsed = parse_strategy_target_weights(session_state.get(STRATEGY_TARGET_WEIGHTS_KEY))
    except Exception:
        parsed = None
    if parsed:
        return parsed
    try:
        meta = session_state.get("real_portfolio_ledger")
    except Exception:
        meta = None
    if isinstance(meta, dict):
        return parse_strategy_target_weights(meta.get("strategy_target_weights"))
    return None


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
    *,
    redistribute_unrepresented: bool = False,
) -> tuple[dict[str, float], tuple[str, ...], dict[str, Any]]:
    """
    Map OBJECTIVE_ALLOCATIONS → holding weights by pro-rating within economic sleeves.

    Labeled as **recommended / stated-objective**, not a user-saved personal target.
    Does **not** invent an objective when the key is missing/invalid.
    Unrepresented sleeves stay explicit; silent renormalization is opt-in only.
    """
    limitations: list[str] = []
    meta: dict[str, Any] = {
        "objective_key": None,
        "category_targets": {},
        "sleeve_membership": {},
        "unrepresented_sleeves": [],
        "mapping_assumption": OBJECTIVE_SLEEVE_MAPPING_ASSUMPTION,
        "redistributed_unrepresented": False,
        "source_kind": "stated_objective_OBJECTIVE_ALLOCATIONS",
    }

    key = canonical_stated_objective(health_objective)
    buckets = objective_category_targets(health_objective)
    if key is None or buckets is None:
        return (
            {},
            ("No valid stated investment objective is available for recommended targets.",),
            meta,
        )

    meta["objective_key"] = key
    meta["category_targets"] = dict(buckets)

    by_obj: dict[str, list[str]] = {"Equity": [], "Bonds": [], "Cash_and_TBills": [], "Other": []}
    for sym in values:
        oc = _objective_class(_holding_class(snapshot, sym))
        by_obj.setdefault(oc, []).append(sym)
    meta["sleeve_membership"] = {k: list(v) for k, v in by_obj.items() if v}

    targets: dict[str, float] = {sym: 0.0 for sym in values}
    unrepresented: list[dict[str, Any]] = []
    for bucket, bt in buckets.items():
        members = by_obj.get(bucket) or []
        if not members:
            if bt > 1e-9:
                unrepresented.append({"sleeve": bucket, "weight": bt})
                limitations.append(
                    f"Stated-objective sleeve '{bucket}' ({bt * 100:.0f}%) has no priced ledger "
                    "holdings to receive it — left explicit (not silently dropped)."
                )
            continue
        sleeve_value = sum(values[m] for m in members)
        if sleeve_value <= 0:
            share = bt / len(members)
            for m in members:
                targets[m] += share
        else:
            for m in members:
                targets[m] += bt * (values[m] / sleeve_value)

    meta["unrepresented_sleeves"] = unrepresented

    # If Other holdings exist with value, keep them at current mix share so weights remain coherent.
    other_members = by_obj.get("Other") or []
    other_value = sum(values[m] for m in other_members)
    total_v = sum(values.values())
    if other_members and total_v > 0 and other_value > 0:
        other_share = other_value / total_v
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
        return {}, tuple(limitations + ["Could not derive holding targets from stated objective."]), meta

    if unrepresented and not redistribute_unrepresented:
        # Keep raw (non-renormalized) sleeve assignment so sum < 1 reflects missing sleeves.
        meta["raw_target_sum"] = s
        return {}, tuple(limitations), meta

    if unrepresented and redistribute_unrepresented:
        targets = {k: v / s for k, v in targets.items()}
        meta["redistributed_unrepresented"] = True
        limitations.append(
            "Unrepresented objective sleeves were **provisionally redistributed** into existing "
            "holdings (user-acknowledged). This is not inventing a new security."
        )
        return targets, tuple(limitations), meta

    # Fully represented (or no residual) — normalize tiny float noise only when sum ≈ 1.
    if abs(s - 1.0) <= 0.02:
        targets = {k: v / s for k, v in targets.items()}
    elif s < 1.0 - 1e-9:
        # Should have been caught by unrepresented path; refuse silent fill.
        return {}, tuple(limitations + ["Objective target weights do not cover 100% of the portfolio."]), meta
    else:
        targets = {k: v / s for k, v in targets.items()}

    return targets, tuple(limitations), meta


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
    target_source: str,
    explicit_holding_targets: Mapping[str, float] | None,
    health_objective: str | None,
    strategy_holding_targets: Mapping[str, float] | None = None,
    redistribute_unrepresented_objective_sleeves: bool = False,
) -> tuple[dict[str, float] | None, str, tuple[str, ...], str | None, dict[str, Any]]:
    """
    Returns (targets, label, limitations, block_status, resolution_meta).

    ``user_explicit`` requires ``explicit_holding_targets`` — never invents them.
    ``current_strategy`` requires a previously saved strategy target — never live drift.
    ``stated_objective_recommended`` requires a valid OBJECTIVE_ALLOCATIONS key.
    """
    source = normalize_target_source(target_source)
    resolution: dict[str, Any] = {"canonical_target_source": source}

    if source == "user_explicit":
        if not explicit_holding_targets:
            return (
                None,
                "user_explicit",
                (),
                STATUS_TARGET_NOT_DEFINED,
                {**resolution, "source_kind": "user_explicit"},
            )
        return (
            dict(explicit_holding_targets),
            "user_explicit",
            (),
            None,
            {**resolution, "source_kind": "user_explicit", "resolved_targets": dict(explicit_holding_targets)},
        )

    if source == "current_strategy":
        parsed = parse_strategy_target_weights(strategy_holding_targets)
        if not parsed:
            return (
                None,
                "current_strategy",
                (
                    "No saved strategy target yet. Establish one explicitly with "
                    "'Use current allocation as strategy target' while on strategy — "
                    "live market weights are not used as a drifting target.",
                ),
                STATUS_TARGET_NOT_DEFINED,
                {**resolution, "source_kind": "saved_strategy_target"},
            )
        note = (
            "Target is the saved **current strategy** allocation (user-accepted). "
            "Live market weights may drift; this strategy target does not auto-update."
        )
        return (
            dict(parsed),
            "current_strategy",
            (note,),
            None,
            {
                **resolution,
                "source_kind": "saved_strategy_target",
                "resolved_targets": dict(parsed),
            },
        )

    if source == "stated_objective_recommended":
        obj = health_objective or snapshot.health_objective
        key = canonical_stated_objective(obj)
        if key is None:
            detail = (
                "Select a stated investment objective (e.g. Balanced Growth) before using "
                "recommended objective targets. Contribution Advisor will not invent an objective, "
                "silently use Portfolio Health / Guided / optimizer weights, or fall back to "
                "DEFAULT_HOLDINGS."
            )
            if str(obj or "").strip():
                detail = (
                    f"Stated objective {obj!r} is not a recognized OBJECTIVE_ALLOCATIONS key. "
                    + detail
                )
            return (
                None,
                "stated_objective_recommended",
                (),
                STATUS_TARGET_NOT_DEFINED,
                {
                    **resolution,
                    "source_kind": "stated_objective_OBJECTIVE_ALLOCATIONS",
                    "objective_key": None,
                    "raw_objective": str(obj or ""),
                },
            )
        targets, limitations, obj_meta = holding_targets_from_stated_objective(
            snapshot,
            values,
            key,
            redistribute_unrepresented=redistribute_unrepresented_objective_sleeves,
        )
        resolution.update(obj_meta)
        if not targets:
            return None, "stated_objective_recommended", limitations, STATUS_TARGET_NOT_DEFINED, resolution
        note = (
            f"Target derived from stated objective '{key}' via OBJECTIVE_ALLOCATIONS "
            "(recommended / labeled sleeve mix pro-rated onto priced ledger holdings — "
            "not Portfolio Health rebalance weights, not Guided Adjustment, not optimizer, "
            "and not a user-saved personal target)."
        )
        resolution["resolved_targets"] = dict(targets)
        return targets, "stated_objective_recommended", (note,) + tuple(limitations), None, resolution

    return None, str(target_source), (), STATUS_TARGET_NOT_DEFINED, resolution


def recommend_contribution_allocation(
    *,
    snapshot: RealPortfolioSnapshot | None,
    contribution_amount: float,
    target_source: TargetSourceChoice | str = "user_explicit",
    explicit_holding_targets: Mapping[str, float] | None = None,
    health_objective: str | None = None,
    strategy_holding_targets: Mapping[str, float] | None = None,
    redistribute_unrepresented_objective_sleeves: bool = False,
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
        ``user_explicit`` | ``stated_objective_recommended`` | ``current_strategy``
        (alias ``current_mix``).
    """
    c = float(contribution_amount or 0.0)
    source = normalize_target_source(str(target_source))

    if snapshot is None or failure_code == "no_real_ledger":
        return _blocked(
            STATUS_NO_REAL_PORTFOLIO,
            contribution=c,
            explanation=(
                "No real portfolio ledger is available. Record transactions in Real Portfolio "
                "before asking where new money should go. Demo or default model holdings are "
                "not used for real-money recommendations."
            ),
            target_source=source,
        )

    block, md_warnings = assess_market_data_for_contribution(snapshot)
    if block:
        return _blocked(
            block,
            contribution=c,
            explanation=md_warnings[0] if md_warnings else "Market data is insufficient for a precise recommendation.",
            warnings=md_warnings,
            target_source=source,
        )

    values = _holding_values_from_snapshot(snapshot, include_cash=include_cash)
    if not values:
        return _blocked(
            STATUS_NO_REAL_PORTFOLIO,
            contribution=c,
            explanation="The real portfolio has no priced holdings (and no cash) to allocate toward.",
            target_source=source,
            warnings=md_warnings,
        )

    targets, source_label, limitations, target_block, resolution = resolve_contribution_targets(
        snapshot=snapshot,
        values=values,
        target_source=source,
        explicit_holding_targets=explicit_holding_targets,
        health_objective=health_objective,
        strategy_holding_targets=strategy_holding_targets,
        redistribute_unrepresented_objective_sleeves=redistribute_unrepresented_objective_sleeves,
    )
    if target_block or targets is None:
        unrep = resolution.get("unrepresented_sleeves") or []
        if source == "stated_objective_recommended" and unrep and not redistribute_unrepresented_objective_sleeves:
            sleeves = ", ".join(
                f"{u.get('sleeve')} ({float(u.get('weight') or 0) * 100:.0f}%)" for u in unrep
            )
            explanation = (
                f"Stated objective '{resolution.get('objective_key')}' has unrepresented sleeve(s): "
                f"{sleeves}. Establish matching holdings (e.g. cash / T-bills) or explicitly acknowledge "
                "provisional redistribution into existing holdings. "
                "Unrepresented weight is not silently renormalized away."
            )
        elif source == "current_strategy":
            explanation = (
                limitations[0]
                if limitations
                else (
                    "Establish a saved strategy target before allocating. "
                    "Live market drift is not used as the target."
                )
            )
        elif source == "stated_objective_recommended":
            explanation = (
                "Select a legitimate stated investment objective before allocating new money. "
                "Portfolio Health / Guided / optimizer weights are not silently applied."
            )
        else:
            explanation = (
                "Select a legitimate target source before allocating new money. "
                "Options: your explicit holding targets, the stated-objective recommended mix "
                "(clearly labeled), or a saved current strategy target. "
                "Portfolio Health / optimizer weights are not silently applied."
            )
        return _blocked(
            STATUS_TARGET_NOT_DEFINED,
            contribution=c,
            explanation=explanation,
            target_source=source_label or source,
            warnings=md_warnings + tuple(limitations),
            assumptions=(
                "Real Portfolio ledger is authoritative for holdings and market values.",
                OBJECTIVE_SLEEVE_MAPPING_ASSUMPTION,
                "Decision support only — not a trade order.",
            ),
            meta=resolution,
        )

    assumptions = (
        "New-money-only mode: adds contribution dollars; does not sell overweight holdings.",
        "Real transaction ledger + current marks are authoritative for holdings and values.",
        "Deposits increase contributed capital / assets — they are not investment profit.",
        "Decision support only — not a brokerage order.",
    ) + tuple(limitations)

    result = allocate_contribution_new_money_only(
        current_values=values,
        target_weights=targets,
        contribution=c,
        target_source=source_label,
        assumptions=assumptions,
        warnings=md_warnings,
    )
    # Frozen result, mutable meta dict — attach resolution for UI / fingerprinting.
    result.meta.update(resolution)
    result.meta["resolved_targets"] = {
        str(k).strip().upper(): float(v) for k, v in (targets or {}).items() if str(k).strip()
    }
    return result


def recommend_contribution_allocation_from_session(
    session_state: Any,
    *,
    contribution_amount: float,
    target_source: TargetSourceChoice | str = "user_explicit",
    explicit_holding_targets: Mapping[str, float] | None = None,
    redistribute_unrepresented_objective_sleeves: bool = False,
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
    strategy = strategy_targets_from_session(session_state)
    if result.snapshot is None:
        code = result.failure.code if result.failure else "no_real_ledger"
        return recommend_contribution_allocation(
            snapshot=None,
            contribution_amount=contribution_amount,
            target_source=target_source,
            explicit_holding_targets=explicit_holding_targets,
            health_objective=str(health_objective or "") or None,
            strategy_holding_targets=strategy,
            redistribute_unrepresented_objective_sleeves=redistribute_unrepresented_objective_sleeves,
            include_cash=include_cash,
            failure_code=str(code),
        )
    return recommend_contribution_allocation(
        snapshot=result.snapshot,
        contribution_amount=contribution_amount,
        target_source=target_source,
        explicit_holding_targets=explicit_holding_targets,
        health_objective=str(health_objective or result.snapshot.health_objective or "") or None,
        strategy_holding_targets=strategy,
        redistribute_unrepresented_objective_sleeves=redistribute_unrepresented_objective_sleeves,
        include_cash=include_cash,
    )
