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
        "balanced growth",
    ),
    "Save for retirement": (
        "You are building a nest egg for later in life — growth matters, but big drops can hurt.",
        "Retirement",
        "retirement",
    ),
    "Generate income": (
        "You care about dividends and interest more than fast price growth.",
        "Dividend Income",
        "income",
    ),
    "Protect my money": (
        "You want to limit big losses even if that means slower growth.",
        "Conservative",
        "capital preservation",
    ),
    "Keep cash safe short-term": (
        "You may need this money soon — stability matters more than growth.",
        "Conservative",
        "short-term cash management",
    ),
}

PRESET_RATIONALE: dict[str, str] = {
    "Conservative": (
        "Designed for users who want lower volatility and more stability — "
        "mostly bonds and cash-like funds (BND, BIL)."
    ),
    "Balanced": (
        "Designed for users who want a mix of growth and stability — "
        "US stocks, international stocks, bonds, and real estate."
    ),
    "Aggressive": (
        "Designed for users who want higher long-term growth and can tolerate larger swings — "
        "heavy stock exposure including growth (QQQ)."
    ),
    "Dividend Income": (
        "Designed for users who want dividends and income-oriented holdings — "
        "dividend ETFs, REITs, and bonds."
    ),
    "Tech Growth": (
        "Designed for users comfortable with technology concentration — "
        "growth-oriented equity ETFs with a small bond buffer."
    ),
    "Retirement": (
        "Designed for long-term investing with a diversified mix of growth and stability — "
        "more bonds than balanced, plus dividend exposure."
    ),
    "All Weather": (
        "Designed to perform across different economic environments — "
        "stocks, long-term bonds, gold, and commodities."
    ),
}

SAMPLE_PORTFOLIOS = {
    "Conservative": "Mostly bonds and cash-like funds. Smoother, slower growth.",
    "Balanced": "Mix of stocks, bonds, and real estate. A common long-term starting point.",
    "Aggressive": "Mostly stocks. Higher growth potential, bigger swings.",
    "Dividend Income": "Focus on dividends and bond interest.",
    "Retirement": "Blend built for long-term saving with some income and stability.",
}


def _apply_preset(name: str, *, sync_objective: str | None = None) -> None:
    if name in core.PORTFOLIO_PRESETS:
        st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[name])
        st.session_state.preset_applied = name
        st.session_state.guide_portfolio_loaded = True
        st.session_state.run_health = False
        st.session_state.pop("health_result", None)
        st.session_state.pop("health_result_fingerprint", None)
        if sync_objective:
            st.session_state.health_objective = sync_objective
        st.rerun()


def _auto_apply_for_goal(goal: str) -> None:
    """When the user picks or changes a goal, load the matching preset and sync the health objective."""
    _, preset, objective = GOAL_CHOICES[goal]
    last = st.session_state.get("guide_last_applied_goal")
    if last == goal:
        return
    is_goal_change = last is not None
    st.session_state.guide_last_applied_goal = goal
    st.session_state.guide_suggested_preset = preset
    st.session_state.health_objective = objective
    should_load = is_goal_change or not st.session_state.get("preset_applied")
    if should_load and preset in core.PORTFOLIO_PRESETS:
        st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[preset])
        st.session_state.preset_applied = preset
        st.session_state.guide_portfolio_loaded = True
        st.session_state.guide_auto_applied_preset = preset
        st.session_state.run_health = False
        st.session_state.pop("health_result", None)
        st.session_state.pop("health_result_fingerprint", None)


