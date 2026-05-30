"""Mathematical Problem Solving Lab — educational portfolio math exercises."""

from __future__ import annotations

import math

import streamlit as st

from components.thinking_lab import render_thinking_topics_panel

APP_DISCLAIMER = "Educational model-based analysis, not financial advice."


def render_problem_solving_lab() -> None:
    """Interactive mini-lab for portfolio math practice."""
    st.caption(APP_DISCLAIMER)

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("##### Practice Problems")
        problem = st.radio(
            "Choose a problem",
            [
                "Portfolio return from weights",
                "Two-asset portfolio volatility",
                "Sharpe ratio check",
            ],
            key="problem_solving_choice",
        )

        if problem == "Portfolio return from weights":
            st.markdown("**Problem:** A portfolio holds 60% in an asset returning 10% and 40% in an asset returning 4%. What is the portfolio return?")
            w1 = st.slider("Weight asset 1 (%)", 0, 100, 60, key="ps_w1") / 100.0
            r1 = st.number_input("Return asset 1 (%)", -50.0, 100.0, 10.0, key="ps_r1") / 100.0
            r2 = st.number_input("Return asset 2 (%)", -50.0, 100.0, 4.0, key="ps_r2") / 100.0
            w2 = 1.0 - w1
            answer = w1 * r1 + w2 * r2
            if st.button("Show solution", key="ps_show_ret"):
                st.success(f"Portfolio return ≈ **{answer * 100:.2f}%**  \n(R_p = w₁R₁ + w₂R₂)")

        elif problem == "Two-asset portfolio volatility":
            st.markdown("**Problem:** Estimate annual volatility for a two-asset mix.")
            w1 = st.slider("Weight asset 1 (%)", 0, 100, 50, key="ps_vol_w1") / 100.0
            s1 = st.number_input("Volatility asset 1 (%)", 0.0, 100.0, 18.0, key="ps_s1") / 100.0
            s2 = st.number_input("Volatility asset 2 (%)", 0.0, 100.0, 6.0, key="ps_s2") / 100.0
            rho = st.slider("Correlation", -1.0, 1.0, 0.25, 0.05, key="ps_rho")
            w2 = 1.0 - w1
            var_p = w1**2 * s1**2 + w2**2 * s2**2 + 2 * w1 * w2 * rho * s1 * s2
            vol_p = math.sqrt(max(var_p, 0.0))
            if st.button("Show solution", key="ps_show_vol"):
                st.success(f"Portfolio volatility ≈ **{vol_p * 100:.2f}%**")

        else:
            st.markdown("**Problem:** Compute Sharpe ratio given return, volatility, and risk-free rate.")
            ret = st.number_input("Portfolio return (%)", -50.0, 100.0, 9.0, key="ps_ret") / 100.0
            vol = st.number_input("Portfolio volatility (%)", 0.1, 100.0, 14.0, key="ps_vol") / 100.0
            rf = st.number_input("Risk-free rate (%)", 0.0, 20.0, 4.0, key="ps_rf") / 100.0
            sharpe = (ret - rf) / vol if vol > 0 else 0.0
            if st.button("Show solution", key="ps_show_sharpe"):
                st.success(f"Sharpe ratio ≈ **{sharpe:.2f}**")

    with right:
        render_thinking_topics_panel()
