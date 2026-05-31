"""Portfolio decision coach — action plans and transparent recommendations."""

from __future__ import annotations

import streamlit as st

import portfolio_core as core
from components.beginner_copy import translate_for_beginner
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode, format_money

DISCLAIMER = f"Model-based decision support for educational purposes. {APP_DISCLAIMER}"


def _plan_block(title: str, items: list[str], icon: str) -> None:
    st.markdown(f"**{icon} {title}**")
    for item in items:
        st.markdown(f"- {item}")


def render_action_plan(
    plan: core.PortfolioActionPlan,
    *,
    score: float | None = None,
    objective: str = "",
    beginner: bool = True,
) -> None:
    score_line = f"Portfolio Health Score: **{score:.0f}/100** · " if score is not None else ""
    obj_line = f"Objective: **{objective.replace('_', ' ').title()}**" if objective else ""
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(46,204,113,0.10) 0%,rgba(20,28,43,0.92) 100%);
        border:1px solid rgba(46,204,113,0.35);border-left:4px solid #2ecc71;border-radius:12px;
        padding:1rem 1.15rem;margin-bottom:0.85rem;">
        <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#94a3b8;">
            Your Portfolio Journey
        </div>
        <div style="font-size:1.05rem;font-weight:600;color:#f1f5f9;margin:0.35rem 0;line-height:1.45;">
            {plan.headline}
        </div>
        <div style="font-size:0.82rem;color:#94a3b8;">{score_line}{obj_line}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            _plan_block("Today", plan.today, "📍")
    with c2:
        with st.container(border=True):
            _plan_block("This Month", plan.this_month, "📅")
    with c3:
        with st.container(border=True):
            _plan_block("This Year", plan.this_year, "🎯")

    st.caption(DISCLAIMER)


def render_recommendation_detail(
    detail: core.RecommendationDetail,
    index: int,
    *,
    beginner: bool = True,
) -> None:
    st.markdown(f"**Recommendation {index + 1}**")
    display_text = translate_for_beginner(detail.text) if beginner else detail.text
    st.markdown(display_text)

    why_label = "Why am I seeing this?" if beginner else "Why? — model reasoning"
    with st.expander(why_label, expanded=False):
        issue = translate_for_beginner(detail.issue) if beginner else detail.issue
        why = translate_for_beginner(detail.why_it_matters) if beginner else detail.why_it_matters
        st.markdown(f"**What is the issue?** {issue}")
        st.markdown(f"**Why does it matter?** {why}")
        st.markdown(f"**What might you consider?** {detail.possible_benefit}")
        st.markdown(f"**Triggered by:** {detail.triggered_by}")
        if detail.evidence:
            st.markdown("**Supporting details**")
            for key, val in detail.evidence.items():
                label = key
                if beginner and key == "Approx. dollar amount":
                    label = "About how much money is involved"
                st.markdown(f"- {label}: `{val}`")
        st.caption(DISCLAIMER)


def render_recommendations_panel(
    health: core.PortfolioHealthResult,
    settings: dict,
) -> None:
    beginner = is_beginner_mode(settings)
    title = "What the model suggests — and why" if beginner else "Recommendations with model reasoning"
    lead = (
        "Each item includes a **Why?** explanation so nothing is a black box."
        if beginner
        else "Expand each recommendation for issue, trigger metrics, and tradeoffs."
    )
    st.markdown(f"#### {title}")
    st.caption(lead)

    details = health.recommendation_details or [
        core.RecommendationDetail(
            text=t,
            issue="See model commentary.",
            why_it_matters="Educational flag from portfolio health rules.",
            triggered_by="Portfolio Health evaluation.",
            possible_benefit="Review allocation and assumptions.",
            evidence={"Portfolio Health Score": f"{health.score:.0f}/100"},
        )
        for t in health.recommendations
    ]

    for i, detail in enumerate(details[:12]):
        render_recommendation_detail(detail, i, beginner=beginner)
        if i < len(details) - 1:
            st.markdown("---")


def render_action_plan_placeholder(beginner: bool = True) -> None:
    st.info(
        "Your **Portfolio Journey / Action Plan** appears after you run Portfolio Health. "
        "Click **Analyze Portfolio** on Overview or **Refresh Portfolio Health** on the Health tab."
    )
    if beginner:
        st.caption("You'll get simple Today / This Month / This Year guidance — not just raw metrics.")
