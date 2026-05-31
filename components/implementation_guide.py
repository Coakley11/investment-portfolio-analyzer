"""How Do I Actually Invest This? — educational portfolio implementation guide."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode

DISCLAIMER = f"Educational overview only — not financial advice. {APP_DISCLAIMER}"

BROKER_EXAMPLES = [
    "Charles Schwab",
    "Fidelity",
    "Vanguard",
    "Robinhood",
    "E*TRADE",
    "Interactive Brokers",
]

ACCOUNT_TYPES = {
    "Individual Brokerage": (
        "A standard taxable account. You can add or withdraw money anytime. "
        "Gains may be taxable when you sell."
    ),
    "Traditional IRA": (
        "A tax-advantaged retirement account. Contributions may be tax-deductible; "
        "withdrawals in retirement are typically taxed as income."
    ),
    "Roth IRA": (
        "A retirement account funded with after-tax dollars. Qualified withdrawals "
        "in retirement are often tax-free."
    ),
    "401(k) (if available)": (
        "An employer-sponsored retirement plan. Many employers offer a match — "
        "you may wish to review your plan documents for options and limits."
    ),
}

REVIEW_SCHEDULE = [
    ("Monthly", "Skim balances, confirm holdings still match your plan, refresh market data in this app."),
    ("Quarterly", "Review allocation drift, read Portfolio Health, consider small adjustments if needed."),
    ("Annually", "Revisit goals, time horizon, and whether your objective still fits your life."),
]

GLOSSARY = [
    ("Ticker", "A short symbol for an investment (e.g., SPY, AGG). You search for this in your brokerage."),
    ("Share", "One unit of ownership in a stock or ETF. You may buy whole or fractional shares at many brokerages."),
    ("Market order", "An order to buy or sell at the current market price. Many brokerages offer this for ETFs."),
    ("Limit order", "An order to buy or sell only at a price you specify or better."),
    ("ETF", "Exchange-traded fund — a basket of investments that trades like a stock. Often used for broad diversification."),
    ("Mutual fund", "A pooled investment that may trade once per day at the end-of-day price. Some retirement accounts use these."),
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
        dollars = pct / 100.0 * initial_value
        rows.append(
            {
                "Ticker": ticker,
                "Asset type": asset_types[i] if i < len(asset_types) else "Equity",
                "Target %": f"{pct:.1f}%",
                "Example amount": _money(dollars),
            }
        )
    return pd.DataFrame(rows)


def _rebalance_implementation_table(
    rebalance_df: pd.DataFrame,
    initial_value: float,
) -> pd.DataFrame:
    if rebalance_df.empty:
        return pd.DataFrame()
    cols = {"Ticker", "Current (%)", "Objective (%)"}
    if not cols.issubset(rebalance_df.columns):
        return pd.DataFrame()
    rows = []
    for _, r in rebalance_df.iterrows():
        cur = float(r["Current (%)"])
        obj = float(r["Objective (%)"])
        ch = obj - cur
        if abs(ch) < 0.5:
            continue
        cur_d = cur / 100.0 * initial_value
        obj_d = obj / 100.0 * initial_value
        ch_d = ch / 100.0 * initial_value
        rows.append(
            {
                "Ticker": r["Ticker"],
                "Current %": f"{cur:.1f}%",
                "Suggested %": f"{obj:.1f}%",
                "Change (pp)": f"{ch:+.1f}%",
                "Current $": _money(cur_d),
                "Suggested $": _money(obj_d),
                "Dollar difference": _money(ch_d),
            }
        )
    return pd.DataFrame(rows)


def _rebalance_narrative(reb_table: pd.DataFrame, initial_value: float) -> str | None:
    """Plain-language educational example for the largest suggested shift."""
    if reb_table.empty:
        return None
    increases = reb_table[reb_table["Change (pp)"].str.startswith("+")]
    decreases = reb_table[reb_table["Change (pp)"].str.startswith("-")]
    if decreases.empty:
        return None
    top_dec = decreases.iloc[0]
    reduce_ticker = top_dec["Ticker"]
    try:
        reduce_d = abs(float(top_dec["Dollar difference"].replace("$", "").replace(",", "")))
    except ValueError:
        reduce_d = 0.0
    increase_names = ", ".join(increases["Ticker"].tolist()[:3]) if not increases.empty else "other holdings"
    return (
        f"One possible way to move toward the suggested allocation: you **may** wish to review reducing "
        f"approximately **{_money(reduce_d)}** of **{reduce_ticker}** and redistributing that amount "
        f"among **{increase_names}**. Many investors spread changes over time rather than all at once."
    )


def _build_checklist_text(
    *,
    initial_value: float,
    allocation_df: pd.DataFrame,
    objective: str,
    account_type: str,
    reb_table: pd.DataFrame,
) -> str:
    lines = [
        "PORTFOLIO IMPLEMENTATION CHECKLIST (Educational — not financial advice)",
        "=" * 60,
        "",
        f"Target portfolio value (model): {_money(initial_value)}",
        f"Investment objective (model): {objective}",
        f"Account type to research: {account_type}",
        "",
        "TARGET ALLOCATION",
        "-" * 40,
    ]
    for _, row in allocation_df.iterrows():
        lines.append(f"  {row['Ticker']:8}  {row['Target %']:>8}  {row['Example amount']}")
    lines.extend(
        [
            "",
            "REVIEW SCHEDULE",
            "-" * 40,
            "  Monthly   — skim balances and confirm holdings match your plan",
            "  Quarterly — review allocation drift and Portfolio Health in this app",
            "  Annually  — revisit goals, horizon, and objective",
            "",
        ]
    )
    if not reb_table.empty:
        lines.extend(["REBALANCING NOTES (model suggestion)", "-" * 40])
        for _, row in reb_table.iterrows():
            lines.append(
                f"  {row['Ticker']:8}  {row['Current %']} → {row['Suggested %']}  "
                f"({row['Dollar difference']})"
            )
        lines.append("")
    lines.extend(
        [
            "GENERAL STEPS (many brokerages)",
            "-" * 40,
            "  1. Open or log into an investment account",
            "  2. Transfer funds from your bank and wait for settlement",
            "  3. Search each ticker and enter dollar amount or shares",
            "  4. Review the order before confirming",
            "  5. Revisit monthly / quarterly / annually",
            "",
            DISCLAIMER,
        ]
    )
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
    """Educational walkthrough: from model allocation to real-world implementation."""
    beginner = is_beginner_mode(settings)
    initial_value = float(settings["initial_value"])
    objective = st.session_state.get("health_objective", "balanced growth")

    title = "How Do I Actually Invest This?"
    lead = (
        "Your model portfolio is ready — this guide explains how people typically "
        "open an account, fund it, and buy the investments in your mix."
        if beginner
        else "Educational bridge from model allocation to common implementation steps."
    )
    st.markdown(f"## {title}")
    st.caption(lead)
    st.caption(DISCLAIMER)

    allocation_df = _holdings_allocation_table(tickers, weights, asset_types, initial_value)
    reb_table = (
        _rebalance_implementation_table(health.rebalance_df, initial_value)
        if health is not None
        else pd.DataFrame()
    )

    # Step 1 — Open an account
    with st.container(border=True):
        st.markdown("### Step 1 — Open an investment account")
        st.markdown(
            "A **brokerage account** is an online account where you can buy and sell "
            "investments like ETFs and stocks. You open one with a **broker** — a company "
            "that holds your investments and connects you to the market."
        )
        st.markdown("**Examples of well-known brokers** (listed for education only — not an endorsement):")
        st.markdown(", ".join(f"*{b}*" for b in BROKER_EXAMPLES))
        st.markdown(
            "Many brokerages offer similar basics: online access, mobile apps, and the ability "
            "to search for investments by **ticker symbol**. Fees and features vary — you may "
            "wish to compare options before opening an account."
        )
        with st.expander("Common account types (educational overview)", expanded=beginner):
            for name, desc in ACCOUNT_TYPES.items():
                st.markdown(f"**{name}** — {desc}")

    # Step 2 — Fund the account
    with st.container(border=True):
        st.markdown("### Step 2 — Fund the account")
        st.markdown(
            "Before buying investments, you typically need cash in the account. "
            "One common approach:"
        )
        st.markdown(
            "1. **Link a bank account** — many brokerages let you connect a checking or savings account.\n"
            "2. **Transfer money** — choose an amount (for example, your investable total from the planning section).\n"
            "3. **Wait for funds to settle** — transfers often take 1–3 business days before the cash is available.\n"
            "4. **Verify available cash** — check your brokerage's buying power or cash balance before placing orders."
        )
        st.caption(
            f"For this model, the sidebar portfolio value is **{_money(initial_value)}** — "
            "you may use a different amount based on your own situation."
        )

    # Step 3 — Buy the investments
    with st.container(border=True):
        st.markdown("### Step 3 — Buy the investments")
        st.markdown(
            "One possible way to implement this allocation is to buy each holding in proportion "
            "to your target weights. Search for the **ticker symbol** and enter a **dollar amount** "
            "or number of shares — many brokerages support both."
        )
        st.dataframe(allocation_df, use_container_width=True, hide_index=True)
        st.markdown(
            "**Example:** If you invest "
            f"**{_money(initial_value)}** using this mix, the model suggests amounts like those "
            "in the table above. Actual share prices and fractional-share rules vary by brokerage."
        )
        st.caption(
            "Educational note: you may wish to leave a small cash buffer for fees or rounding."
        )

    # Step 4 — Maintain
    with st.container(border=True):
        st.markdown("### Step 4 — Maintain the portfolio")
        st.markdown(
            "Investing is not a one-time task. Many long-term investors set a simple review rhythm:"
        )
        for period, action in REVIEW_SCHEDULE:
            st.markdown(f"- **{period}:** {action}")

    # Step 5 — Rebalancing
    with st.container(border=True):
        st.markdown("### Step 5 — Rebalancing guide")
        if not reb_table.empty:
            st.markdown(
                "If the model suggests allocation changes, here is an educational comparison "
                "of your current mix vs. the suggested mix (from Portfolio Health):"
            )
            st.dataframe(reb_table, use_container_width=True, hide_index=True)
            narrative = (
                _rebalance_narrative(health.rebalance_df, initial_value)
                if health is not None
                else None
            )
            if narrative:
                st.markdown("#### Educational example")
                st.info(narrative)
            st.caption(
                "This is one possible framing — many investors rebalance gradually or on a schedule "
                "rather than all at once. For educational purposes only."
            )
        else:
            st.markdown(
                "When holdings drift away from your target mix, you **may** wish to review "
                "whether to shift money between investments. Run **Analyze Portfolio** on the "
                "Overview tab to see model suggestions with dollar amounts."
            )
            if health is not None:
                st.success(
                    "The model does not suggest large allocation changes right now. "
                    "A periodic review is still a good habit."
                )

    # Walkthrough
    with st.container(border=True):
        st.markdown("### What would I actually click?")
        st.markdown(
            "Every brokerage looks slightly different, but many follow a similar flow. "
            "This is an **educational walkthrough**, not instructions for any specific site:"
        )
        st.markdown(
            "1. **Log in** to your brokerage account.\n"
            "2. **Search** for a ticker symbol (e.g., the first row in your allocation table).\n"
            "3. **Review** the investment name and type to confirm it matches what you intended.\n"
            "4. **Enter the amount** to invest (dollars or shares).\n"
            "5. **Review the order** — check ticker, amount, and order type.\n"
            "6. **Confirm** — only after you are comfortable with the details."
        )
        with st.expander("Common terms (plain language)", expanded=False):
            for term, definition in GLOSSARY:
                st.markdown(f"**{term}** — {definition}")

    # Checklist
    with st.container(border=True):
        st.markdown("### Brokerage implementation checklist")
        st.caption("A summary you can save for your own notes — not a trading instruction.")
        account_type = st.selectbox(
            "Account type you are researching",
            list(ACCOUNT_TYPES.keys()),
            key=f"{key_prefix}_checklist_account",
        )
        checklist_text = _build_checklist_text(
            initial_value=initial_value,
            allocation_df=allocation_df,
            objective=objective,
            account_type=account_type,
            reb_table=reb_table,
        )
        st.download_button(
            label="Download checklist (.txt)",
            data=checklist_text,
            file_name="portfolio_implementation_checklist.txt",
            mime="text/plain",
            key=f"{key_prefix}_checklist_download",
        )
        with st.expander("Preview checklist", expanded=False):
            st.text(checklist_text)
