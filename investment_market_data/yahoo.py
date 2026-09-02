"""Low-level Yahoo Finance fetch helpers (no caching — use MarketDataProvider)."""

from __future__ import annotations

import logging
import time
import warnings
from typing import Any

import pandas as pd

from investment_market_data.diagnostics import record_fetch_attempt, record_yahoo_request

_SKIP_SPOT = frozenset({"US TREASURY", "MORTGAGE", "CORP BOND", "CASH"})
_LOG = logging.getLogger(__name__)

# Controlled backoff between single-ticker fallbacks (seconds).
_FALLBACK_SLEEP_SEC = 0.35
_MAX_SINGLE_FALLBACKS = 12


class MarketDataFetchError(ValueError):
    """Raised when Yahoo/yfinance returns no usable price history."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details or {})


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _yahoo_shared_errors() -> dict[str, str]:
    try:
        import yfinance as yf

        shared = getattr(yf, "shared", None)
        errors = getattr(shared, "_ERRORS", None) if shared is not None else None
        if isinstance(errors, dict) and errors:
            return {str(k): str(v)[:400] for k, v in errors.items()}
    except Exception:
        pass
    return {}


def _clear_yahoo_shared_errors() -> None:
    try:
        import yfinance as yf

        shared = getattr(yf, "shared", None)
        errors = getattr(shared, "_ERRORS", None) if shared is not None else None
        if isinstance(errors, dict):
            errors.clear()
    except Exception:
        pass


def _frame_shape(frame: pd.DataFrame | None) -> tuple[int, int] | None:
    if frame is None or not isinstance(frame, pd.DataFrame):
        return None
    try:
        return (int(frame.shape[0]), int(frame.shape[1]))
    except Exception:
        return None


def _extract_close_prices(raw: pd.DataFrame, clean: list[str]) -> pd.DataFrame:
    """Normalize yfinance download/history output to a Close price frame."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = list(raw.columns.get_level_values(0))
        if "Close" in level0:
            prices = raw["Close"].copy()
        elif "Adj Close" in level0:
            prices = raw["Adj Close"].copy()
        else:
            prices = raw.xs(raw.columns.levels[0][0], axis=1, level=0).copy()
    else:
        if "Close" in raw.columns:
            prices = raw[["Close"]].rename(columns={"Close": clean[0] if len(clean) == 1 else "Close"})
        elif "Adj Close" in raw.columns:
            prices = raw[["Adj Close"]].rename(
                columns={"Adj Close": clean[0] if len(clean) == 1 else "Adj Close"}
            )
        else:
            col = raw.columns[0]
            prices = raw[[col]].rename(columns={col: clean[0] if len(clean) == 1 else str(col)})

    if isinstance(prices, pd.Series):
        prices = prices.to_frame(name=clean[0] if clean else "Close")

    # Single-ticker MultiIndex can leave a Series; ensure columns are symbols when possible.
    if len(clean) == 1 and prices.shape[1] == 1 and list(prices.columns) != clean:
        prices = prices.rename(columns={prices.columns[0]: clean[0]})

    prices = prices.dropna(how="all").ffill().dropna(how="any")
    return prices


def _download_batch(
    clean: list[str],
    start: str,
    end: str | None,
    *,
    threads: bool,
) -> tuple[pd.DataFrame, list[str], dict[str, str]]:
    import yfinance as yf

    _clear_yahoo_shared_errors()
    warn_msgs: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raw = yf.download(
            clean if len(clean) > 1 else clean[0],
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=threads,
        )
        for item in caught:
            msg = str(item.message)
            if msg and msg not in warn_msgs:
                warn_msgs.append(msg[:400])
    if raw is None:
        raw = pd.DataFrame()
    return raw, warn_msgs, _yahoo_shared_errors()


