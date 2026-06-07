"""Shared UI helpers for beginner-friendly copy and layout."""

from __future__ import annotations

import datetime as dt
from typing import Any

import streamlit as st

APP_DISCLAIMER = "Educational model-based analysis, not financial advice."

HISTORICAL_PERIOD_HELP_BEGINNER = """
**Historical analysis period**

These dates determine which historical market data is used to estimate:

- Returns
- Volatility
- Risk
- Correlations
- Monte Carlo assumptions
- Optimization inputs

They do **not** determine when you invest.

They only determine which historical period is used as the baseline for analysis.
""".strip()

HISTORICAL_PERIOD_HELP_ADVANCED = (
    "Start and end of the price download window. Returns, risk, correlations, "
    "Portfolio Health, forward macro, Monte Carlo, optimizer, and frontier all "
    "use daily returns from this range as the historical baseline."
)

HISTORICAL_LOOKBACK_DATE_HELP = (
    "These dates define the historical market data used for return, volatility, "
    "correlation, and risk calculations."
)

HISTORICAL_PERIOD_DATE_INPUT_HELP = HISTORICAL_LOOKBACK_DATE_HELP

HISTORICAL_METRICS_BANNER_BODY = (
    "The return, volatility, Sharpe ratio, drawdown, and correlation metrics below are "
    "calculated using the selected historical lookback period and current portfolio weights.\n\n"
    "Macro assumptions do **not** change these historical metrics."
)

MACRO_ASSUMPTIONS_BANNER_AFFECTS = (
    "Health Score",
    "Recommendations",
    "Forward Projections",
    "Monte Carlo (Forward Mode)",
    "Frontier / Optimizer (Forward Mode)",
)

MACRO_ASSUMPTIONS_BANNER_UNAFFECTED = (
    "Historical Return",
    "Historical Volatility",
    "Historical Sharpe Ratio",
    "Historical Drawdown",
)

BEGINNER_METRIC_HELP = {
    "annual_return": "How much your portfolio grew per year on average over the period you selected.",
    "volatility": "How much your portfolio tends to move up and down. Higher = a bumpier ride.",
    "sharpe": "Whether the return you're getting is worth the amount of risk you're taking. Higher is generally better.",
    "sortino": "Like the risk/reward score above, but focuses more on bad drops than normal ups and downs.",
    "drawdown": "The largest drop from a previous high point. Helps you imagine a worst-case dip.",
    "cagr": "Average yearly growth if your gains compounded smoothly over time.",
    "beta": "How much your portfolio moves compared to the broad market (SPY). About 1.0 = similar to the market.",
    "projected": "A simple one-year estimate based on past patterns — not a guarantee.",
}

TECHNICAL_METRIC_HELP = {
    "annual_return": "Annualized mean daily return over the selected window.",
    "volatility": "Annualized standard deviation of daily returns.",
    "sharpe": "Return per unit of total risk. Above ~1.0 is strong.",
    "sortino": "Like Sharpe, but penalizes only downside volatility.",
    "drawdown": "Largest peak-to-trough decline over the analysis period.",
    "cagr": "Compound annual growth rate.",
    "beta": "Sensitivity vs SPY: 1.0 moves with the market; >1 is more aggressive.",
    "projected": "One-year projection from historical return/vol assumptions.",
}


PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY = "pending_sidebar_portfolio_value"


def apply_pending_sidebar_portfolio_value() -> None:
    """Apply a deferred portfolio value update before the sidebar number_input is drawn."""
    if PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY in st.session_state:
        st.session_state["sidebar_portfolio_value"] = st.session_state.pop(
            PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY
        )


def request_sidebar_portfolio_value(value: int | float) -> None:
    """Queue portfolio value change for the next run (avoids Streamlit widget key conflict)."""
    st.session_state[PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY] = int(value)


def is_beginner_mode(settings: dict) -> bool:
    return settings.get("experience", "Beginner Mode") == "Beginner Mode"


def metric_help(settings: dict) -> dict[str, str]:
    return BEGINNER_METRIC_HELP if is_beginner_mode(settings) else TECHNICAL_METRIC_HELP


