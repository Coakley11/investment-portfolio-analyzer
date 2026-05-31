"""Beginner-friendly Getting Started Guide — plain English, step-by-step."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import portfolio_core as core

APP_DISCLAIMER = "Educational model-based analysis, not financial advice."

GOAL_CHOICES = {
    "Grow my money long term": (
        "You want your money to grow over many years and can handle some ups and downs.",
        "Balanced",
    ),
    "Save for retirement": (
        "You are building a nest egg for later in life — growth matters, but big drops can hurt.",
        "Retirement",
    ),
    "Generate income": (
        "You care about dividends and interest more than fast price growth.",
        "Dividend Income",
    ),
    "Protect my money": (
        "You want to limit big losses even if that means slower growth.",
        "Conservative",
    ),
    "Keep cash safe short-term": (
        "You may need this money soon — stability matters more than growth.",
        "Conservative",
    ),
}

SAMPLE_PORTFOLIOS = {
    "Conservative": "Mostly bonds and cash-like funds. Smoother, slower growth.",
    "Balanced": "Mix of stocks, bonds, and real estate. A common long-term starting point.",
    "Aggressive": "Mostly stocks. Higher growth potential, bigger swings.",
    "Dividend Income": "Focus on dividends and bond interest.",
    "Retirement": "Blend built for long-term saving with some income and stability.",
}


def _apply_preset(name: str) -> None:
    if name in core.PORTFOLIO_PRESETS:
        st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[name])
        st.session_state.preset_applied = name
        st.session_state.run_health = False
        st.rerun()


def render_getting_started_guide(*, beginner_mode: bool = True) -> None:
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0c1524,#1a2d4a);border:1px solid #2d3f57;
        border-radius:14px;padding:1.1rem 1.25rem;margin-bottom:1rem;">
        <h3 style="color:#f1f5f9;margin:0 0 0.35rem 0;">Your portfolio coach</h3>
        <p style="color:#94a3b8;margin:0;font-size:0.92rem;line-height:1.55;">
        This app tells you <b>what to do</b> and <b>why</b> — in everyday language.
        You do not need a finance degree. Follow the six steps below.
        </p>
        </div>
        <p style="color:#f5d08a;font-size:0.85rem;margin:0 0 1rem 0;">⚠️ {APP_DISCLAIMER}</p>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "Market prices load **automatically** for the investments you enter. "
        "Use **Refresh Market Data** in the sidebar when you want the latest prices — no file upload required."
    )

    # ── Step 1 ───────────────────────────────────────────────────────────────
    with st.expander("Step 1 — What is your goal?", expanded=True):
        st.markdown("Pick the option that sounds most like you:")
        goal = st.radio(
            "Your goal",
            list(GOAL_CHOICES.keys()),
            label_visibility="collapsed",
            key="guide_goal_choice",
        )
        explain, preset = GOAL_CHOICES[goal]
        st.markdown(f"**In plain English:** {explain}")
        st.session_state.guide_suggested_preset = preset
        st.caption(f"Suggested starting portfolio type: **{preset}** (you can change it in Step 2).")

    # ── Step 2 ───────────────────────────────────────────────────────────────
    with st.expander("Step 2 — Choose a suggested portfolio", expanded=True):
        st.markdown(
            "Each option below is a ready-made mix of funds (ETFs). "
            "Click **Use this portfolio** to load it into **Portfolio Inputs**."
        )
        suggested = st.session_state.get("guide_suggested_preset", "Balanced")
        cols = st.columns(2)
        names = list(SAMPLE_PORTFOLIOS.keys())
        for i, name in enumerate(names):
            with cols[i % 2]:
                st.markdown(f"**{name}**")
                st.caption(SAMPLE_PORTFOLIOS[name])
                if name == suggested:
                    st.caption("✓ Matches your goal from Step 1")
                if st.button(f"Use {name}", key=f"guide_preset_{name}", use_container_width=True):
                    _apply_preset(name)

    # ── Step 3 ───────────────────────────────────────────────────────────────
    with st.expander("Step 3 — Analyze your portfolio", expanded=False):
        st.markdown(
            """
            **What happens when you analyze (automatically):**

            1. The app downloads recent prices for your tickers (like SPY or BND).
            2. It calculates how your mix would have behaved in the past.
            3. It prepares health scores, charts, and suggestions on other tabs.

            **What you should do:** Open the **Portfolio Inputs** tab to confirm your holdings, then open **Overview**.
            If numbers look old, click **Refresh Market Data** in the sidebar.
            """
        )
        st.markdown("📍 **Next tabs:** Portfolio Inputs → Overview → Portfolio Health")

    # ── Step 4 ───────────────────────────────────────────────────────────────
    with st.expander("Step 4 — Read your Portfolio Health Score", expanded=False):
        st.markdown(
            """
            **What it means:** A score from 0–100 that summarizes how well your mix fits a simple model of
            return, risk, diversification, and your goal. Think of it as a checkup, not a grade on your worth.

            | Score | Plain English |
            |-------|----------------|
            | **70+** | Generally in good shape for the model’s assumptions |
            | **50–69** | Okay, but worth reviewing suggestions |
            | **Below 50** | Consider changes — higher risk or misalignment with your goal |

            **How to improve it:** Follow the app’s suggestions (Step 5), diversify, align with your goal,
            and avoid one holding dominating the portfolio.
            """
        )
        st.markdown("📍 Open **Portfolio Health** → click **Refresh Portfolio Health**")

    # ── Step 5 ───────────────────────────────────────────────────────────────
    with st.expander("Step 5 — Review suggestions", expanded=False):
        st.markdown(
            """
            **What recommendations mean:** The app compares your portfolio to rules of thumb — not to what
            will definitely happen. Suggestions might include:

            - **Rebalance** — your percentages drifted away from your plan after markets moved.
            - **Add bonds or cash** — if risk looks high for your goal.
            - **Reduce one big holding** — if one fund drives most of your risk.

            **Why the app suggests them:** To keep your mix aligned with the goal you chose and to spread risk.
            You decide whether to act. This is not personal financial advice.
            """
        )
        st.markdown("📍 **Overview** (recommendations) · **Explain This Portfolio** (plain memo) · **Portfolio Health**")

    # ── Step 6 ───────────────────────────────────────────────────────────────
    with st.expander("Step 6 — Check your portfolio every month", expanded=False):
        st.markdown(
            """
            **Simple monthly routine (about 10 minutes):**

            1. Click **Refresh Market Data** in the sidebar.
            2. Open **Portfolio Health** and refresh your score.
            3. Read **What's Working** and **What's Not Working**.
            4. Glance at **Overview** to see if performance still fits your goal.

            **Once a year:** Revisit Step 1 — your goal or comfort with risk may have changed.
            """
        )

    if not beginner_mode:
        with st.expander("Advanced topics (optional)", expanded=False):
            st.markdown(
                """
                - **Monte Carlo** — many random “what if” future paths; shows a range, not a prediction.
                - **Optimizer** — math suggesting efficient mixes; a model, not a guarantee.
                - **Correlation** — whether investments move together; lower can mean smoother combined ride.
                - **Efficient Frontier** — chart of best risk/return tradeoffs in the model.

                Switch to **Advanced Mode** in the sidebar for full charts and technical labels.
                """
            )

    with st.expander("Quick glossary (everyday language)", expanded=False):
        terms = [
            ("Volatility", "How much your portfolio tends to move up and down."),
            ("Risk/reward score (Sharpe)", "Whether return is worth the risk you're taking."),
            ("Worst drop (drawdown)", "Biggest fall from a previous high."),
            ("Diversification", "Not putting all eggs in one basket — different funds help smooth the ride."),
            ("Rebalancing", "Adjusting back to your target percentages after markets move."),
        ]
        for term, plain in terms:
            st.markdown(f"**{term}** — {plain}")