def _history_one(symbol: str, start: str, end: str | None) -> pd.DataFrame:
    import yfinance as yf

    kwargs: dict[str, Any] = {"start": start, "auto_adjust": True}
    if end:
        kwargs["end"] = end
    hist = yf.Ticker(symbol).history(**kwargs)
    if hist is None or hist.empty or "Close" not in hist.columns:
        return pd.DataFrame()
    out = hist[["Close"]].rename(columns={"Close": symbol})
    # Drop timezone for alignment with batch downloads.
    try:
        if getattr(out.index, "tz", None) is not None:
            out.index = out.index.tz_localize(None)
    except Exception:
        pass
    return out


def _merge_symbol_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [f for f in frames if f is not None and not f.empty]
    if not usable:
        return pd.DataFrame()
    merged = usable[0]
    for frame in usable[1:]:
        merged = merged.join(frame, how="outer")
    return merged.dropna(how="all").ffill().dropna(how="any")


def _user_facing_empty_message(
    *,
    clean: list[str],
    start: str,
    end: str | None,
    provider_errors: dict[str, str],
    warnings_list: list[str],
    attempts: list[str],
) -> str:
    joined = ", ".join(clean[:8]) + ("…" if len(clean) > 8 else "")
    end_label = end or "today"
    err_preview = ""
    if provider_errors:
        sample = "; ".join(f"{k}: {v}" for k, v in list(provider_errors.items())[:3])
        err_preview = f" Yahoo/yfinance detail: {sample}."
    elif warnings_list:
        err_preview = f" Warning: {warnings_list[0]}"

    rate_like = any(
        any(tok in str(v).lower() for tok in ("rate", "too many", "429", "unauthorized", "blocked", "json"))
        for v in list(provider_errors.values()) + warnings_list
    )
    hint = (
        "Yahoo Finance likely rate-limited or blocked this host (common on Streamlit Cloud shared IPs). "
        if rate_like or not provider_errors
        else "Provider rejected one or more symbols. "
    )
    return (
        f"No Yahoo price history for [{joined}] from {start} to {end_label}. "
        f"{hint}"
        f"Attempts: {', '.join(attempts)}. "
        f"This is a market-data fetch failure, not a portfolio-math error.{err_preview}"
    )


