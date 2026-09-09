"""
Build a ledger-backed RealPortfolioSnapshot (read-only, no AMI routing).

Authoritative path: portfolio_transactions → portfolio_engine ledger replay → market quotes.
Does not read holdings_df, planning sidebar value keys, presets, or demo portfolios for valuation.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_models import (
    REAL_PORTFOLIO_DATA_SOURCE,
    RealHoldingSnapshot,
    RealPortfolioSnapshot,
    RealPortfolioSnapshotBuildFailure,
    RealPortfolioSnapshotBuildResult,
)

# Mismatch detection (read-only warning only).
_TICKER_SET_MISMATCH = True  # any symmetric difference in ticker sets
_WEIGHT_TOLERANCE_PP = 2.0  # absolute percentage-point difference on shared tickers
_FRESH_QUOTE_MAX_AGE_SEC = 90.0  # below this → market_data_status "fresh" when all priced

# Health / AMI often store display strings (e.g. "60.0%") via record_rebalance_from_health.
# These are model-portfolio Objective % labels — not an explicit real-portfolio target store.
_TARGET_WEIGHT_METADATA_KEYS = frozenset(
    {
        "source",
        "label",
        "updated_at",
        "schema",
        "type",
        "mode",
        "quality",
        "notes",
        "version",
        "origin",
        "target_source",
    }
)


def parse_weight_like_value(value: Any) -> float | None:
    """
    Coerce a single weight-like value to float percentage points when legitimate.

    Accepts: int/float, ``"60"``, ``"60.0"``, ``"60%"``, ``"60.0%"``.
    Rejects: None, nested dicts/lists, drift labels (``"+2.5pp"``), bare text, bools.
    Does not invent weights.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    low = text.lower()
    # Drift / commentary strings from Health AMI cache — not allocation weights.
    if "pp" in low or "drift" in low or "avg" in low:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    text = text.replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def extract_numeric_weight_map(raw: Any) -> dict[str, float]:
    """
    Extract ticker/sleeve → numeric weight from a heterogeneous mapping.

    Skips metadata keys and non-coercible values. Empty result means no usable weights.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        if name.lower() in _TARGET_WEIGHT_METADATA_KEYS:
            continue
        parsed = parse_weight_like_value(val)
        if parsed is None:
            continue
        out[name] = parsed
    return out


def _explicit_real_portfolio_target_allocation(session_state: Mapping[str, Any] | None) -> dict[str, float] | None:
    """
    Only an explicitly saved real-portfolio target becomes snapshot.target_allocation.

    Health ``target_weights`` (often ``"60.0%"`` display strings) are model-portfolio
    rebalance labels and must NOT be promoted as a user-defined real target.
    """
    if session_state is None:
        return None
    for key in (
        "real_portfolio_target_allocation",
        "saved_real_portfolio_target_allocation",
    ):
        if key not in session_state:
            continue
        parsed = extract_numeric_weight_map(session_state.get(key))
        if parsed:
            return parsed
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stored_at_to_utc(stored_at_unix: float | None) -> datetime | None:
    if stored_at_unix is None:
        return None
    try:
        return datetime.fromtimestamp(float(stored_at_unix), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _quote_for_ticker(
    ticker: str,
    *,
    prices: dict[str, float] | None,
    as_of: datetime,
) -> tuple[float | None, str, datetime | None, float | None]:
    """
    Resolve quote for snapshot marking.

    Returns price, source, price_as_of, cache_age_seconds.
    price_as_of is documented as UTC time the quote was cached or fetched — not exchange time.
    """
    sym = str(ticker or "").strip().upper()
    if prices is not None:
        if sym in prices:
            px = prices[sym]
            if px is None or float(px) <= 0:
                return None, "injected", None, None
            return float(px), "injected_test", as_of, 0.0
        return None, "", None, None
    try:
        from investment_market_data import get_market_data_provider

        provider = get_market_data_provider()
        px, src, stored_at = provider.get_spot_quote_freshness(sym)
        price_as_of = _stored_at_to_utc(stored_at) or as_of
        age = None
        if stored_at is not None:
            import time

            age = max(0.0, time.time() - float(stored_at))
        if px is None or float(px) <= 0:
            return None, str(src or ""), price_as_of, age
        return float(px), str(src or "market_data_provider"), price_as_of, age
    except Exception:
        return None, "", None, None


def _ledger_has_open_securities(transactions: list[pe.PortfolioTransaction]) -> bool:
    ledger, _cash = pe._ledger_from_transactions(transactions)
    return bool(ledger)


def _has_meaningful_transactions(records: list[Any] | None) -> bool:
    if not isinstance(records, list) or not records:
        return False
    txns = pe.transactions_from_records(records)
    if not txns:
        return False
    if _ledger_has_open_securities(txns):
        return True
    for t in txns:
        if t.action in ("cash_deposit", "cash_withdrawal"):
            return True
    return False


def _optional_plan_context(session_state: Mapping[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(context, dict):
        merged.update(context)
    if session_state is not None:
        for key in (
            "plan_risk",
            "plan_horizon",
            "plan_monthly",
            "plan_monthly_provided",
            "plan_emergency",
            "plan_near_term",
            "plan_debt",
            "target_weights",
            "rebalance_drift",
            "health_objective",
            "portfolio_objective",
            "investment_objective",
        ):
            if key in session_state and key not in merged:
                merged[key] = session_state[key]
    return merged


def _holdings_df_mismatch_warning(session_state: Mapping[str, Any] | None, ledger_weights: dict[str, float]) -> str | None:
    if session_state is None:
        return None
    try:
        import pandas as pd
    except ImportError:
        return None
    df = session_state.get("holdings_df")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if "Ticker" not in df.columns or "Weight (%)" not in df.columns:
        return None
    model_weights: dict[str, float] = {}
    for _, row in df.iterrows():
        tick = str(row.get("Ticker") or "").strip().upper()
        if not tick or tick in ("CASH", "$CASH"):
            continue
        try:
            model_weights[tick] = float(row.get("Weight (%)") or 0.0)
        except (TypeError, ValueError):
            continue
    if not model_weights:
        return None
    ledger_weights = {k: v for k, v in ledger_weights.items() if k not in ("$CASH", "CASH")}
    ledger_tickers = set(ledger_weights.keys())
    model_tickers = set(model_weights)
    if ledger_tickers != model_tickers:
        only_ledger = sorted(ledger_tickers - model_tickers)
        only_model = sorted(model_tickers - ledger_tickers)
        parts = []
        if only_ledger:
            parts.append(f"ledger-only tickers: {', '.join(only_ledger[:8])}")
        if only_model:
            parts.append(f"model-only tickers: {', '.join(only_model[:8])}")
        return (
            "Transaction ledger tickers differ from the weight-based holdings editor "
            f"({'; '.join(parts)}). Real portfolio analysis uses the ledger only."
        )
    shared = ledger_tickers
    total_ledger = sum(ledger_weights.get(t, 0.0) for t in shared)
    total_model = sum(model_weights.get(t, 0.0) for t in shared)
    if total_model <= 0:
        return None
    for tick in shared:
        lw = ledger_weights.get(tick, 0.0)
        mw = model_weights.get(tick, 0.0)
        norm_l = lw / total_ledger * 100.0 if total_ledger > 0 else 0.0
        norm_m = mw / total_model * 100.0
        if abs(norm_l - norm_m) > _WEIGHT_TOLERANCE_PP:
            return (
                f"Normalized weights for {tick} differ by more than {_WEIGHT_TOLERANCE_PP:.1f} pp "
                f"(ledger ~{norm_l:.1f}% vs model ~{norm_m:.1f}%). "
                "Real portfolio analysis uses ledger marks, not holdings_df."
            )
    return None


def _concentration_metrics(weights_pct: list[float]) -> dict[str, float]:
    if not weights_pct:
        return {
            "largest_holding_weight_pct": 0.0,
            "top_three_weight_pct": 0.0,
            "top_five_weight_pct": 0.0,
            "herfindahl_hhi": 0.0,
        }
    sorted_w = sorted(weights_pct, reverse=True)
    fracs = [w / 100.0 for w in sorted_w if w > 0]
    hhi = sum(f * f for f in fracs)
    return {
        "largest_holding_weight_pct": sorted_w[0],
        "top_three_weight_pct": sum(sorted_w[:3]),
        "top_five_weight_pct": sum(sorted_w[:5]),
        "herfindahl_hhi": round(hhi, 6),
    }


def _resolve_market_data_status(
    *,
    priced_count: int,
    total_positions: int,
    max_age: float | None,
    any_quote: bool,
) -> str:
    if total_positions == 0:
        return "unavailable"
    if priced_count == 0:
        return "unavailable"
    if priced_count < total_positions:
        return "partial"
    if max_age is not None and max_age <= _FRESH_QUOTE_MAX_AGE_SEC:
        return "fresh"
    if any_quote:
        return "cached"
    return "unavailable"


def build_real_portfolio_snapshot(
    session_state: Mapping[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
    prices: dict[str, float] | None = None,
) -> RealPortfolioSnapshotBuildResult:
    """
    Build a RealPortfolioSnapshot from persisted transactions only.

    Parameters
    ----------
    prices:
        Optional injected quotes for tests. When provided, only these symbols are priced.
    """
    records: list[Any] | None = None
    if isinstance(context, dict) and isinstance(context.get("portfolio_transactions"), list):
        records = context["portfolio_transactions"]
    elif session_state is not None and isinstance(session_state.get("portfolio_transactions"), list):
        records = list(session_state.get("portfolio_transactions") or [])

    if not _has_meaningful_transactions(records):
        return RealPortfolioSnapshotBuildResult(
            failure=RealPortfolioSnapshotBuildFailure(
                code="no_real_ledger",
                message="No transaction-based portfolio is saved. Real portfolio analysis requires portfolio_transactions.",
            )
        )

    txns = pe.transactions_from_records(records)
    ledger, cash_balance = pe._ledger_from_transactions(txns)
    as_of = _utc_now()

    holdings: list[RealHoldingSnapshot] = []
    portfolio_flags: list[str] = []
    quote_ages: list[float] = []
    priced_market_total = 0.0
    total_cost_basis = 0.0
    priced_gain_dollar = 0.0
    priced_cost_basis = 0.0
    unpriced_count = 0
    allocation_class: dict[str, float] = {}

    target_weights_raw = _optional_plan_context(session_state, context).get("target_weights")
    # Optional per-holding display context from Health/AMI cache (may be "60.0%" strings).
    # Not treated as an authoritative real-portfolio target allocation.
    target_by_ticker: dict[str, float] = {}
    for k, v in extract_numeric_weight_map(target_weights_raw).items():
        target_by_ticker[str(k).upper()] = float(v)

    for ticker, entry in sorted(ledger.items()):
        shares = float(entry.get("shares") or 0.0)
        if shares <= 1e-9:
            continue
        total_cost = float(entry.get("total_cost") or 0.0)
        avg_cost = total_cost / shares if shares > 0 else 0.0
        position_cost = shares * avg_cost
        total_cost_basis += position_cost

        asset_type = pe.resolve_instrument_type(str(entry.get("asset_type")), ticker)
        # Economic sleeves for drift/AMI (bond ETFs → Bonds), not instrument-type cards.
        asset_class = pe.economic_exposure_bucket(asset_type, ticker)
        company = str(entry.get("company_name") or pe.infer_company_name(ticker))

        px, src, price_as_of, age = _quote_for_ticker(ticker, prices=prices, as_of=as_of)
        if age is not None:
            quote_ages.append(age)

        flags: list[str] = []
        if px is None or px <= 0:
            unpriced_count += 1
            flags.append("missing_price")
            holding = RealHoldingSnapshot(
                ticker=ticker,
                name=company,
                shares=shares,
                average_cost=avg_cost,
                total_cost_basis=position_cost,
                current_price=None,
                current_value=0.0,
                gain_loss_dollars=None,
                gain_loss_pct=None,
                current_weight=0.0,
                target_weight=target_by_ticker.get(ticker),
                asset_class=asset_class,
                price_source=str(src or ""),
                price_as_of=price_as_of,
                data_quality_flags=tuple(flags),
            )
        else:
            market_value = shares * px
            gain_d = market_value - position_cost
            gain_p = (gain_d / position_cost * 100.0) if position_cost > 0 else 0.0
            priced_market_total += market_value
            priced_gain_dollar += gain_d
            priced_cost_basis += position_cost
            holding = RealHoldingSnapshot(
                ticker=ticker,
                name=company,
                shares=shares,
                average_cost=avg_cost,
                total_cost_basis=position_cost,
                current_price=px,
                current_value=market_value,
                gain_loss_dollars=gain_d,
                gain_loss_pct=gain_p,
                current_weight=0.0,
                target_weight=target_by_ticker.get(ticker),
                asset_class=asset_class,
                price_source=src,
                price_as_of=price_as_of,
                data_quality_flags=tuple(flags),
            )
            allocation_class[asset_class] = allocation_class.get(asset_class, 0.0) + market_value

        holdings.append(holding)

    total_market_value = priced_market_total + cash_balance
    if cash_balance > 0:
        allocation_class["Cash"] = allocation_class.get("Cash", 0.0) + cash_balance

    if unpriced_count:
        portfolio_flags.append("missing_prices")
    if cash_balance < -1e-6:
        portfolio_flags.append("negative_cash_balance")
    if unpriced_count and priced_market_total <= 0 and not cash_balance:
        portfolio_flags.append("no_priced_holdings")

    # Weights use known total (priced securities + cash); unpriced names stay at 0% with flags.
    allocation_by_holding: dict[str, float] = {}
    if total_market_value > 0:
        updated: list[RealHoldingSnapshot] = []
        for h in holdings:
            if h.current_price is not None and h.current_value > 0:
                w = h.current_value / total_market_value * 100.0
            else:
                w = 0.0
            allocation_by_holding[h.ticker] = w
            updated.append(
                RealHoldingSnapshot(
                    ticker=h.ticker,
                    name=h.name,
                    shares=h.shares,
                    average_cost=h.average_cost,
                    total_cost_basis=h.total_cost_basis,
                    current_price=h.current_price,
                    current_value=h.current_value,
                    gain_loss_dollars=h.gain_loss_dollars,
                    gain_loss_pct=h.gain_loss_pct,
                    current_weight=w,
                    target_weight=h.target_weight,
                    asset_class=h.asset_class,
                    price_source=h.price_source,
                    price_as_of=h.price_as_of,
                    data_quality_flags=h.data_quality_flags,
                )
            )
        holdings = updated

    if total_market_value > 0 and abs(cash_balance) > 1e-9:
        allocation_by_holding["$CASH"] = cash_balance / total_market_value * 100.0

    allocation_by_asset_class = {
        k: (v / total_market_value * 100.0 if total_market_value > 0 else 0.0)
        for k, v in allocation_class.items()
    }

    weights_list = [h.current_weight for h in holdings if h.current_weight > 0]
    concentration = _concentration_metrics(weights_list)
    sorted_holdings = sorted(holdings, key=lambda h: h.current_value, reverse=True)
    largest = tuple(sorted_holdings[:5])

    max_age = max(quote_ages) if quote_ages else None
    market_status = _resolve_market_data_status(
        priced_count=len(weights_list),
        total_positions=len(holdings),
        max_age=max_age,
        any_quote=bool(quote_ages),
    )
    market_age_int = int(round(max_age)) if max_age is not None else None

    total_gain_pct: float | None
    priced_gain_pct: float | None
    if unpriced_count > 0:
        total_gain_pct = None
        priced_gain_pct = (
            (priced_gain_dollar / priced_cost_basis * 100.0) if priced_cost_basis > 0 else None
        )
    else:
        total_gain_pct = (priced_gain_dollar / total_cost_basis * 100.0) if total_cost_basis > 0 else None
        priced_gain_pct = total_gain_pct

    plan_ctx = _optional_plan_context(session_state, context)
    risk = str(plan_ctx.get("plan_risk") or plan_ctx.get("risk_tolerance") or "").strip()
    health_obj = str(
        plan_ctx.get("health_objective")
        or plan_ctx.get("portfolio_objective")
        or plan_ctx.get("investment_objective")
        or ""
    ).strip()
    horizon = plan_ctx.get("plan_horizon")
    try:
        horizon_int = int(horizon) if horizon is not None else None
    except (TypeError, ValueError):
        horizon_int = None
    monthly: float | None = None
    if plan_ctx.get("plan_monthly_provided"):
        try:
            monthly = float(plan_ctx.get("plan_monthly"))
        except (TypeError, ValueError):
            monthly = None
    reserves: dict[str, float] = {}
    for key, label in (
        ("plan_emergency", "emergency"),
        ("plan_debt", "debt"),
        ("plan_expenses", "plan_expenses"),
    ):
        try:
            val = plan_ctx.get(key)
            if val is not None:
                reserves[label] = float(val)
        except (TypeError, ValueError):
            pass
    near_term = plan_ctx.get("plan_near_term")
    try:
        near_term_f = float(near_term) if near_term is not None else None
    except (TypeError, ValueError):
        near_term_f = None

    # Authoritative real-portfolio target only — never invent from Health display strings.
    target_alloc = _explicit_real_portfolio_target_allocation(session_state)
    # Optional drift commentary map: keep only coercible numerics; skip "+2.5pp" labels.
    drift: dict[str, float] | None = None
    drift_raw = plan_ctx.get("rebalance_drift")
    if isinstance(drift_raw, dict):
        drift_parsed: dict[str, float] = {}
        for k, v in drift_raw.items():
            # Prefer raw float; allow numeric strings; skip "±Npp" Health labels.
            parsed = parse_weight_like_value(v)
            if parsed is not None:
                drift_parsed[str(k)] = parsed
        drift = drift_parsed or None

    mismatch = _holdings_df_mismatch_warning(session_state, allocation_by_holding)

    snapshot = RealPortfolioSnapshot(
        as_of=as_of,
        market_data_status=market_status,  # type: ignore[arg-type]
        market_data_age_seconds=market_age_int,
        data_source=REAL_PORTFOLIO_DATA_SOURCE,
        total_market_value=total_market_value,
        total_cost_basis=total_cost_basis,
        total_gain_loss_dollars=priced_gain_dollar if priced_cost_basis > 0 or unpriced_count == 0 else None,
        total_gain_loss_pct=total_gain_pct,
        priced_holdings_gain_loss_pct=priced_gain_pct,
        cash=cash_balance,
        holdings=tuple(holdings),
        allocation_by_holding=allocation_by_holding,
        allocation_by_asset_class=allocation_by_asset_class,
        largest_positions=largest,
        concentration_metrics=concentration,
        target_allocation=target_alloc,
        allocation_drift=drift,
        recent_performance=None,
        benchmark_performance=None,
        risk_tolerance=risk,
        investment_horizon=horizon_int,
        monthly_contribution=monthly,
        reserves=reserves or None,
        near_term_needs=near_term_f,
        health_objective=health_obj,
        data_quality_flags=tuple(portfolio_flags),
        holdings_df_mismatch_warning=mismatch,
        known_marked_securities_value=priced_market_total,
        unpriced_holdings_count=unpriced_count,
    )
    return RealPortfolioSnapshotBuildResult(snapshot=snapshot)


def build_real_portfolio_snapshot_copy_safe(
    session_state: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> RealPortfolioSnapshotBuildResult:
    """Build snapshot from a deep-copied session mapping (for mutation tests)."""
    if session_state is None:
        return build_real_portfolio_snapshot(None, **kwargs)
    return build_real_portfolio_snapshot(copy.deepcopy(dict(session_state)), **kwargs)
