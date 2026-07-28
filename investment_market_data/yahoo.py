"""Low-level Yahoo Finance fetch helpers (no caching — use MarketDataProvider)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from investment_market_data.diagnostics import record_yahoo_request

_SKIP_SPOT = frozenset({"US TREASURY", "MORTGAGE", "CORP BOND", "CASH"})


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def fetch_price_history_raw(
    tickers: list[str],
    start: str,
    end: str | None = None,
) -> pd.DataFrame:
    """Download adjusted close prices via yfinance (single batched request)."""
    import yfinance as yf

    clean = [normalize_symbol(t) for t in tickers if t and str(t).strip()]
    if not clean:
        raise ValueError("At least one ticker is required.")

    record_yahoo_request("history_batch", count=1)
    raw = yf.download(
        clean,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if raw.empty:
        raise ValueError("No price data returned. Check tickers and date range.")

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            prices = raw["Close"]
        elif "Adj Close" in raw.columns.get_level_values(0):
            prices = raw["Adj Close"]
        else:
            prices = raw.xs(raw.columns.levels[0][0], axis=1, level=0)
    else:
        col = "Close" if "Close" in raw.columns else raw.columns[0]
        prices = raw[[col]].rename(columns={col: clean[0]})

    prices = prices.dropna(how="all").ffill().dropna(how="any")
    if prices.empty:
        raise ValueError("Price history is empty after cleaning.")
    return prices


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
        raw = yf.download(
            clean,
            period="5d",
            auto_adjust=False,
            progress=False,
            group_by="column",
            threads=True,
        )
        if raw.empty:
            return out
        if isinstance(raw.columns, pd.MultiIndex):
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
    except Exception:
        pass

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
    except Exception:
        pass
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
