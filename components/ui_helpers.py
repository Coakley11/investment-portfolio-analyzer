"""Shared UI helpers for beginner-friendly copy and layout."""

from __future__ import annotations

import streamlit as st

APP_DISCLAIMER = "Educational model-based analysis, not financial advice."

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


def what_why_do(title: str, what: str, why: str, action: str) -> None:
    """Beginner framing: what / why / what to do."""
    with st.expander(f"❓ What does “{title}” mean?", expanded=False):
        st.markdown(f"**What is this?** {what}")
        st.markdown(f"**Why should I care?** {why}")
        st.markdown(f"**What should I do?** {action}")


def clear_market_data_cache() -> None:
    st.cache_data.clear()


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
        clear_market_data_cache()
        for key in (
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