def fetch_price_history_raw(
    tickers: list[str],
    start: str,
    end: str | None = None,
) -> pd.DataFrame:
    """
    Download adjusted close prices via yfinance.

    Strategy: batched download → single-ticker download fallback → Ticker.history.
    Does not invent or substitute prices when Yahoo returns empty.
    """
    clean = [normalize_symbol(t) for t in tickers if t and str(t).strip()]
    clean = list(dict.fromkeys(clean))
    if not clean:
        raise ValueError("At least one ticker is required.")

    attempts: list[str] = []
    all_warnings: list[str] = []
    all_errors: dict[str, str] = {}
    last_shape: tuple[int, int] | None = None
    exception_note: str | None = None

    # --- Attempt 1: batch ---
    record_yahoo_request("history_batch", count=1)
    attempts.append("batch_download")
    try:
        raw, warn_msgs, errors = _download_batch(clean, start, end, threads=True)
        all_warnings.extend(warn_msgs)
        all_errors.update(errors)
        last_shape = _frame_shape(raw)
        prices = _extract_close_prices(raw, clean)
        if not prices.empty:
            record_fetch_attempt(
                kind="history",
                ok=True,
                symbols=clean,
                start=start,
                end=end,
                shape=tuple(prices.shape),
                attempts=attempts,
            )
            return prices
    except Exception as exc:
        exception_note = f"{type(exc).__name__}: {exc}"
        _LOG.warning("Yahoo batch history failed: %s", exception_note)
        all_errors.setdefault("_batch", exception_note)

    # --- Attempt 2: per-symbol download (limited) ---
    per_frames: list[pd.DataFrame] = []
    missing = list(clean)
    if missing:
        attempts.append("per_symbol_download")
        for i, sym in enumerate(missing[:_MAX_SINGLE_FALLBACKS]):
            if i:
                time.sleep(_FALLBACK_SLEEP_SEC)
            record_yahoo_request("history_symbol", count=1)
            try:
                raw, warn_msgs, errors = _download_batch([sym], start, end, threads=False)
                all_warnings.extend(warn_msgs)
                all_errors.update(errors)
                last_shape = _frame_shape(raw) or last_shape
                frame = _extract_close_prices(raw, [sym])
                if not frame.empty:
                    per_frames.append(frame)
            except Exception as exc:
                note = f"{type(exc).__name__}: {exc}"
                all_errors[sym] = note
                _LOG.warning("Yahoo single download failed for %s: %s", sym, note)

    merged = _merge_symbol_frames(per_frames)
    if not merged.empty and set(merged.columns) >= set(clean):
        record_fetch_attempt(
            kind="history",
            ok=True,
            symbols=clean,
            start=start,
            end=end,
            shape=tuple(merged.shape),
            attempts=attempts,
        )
        return merged[clean]

    # --- Attempt 3: Ticker.history for still-missing symbols ---
    have = set(merged.columns) if not merged.empty else set()
    still = [s for s in clean if s not in have]
    if still:
        attempts.append("ticker_history")
        hist_frames = [merged] if not merged.empty else []
        for i, sym in enumerate(still[:_MAX_SINGLE_FALLBACKS]):
            if i or per_frames:
                time.sleep(_FALLBACK_SLEEP_SEC)
            record_yahoo_request("history_ticker", count=1)
            try:
                frame = _history_one(sym, start, end)
                last_shape = _frame_shape(frame) or last_shape
                if not frame.empty:
                    hist_frames.append(frame)
                else:
                    all_errors.setdefault(sym, "Ticker.history returned empty")
            except Exception as exc:
                note = f"{type(exc).__name__}: {exc}"
                all_errors[sym] = note
                _LOG.warning("Yahoo Ticker.history failed for %s: %s", sym, note)
        merged = _merge_symbol_frames(hist_frames)

    if not merged.empty:
        # Return whatever symbols we could fetch; require all requested for analysis consistency.
        missing_final = [s for s in clean if s not in merged.columns]
        if not missing_final:
            record_fetch_attempt(
                kind="history",
                ok=True,
                symbols=clean,
                start=start,
                end=end,
                shape=tuple(merged.shape),
                attempts=attempts,
            )
            return merged[clean]
        all_errors.setdefault("_partial", f"missing symbols: {', '.join(missing_final)}")

    details = {
        "provider": "yfinance",
        "symbols": clean,
        "start": start,
        "end": end,
        "response_shape": last_shape,
        "attempts": attempts,
        "yahoo_errors": all_errors,
        "warnings": all_warnings[:5],
        "exception": exception_note,
    }
    message = _user_facing_empty_message(
        clean=clean,
        start=start,
        end=end,
        provider_errors=all_errors,
        warnings_list=all_warnings,
        attempts=attempts,
    )
    record_fetch_attempt(
        kind="history",
        ok=False,
        symbols=clean,
        start=start,
        end=end,
        shape=last_shape,
        attempts=attempts,
        error_class="MarketDataFetchError",
        error_message=message,
        yahoo_errors=all_errors,
        warnings_list=all_warnings[:5],
    )
    raise MarketDataFetchError(message, details=details)


