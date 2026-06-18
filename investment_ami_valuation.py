"""Valuation attribution and analyst framing for Investment AMI Phase 2b."""

from __future__ import annotations

import re
from typing import Any

# Approximate trailing P/E and style when live data is unavailable.
_STATIC_VALUATION: dict[str, dict[str, Any]] = {
    "VOO": {"pe": 24.5, "style": "broad", "category": "Large Blend", "name": "Vanguard S&P 500 ETF"},
    "VTI": {"pe": 24.0, "style": "broad", "category": "Large Blend", "name": "Vanguard Total Stock Market ETF"},
    "SPY": {"pe": 24.5, "style": "broad", "category": "Large Blend", "name": "SPY"},
    "IVV": {"pe": 24.5, "style": "broad", "category": "Large Blend", "name": "iShares Core S&P 500 ETF"},
    "QQQ": {"pe": 31.0, "style": "growth", "category": "Large Growth", "name": "Invesco QQQ Trust"},
    "VGT": {"pe": 33.0, "style": "growth", "category": "Technology", "name": "Vanguard Information Technology ETF"},
    "SCHD": {"pe": 16.5, "style": "dividend", "category": "Large Value", "name": "Schwab U.S. Dividend Equity ETF"},
    "VYM": {"pe": 17.0, "style": "dividend", "category": "Large Value", "name": "Vanguard High Dividend Yield ETF"},
    "VNQ": {"pe": 18.0, "style": "reit", "category": "Real Estate", "name": "Vanguard Real Estate ETF"},
    "VXUS": {"pe": 14.5, "style": "international", "category": "Foreign Large Blend", "name": "Vanguard Total International Stock ETF"},
    "BND": {"pe": None, "style": "bond", "category": "Bond", "name": "Vanguard Total Bond Market ETF"},
}

# Fair P/E bands by fund style (trailing P/E, illustrative).
_STYLE_PE_BANDS: dict[str, tuple[float, float, float]] = {
    "broad": (16.0, 20.0, 24.0),  # cheap, fair, expensive thresholds
    "dividend": (13.0, 16.5, 20.0),
    "growth": (22.0, 28.0, 32.0),
    "international": (11.0, 14.0, 17.0),
    "reit": (14.0, 17.0, 20.0),
}

_KNOWN_TICKERS = frozenset(_STATIC_VALUATION.keys()) | frozenset(
    {"XLK", "FTEC", "MGK", "VUG", "VTV", "IWM", "ARKK", "SMH", "SOXX"}
)

_VALUATION_SHIFTS = {"Cheap": 0.02, "Fair Value": 0.0, "Expensive": -0.015, "Bubble-like": -0.03}
_VALUATION_VOL = {"Cheap": 0.95, "Fair Value": 1.0, "Expensive": 1.08, "Bubble-like": 1.15}


def _normalize_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def tickers_mentioned_in_question(question: str) -> list[str]:
    q = re.sub(r"[^A-Z0-9 ]", " ", str(question or "").upper())
    return [t for t in sorted(_KNOWN_TICKERS, key=len, reverse=True) if re.search(rf"\b{t}\b", q)]


def _lookup_live_pe(ticker: str) -> float | None:
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        for key in ("trailingPE", "forwardPE"):
            raw = info.get(key)
            if raw is not None:
                val = float(raw)
                if 3.0 < val < 200.0:
                    return round(val, 1)
    except Exception:
        pass
    return None


def lookup_ticker_valuation(ticker: str) -> dict[str, Any]:
    """Return valuation snapshot for a ticker (live P/E when available, else static)."""
    sym = _normalize_ticker(ticker)
    static = dict(_STATIC_VALUATION.get(sym) or {})
    live_pe = _lookup_live_pe(sym)
    pe = live_pe if live_pe is not None else static.get("pe")
    style = str(static.get("style") or "broad")
    if sym in {"QQQ", "VGT", "XLK", "FTEC", "MGK", "VUG", "ARKK", "SMH", "SOXX"}:
        style = "growth"
    elif sym in {"SCHD", "VYM", "VTV"}:
        style = "dividend"
    elif sym in {"VNQ"}:
        style = "reit"
    elif sym in {"BND", "AGG", "TLT", "BIL"}:
        style = "bond"
    return {
        "ticker": sym,
        "name": static.get("name") or sym,
        "category": static.get("category") or "Equity ETF",
        "style": style,
        "pe": pe,
        "pe_source": "live" if live_pe is not None else ("static" if pe is not None else "none"),
    }