def coach_card(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div style="background:linear-gradient(90deg,rgba(77,163,255,0.12) 0%,rgba(20,28,43,0.9) 100%);
        border:1px solid rgba(77,163,255,0.35);border-left:4px solid #4da3ff;border-radius:10px;
        padding:0.85rem 1rem;margin-bottom:0.85rem;">
        <div style="font-weight:600;color:#f1f5f9;margin-bottom:0.35rem;">{title}</div>
        <div style="color:#cbd5e1;font-size:0.9rem;line-height:1.5;">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def historical_window_years(start: dt.date, end: dt.date) -> float:
    if end <= start:
        return 0.0
    return (end - start).days / 365.25


def format_historical_window_label(start: dt.date, end: dt.date) -> str:
    years = historical_window_years(start, end)
    return f"{start.strftime('%b %Y')} → {end.strftime('%b %Y')} ({years:.1f} years)"


def render_historical_window_summary(*, start: dt.date, end: dt.date, container: Any | None = None) -> None:
    """Active lookback summary near sidebar date controls."""
    target = container or st.sidebar
    label = format_historical_window_label(start, end)
    target.markdown(
        f"""
        <div style="background:rgba(77,163,255,0.08);border:1px solid rgba(77,163,255,0.35);
        border-radius:8px;padding:0.55rem 0.7rem;margin:0.35rem 0 0.5rem 0;">
        <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;">
        Historical Window</div>
        <div style="font-weight:600;color:#e2e8f0;font-size:0.92rem;margin-top:0.15rem;">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_historical_metrics_banner(*, container: Any | None = None) -> None:
    """Banner on Overview, Analyze, and Portfolio Health for historical headline metrics."""
    target = container or st
    target.markdown("#### Historical Metrics")
    target.info(HISTORICAL_METRICS_BANNER_BODY)


def render_macro_assumptions_banner(*, container: Any | None = None) -> None:
    """Explain what macro settings affect vs historical metrics."""
    target = container or st
    affects = "\n".join(f"- ✓ {item}" for item in MACRO_ASSUMPTIONS_BANNER_AFFECTS)
    unaffected = "\n".join(f"- ✗ {item}" for item in MACRO_ASSUMPTIONS_BANNER_UNAFFECTED)
    target.markdown("#### Macro Assumptions")
    target.markdown(
        f"These settings affect:\n{affects}\n\nThese settings do **not** affect:\n{unaffected}"
    )


def render_beginner_lookback_vs_horizon_education(*, container: Any | None = None) -> None:
    """Beginner Coach note: historical lookback vs planning horizon."""
    target = container or st
    with target.expander("Historical lookback vs planning horizon", expanded=False):
        st.markdown(
            """
            **Historical Lookback** — What happened in the past.

            Use sidebar **Historical Lookback Start / End** to choose which past market data
            feeds return, volatility, and risk calculations.

            **Planning Horizon** — How far into the future you want to project.

            Use goal or planning sliders (for example **Years until you need the money**)
            for forward suggestions — not the sidebar dates.

            **Example**

            - Lookback: **2015–2025**
            - Planning horizon: **10 years**

            This means: use the last 10 years of market history as the baseline when
            estimating or projecting the next 10 years (Monte Carlo, forward macro, etc.).
            """
        )


def render_historical_period_sidebar_help(*, beginner: bool) -> None:
    """Sidebar help for historical lookback dates."""
    if beginner:
        with st.sidebar.expander("Historical lookback — what do these dates mean?", expanded=False):
            st.markdown(HISTORICAL_PERIOD_HELP_BEGINNER)
    else:
        st.sidebar.caption(
            "Historical lookback dates define the baseline for analytics, health, forward macro, "
            "Monte Carlo, optimizer, and frontier."
        )


def what_why_do(title: str, what: str, why: str, action: str) -> None:
    """Beginner framing: what / why / what to do."""
    with st.expander(f"❓ What does “{title}” mean?", expanded=False):
        st.markdown(f"**What is this?** {what}")
        st.markdown(f"**Why should I care?** {why}")
        st.markdown(f"**What should I do?** {action}")


def refresh_market_data_sidebar() -> bool:
    """Sidebar control to refresh downloaded prices. Returns True if user clicked refresh."""
    st.sidebar.markdown("### Market data")
    st.sidebar.caption(
        "Prices download automatically for your tickers. No file upload needed."
    )
    clicked = st.sidebar.button(
        "Refresh Market Data",
        use_container_width=True,
        type="secondary",
        help="Download the latest prices and refresh charts and metrics.",
    )
    if clicked:
        st.cache_data.clear()
        from components.macro_engine import clear_forward_projection_cache

        clear_forward_projection_cache()
        for key in (
            "forward_projection",
            "forward_projection_fp",
            "run_benchmark",
            "run_rolling",
            "run_risk_macro",
            "run_macro_regime",
            "run_health",
            "run_forward_macro",
            "run_mc",
            "run_optimizer",
            "run_frontier",
            "health_summary",
            "health_result",
            "health_result_fingerprint",
        ):
            st.session_state.pop(key, None)
        st.session_state.market_data_refreshed = True
        st.rerun()
    if st.session_state.pop("market_data_refreshed", False):
        st.sidebar.success("Market data refreshed.")
    return clicked


def format_money(x: float) -> str:
    return f"${x:,.0f}"


def add_value_column(df, weight_col: str, total_value: float, value_col: str = "Value ($)") -> "pd.DataFrame":
    """Add dollar column from weight percentages and total portfolio value."""
    import pandas as pd

    out = df.copy()
    if weight_col in out.columns:
        out[value_col] = out[weight_col].astype(float) / 100.0 * total_value
    return out

