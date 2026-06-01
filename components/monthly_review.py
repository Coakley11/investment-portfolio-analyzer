"""Monthly portfolio review workflow — simple routine for beginners."""

from __future__ import annotations

import streamlit as st

from components.ui_helpers import APP_DISCLAIMER

MONTHLY_CHECKLIST = [
    ("Refresh Market Data", "In the sidebar, click **Refresh Market Data** to update prices."),
    ("Run Analyze Portfolio", "Open **④ Analyze Portfolio** and click **Analyze Portfolio**."),
    ("Review Health Score", "Check your score and status summary on the same tab."),
    ("Read Recommendations", "Open **⑤ Recommendations** and review each coaching card."),
    ("Decide If Changes Are Worth Reviewing", "You do not need to trade every month — only act if something meaningful changed."),
]

REVIEW_SCHEDULE = [
    ("Monthly", "About 10 minutes — refresh, analyze, skim recommendations."),
    ("Quarterly", "Review allocation adjustments if several holdings drifted from your goal."),
    ("Annually", "Revisit your goal and whether your objective still fits your life."),
]


def render_monthly_review_workflow(*, expanded: bool = False, standalone: bool = False) -> None:
    """What Should I Do Each Month? — simple checklist."""
    if standalone:
        st.markdown("### What should I do each month?")
        st.caption(f"Simple routine to stay on track. {APP_DISCLAIMER}")
        _render_checklist_body()
        return
    with st.expander("📅 What Should I Do Each Month?", expanded=expanded):
        st.caption(f"Simple routine to stay on track. {APP_DISCLAIMER}")
        _render_checklist_body()


def _render_checklist_body() -> None:
    for i, (title, detail) in enumerate(MONTHLY_CHECKLIST, start=1):
        st.markdown(
            f"""
            <div style="background:rgba(20,28,43,0.85);border:1px solid #334155;border-left:3px solid #4da3ff;
            border-radius:8px;padding:0.65rem 0.85rem;margin-bottom:0.45rem;">
            <span style="font-weight:600;color:#f1f5f9;">{i}. {title}</span>
            <div style="color:#94a3b8;font-size:0.88rem;margin-top:0.25rem;line-height:1.45;">{detail}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with st.expander("How often should I do more?", expanded=False):
        for period, action in REVIEW_SCHEDULE:
            st.markdown(f"- **{period}:** {action}")
