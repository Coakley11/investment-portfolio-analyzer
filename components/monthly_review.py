"""Monthly portfolio review workflow — simple routine for beginners."""

from __future__ import annotations

import streamlit as st

from components.ui_helpers import APP_DISCLAIMER

MONTHLY_CHECKLIST = [
    ("Refresh Market Data", "Use **Refresh Market Data** in the sidebar to pull the latest prices."),
    ("Review Portfolio Health", "Open **❤️ Portfolio Health** and click **Refresh Portfolio Health**."),
    ("Read Recommendations", "On **🏠 Overview** or Portfolio Health, expand **Why am I seeing this?** on each suggestion."),
    ("Check Rebalancing Suggestions", "Review dollar-based rebalance cards — no need to act immediately."),
    ("Review Macro Environment", "Skim macro assumptions on Portfolio Health — defaults are fine to start."),
    ("Decide If Changes Are Needed", "Only consider changes if drift, score, or your goal changed. Educational model only."),
]

REVIEW_SCHEDULE = [
    ("Monthly", "Refresh data, skim health score, read top recommendations (~10 minutes)."),
    ("Quarterly", "Review rebalancing suggestions and allocation drift in dollar terms."),
    ("Annually", "Revisit your goal, time horizon, and whether your objective still fits."),
]


def render_monthly_review_workflow(*, expanded: bool = False) -> None:
    """What Should I Do Each Month? — step card checklist."""
    with st.expander("📅 What Should I Do Each Month?", expanded=expanded):
        st.caption(f"Simple routine to stay on track. {APP_DISCLAIMER}")
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
        st.markdown("**Review cadence**")
        for period, action in REVIEW_SCHEDULE:
            st.markdown(f"- **{period}:** {action}")
