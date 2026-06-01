"""How Do I Actually Invest This? — educational portfolio implementation guide."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core
from components.rebalancing_panel import render_rebalancing_panel
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode

DISCLAIMER = f"Educational overview only — not financial advice. {APP_DISCLAIMER}"

BROKER_INFO = [
    {
        "name": "Charles Schwab",
        "url": "https://www.schwab.com",
        "description": "Full-service brokerage with online trading, research tools, and branch support.",
        "audience": "Often used by self-directed investors and retirement savers.",
    },
    {
        "name": "Fidelity",
        "url": "https://www.fidelity.com",
        "description": "Large brokerage with ETFs, mutual funds, retirement accounts, and mobile apps.",
        "audience": "Commonly used for 401(k) rollovers and long-term investing.",
    },
    {
        "name": "Vanguard",
        "url": "https://www.vanguard.com",
        "description": "Known for low-cost index funds and ETFs; strong focus on long-term investing.",
        "audience": "Popular with buy-and-hold and retirement-focused investors.",
    },
    {
        "name": "Robinhood",
        "url": "https://robinhood.com",
        "description": "Mobile-first app with simple stock and ETF trading; fractional shares on many symbols.",
        "audience": "Often used by newer investors comfortable with app-based trading.",
    },
    {
        "name": "E*TRADE",
        "url": "https://us.etrade.com",
        "description": "Online brokerage with trading platforms, retirement accounts, and banking options.",
        "audience": "Used by active traders and retirement account holders.",
    },
    {
        "name": "Interactive Brokers",
        "url": "https://www.interactivebrokers.com",
        "description": "Professional-grade platform with broad market access and advanced tools.",
        "audience": "Often used by experienced and international investors.",
    },
]

ACCOUNT_TYPES = {
    "Individual Brokerage": "Standard taxable account — flexible deposits and withdrawals.",
    "Traditional IRA": "Tax-advantaged retirement account; withdrawals taxed as income in retirement.",
    "Roth IRA": "After-tax contributions; qualified withdrawals may be tax-free in retirement.",
    "401(k) (if available)": "Employer-sponsored plan — review your plan documents for fund options.",
}

GLOSSARY = [
    ("Ticker", "Short symbol for an investment (e.g., SPY). Search this in your brokerage."),
    ("ETF", "Exchange-traded fund — a basket of investments that trades like a stock."),
    ("Market order", "Buy or sell at the current market price."),
    ("Share", "One unit of ownership — many brokerages offer fractional shares."),
]


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _holdings_allocation_table(
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    initial_value: float,
) -> pd.DataFrame:
    w = core.normalize_weights(weights)
    rows = []
    for i, ticker in enumerate(tickers):
        pct = float(w[i]) * 100
        rows.append(
            {
                "Ticker": ticker,
                "Target %": f"{pct:.1f}%",
                "Suggested amount": _money(pct / 100.0 * initial_value),
            }
        )
    return pd.DataFrame(rows)


def _build_checklist_text(
    *,
    initial_value: float,
    allocation_df: pd.DataFrame,
    objective: str,
    account_type: str,
) -> str:
    lines = [
        "PORTFOLIO IMPLEMENTATION CHECKLIST (Educational — not financial advice)",
        "=" * 60,
        f"Target portfolio value (model): {_money(initial_value)}",
        f"Objective: {objective}",
        f"Account type researched: {account_type}",
        "",
        "TARGET ALLOCATION",
    ]
    for _, row in allocation_df.iterrows():
        lines.append(f"  {row['Ticker']:8}  {row['Target %']:>8}  {row['Suggested amount']}")
    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def render_implementation_guide(
    *,
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    settings: dict,
    health: core.PortfolioHealthResult | None = None,
    key_prefix: str = "impl",
) -> None:
    """Tabbed educational walkthrough — reduces vertical scrolling."""
    st.session_state.visited_implement = True
    beginner = is_beginner_mode(settings)
    initial_value = float(settings["initial_value"])
    objective = st.session_state.get("health_objective", "balanced growth")
    allocation_df = _holdings_allocation_table(tickers, weights, asset_types, initial_value)

    st.caption(DISCLAIMER)

    tab_names = [
        "Open Account",
        "Fund Account",
        "Buy Investments",
        "Maintain Portfolio",
        "Rebalance Portfolio",
    ]
    if not beginner:
        tab_names.append("Popular Brokers")
    guide_tabs = st.tabs(tab_names)

    with guide_tabs[0]:
        st.markdown("#### Open an investment account")
        st.markdown(
            "A **brokerage account** lets you buy ETFs and stocks online. "
            "Compare fees and features — this list is educational, not an endorsement."
        )
        account_type = st.selectbox(
            "Account type you are researching",
            list(ACCOUNT_TYPES.keys()),
            key=f"{key_prefix}_account_type",
        )
        st.markdown(f"**{account_type}** — {ACCOUNT_TYPES[account_type]}")

    with guide_tabs[1]:
        st.markdown("#### Fund the account")
        st.markdown(
            "1. Link a bank account\n"
            "2. Transfer your **investable amount** (see How Much to Invest)\n"
            "3. Wait 1–3 business days for funds to settle\n"
            "4. Confirm available cash before placing orders"
        )
        st.info(f"Model portfolio value in sidebar: **{_money(initial_value)}**")

    with guide_tabs[2]:
        st.markdown("#### Buy the investments")
        st.markdown("Search each **ticker** and enter a **dollar amount** matching your target mix:")
        st.dataframe(allocation_df, use_container_width=True, hide_index=True)
        with st.expander("Common terms", expanded=False):
            for term, definition in GLOSSARY:
                st.markdown(f"**{term}** — {definition}")

    with guide_tabs[3]:
        st.markdown("#### Maintain the portfolio")
        st.markdown(
            "- **Monthly:** Refresh market data, skim health score\n"
            "- **Quarterly:** Review rebalancing suggestions\n"
            "- **Annually:** Revisit your goal and objective"
        )
        checklist_text = _build_checklist_text(
            initial_value=initial_value,
            allocation_df=allocation_df,
            objective=objective,
            account_type=st.session_state.get(f"{key_prefix}_account_type", "Individual Brokerage"),
        )
        st.download_button(
            "Download checklist (.txt)",
            checklist_text,
            "portfolio_implementation_checklist.txt",
            "text/plain",
            key=f"{key_prefix}_checklist_dl",
        )

    with guide_tabs[4]:
        st.markdown("#### Rebalance portfolio")
        if health is not None:
            render_rebalancing_panel(health, settings=settings, initial_value=initial_value, key_prefix=key_prefix)
        else:
            hint = (
                "Run **Analyze Portfolio** on tab ④ first — allocation guidance appears here after analysis."
                if beginner
                else "Run **Analyze Portfolio** on Overview first — rebalance guidance with dollar amounts "
                "appears here after analysis."
            )
            st.info(hint)

    if not beginner:
        with guide_tabs[5]:
            st.markdown("#### Popular brokerage websites")
            st.caption("Educational reference — not a recommendation of any single broker.")
            for broker in BROKER_INFO:
                with st.container(border=True):
                    st.markdown(f"**[{broker['name']}]({broker['url']})**")
                    st.markdown(broker["description"])
                    st.caption(f"Commonly used by: {broker['audience']}")
    else:
        st.markdown("##### Broker resources (educational)")
        st.caption("Official websites for research — not endorsements.")
        bcols = st.columns(2)
        for i, broker in enumerate(BROKER_INFO[:4]):
            with bcols[i % 2]:
                st.markdown(f"**[{broker['name']}]({broker['url']})** — {broker['description'][:80]}…")