def render_getting_started_guide(*, beginner_mode: bool = True) -> None:
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0c1524,#1a2d4a);border:1px solid #2d3f57;
        border-radius:14px;padding:1.1rem 1.25rem;margin-bottom:1rem;">
        <h3 style="color:#f1f5f9;margin:0 0 0.35rem 0;">Your portfolio coach</h3>
        <p style="color:#94a3b8;margin:0;font-size:0.92rem;line-height:1.55;">
        This app tells you <b>what to do</b> and <b>why</b> — in everyday language.
        You do not need a finance degree. Follow the six steps below (also in the sidebar checklist).
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

    with st.expander("Step 1 — What is your goal?", expanded=True):
        st.markdown("Pick the option that sounds most like you. **Your portfolio loads automatically** when you choose:")
        goal = st.radio(
            "Your goal",
            list(GOAL_CHOICES.keys()),
            label_visibility="collapsed",
            key="guide_goal_choice",
        )
        explain, preset, objective = GOAL_CHOICES[goal]
        _auto_apply_for_goal(goal)
        st.markdown(f"**In plain English:** {explain}")
        st.session_state.guide_suggested_preset = preset

        auto = st.session_state.get("guide_auto_applied_preset")
        if auto == preset:
            st.success(f"✓ Loaded the **{preset}** portfolio for you. See Step 2 for why this mix was chosen.")
            st.session_state.pop("guide_auto_applied_preset", None)

        st.caption(f"Portfolio objective set to **{objective.replace('_', ' ')}** for health scoring.")

    with st.expander("Step 2 — Your suggested portfolio (and why)", expanded=True):
        suggested = st.session_state.get("guide_suggested_preset", "Balanced")
        st.markdown(
            f"**Currently loaded:** {st.session_state.get('preset_applied', suggested)}  \n"
            f"**Why this mix?** {PRESET_RATIONALE.get(suggested, SAMPLE_PORTFOLIOS.get(suggested, ''))}"
        )
        st.markdown(
            "Each option below is a ready-made mix of funds (ETFs). "
            "Click **Use this portfolio** to switch to a different starting mix."
        )
        cols = st.columns(2)
        names = list(SAMPLE_PORTFOLIOS.keys())
        for i, name in enumerate(names):
            with cols[i % 2]:
                st.markdown(f"**{name}**")
                st.caption(SAMPLE_PORTFOLIOS[name])
                if name == suggested:
                    st.caption("✓ Matches your goal from Step 1")
                if st.button(f"Use {name}", key=f"guide_preset_{name}", use_container_width=True):
                    obj = st.session_state.get("health_objective", "balanced growth")
                    for _, (_, p, o) in GOAL_CHOICES.items():
                        if p == name:
                            obj = o
                            break
                    _apply_preset(name, sync_objective=obj)

        st.dataframe(
            pd.DataFrame(core.PORTFOLIO_PRESETS.get(st.session_state.get("preset_applied", suggested), [])),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Step 3 — Analyze your portfolio", expanded=not st.session_state.get("run_health", False)):
        st.markdown(
            """
            **What happens when you analyze:**

            1. The app downloads recent prices for your tickers (like SPY or BND).
            2. It calculates how your mix would have behaved in the past.
            3. It prepares your health score, action plan, and suggestions.

            **What you should do now:**

            1. Open the **📋 Overview** tab (see the banner above the tabs).
            2. In **💼 Portfolio Inputs**, review **How Much Should I Invest?** and your dollar amounts.
            3. Click the blue **Analyze Portfolio** button.
            """
        )
        if st.button("Go to Overview & Analyze", type="primary", key="guide_analyze_cta"):
            st.session_state.run_health = True
            st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
            st.info("Switch to the **📋 Overview** tab — analysis will run automatically.")
            st.rerun()

    with st.expander("Step 4 — Read your Portfolio Health Score", expanded=False):
        st.markdown(
            """
            **What it means:** A score from 0–100 that summarizes how well your mix fits a simple model of
            return, risk, diversification, and your goal. Think of it as a checkup, not a grade on your worth.

            **Your Portfolio Journey / Action Plan** (Overview & Portfolio Health) answers:
            - **Today** — what to look at now
            - **This Month** — rebalance or refresh?
            - **This Year** — still aligned with your goal?

            | Score | Plain English |
            |-------|----------------|
            | **70+** | Generally in good shape for the model's assumptions |
            | **50–69** | Okay, but worth reviewing suggestions |
            | **Below 50** | Consider changes — higher risk or misalignment with your goal |

            **How to improve it:** Follow the app's suggestions (Step 5), diversify, align with your goal,
            and avoid one holding dominating the portfolio.
            """
        )
        st.markdown("📍 Open **❤️ Portfolio Health** → click **Refresh Portfolio Health**")

    with st.expander("Step 5 — Review suggestions", expanded=False):
        st.markdown(
            """
            **What recommendations mean:** Each suggestion includes **Why am I seeing this?** with:
            - **Issue** — what the model flagged
            - **Why it matters** — why you should care
            - **Triggered by** — the metric that caused it
            - **Possible benefit** — what might improve if you review it

            Examples: rebalance drift, high concentration, elevated recession probability.
            """
        )
        st.markdown("📍 **📋 Overview** (recommendations) · **📄 Explain Portfolio** (plain memo) · **❤️ Portfolio Health**")

    with st.expander("Step 6 — Check your portfolio every month", expanded=False):
        st.markdown(
            """
            **Simple monthly routine (about 10 minutes):**

            1. Click **Refresh Market Data** in the sidebar.
            2. Open **❤️ Portfolio Health** and refresh your score.
            3. Read your **Portfolio Journey** (Today / Month / Year) and **Why?** on each recommendation.
            4. Glance at **📋 Overview** to see if performance still fits your goal.

            **Once a year:** Revisit Step 1 — your goal or comfort with risk may have changed.
            """
        )

    with st.expander("Bonus — What are macro assumptions?", expanded=False):
        st.markdown(
            """
            On the **❤️ Portfolio Health** tab you'll see settings like interest rates, inflation,
            and recession probability. These describe what you think the economy might look like —
            the app uses them to stress-test your portfolio and tailor suggestions.

            **You do not need to be an expert.** Defaults are fine to start. Open the full guide on
            the Portfolio Health tab: **How Do I Choose These Assumptions?**
            """
        )

    if not beginner_mode:
        with st.expander("Advanced topics (optional)", expanded=False):
            st.markdown(
                """
                - **Monte Carlo** — many random "what if" future paths; shows a range, not a prediction.
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


__all__ = ["PRESET_RATIONALE", "render_getting_started_guide", "GOAL_CHOICES", "SAMPLE_PORTFOLIOS"]
