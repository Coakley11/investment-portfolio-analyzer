"""Thinking topics panel for the Mathematical Problem Solving Lab."""

from __future__ import annotations

import streamlit as st

THINKING_TOPICS: list[dict[str, str]] = [
    {
        "title": "Portfolio Return",
        "formula": r"R_p = \sum_i w_i R_i",
        "idea": "Blend individual asset returns using portfolio weights.",
    },
    {
        "title": "Portfolio Variance",
        "formula": r"\sigma_p^2 = \mathbf{w}^\top \Sigma \mathbf{w}",
        "idea": "Risk depends on weights and how assets move together (covariance matrix).",
    },
    {
        "title": "Sharpe Ratio",
        "formula": r"\text{Sharpe} = \dfrac{R_p - R_f}{\sigma_p}",
        "idea": "Return earned per unit of total risk above the risk-free rate.",
    },
    {
        "title": "Two-Asset Mix",
        "formula": r"\sigma_p = \sqrt{w_1^2\sigma_1^2 + w_2^2\sigma_2^2 + 2 w_1 w_2 \rho \sigma_1 \sigma_2}",
        "idea": "Correlation ρ controls diversification benefit between two holdings.",
    },
    {
        "title": "Max Drawdown",
        "formula": r"\text{MDD} = \min_t \left(\dfrac{V_t - \max_{\tau \le t} V_\tau}{\max_{\tau \le t} V_\tau}\right)",
        "idea": "Largest peak-to-trough decline in portfolio value over the window.",
    },
]


def render_thinking_lab() -> None:
    """Full thinking-topics view (alias target)."""
    render_thinking_topics_panel()


def render_thinking_topics_panel() -> None:
    """Render selectable portfolio-math thinking topics."""
    st.markdown("##### Thinking Topics")
    st.caption("Core formulas used throughout the analyzer (educational reference).")
    labels = [t["title"] for t in THINKING_TOPICS]
    choice = st.selectbox("Topic", labels, key="thinking_topic_select")
    topic = next(t for t in THINKING_TOPICS if t["title"] == choice)
    st.latex(topic["formula"])
    st.markdown(topic["idea"])
