"""Cash-flow-aware Real Portfolio historical performance (TWR / XIRR / NAV history).

Authoritative input: ``portfolio_transactions`` (deposits, withdrawals, buys, sells).
Historical marks: caller-supplied price panel (tests use fixtures; UI uses adjusted closes).

Does **not** mutate the ledger. Does **not** treat deposits as investment return.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal, Mapping, Sequence

import pandas as pd

PeriodKey = Literal[
    "1d",
    "1w",
    "1m",
    "3m",
    "ytd",
    "1y",
    "since_inception",
]

PERIOD_LABELS: dict[PeriodKey, str] = {
    "1d": "1 day",
    "1w": "1 week",
    "1m": "1 month",
    "3m": "3 months",
    "ytd": "YTD",
    "1y": "1 year",
    "since_inception": "Since inception",
}

# Do not headline-annualize XIRR when the observation span is shorter than this.
XIRR_ANNUALIZE_MIN_DAYS = 90

PRICE_SOURCE_LABEL = (
    "Historical security marks use adjusted close prices from the app market-data provider "
    "(Yahoo via investment_market_data). Adjusted closes include dividend/split adjustments."
)


@dataclass(frozen=True)
class NavPoint:
    as_of: date
    nav: float
    securities_mv: float
    cash: float
    external_cf: float  # net external flow booked on this date (deposit − withdrawal)
    cumulative_net_contributions: float


@dataclass(frozen=True)
class PeriodPerformance:
    period: PeriodKey
    label: str
    available: bool
    start_date: date | None
    end_date: date | None
    twr: float | None
    money_weighted_period: float | None  # Modified Dietz over the window (not annualized)
    xirr_annualized: float | None
    xirr_shown: bool
    benchmark_return: float | None
    excess_twr_vs_benchmark: float | None
    message: str = ""


@dataclass(frozen=True)
class TimePerformanceResult:
    ok: bool
    status: str
    inception_date: date | None
    as_of: date | None
    nav_series: tuple[NavPoint, ...]
    twr_since_inception: float | None
    money_weighted_period_since_inception: float | None
    xirr_annualized: float | None
    xirr_shown: bool
    observation_days: int
    periods: tuple[PeriodPerformance, ...]
    twr_index: tuple[tuple[date, float], ...]  # growth of 100, flow-neutral
    benchmark_symbol: str
    benchmark_label: str
    price_source_note: str
    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()[:10]
    return date.fromisoformat(text)


def _txn_cash_amount(txn: Any) -> float:
    qty = float(getattr(txn, "quantity", 0.0) or 0.0)
    px = float(getattr(txn, "execution_price", 0.0) or 0.0)
    if qty > 0:
        return qty
    return px


def _txn_sort_key(txn: Any) -> tuple:
    action = str(getattr(txn, "action", "") or "")
    # Deposits before buys on the same day so funding is available.
    rank = {
        "cash_deposit": 0,
        "buy": 1,
        "sell": 2,
        "cash_withdrawal": 3,
    }.get(action, 9)
    return (_parse_date(getattr(txn, "date", "")), rank, str(getattr(txn, "id", "") or ""))


def external_flow_on_date(transactions: Sequence[Any], day: date) -> float:
    """Net external contribution on ``day`` (deposits positive, withdrawals negative)."""
    total = 0.0
    for txn in transactions:
        if _parse_date(getattr(txn, "date", "")) != day:
            continue
        action = str(getattr(txn, "action", "") or "")
        if action == "cash_deposit":
            total += _txn_cash_amount(txn)
        elif action == "cash_withdrawal":
            total -= _txn_cash_amount(txn)
    return total


def reconstruct_holdings_and_cash(
    transactions: Sequence[Any],
    *,
    as_of: date,
) -> tuple[dict[str, float], float, float]:
    """
    Replay ledger through ``as_of`` (inclusive).

    Returns (shares_by_ticker, cash, cumulative_net_external_contributions).
    Buys/sells move cash ↔ shares; only deposits/withdrawals change contributed capital.
    """
    cash = 0.0
    shares: dict[str, float] = {}
    contrib = 0.0
    for txn in sorted(transactions, key=_txn_sort_key):
        day = _parse_date(getattr(txn, "date", ""))
        if day > as_of:
            break
        action = str(getattr(txn, "action", "") or "")
        if action == "cash_deposit":
            amt = _txn_cash_amount(txn)
            cash += amt
            contrib += amt
        elif action == "cash_withdrawal":
            amt = _txn_cash_amount(txn)
            cash -= amt
            contrib -= amt
        elif action == "buy":
            sym = str(getattr(txn, "ticker", "") or "").strip().upper()
            qty = float(getattr(txn, "quantity", 0.0) or 0.0)
            px = float(getattr(txn, "execution_price", 0.0) or 0.0)
            if not sym or qty <= 0 or px <= 0:
                continue
            cash -= qty * px
            shares[sym] = shares.get(sym, 0.0) + qty
        elif action == "sell":
            sym = str(getattr(txn, "ticker", "") or "").strip().upper()
            qty = float(getattr(txn, "quantity", 0.0) or 0.0)
            px = float(getattr(txn, "execution_price", 0.0) or 0.0)
            if not sym or qty <= 0 or px <= 0:
                continue
            owned = shares.get(sym, 0.0)
            sell_qty = min(qty, owned)
            if sell_qty <= 0:
                continue
            cash += sell_qty * px
            shares[sym] = owned - sell_qty
            if shares[sym] <= 1e-12:
                shares.pop(sym, None)
    return shares, cash, contrib


def _price_on_or_before(
    prices: pd.DataFrame,
    day: date,
    ticker: str,
    *,
    max_lookback_days: int = 7,
) -> float | None:
    if prices is None or prices.empty or ticker not in prices.columns:
        return None
    col = prices[ticker].dropna()
    if col.empty:
        return None
    idx = pd.to_datetime(col.index).date
    series = pd.Series(col.values, index=list(idx))
    # Prefer exact / recent calendar lookback
    for back in range(0, max_lookback_days + 1):
        d = day - timedelta(days=back)
        if d in series.index:
            val = float(series.loc[d])
            if isinstance(val, float) and val > 0:
                return val
            # duplicate index edge
            try:
                raw = series.loc[d]
                val2 = float(raw.iloc[-1]) if hasattr(raw, "iloc") else float(raw)
                if val2 > 0:
                    return val2
            except Exception:
                pass
    eligible = series[series.index <= day]
    if eligible.empty:
        return None
    last_day = eligible.index[-1]
    if (day - last_day).days <= max_lookback_days:
        val = float(eligible.iloc[-1])
        return val if val > 0 else None
    return None


def mark_portfolio(
    shares: Mapping[str, float],
    cash: float,
    prices: pd.DataFrame,
    day: date,
) -> tuple[float | None, float | None, tuple[str, ...]]:
    """Mark securities; return (nav, securities_mv, missing_tickers)."""
    missing: list[str] = []
    mv = 0.0
    for sym, qty in shares.items():
        if qty <= 1e-12:
            continue
        px = _price_on_or_before(prices, day, sym)
        if px is None:
            missing.append(sym)
            continue
        mv += float(qty) * px
    if missing:
        return None, None, tuple(sorted(set(missing)))
    nav = mv + float(cash)
    return nav, mv, ()


def build_nav_series(
    transactions: Sequence[Any],
    prices: pd.DataFrame,
    *,
    as_of: date | None = None,
    valuation_dates: Sequence[date] | None = None,
) -> tuple[tuple[NavPoint, ...], tuple[str, ...]]:
    """
    Reconstruct end-of-day NAV on valuation dates.

    ``prices``: DataFrame indexed by datetime/date, columns = tickers, values = adjusted closes.
    Missing marks for any open holding → that day is omitted.
    """
    if not transactions:
        return (), ("no_transactions",)

    sorted_txns = sorted(transactions, key=_txn_sort_key)
    first = _parse_date(getattr(sorted_txns[0], "date", ""))
    end = as_of or date.today()
    if end < first:
        return (), ("as_of_before_inception",)

    if valuation_dates is None:
        if prices is None or prices.empty:
            return (), ("no_price_history",)
        idx_dates = sorted({pd.Timestamp(x).date() for x in prices.index})
        valuation_dates = [d for d in idx_dates if first <= d <= end]
        txn_days = sorted({_parse_date(getattr(t, "date", "")) for t in sorted_txns})
        extra = [d for d in txn_days if first <= d <= end]
        valuation_dates = sorted(set(valuation_dates) | set(extra))
    else:
        valuation_dates = [d for d in valuation_dates if first <= d <= end]

    points: list[NavPoint] = []
    skipped = 0
    for day in valuation_dates:
        shares, cash, contrib = reconstruct_holdings_and_cash(sorted_txns, as_of=day)
        if not shares and abs(cash) < 1e-9 and abs(contrib) < 1e-9:
            continue
        nav, mv, missing = mark_portfolio(shares, cash, prices, day)
        if nav is None or mv is None:
            skipped += 1
            continue
        cf = external_flow_on_date(sorted_txns, day)
        points.append(
            NavPoint(
                as_of=day,
                nav=float(nav),
                securities_mv=float(mv),
                cash=float(cash),
                external_cf=float(cf),
                cumulative_net_contributions=float(contrib),
            )
        )
    warnings: list[str] = []
    if skipped:
        warnings.append(f"omitted_valuation_days:{skipped}")
    if len(points) < 2:
        warnings.append("insufficient_nav_points")
    return tuple(points), tuple(warnings)


def compute_twr(nav_points: Sequence[NavPoint]) -> tuple[float | None, tuple[tuple[date, float], ...]]:
    """
    True time-weighted return with **end-of-day external flow** convention:

        r_t = (NAV_t − CF_t) / NAV_{t−1} − 1

    where CF_t is net external contribution on day t (deposit positive).
    Buys/sells are not CF. Geometric link: TWR = Π(1+r_t) − 1.
    """
    if len(nav_points) < 2:
        return None, ()
    index: list[tuple[date, float]] = [(nav_points[0].as_of, 100.0)]
    growth = 100.0
    prev = nav_points[0]
    for pt in nav_points[1:]:
        if prev.nav <= 1e-9:
            return None, tuple(index)
        r = (pt.nav - pt.external_cf) / prev.nav - 1.0
        growth *= 1.0 + r
        index.append((pt.as_of, growth))
        prev = pt
    twr = growth / 100.0 - 1.0
    return twr, tuple(index)


def compute_modified_dietz(
    nav_points: Sequence[NavPoint],
    *,
    start_idx: int = 0,
    end_idx: int | None = None,
) -> float | None:
    """Money-weighted period return (Modified Dietz), not annualized."""
    if end_idx is None:
        end_idx = len(nav_points) - 1
    if end_idx <= start_idx or start_idx < 0 or end_idx >= len(nav_points):
        return None
    start = nav_points[start_idx]
    end = nav_points[end_idx]
    window = nav_points[start_idx : end_idx + 1]
    flows = [(p.as_of, p.external_cf) for p in window[1:] if abs(p.external_cf) > 1e-12]
    total_cf = sum(cf for _, cf in flows)
    days = (end.as_of - start.as_of).days
    if days <= 0:
        return None
    weighted = 0.0
    for d, cf in flows:
        w = (end.as_of - d).days / days
        weighted += cf * w
    denom = start.nav + weighted
    if abs(denom) <= 1e-9:
        return None
    return (end.nav - start.nav - total_cf) / denom


def _xirr(cash_flows: Sequence[tuple[date, float]], *, guess: float = 0.1) -> float | None:
    """Annualized IRR for dated cash flows. Returns None if not solvable."""
    if len(cash_flows) < 2:
        return None
    flows = sorted(cash_flows, key=lambda x: x[0])
    t0 = flows[0][0]
    amounts = [a for _, a in flows]
    if not (min(amounts) < 0 < max(amounts)):
        return None

    def npv(rate: float) -> float:
        total = 0.0
        for d, amt in flows:
            years = (d - t0).days / 365.0
            total += amt / ((1.0 + rate) ** years)
        return total

    def d_npv(rate: float) -> float:
        total = 0.0
        for d, amt in flows:
            years = (d - t0).days / 365.0
            if years == 0:
                continue
            total -= years * amt / ((1.0 + rate) ** (years + 1.0))
        return total

    rate = guess
    for _ in range(64):
        f = npv(rate)
        df = d_npv(rate)
        if abs(df) < 1e-14:
            break
        new_rate = rate - f / df
        if not math.isfinite(new_rate) or new_rate <= -0.999999:
            break
        if abs(new_rate - rate) < 1e-10:
            return float(new_rate)
        rate = new_rate
    lo, hi = -0.99, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if abs(f_mid) < 1e-10:
            return float(mid)
        if f_lo * f_mid <= 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return float(0.5 * (lo + hi))


def compute_xirr_from_nav_series(
    nav_points: Sequence[NavPoint],
    transactions: Sequence[Any],
) -> tuple[float | None, int]:
    """
    Investor-perspective XIRR:
    - deposits as negative flows (money out of pocket)
    - withdrawals as positive flows
    - ending NAV as positive terminal value
    """
    if len(nav_points) < 1:
        return None, 0
    end = nav_points[-1]
    start = nav_points[0]
    flows: list[tuple[date, float]] = []
    for txn in sorted(transactions, key=_txn_sort_key):
        day = _parse_date(getattr(txn, "date", ""))
        if day < start.as_of or day > end.as_of:
            continue
        action = str(getattr(txn, "action", "") or "")
        if action == "cash_deposit":
            flows.append((day, -_txn_cash_amount(txn)))
        elif action == "cash_withdrawal":
            flows.append((day, _txn_cash_amount(txn)))
    flows.append((end.as_of, float(end.nav)))
    collapsed: dict[date, float] = {}
    for d, a in flows:
        collapsed[d] = collapsed.get(d, 0.0) + a
    paired = sorted(collapsed.items(), key=lambda x: x[0])
    days = (end.as_of - start.as_of).days
    return _xirr(paired), max(0, days)


def benchmark_total_return(
    prices: pd.DataFrame,
    symbol: str,
    start: date,
    end: date,
) -> float | None:
    """Buy-and-hold total return using adjusted closes over [start, end]."""
    sym = str(symbol or "").strip().upper()
    if not sym or prices is None or prices.empty or sym not in prices.columns:
        return None
    start_px = _price_on_or_before(prices, start, sym, max_lookback_days=7)
    end_px = _price_on_or_before(prices, end, sym, max_lookback_days=7)
    if start_px is None or end_px is None or start_px <= 0:
        return None
    return end_px / start_px - 1.0


def _window_start(end: date, period: PeriodKey, inception: date) -> date | None:
    if period == "since_inception":
        return inception
    if period == "1d":
        return end - timedelta(days=1)
    if period == "1w":
        return end - timedelta(days=7)
    if period == "1m":
        return end - timedelta(days=31)
    if period == "3m":
        return end - timedelta(days=93)
    if period == "ytd":
        return date(end.year, 1, 1)
    if period == "1y":
        return end - timedelta(days=365)
    return None


def _slice_nav_for_period(
    nav_points: Sequence[NavPoint],
    period: PeriodKey,
) -> tuple[int, int] | None:
    if len(nav_points) < 2:
        return None
    end_idx = len(nav_points) - 1
    end = nav_points[end_idx].as_of
    inception = nav_points[0].as_of
    want = _window_start(end, period, inception)
    if want is None:
        return None
    if period != "since_inception" and want < inception:
        return None
    start_idx = None
    for i, p in enumerate(nav_points):
        if p.as_of >= want:
            start_idx = i
            break
    if start_idx is None or start_idx >= end_idx:
        return None
    if period != "since_inception":
        if nav_points[0].as_of > want:
            return None
        span = (end - nav_points[start_idx].as_of).days
        need = {
            "1d": 1,
            "1w": 5,
            "1m": 20,
            "3m": 60,
            "ytd": 1,
            "1y": 200,
        }.get(period, 1)
        if span < need and period in ("1w", "1m", "3m", "1y"):
            return None
    return start_idx, end_idx


def analyze_period(
    nav_points: Sequence[NavPoint],
    transactions: Sequence[Any],
    prices: pd.DataFrame,
    period: PeriodKey,
    *,
    benchmark_symbol: str,
) -> PeriodPerformance:
    label = PERIOD_LABELS[period]
    sliced = _slice_nav_for_period(nav_points, period)
    if sliced is None:
        return PeriodPerformance(
            period=period,
            label=label,
            available=False,
            start_date=None,
            end_date=None,
            twr=None,
            money_weighted_period=None,
            xirr_annualized=None,
            xirr_shown=False,
            benchmark_return=None,
            excess_twr_vs_benchmark=None,
            message="Insufficient history for this window.",
        )
    i0, i1 = sliced
    window = nav_points[i0 : i1 + 1]
    twr, _ = compute_twr(window)
    diet = compute_modified_dietz(nav_points, start_idx=i0, end_idx=i1)
    xirr, obs_days = compute_xirr_from_nav_series(window, transactions)
    show_xirr = xirr is not None and obs_days >= XIRR_ANNUALIZE_MIN_DAYS
    bsym = str(benchmark_symbol or "VTI").strip().upper() or "VTI"
    bref = benchmark_total_return(prices, bsym, window[0].as_of, window[-1].as_of)
    excess = (twr - bref) if (twr is not None and bref is not None) else None
    return PeriodPerformance(
        period=period,
        label=label,
        available=twr is not None,
        start_date=window[0].as_of,
        end_date=window[-1].as_of,
        twr=twr,
        money_weighted_period=diet,
        xirr_annualized=xirr if show_xirr else None,
        xirr_shown=show_xirr,
        benchmark_return=bref,
        excess_twr_vs_benchmark=excess,
        message="" if twr is not None else "Could not compute TWR for this window.",
    )


def analyze_real_portfolio_time_performance(
    transactions: Sequence[Any],
    prices: pd.DataFrame,
    *,
    as_of: date | None = None,
    benchmark_symbol: str = "VTI",
    valuation_dates: Sequence[date] | None = None,
) -> TimePerformanceResult:
    """Full historical performance package from ledger + historical price panel."""
    bsym = str(benchmark_symbol or "VTI").strip().upper() or "VTI"
    limitations: list[str] = [
        PRICE_SOURCE_LABEL,
        "Deposits/withdrawals are external cash flows — not investment return.",
        "Buys/sells are internal (cash ↔ securities) and do not themselves create TWR.",
        "Unrealized G/L vs cost basis is a separate current mark metric — not TWR.",
        f"Benchmark {bsym} is a market reference total return over the same dates — "
        "not a matched multi-asset strategy benchmark unless holdings equal that symbol.",
    ]
    if not transactions:
        return TimePerformanceResult(
            ok=False,
            status="no_transactions",
            inception_date=None,
            as_of=None,
            nav_series=(),
            twr_since_inception=None,
            money_weighted_period_since_inception=None,
            xirr_annualized=None,
            xirr_shown=False,
            observation_days=0,
            periods=(),
            twr_index=(),
            benchmark_symbol=bsym,
            benchmark_label=f"{bsym} total return (adjusted close)",
            price_source_note=PRICE_SOURCE_LABEL,
            limitations=tuple(limitations),
            warnings=("No real portfolio transactions to analyze.",),
        )

    nav_series, warn = build_nav_series(
        transactions,
        prices,
        as_of=as_of,
        valuation_dates=valuation_dates,
    )
    if len(nav_series) < 2:
        return TimePerformanceResult(
            ok=False,
            status="insufficient_history",
            inception_date=nav_series[0].as_of if nav_series else None,
            as_of=nav_series[-1].as_of if nav_series else as_of,
            nav_series=nav_series,
            twr_since_inception=None,
            money_weighted_period_since_inception=None,
            xirr_annualized=None,
            xirr_shown=False,
            observation_days=0,
            periods=(),
            twr_index=(),
            benchmark_symbol=bsym,
            benchmark_label=f"{bsym} total return (adjusted close)",
            price_source_note=PRICE_SOURCE_LABEL,
            limitations=tuple(limitations),
            warnings=warn
            + (
                "Need at least two successfully marked valuation dates "
                "(check historical prices for all open holdings).",
            ),
        )

    twr, index = compute_twr(nav_series)
    diet = compute_modified_dietz(nav_series)
    xirr, obs_days = compute_xirr_from_nav_series(nav_series, transactions)
    show_xirr = xirr is not None and obs_days >= XIRR_ANNUALIZE_MIN_DAYS
    if xirr is not None and not show_xirr:
        limitations.append(
            f"Annualized XIRR computed but suppressed from headlines "
            f"(observation span {obs_days} days < {XIRR_ANNUALIZE_MIN_DAYS})."
        )

    periods = tuple(
        analyze_period(nav_series, transactions, prices, key, benchmark_symbol=bsym)
        for key in ("1d", "1w", "1m", "3m", "ytd", "1y", "since_inception")
    )

    return TimePerformanceResult(
        ok=True,
        status="ok",
        inception_date=nav_series[0].as_of,
        as_of=nav_series[-1].as_of,
        nav_series=nav_series,
        twr_since_inception=twr,
        money_weighted_period_since_inception=diet,
        xirr_annualized=xirr if show_xirr else None,
        xirr_shown=show_xirr,
        observation_days=obs_days,
        periods=periods,
        twr_index=index,
        benchmark_symbol=bsym,
        benchmark_label=f"{bsym} total return (adjusted close)",
        price_source_note=PRICE_SOURCE_LABEL,
        limitations=tuple(limitations),
        warnings=warn,
        meta={
            "xirr_annualized_raw": xirr,
            "xirr_suppressed": xirr is not None and not show_xirr,
        },
    )


def load_price_history_for_transactions(
    transactions: Sequence[Any],
    *,
    benchmark_symbol: str = "VTI",
    as_of: date | None = None,
    fetch_history=None,
) -> pd.DataFrame:
    """Fetch adjusted-close history covering inception→as_of for held tickers + benchmark."""
    if not transactions:
        return pd.DataFrame()
    tickers = sorted(
        {
            str(getattr(t, "ticker", "") or "").strip().upper()
            for t in transactions
            if str(getattr(t, "action", "")) in ("buy", "sell")
            and str(getattr(t, "ticker", "") or "").strip()
        }
        | {str(benchmark_symbol or "VTI").strip().upper()}
    )
    start = min(_parse_date(getattr(t, "date", "")) for t in transactions) - timedelta(days=5)
    end = as_of or date.today()
    end_plus = end + timedelta(days=1)
    if fetch_history is None:
        from portfolio_core import fetch_price_history

        fetch_history = fetch_price_history
    df = fetch_history(tickers, start.isoformat(), end_plus.isoformat())
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).strip().upper() for c in out.columns]
    return out