def batch_spot_prices_raw(symbols: list[str]) -> dict[str, float | None]:
    """Best-effort batched last prices (one download when multiple symbols)."""
    clean = [normalize_symbol(s) for s in symbols if s and normalize_symbol(s) not in _SKIP_SPOT]
    clean = list(dict.fromkeys(clean))
    if not clean:
        return {}

    out: dict[str, float | None] = {s: None for s in clean}
    if len(clean) == 1:
        sym = clean[0]
        px, _ = fetch_latest_quote_raw(sym)
        out[sym] = px
        return out

    import yfinance as yf

    record_yahoo_request("spot_batch", count=1)
    try:
        _clear_yahoo_shared_errors()
        raw = yf.download(
            clean,
            period="5d",
            auto_adjust=False,
            progress=False,
            group_by="column",
            threads=True,
        )
        if raw is None or raw.empty:
            record_fetch_attempt(
                kind="spot_batch",
                ok=False,
                symbols=clean,
                start=None,
                end=None,
                shape=_frame_shape(raw if isinstance(raw, pd.DataFrame) else None),
                attempts=["spot_batch_5d"],
                error_class="EmptyDataFrame",
                error_message="spot batch empty",
                yahoo_errors=_yahoo_shared_errors(),
            )
        elif isinstance(raw.columns, pd.MultiIndex):
            for sym in clean:
                try:
                    close = raw["Close"][sym].dropna()
                    if not close.empty:
                        val = float(close.iloc[-1])
                        if val > 0:
                            out[sym] = val
                except (KeyError, TypeError, ValueError):
                    continue
        else:
            sym = clean[0]
            close_col = "Close" if "Close" in raw.columns else raw.columns[-1]
            close = raw[close_col].dropna()
            if not close.empty:
                val = float(close.iloc[-1])
                if val > 0:
                    out[sym] = val
    except Exception as exc:
        record_fetch_attempt(
            kind="spot_batch",
            ok=False,
            symbols=clean,
            start=None,
            end=None,
            shape=None,
            attempts=["spot_batch_5d"],
            error_class=type(exc).__name__,
            error_message=str(exc)[:400],
        )

    for sym in clean:
        if out.get(sym) is None:
            px, _ = fetch_latest_quote_raw(sym)
            out[sym] = px
    return out


def fetch_latest_quote_raw(symbol: str) -> tuple[float | None, str]:
    """Latest per-share price with source label (portfolio engine semantics)."""
    sym = normalize_symbol(symbol)
    if not sym or sym in _SKIP_SPOT:
        return None, ""
    try:
        import yfinance as yf

        record_yahoo_request("spot_quote", count=1)
        ticker = yf.Ticker(sym)
        fast = getattr(ticker, "fast_info", None)
        last = getattr(fast, "last_price", None) if fast is not None else None
        if last is not None:
            px = float(last)
            if px > 0:
                return px, "yfinance_last_price"
        info = ticker.info or {}
        for key in ("regularMarketPrice", "currentPrice", "previousClose"):
            val = info.get(key)
            if val is not None:
                px = float(val)
                if px > 0:
                    return px, f"yfinance_{key}"
        hist = ticker.history(period="10d", auto_adjust=False)
        if hist is not None and not hist.empty and "Close" in hist.columns:
            close = float(hist["Close"].iloc[-1])
            if close > 0:
                return close, "yfinance_close"
        hist_adj = ticker.history(period="10d", auto_adjust=True)
        if hist_adj is not None and not hist_adj.empty and "Close" in hist_adj.columns:
            close = float(hist_adj["Close"].iloc[-1])
            if close > 0:
                return close, "yfinance_adj_close"
        record_fetch_attempt(
            kind="spot_quote",
            ok=False,
            symbols=[sym],
            start=None,
            end=None,
            shape=None,
            attempts=["fast_info", "info", "history_10d"],
            error_class="NoQuote",
            error_message=f"No usable spot quote for {sym}",
            yahoo_errors=_yahoo_shared_errors(),
        )
    except Exception as exc:
        record_fetch_attempt(
            kind="spot_quote",
            ok=False,
            symbols=[sym],
            start=None,
            end=None,
            shape=None,
            attempts=["spot_quote"],
            error_class=type(exc).__name__,
            error_message=str(exc)[:400],
        )
    return None, ""


