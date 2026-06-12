"""
ETF metadata and holdings lookup — live yfinance with static fallback.

Calculation-only module; UI in components/etf_holdings_explorer.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

# Curated list for search/picker (major index, bond, dividend, sector ETFs)
POPULAR_ETF_TICKERS: tuple[str, ...] = (
    "VTI",
    "VOO",
    "VUG",
    "VTV",
    "VXUS",
    "BND",
    "AGG",
    "SCHD",
    "VYM",
    "VNQ",
    "QQQ",
    "SPY",
    "IVV",
    "IWM",
    "TLT",
    "BIL",
)

# Sample top holdings when live fetch fails (labeled as sample in UI)
_STATIC_HOLDINGS: dict[str, list[dict[str, Any]]] = {
    "VOO": [
        {"symbol": "AAPL", "name": "Apple Inc", "weight": 0.07, "sector": "Technology"},
        {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 0.06, "sector": "Technology"},
        {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.06, "sector": "Technology"},
        {"symbol": "AMZN", "name": "Amazon.com Inc", "weight": 0.04, "sector": "Consumer Cyclical"},
        {"symbol": "GOOGL", "name": "Alphabet Inc Class A", "weight": 0.04, "sector": "Communication Services"},
    ],
    "VTI": [
        {"symbol": "AAPL", "name": "Apple Inc", "weight": 0.06, "sector": "Technology"},
        {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 0.05, "sector": "Technology"},
        {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.05, "sector": "Technology"},
        {"symbol": "AMZN", "name": "Amazon.com Inc", "weight": 0.03, "sector": "Consumer Cyclical"},
        {"symbol": "META", "name": "Meta Platforms Inc", "weight": 0.02, "sector": "Communication Services"},
    ],
    "QQQ": [
        {"symbol": "AAPL", "name": "Apple Inc", "weight": 0.09, "sector": "Technology"},
        {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 0.08, "sector": "Technology"},
        {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.08, "sector": "Technology"},
        {"symbol": "AMZN", "name": "Amazon.com Inc", "weight": 0.05, "sector": "Consumer Cyclical"},
        {"symbol": "META", "name": "Meta Platforms Inc", "weight": 0.04, "sector": "Communication Services"},
    ],
    "BND": [
        {"symbol": "US TREASURY", "name": "U.S. Treasury Notes", "weight": 0.35, "sector": "Government"},
        {"symbol": "MORTGAGE", "name": "Mortgage-Backed Securities", "weight": 0.25, "sector": "Fixed Income"},
        {"symbol": "CORP BOND", "name": "Investment Grade Corporate", "weight": 0.20, "sector": "Corporate"},
    ],
    "SCHD": [
        {"symbol": "HD", "name": "Home Depot Inc", "weight": 0.04, "sector": "Consumer Cyclical"},
        {"symbol": "KO", "name": "Coca-Cola Co", "weight": 0.04, "sector": "Consumer Defensive"},
        {"symbol": "VZ", "name": "Verizon Communications", "weight": 0.04, "sector": "Communication Services"},
    ],
}

_STATIC_META: dict[str, dict[str, str]] = {
    "VTI": {"name": "Vanguard Total Stock Market ETF", "issuer": "Vanguard", "asset_class": "Equity", "category": "Large Blend"},
    "VOO": {"name": "Vanguard S&P 500 ETF", "issuer": "Vanguard", "asset_class": "Equity", "category": "Large Blend"},
    "VXUS": {"name": "Vanguard Total International Stock ETF", "issuer": "Vanguard", "asset_class": "Equity", "category": "Foreign Large Blend"},
    "BND": {"name": "Vanguard Total Bond Market ETF", "issuer": "Vanguard", "asset_class": "Bonds", "category": "Intermediate Core Bond"},
    "SCHD": {"name": "Schwab U.S. Dividend Equity ETF", "issuer": "Schwab", "asset_class": "Equity", "category": "Large Value"},
    "QQQ": {"name": "Invesco QQQ Trust", "issuer": "Invesco", "asset_class": "Equity", "category": "Large Growth"},
}


@dataclass(frozen=True)
class EtfLookupResult:
    ticker: str
    name: str
    issuer: str
    asset_class: str
    category: str
    expense_ratio_pct: float | None
    data_source: str
    holdings: pd.DataFrame
    sectors: pd.DataFrame


def _normalize_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def _holdings_from_yfinance(ticker: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], str]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    fd = getattr(t, "funds_data", None)
    meta: dict[str, Any] = {
        "name": str(info.get("longName") or info.get("shortName") or ticker),
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
            for sym, row in top.iterrows():
                sym_s = str(sym).strip().upper()
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
                        "price": _latest_price(sym_s),
                    }
                )
            holdings_df = pd.DataFrame(rows)
            sectors = _sector_df_from_funds(fd)
            return holdings_df, sectors, meta, "live"

    static = _STATIC_HOLDINGS.get(ticker)
    if static:
        meta.update(_STATIC_META.get(ticker, {}))
        return pd.DataFrame(static), pd.DataFrame(), meta, "sample"

    return pd.DataFrame(), pd.DataFrame(), meta, "unavailable"


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


def _latest_price(symbol: str) -> float | None:
    if not symbol or symbol in ("US TREASURY", "MORTGAGE", "CORP BOND"):
        return None
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        for key in ("regularMarketPrice", "currentPrice", "previousClose"):
            val = info.get(key)
            if val is not None:
                return float(val)
    except Exception:
        pass
    return None


def lookup_etf(ticker: str) -> EtfLookupResult:
    """Fetch ETF profile and holdings (live → sample → empty)."""
    sym = _normalize_ticker(ticker)
    if not sym:
        raise ValueError("Ticker required")
    holdings, sectors, meta, source = _holdings_from_yfinance(sym)
    static_meta = _STATIC_META.get(sym, {})
    return EtfLookupResult(
        ticker=sym,
        name=str(meta.get("name") or static_meta.get("name") or sym),
        issuer=str(meta.get("issuer") or static_meta.get("issuer") or "—"),
        asset_class=str(meta.get("asset_class") or static_meta.get("asset_class") or "—"),
        category=str(meta.get("category") or static_meta.get("category") or "—"),
        expense_ratio_pct=meta.get("expense_ratio_pct"),
        data_source=source,
        holdings=holdings,
        sectors=sectors,
    )


def portfolio_etf_tickers(holdings_df: pd.DataFrame) -> list[tuple[str, float]]:
    """Return (ticker, portfolio_weight_fraction) for ETF-like rows."""
    if holdings_df is None or holdings_df.empty:
        return []
    out: list[tuple[str, float]] = []
    etf_types = {"Bonds", "REIT", "Dividend ETF", "T-Bills"}
    for _, row in holdings_df.dropna(subset=["Ticker"]).iterrows():
        t = _normalize_ticker(str(row.get("Ticker") or ""))
        if not t:
            continue
        try:
            w = float(row.get("Weight (%)") or 0) / 100.0
        except (TypeError, ValueError):
            w = 0.0
        if w <= 0:
            continue
        at = str(row.get("Asset Type") or "Equity")
        if t in POPULAR_ETF_TICKERS or at in etf_types:
            out.append((t, w))
    return out


def aggregate_underlying_exposure(
    etf_weights: list[tuple[str, float]],
    *,
    holdings_by_etf: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Combine ETF weights into underlying stock/firm exposure."""
    agg: dict[str, dict[str, Any]] = {}
    for etf, port_w in etf_weights:
        h = holdings_by_etf.get(etf)
        if h is None or h.empty:
            continue
        for _, row in h.iterrows():
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            try:
                inner_w = float(row.get("weight") or 0)
            except (TypeError, ValueError):
                inner_w = 0.0
            exp = port_w * inner_w
            if sym not in agg:
                agg[sym] = {
                    "symbol": sym,
                    "name": str(row.get("name") or sym),
                    "sector": str(row.get("sector") or ""),
                    "portfolio_weight": 0.0,
                    "sources": [],
                }
            agg[sym]["portfolio_weight"] += exp
            agg[sym]["sources"].append(etf)
    if not agg:
        return pd.DataFrame()
    df = pd.DataFrame(list(agg.values()))
    df["portfolio_weight_pct"] = df["portfolio_weight"] * 100
    df["sources"] = df["sources"].apply(lambda xs: ", ".join(sorted(set(xs))))
    return df.sort_values("portfolio_weight", ascending=False).reset_index(drop=True)


