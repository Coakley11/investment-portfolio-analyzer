"""ETF overlap pair resolution for instant engines (uses P0 market data via ``etf_holdings``)."""

from __future__ import annotations

import re
from typing import Any


def tickers_mentioned_in_question(question: str) -> list[str]:
    q = re.sub(r"[^A-Z0-9 ]", " ", str(question or "").upper())
    known = ("VOO", "QQQ", "VTI", "SPY", "IVV", "SCHD", "VYM", "VNQ", "BND", "VXUS", "VGT", "MGK")
    return [t for t in known if re.search(rf"\b{t}\b", q)]


def compute_pairwise_overlap_pct(ticker_a: str, ticker_b: str) -> float | None:
    """Return overlap percentage (0–100) using ``lookup_etf`` → ``MarketDataProvider``."""
    t1 = str(ticker_a or "").strip().upper()
    t2 = str(ticker_b or "").strip().upper()
    if not t1 or not t2:
        return None
    try:
        import etf_holdings as eh

        h1 = eh.lookup_etf(t1).holdings
        h2 = eh.lookup_etf(t2).holdings
        return float(eh.pairwise_etf_overlap(h1, h2) * 100)
    except Exception:
        return None


def resolve_etf_overlap_pairs(
    context: dict[str, Any],
    *,
    question: str = "",
) -> list[dict[str, Any]]:
    """
    Merge context ``etf_overlap_pairs`` with live pairwise lookup when the question names two ETFs.
    """
    pairs = context.get("etf_overlap_pairs")
    mentioned = tickers_mentioned_in_question(question)

    if isinstance(pairs, list) and mentioned and len(mentioned) >= 2:
        for p in pairs:
            pair_str = str(p.get("pair") or "")
            if mentioned[0] in pair_str and mentioned[1] in pair_str:
                pairs = [p] + [x for x in pairs if x is not p]
                break
        else:
            ov = compute_pairwise_overlap_pct(mentioned[0], mentioned[1])
            if ov is not None:
                t1, t2 = mentioned[0], mentioned[1]
                pairs = [{"pair": f"{t1}/{t2}", "overlap_pct": round(ov, 1)}] + list(pairs or [])

    if isinstance(pairs, list):
        return [p for p in pairs if isinstance(p, dict)]
    return []
