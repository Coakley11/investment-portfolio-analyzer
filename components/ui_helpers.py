"""Shared UI helpers for beginner-friendly copy and layout."""

from __future__ import annotations

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

HISTORICAL_PERIOD_DATE_INPUT_HELP = (
    "Historical analysis period — which past market data feeds returns, risk, "
    "correlations, health, and forward tools. Not your investment date."
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


def render_historical_period_sidebar_help(*, beginner: bool) -> None:
    """Sidebar help for Start/End dates — tooltip text lives on the date inputs."""
    if beginner:
        with st.sidebar.expander("Historical analysis period — what do these dates mean?", expanded=False):
            st.markdown(HISTORICAL_PERIOD_HELP_BEGINNER)
    else:
        st.sidebar.caption(
            "Start/End define the historical baseline for analytics, health, forward macro, "
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