def fetch_ticker_info_raw(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    sym = normalize_symbol(symbol)
    record_yahoo_request("ticker_info", count=1)
    return yf.Ticker(sym).info or {}


def fetch_trailing_pe_raw(symbol: str) -> float | None:
    info = fetch_ticker_info_raw(symbol)
    for key in ("trailingPE", "forwardPE"):
        raw = info.get(key)
        if raw is not None:
            try:
                val = float(raw)
                if 3.0 < val < 200.0:
                    return round(val, 1)
            except (TypeError, ValueError):
                continue
    return None


def fetch_etf_fund_data_raw(ticker: str) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """
    Live ETF metadata + holdings rows (without underlying prices) + sector frame.
    Returns (meta, holdings_df, sectors_df).
    """
    import yfinance as yf

    sym = normalize_symbol(ticker)
    record_yahoo_request("etf_fund", count=1)
    t = yf.Ticker(sym)
    info = t.info or {}
    fd = getattr(t, "funds_data", None)
    meta: dict[str, Any] = {
        "name": str(info.get("longName") or info.get("shortName") or sym),
        "issuer": "",
        "asset_class": "Equity",
        "category": str(info.get("category") or ""),
        "expense_ratio_pct": None,
    }
    exp = info.get("netExpenseRatio")
    if exp is not None:
        try:
            meta["expense_ratio_pct"] = float(exp)
        except (TypeError, ValueError):
            pass

    holdings_df = pd.DataFrame()
    sectors_df = pd.DataFrame()
    if fd is not None:
        overview = getattr(fd, "fund_overview", None) or {}
        if isinstance(overview, dict):
            meta["issuer"] = str(overview.get("family") or meta["issuer"])
            meta["category"] = str(overview.get("categoryName") or meta["category"])
            legal = str(overview.get("legalType") or "")
            if "bond" in legal.lower() or "bond" in meta["category"].lower():
                meta["asset_class"] = "Bonds"
        desc = str(getattr(fd, "description", "") or "")
        if "bond" in desc.lower() and meta["asset_class"] == "Equity":
            meta["asset_class"] = "Bonds"

        top = getattr(fd, "top_holdings", None)
        if top is not None and isinstance(top, pd.DataFrame) and not top.empty:
            rows = []
            for sym_h, row in top.iterrows():
                sym_s = normalize_symbol(str(sym_h))
                name = str(row.get("Name") or sym_s)
                wt = row.get("Holding Percent")
                try:
                    weight = float(wt)
                except (TypeError, ValueError):
                    weight = 0.0
                rows.append(
                    {
                        "symbol": sym_s,
                        "name": name,
                        "weight": weight,
                        "sector": "",
                        "price": None,
                    }
                )
            holdings_df = pd.DataFrame(rows)
        sectors_df = _sector_df_from_funds(fd)
    return meta, holdings_df, sectors_df


def _sector_df_from_funds(fd: Any) -> pd.DataFrame:
    sw = getattr(fd, "sector_weightings", None)
    if sw is None:
        return pd.DataFrame()
    if isinstance(sw, dict) and sw:
        rows = [
            {"Sector": str(k).replace("_", " ").title(), "Weight": float(v)}
            for k, v in sw.items()
            if v is not None
        ]
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).sort_values("Weight", ascending=False).reset_index(drop=True)
        df["Weight %"] = df["Weight"].map(lambda x: f"{float(x) * 100:.1f}%")
        return df[["Sector", "Weight %"]]
    if isinstance(sw, pd.DataFrame) and not sw.empty:
        out = sw.copy()
        out.columns = [str(c) for c in out.columns]
        return out
    return pd.DataFrame()


def fetch_stock_splits_raw(symbol: str) -> pd.Series | None:
    import yfinance as yf

    sym = normalize_symbol(symbol)
    record_yahoo_request("splits", count=1)
    splits = yf.Ticker(sym).splits
    if splits is None or len(splits) == 0:
        return None
    return splits