def concentration_hhi(weights: pd.Series) -> float:
    """Herfindahl index on weight fractions (0–1 scale, higher = more concentrated)."""
    w = weights.fillna(0).astype(float)
    total = w.sum()
    if total <= 0:
        return 0.0
    p = w / total
    return float((p**2).sum())


def pairwise_etf_overlap(h1: pd.DataFrame, h2: pd.DataFrame) -> float:
    """Sum of min inner weights for shared symbols (0–1)."""
    if h1.empty or h2.empty:
        return 0.0
    a = {str(r["symbol"]).upper(): float(r["weight"]) for _, r in h1.iterrows()}
    b = {str(r["symbol"]).upper(): float(r["weight"]) for _, r in h2.iterrows()}
    shared = set(a) & set(b)
    return sum(min(a[s], b[s]) for s in shared)


def overlap_warnings(
    etf_tickers: list[str],
    holdings_by_etf: dict[str, pd.DataFrame],
    *,
    threshold: float = 0.35,
) -> list[str]:
    warnings: list[str] = []
    for i, t1 in enumerate(etf_tickers):
        for t2 in etf_tickers[i + 1 :]:
            ov = pairwise_etf_overlap(holdings_by_etf.get(t1, pd.DataFrame()), holdings_by_etf.get(t2, pd.DataFrame()))
            if ov >= threshold:
                warnings.append(
                    f"**{t1}** and **{t2}** share about **{ov * 100:.0f}%** overlapping holdings — consider diversifying."
                )
    return warnings
