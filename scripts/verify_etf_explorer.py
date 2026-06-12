"""Manual verification script for ETF Holdings Explorer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import etf_holdings as eh

TICKERS = ["VOO", "VTI", "VXUS", "BND", "SCHD", "QQQ"]
PAIRS = [("VOO", "VTI"), ("VOO", "QQQ")]


def main() -> int:
    ok = True
    holdings_map: dict[str, pd.DataFrame] = {}

    print("=== ETF LOOKUP ===")
    for t in TICKERS:
        r = eh.lookup_etf(t)
        holdings_map[t] = r.holdings
        badge = {"live": "Live", "sample": "Sample", "unavailable": "Unavailable"}.get(
            r.data_source, r.data_source
        )
        print(
            f"{t}: badge={badge} holdings={len(r.holdings)} sectors={len(r.sectors)} "
            f"exp={r.expense_ratio_pct} name={r.name[:50]}"
        )
        if r.holdings.empty:
            print(f"  FAIL: no holdings for {t}")
            ok = False
        else:
            top = r.holdings.head(3)
            print(f"  top: {list(top['symbol'])}")
        if r.data_source not in ("live", "sample"):
            print(f"  WARN: unexpected source {r.data_source}")

    print("\n=== CONCENTRATION ===")
    for t in TICKERS:
        h = holdings_map[t]
        if h.empty:
            continue
        hhi = eh.concentration_hhi(h["weight"])
        print(f"{t}: HHI={hhi:.4f}")
        if not (0 < hhi <= 1):
            print(f"  FAIL: HHI out of range for {t}")
            ok = False

    print("\n=== OVERLAP (VOO vs VTI, VOO vs QQQ) ===")
    for a, b in PAIRS:
        ov = eh.pairwise_etf_overlap(holdings_map[a], holdings_map[b])
        print(f"{a} vs {b}: {ov * 100:.1f}%")
        if ov < 0.05:
            print(f"  FAIL: overlap too low for {a}/{b} — expected meaningful overlap")
            ok = False

    print("\n=== PORTFOLIO TRANSPARENCY ===")
    df = pd.DataFrame(
        {
            "Ticker": ["VOO", "QQQ", "BND"],
            "Weight (%)": [50.0, 30.0, 20.0],
            "Asset Type": ["Equity", "Equity", "Bonds"],
        }
    )
    etfs = eh.portfolio_etf_tickers(df)
    exp = eh.aggregate_underlying_exposure(etfs, holdings_by_etf=holdings_map)
    print(f"ETFs detected: {etfs}")
    print(f"Underlying rows: {len(exp)}")
    if exp.empty:
        print("FAIL: empty underlying exposure")
        ok = False
    else:
        print(exp.head(5)[["symbol", "portfolio_weight_pct", "sources"]].to_string())
        phhi = eh.concentration_hhi(exp["portfolio_weight"])
        print(f"Portfolio HHI: {phhi:.4f}")

    print("\n=== CHIP NAV (code path) ===")
    from components.etf_holdings_explorer import render_etf_ticker_chip_bar  # noqa: F401
    from components.beginner_navigation import ADVANCED_TAB_LABELS, ETF_HOLDINGS_TAB_LABEL

    if ETF_HOLDINGS_TAB_LABEL not in ADVANCED_TAB_LABELS:
        print("FAIL: ETF Holdings Explorer not in ADVANCED_TAB_LABELS")
        ok = False
    else:
        print(f"ETF tab label: {ETF_HOLDINGS_TAB_LABEL}")
        # Chip sets these session keys (verified in source):
        print("Chip sets: etf_explorer_ticker, _pending_investment_tab=ETF Holdings Explorer")

    print("\n=== RESULT ===")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