def _earnings_yield_pct(pe: float | None) -> float | None:
    if pe is None or pe <= 0:
        return None
    return round(100.0 / pe, 2)


def _style_richness_label(pe: float, style: str) -> str:
    bands = _STYLE_PE_BANDS.get(style, _STYLE_PE_BANDS["broad"])
    cheap, fair, expensive = bands
    if pe <= cheap:
        return "cheap"
    if pe <= fair:
        return "fairly valued"
    if pe <= expensive:
        return "moderately rich"
    return "expensive"


def _macro_adjust_label(base: str, macro_env: str) -> str:
    env = str(macro_env or "Fair Value").strip()
    if env == "Cheap" and base in {"moderately rich", "expensive"}:
        return "fairly valued"
    if env in {"Expensive", "Bubble-like"} and base in {"fairly valued", "moderately rich"}:
        return "moderately rich" if base == "fairly valued" else "expensive"
    if env == "Bubble-like" and base == "fairly valued":
        return "moderately rich"
    return base


def implied_growth_rate_pct(pe: float | None, *, required_return_pct: float = 10.0) -> float | None:
    """
    Educational implied growth estimate from P/E.

    Uses earnings yield vs required return: if market prices E/P below required return,
    implied growth fills the gap (simplified Gordon-style intuition).
    """
    ey = _earnings_yield_pct(pe)
    if ey is None:
        return None
    # earnings yield + expected growth ≈ required return (simplified)
    return round(max(-5.0, min(25.0, required_return_pct - ey)), 1)


def assess_valuation_richness(
    ticker_data: dict[str, Any],
    *,
    macro_env: str = "Fair Value",
) -> dict[str, Any]:
    pe = ticker_data.get("pe")
    style = str(ticker_data.get("style") or "broad")
    if style == "bond":
        return {
            "label": "not applicable",
            "headline": "Bond funds are not valued on equity P/E — use yield and rate sensitivity instead.",
            "earnings_yield_pct": None,
            "implied_growth_pct": None,
        }
    if pe is None:
        return {
            "label": "unknown",
            "headline": "P/E data unavailable — frame valuation using style and macro environment.",
            "earnings_yield_pct": None,
            "implied_growth_pct": None,
        }
    base = _style_richness_label(float(pe), style)
    label = _macro_adjust_label(base, macro_env)
    ey = _earnings_yield_pct(float(pe))
    impl_g = implied_growth_rate_pct(float(pe))
    cheap, fair, expensive = _STYLE_PE_BANDS.get(style, _STYLE_PE_BANDS["broad"])
    headlines = {
        "cheap": f"appears **cheap** for a {style} fund (P/E **{pe:.1f}** vs typical fair band ~**{fair:.0f}**).",
        "fairly valued": f"appears **fairly valued** for a {style} fund (P/E **{pe:.1f}** near typical ~**{fair:.0f}**).",
        "moderately rich": f"looks **moderately rich** (P/E **{pe:.1f}** above typical ~**{fair:.0f}** for {style} funds).",
        "expensive": f"looks **expensive** vs {style} history (P/E **{pe:.1f}** well above ~**{expensive:.0f}**).",
    }
    return {
        "label": label,
        "headline": headlines.get(label, headlines["fairly valued"]),
        "earnings_yield_pct": ey,
        "implied_growth_pct": impl_g,
        "fair_pe_mid": fair,
    }


def valuation_sensitivity(
    pe: float | None,
    *,
    style: str = "broad",
    growth_shift_pct: float = 2.0,
) -> list[dict[str, str]]:
    """What-if bands for growth assumption changes."""
    if pe is None or pe <= 0:
        return []
    base_g = implied_growth_rate_pct(pe) or 5.0
    fair = _STYLE_PE_BANDS.get(style, _STYLE_PE_BANDS["broad"])[1]
    rows = [
        {
            "scenario": f"Growth expectations fall {growth_shift_pct:.0f}%",
            "impact": f"P/E could compress toward ~{max(fair - 2, 12):.0f}–{fair:.0f} if earnings hold — price downside risk rises.",
        },
        {
            "scenario": f"Growth expectations rise {growth_shift_pct:.0f}%",
            "impact": f"Higher implied growth (~{base_g + growth_shift_pct:.1f}%) could support a richer P/E — upside depends on delivery.",
        },
        {
            "scenario": "Macro valuation shifts to Expensive",
            "impact": "Broad market multiples often compress — even fairly priced funds can lag if sentiment turns.",
        },
    ]
    return rows


