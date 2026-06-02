"""Beginner-friendly Getting Started Guide — plain English, step-by-step."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import portfolio_core as core
from components.beginner_navigation import PRESET_DISPLAY
from components.monthly_review import render_monthly_review_workflow

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
    "Retirement": (
        "Designed for long-term investing with a diversified mix of growth and stability — "
        "more bonds than balanced, plus dividend exposure."
    ),
}

# Presets shown one-at-a-time in tabs (Capital Preservation uses Conservative holdings)
PRESET_TABS = [
    ("Conservative", "Conservative", "capital preservation"),
    ("Balanced", "Balanced", "balanced growth"),
    ("Aggressive", "Growth", "aggressive growth"),
    ("Dividend Income", "Income", "income"),
    ("Retirement", "Retirement", "retirement"),
    ("Conservative", "Capital Preservation", "capital preservation"),
]


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
        try:
            from investment_activity import log_portfolio_created

            log_portfolio_created(
                st,
                preset=name,
                holdings_count=len(st.session_state.holdings_df),
            )
        except Exception:
            pass
        st.rerun()


def _auto_apply_for_goal(goal: str) -> None:
    _, preset, objective = GOAL_CHOICES[goal]
    last = st.session_state.get("guide_last_applied_goal")
    if last == goal:
        return
    is_goal_change = last is not None
    st.session_state.guide_last_applied_goal = goal
    st.session_state.guide_suggested_preset = preset
    st.session_state.health_objective = objective
    if is_goal_change:
        try:
            from investment_activity import log_goal_selected

            log_goal_selected(st, goal_title=goal, objective=objective)
        except Exception:
            pass
    should_load = is_goal_change or not st.session_state.get("preset_applied")
    if should_load and preset in core.PORTFOLIO_PRESETS:
        st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[preset])
        st.session_state.preset_applied = preset
        st.session_state.guide_portfolio_loaded = True
        st.session_state.guide_auto_applied_preset = preset
        st.session_state.run_health = False
        st.session_state.pop("health_result", None)
        st.session_state.pop("health_result_fingerprint", None)
        if not is_goal_change:
            try:
                from investment_activity import log_goal_selected, log_portfolio_created

                log_goal_selected(st, goal_title=goal, objective=objective)
                log_portfolio_created(
                    st,
                    preset=preset,
                    holdings_count=len(st.session_state.holdings_df),
                )
            except Exception:
                pass


def _render_preset_tab(preset_key: str, tab_label: str, objective: str, suggested: str) -> None:
    info = PRESET_DISPLAY.get(preset_key, {})
    st.markdown(f"**{tab_label}** — {info.get('tagline', PRESET_RATIONALE.get(preset_key, ''))}")
    st.caption(f"Expected characteristics: {info.get('characteristics', 'See allocation below.')}")
    st.markdown(f"**Why this mix?** {PRESET_RATIONALE.get(preset_key, '')}")
    if preset_key == suggested:
        st.success("✓ Matches your goal from Step 1")
    if st.button(f"Use {tab_label} portfolio", key=f"guide_preset_{tab_label}", use_container_width=True):
        _apply_preset(preset_key, sync_objective=objective)
    active = st.session_state.get("preset_applied", suggested)
    if preset_key == active or (tab_label == "Capital Preservation" and active == "Conservative"):
        st.dataframe(
            pd.DataFrame(core.PORTFOLIO_PRESETS[preset_key]),
            use_container_width=True,
            hide_index=True,
        )


def render_getting_started_guide(*, beginner_mode: bool = True) -> None:
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0c1524,#1a2d4a);border:1px solid #2d3f57;
        border-radius:14px;padding:1.1rem 1.25rem;margin-bottom:1rem;">
        <h3 style="color:#f1f5f9;margin:0 0 0.35rem 0;">Your portfolio coach</h3>
        <p style="color:#94a3b8;margin:0;font-size:0.92rem;line-height:1.55;">
        Step-by-step guidance — not a long report. Use the tabs below and the sidebar checklist.
        </p>
        </div>
        <p style="color:#f5d08a;font-size:0.85rem;margin:0 0 1rem 0;">⚠️ {APP_DISCLAIMER}</p>
        """,
        unsafe_allow_html=True,
    )

    step_tabs = st.tabs(
        ["1 · Goal", "2 · Portfolio", "3 · Analyze", "4 · Health", "5 · Tips", "6 · Monthly"]
    )

    with step_tabs[0]:
        st.markdown("#### Step 1 — Choose your goal")
        st.caption("Your portfolio loads automatically when you pick an option.")
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
            st.success(f"✓ Loaded the **{preset}** portfolio. See Step 2 for details.")
            st.session_state.pop("guide_auto_applied_preset", None)
        st.caption(f"Portfolio objective: **{objective.replace('_', ' ')}**")

    with step_tabs[1]:
        st.markdown("#### Step 2 — Pick a portfolio type")
        st.caption("One portfolio at a time — click a tab to compare types.")
        suggested = st.session_state.get("guide_suggested_preset", "Balanced")
        st.info(f"Currently loaded: **{st.session_state.get('preset_applied', suggested)}**")
        tab_labels = [t[1] for t in PRESET_TABS]
        preset_tabs = st.tabs(tab_labels)
        for tab_obj, (preset_key, label, obj) in zip(preset_tabs, PRESET_TABS):
            with tab_obj:
                _render_preset_tab(preset_key, label, obj, suggested)

    with step_tabs[2]:
        st.markdown("#### Step 3 — Analyze your portfolio")
        st.markdown(
            "1. Open **💼 Portfolio Inputs** → confirm **How Much to Invest** and your mix.\n"
            "2. Open **🏠 Overview** → click **Analyze Portfolio**.\n"
            "3. The app downloads prices and prepares your health score."
        )
        if st.button("Analyze Portfolio Now", type="primary", key="guide_analyze_cta"):
            st.session_state.request_portfolio_analyze = True
            st.session_state.health_refresh = st.session_state.get("health_refresh", 0) + 1
            st.rerun()

    with step_tabs[3]:
        st.markdown("#### Step 4 — Review your health score")
        st.markdown(
            "| Score | Meaning |\n|-------|--------|\n"
            "| **70+** | Generally in good shape |\n"
            "| **50–69** | Worth reviewing suggestions |\n"
            "| **Below 50** | Consider changes |"
        )
        st.caption("Open **❤️ Portfolio Health** after analyzing.")

    with step_tabs[4]:
        st.markdown("#### Step 5 — Read recommendations")
        st.markdown(
            "Each suggestion includes **Why am I seeing this?** with the issue, why it matters, "
            "and what the model is trying to improve. Found on **🏠 Overview** and **❤️ Portfolio Health**."
        )

    with step_tabs[5]:
        st.markdown("#### Step 6 — Monthly routine")
        render_monthly_review_workflow(expanded=True)

    if not beginner_mode:
        with st.expander("Advanced topics (optional)", expanded=False):
            st.markdown(
                "Monte Carlo, Optimizer, Efficient Frontier — switch to **Advanced Mode** in the sidebar."
            )

    with st.expander("Quick glossary", expanded=False):
        for term, plain in [
            ("Volatility", "How much your portfolio tends to move up and down."),
            ("Rebalancing", "Adjusting back to target percentages after markets move."),
            ("Diversification", "Spreading money across different types of investments."),
        ]:
            st.markdown(f"**{term}** — {plain}")


__all__ = ["PRESET_RATIONALE", "render_getting_started_guide", "GOAL_CHOICES", "PRESET_TABS"]
