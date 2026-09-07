"""Benchmark & alternative comparison panel (market-reference series).

Not the Health objective policy benchmark (SPY/AGG/BIL objective mix).
Compares the static-weight portfolio model to simple market alternatives.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
import streamlit as st

import dashboard_charts as charts
import portfolio_core as core
from components.ui_helpers import APP_DISCLAIMER, format_money


def _section(title: str, lead: str = "") -> None:
    st.markdown(f"#### {title}")
    if lead:
        st.caption(lead)


def _pct(x: float) -> str:
    return f"{float(x) * 100:.2f}%"


def build_market_alternative_comparison_returns(
    portfolio_returns: pd.Series,
    comparison_asset_returns: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the comparison return frame for market alternatives.

    Series identities (not the Health policy benchmark):
    - Current Portfolio — static current weights backtest
    - SPY — equity market reference
    - QQQ — growth/tech market reference
    - 60/40 SPY/AGG — simple stock/bond alternative
    - T-Bills / BIL — cash-like alternative
    """
    if portfolio_returns is None or len(portfolio_returns) == 0:
        raise ValueError("portfolio_returns are empty.")
    if comparison_asset_returns is None or comparison_asset_returns.empty:
        raise ValueError("comparison_asset_returns are empty.")

    col_map = {str(c).strip().upper(): c for c in comparison_asset_returns.columns}
    required = ("SPY", "QQQ", "AGG", "BIL")
    missing = [s for s in required if s not in col_map]
    if missing:
        raise ValueError(f"comparison returns missing columns: {missing}")

    spy = comparison_asset_returns[col_map["SPY"]]
    qqq = comparison_asset_returns[col_map["QQQ"]]
    agg = comparison_asset_returns[col_map["AGG"]]
    bil = comparison_asset_returns[col_map["BIL"]]
    synth_6040 = spy * 0.60 + agg * 0.40

    frame = pd.DataFrame(
        {
            "Current Portfolio": portfolio_returns,
            "SPY (market reference)": spy,
            "QQQ (market reference)": qqq,
            "60/40 SPY/AGG (simple alt.)": synth_6040,
            "T-Bills / BIL (cash-like alt.)": bil,
        }
    )
    return frame.dropna()


def run_market_alternative_comparison(
    portfolio_returns: pd.Series,
    comparison_asset_returns: pd.DataFrame,
    *,
    initial_value: float,
    risk_free_rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute metrics table + growth frame (ticker-aligned portfolio series required)."""
    benchmark_returns = build_market_alternative_comparison_returns(
        portfolio_returns, comparison_asset_returns
    )
    return core.benchmark_comparison(
        benchmark_returns,
        float(initial_value),
        float(risk_free_rate),
    )


def ending_value_column_name(initial_value: float) -> str:
    return f"Growth of ${float(initial_value):,.0f}"


def render_benchmark_alternative_comparison(
    *,
    returns: pd.DataFrame,
    weights: np.ndarray,
    tickers: list[str],
    settings: dict[str, Any],
    load_comparison_prices: Callable[[str, str | None], pd.DataFrame],
    compute_daily_returns: Callable[[pd.DataFrame], pd.DataFrame],
    key_prefix: str = "benchmark_alt",
    section_title: str = "Benchmark & Alternative Comparison",
    as_expander: bool = False,
    expander_label: str | None = None,
    expander_expanded: bool = True,
) -> None:
    """
    Shared UI for market-alternative comparison.

    Used by Advanced Portfolio Analytics (primary) and legacy Overview (if reached).
    """
    initial_value = float(settings["initial_value"])
    start = settings["start"]
    end = settings.get("end")
    risk_free = float(settings["risk_free"])
    run_key = f"{key_prefix}_run"
    btn_key = f"{key_prefix}_run_btn"

    def _body() -> None:
        if as_expander:
            _section(
                "Compare to simple alternatives",
                "Static-weight model vs SPY, QQQ, a simple 60/40, and cash-like T-Bills. "
                "These are market-reference alternatives — not the Health objective policy "
                "benchmark (objective-weighted SPY/AGG/BIL).",
            )
        else:
            st.caption(
                "Static-weight model vs SPY, QQQ, a simple 60/40, and cash-like T-Bills. "
                "These are market-reference alternatives — not the Health objective policy "
                "benchmark (objective-weighted SPY/AGG/BIL)."
            )
        st.caption(
            f"Educational comparison only. {APP_DISCLAIMER} "
            "Does not use the transaction ledger; deposits are not counted as return."
        )
        if st.button("Run Benchmark Comparison", key=btn_key):
            st.session_state[run_key] = True

        if not st.session_state.get(run_key, False):
            st.caption("Click **Run Benchmark Comparison** to load.")
            return

        with st.spinner("Loading benchmark comparison…"):
            ticker_labels = [str(t).strip().upper() for t in tickers]
            port_rets = core.portfolio_daily_returns(
                returns, weights, tickers=ticker_labels
            )
            comp_prices = load_comparison_prices(start, end)
            comp_returns_raw = compute_daily_returns(comp_prices)
            table, growth = run_market_alternative_comparison(
                port_rets,
                comp_returns_raw,
                initial_value=initial_value,
                risk_free_rate=risk_free,
            )

        btab = table.copy()
        for col in ["Annual Return", "Volatility", "Sharpe Ratio", "Max Drawdown", "CAGR"]:
            if col not in btab.columns:
                continue
            if col != "Sharpe Ratio":
                btab[col] = btab[col].map(_pct)
            else:
                btab[col] = btab[col].map(lambda x: f"{float(x):.2f}")

        growth_col = ending_value_column_name(initial_value)
        if growth_col in btab.columns:
            btab[growth_col] = btab[growth_col].map(format_money)
        else:
            # Tolerate older column name if present.
            legacy = next(
                (c for c in btab.columns if str(c).startswith("Growth of $")),
                None,
            )
            if legacy:
                btab[legacy] = btab[legacy].map(format_money)

        st.caption(
            f"Starting capital for this comparison: **{format_money(initial_value)}**. "
            "**Current Portfolio** uses your current ticker weights over the historical lookback. "
            "**SPY / QQQ** = market references; **60/40** and **T-Bills** = simple alternatives. "
            "Health policy delivery uses a separate objective-weighted SPY/AGG/BIL series."
        )
        st.dataframe(btab, use_container_width=True, hide_index=True)
        gcmp = growth.reset_index().rename(columns={"index": "Date"})
        if "Date" not in gcmp.columns:
            gcmp["Date"] = growth.index
        st.plotly_chart(charts.benchmark_growth_chart(gcmp), use_container_width=True)

    if as_expander:
        label = expander_label or section_title
        with st.expander(label, expanded=expander_expanded):
            _body()
    else:
        st.markdown("---")
        _section(section_title)
        _body()


__all__ = [
    "build_market_alternative_comparison_returns",
    "ending_value_column_name",
    "render_benchmark_alternative_comparison",
    "run_market_alternative_comparison",
]