def resolve_valuation_target(question: str, ctx: dict[str, Any]) -> str | None:
    mentioned = tickers_mentioned_in_question(question)
    if mentioned:
        return mentioned[0]
    weights = ctx.get("current_weights") or {}
    if isinstance(weights, dict):
        equity_rows: list[tuple[str, float]] = []
        for t, w in weights.items():
            sym = _normalize_ticker(str(t))
            if sym in {"BND", "AGG", "TLT", "BIL", "SCHZ", "IEF"}:
                continue
            pct = None
            try:
                pct = float(str(w).replace("%", "").strip())
            except (TypeError, ValueError):
                pass
            if sym and pct and pct > 0:
                equity_rows.append((sym, pct))
        if equity_rows:
            equity_rows.sort(key=lambda x: x[1], reverse=True)
            return equity_rows[0][0]
    holdings = ctx.get("holdings")
    if isinstance(holdings, list) and holdings:
        for h in holdings:
            sym = _normalize_ticker(str(h))
            if sym and sym not in {"BND", "AGG", "TLT", "BIL"}:
                return sym
    return None


def portfolio_equity_pct(ctx: dict[str, Any]) -> float:
    rows: list[tuple[str, float]] = []
    weights = ctx.get("current_weights") or {}
    if isinstance(weights, dict):
        for t, w in weights.items():
            try:
                pct = float(str(w).replace("%", "").strip())
            except (TypeError, ValueError):
                continue
            sym = _normalize_ticker(str(t))
            if sym and pct > 0:
                rows.append((sym, pct))
    if not rows:
        return 70.0
    bond = sum(p for t, p in rows if t in {"BND", "AGG", "TLT", "BIL", "SCHZ", "IEF"})
    return max(0.0, 100.0 - bond)


def macro_valuation_effects(macro_env: str, equity_pct: float) -> dict[str, Any]:
    env = str(macro_env or "Fair Value").strip() or "Fair Value"
    profile = {"equity": equity_pct / 100.0, "bonds": 0.0, "reit": 0.0, "tbills": 0.0}
    shift = _VALUATION_SHIFTS.get(env, 0.0) * profile["equity"]
    vol_mult = _VALUATION_VOL.get(env, 1.0)
    return {
        "environment": env,
        "equity_return_shift_pct": round(shift * 100, 2),
        "volatility_multiplier": vol_mult,
    }


def resolve_valuation_context(question: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """Build valuation context for structured answers."""
    macro_env = str(
        ctx.get("health_valuation")
        or (ctx.get("scenario_params") or {}).get("valuation_environment")
        or "Fair Value"
    ).strip()
    target = resolve_valuation_target(question, ctx)
    ticker_data = lookup_ticker_valuation(target) if target else {}
    assessment = assess_valuation_richness(ticker_data, macro_env=macro_env) if ticker_data else {}
    equity_pct = portfolio_equity_pct(ctx)
    macro_fx = macro_valuation_effects(macro_env, equity_pct)
    pe = ticker_data.get("pe")
    style = str(ticker_data.get("style") or "broad")
    return {
        "target_ticker": target,
        "ticker_data": ticker_data,
        "assessment": assessment,
        "macro_env": macro_env,
        "macro_effects": macro_fx,
        "equity_pct": equity_pct,
        "sensitivity": valuation_sensitivity(pe, style=style) if pe else [],
        "portfolio_weight_pct": _portfolio_weight_for_ticker(target, ctx) if target else None,
    }


def _portfolio_weight_for_ticker(ticker: str | None, ctx: dict[str, Any]) -> float | None:
    if not ticker:
        return None
    sym = _normalize_ticker(ticker)
    weights = ctx.get("current_weights") or {}
    if isinstance(weights, dict):
        for t, w in weights.items():
            if _normalize_ticker(str(t)) == sym:
                try:
                    return float(str(w).replace("%", "").strip())
                except (TypeError, ValueError):
                    return None
    return None
