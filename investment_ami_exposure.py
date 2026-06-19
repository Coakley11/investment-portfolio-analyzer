"""Portfolio exposure attribution for Investment AMI (direct vs embedded sleeves)."""

from __future__ import annotations

from typing import Any

# Dedicated technology / growth ETF sleeves (portfolio weight = direct tech exposure).
DIRECT_TECH_ETFS = frozenset(
    {
        "QQQ",
        "VGT",
        "XLK",
        "FTEC",
        "IGV",
        "SMH",
        "SOXX",
        "ARKK",
        "TQQQ",
        "TECL",
        "MGK",
        "VUG",
    }
)

# Approximate technology sector weight inside common ETFs (% of fund, not portfolio).
# Used when live holdings/sectors are unavailable (static fallback).
_STATIC_ETF_TECH_WEIGHT_PCT: dict[str, float] = {
    "VTI": 29.0,
    "VOO": 32.0,
    "SPY": 32.0,
    "IVV": 32.0,
    "QQQ": 95.0,
    "VGT": 98.0,
    "XLK": 98.0,
    "FTEC": 98.0,
    "SCHD": 16.0,
    "VYM": 12.0,
    "VNQ": 2.0,
    "BND": 0.0,
    "AGG": 0.0,
    "TLT": 0.0,
    "BIL": 0.0,
    "VXUS": 10.0,
}


def _is_technology_sector(sector: str) -> bool:
    s = str(sector or "").strip().lower()
    return s in {"technology", "information technology", "tech"} or "technology" in s


def _tech_weight_in_etf(ticker: str) -> float | None:
    """Technology sector weight inside an ETF (% of fund, 0–100)."""
    sym = str(ticker or "").strip().upper()
    if not sym:
        return None
    if sym in DIRECT_TECH_ETFS:
        return 100.0
    try:
        import etf_holdings as eh

        result = eh.lookup_etf(sym)
        sectors = result.sectors
        if sectors is not None and not sectors.empty:
            tech = 0.0
            for _, row in sectors.iterrows():
                label = str(row.get("sector") or row.get("Sector") or row.index[0] if hasattr(row, "index") else "")
                if _is_technology_sector(label):
                    try:
                        tech += float(row.get("weight") or row.get("Weight") or 0) * 100.0
                    except (TypeError, ValueError):
                        pass
            if tech > 0:
                return min(tech, 100.0)
        holdings = result.holdings
        if holdings is not None and not holdings.empty and "sector" in holdings.columns:
            tech_inner = 0.0
            for _, row in holdings.iterrows():
                if _is_technology_sector(str(row.get("sector") or "")):
                    try:
                        w = float(row.get("weight") or 0)
                        tech_inner += w * 100.0 if w <= 1.0 else w
                    except (TypeError, ValueError):
                        pass
            if tech_inner > 0:
                return min(tech_inner, 100.0)
    except Exception:
        pass
    fallback = _STATIC_ETF_TECH_WEIGHT_PCT.get(sym)
    return float(fallback) if fallback is not None else None


def build_tech_exposure_from_weights(weights: dict[str, Any] | list[tuple[str, float]]) -> dict[str, Any]:
    """
    Compute direct vs embedded technology exposure for portfolio weights.

    Returns dict with direct_pct, embedded_pct, total_pct, and per-fund contributions.
    """
    rows: list[tuple[str, float]] = []
    if isinstance(weights, dict):
        for ticker, wt in weights.items():
            text = str(wt or "").replace("%", "").strip()
            try:
                pct = float(text)
            except (TypeError, ValueError):
                continue
            sym = str(ticker or "").strip().upper()
            if sym and pct > 0:
                rows.append((sym, pct))
    elif isinstance(weights, list):
        rows = [(str(t).upper(), float(p)) for t, p in weights if str(t).strip() and float(p) > 0]

    direct_pct = 0.0
    embedded_pct = 0.0
    direct_holdings: list[dict[str, Any]] = []
    embedded_holdings: list[dict[str, Any]] = []

    for sym, port_w in rows:
        if sym in DIRECT_TECH_ETFS:
            direct_pct += port_w
            direct_holdings.append({"ticker": sym, "portfolio_weight_pct": round(port_w, 1)})
            continue
        tech_in_fund = _tech_weight_in_etf(sym)
        if tech_in_fund is None or tech_in_fund <= 0:
            continue
        contribution = port_w * (tech_in_fund / 100.0)
        embedded_pct += contribution
        embedded_holdings.append(
            {
                "ticker": sym,
                "portfolio_weight_pct": round(port_w, 1),
                "tech_weight_in_fund_pct": round(tech_in_fund, 1),
                "contribution_pct": round(contribution, 2),
            }
        )

    embedded_holdings.sort(key=lambda x: float(x.get("contribution_pct") or 0), reverse=True)
    total = direct_pct + embedded_pct
    return {
        "direct_pct": round(direct_pct, 2),
        "embedded_pct": round(embedded_pct, 2),
        "total_pct": round(total, 2),
        "direct_holdings": direct_holdings,
        "embedded_holdings": embedded_holdings[:8],
    }


def format_tech_exposure_calculation_chain(exposure: dict[str, Any]) -> str:
    """Render portfolio tech exposure as explicit weight × fund-tech% derivations."""
    if not isinstance(exposure, dict):
        return ""
    lines: list[str] = []
    for h in exposure.get("direct_holdings") or []:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("ticker") or "").upper()
        pw = float(h.get("portfolio_weight_pct") or 0)
        if sym and pw > 0:
            lines.append(f"**{sym}** {pw:.1f}% × 100% (direct tech sleeve) = **{pw:.1f}%**")
    for h in exposure.get("embedded_holdings") or []:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("ticker") or "").upper()
        pw = float(h.get("portfolio_weight_pct") or 0)
        tw = float(h.get("tech_weight_in_fund_pct") or 0)
        contrib = float(h.get("contribution_pct") or 0)
        if sym and pw > 0 and tw > 0:
            lines.append(f"**{sym}** {pw:.1f}% × {tw:.1f}% = **{contrib:.1f}%**")
    total = float(exposure.get("total_pct") or 0)
    if lines:
        lines.append(f"**Total technology exposure ≈ {total:.1f}%**")
    return "\n".join(lines)


def format_portfolio_weights_table(rows: list[tuple[str, float]]) -> str:
    if not rows:
        return "- (no holdings)"
    return "\n".join(f"- **{t}** {p:.1f}%" for t, p in rows)


def resolve_tech_exposure(ctx: dict[str, Any]) -> dict[str, Any]:
    """Use precomputed context or derive from current_weights / holdings."""
    pre = ctx.get("tech_exposure")
    if isinstance(pre, dict) and pre.get("total_pct") is not None:
        return dict(pre)
    weights = ctx.get("current_weights")
    if isinstance(weights, dict) and weights:
        return build_tech_exposure_from_weights(weights)
    holdings = ctx.get("holdings")
    if isinstance(holdings, list) and holdings:
        even = 100.0 / max(len(holdings), 1)
        return build_tech_exposure_from_weights([(str(t), even) for t in holdings[:12]])
    return {
        "direct_pct": 0.0,
        "embedded_pct": 0.0,
        "total_pct": 0.0,
        "direct_holdings": [],
        "embedded_holdings": [],
    }
