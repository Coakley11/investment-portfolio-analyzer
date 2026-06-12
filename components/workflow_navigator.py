"""Visual workflow navigator (Goal → Recs) shared by Beginner and Advanced modes."""

from __future__ import annotations

from typing import Any

import streamlit as st

from components.portfolio_editor_guidance import render_workflow_journey_banner
from investment_workflow import (
    WORKFLOW_CORE_STEPS,
    StepVisual,
    WorkflowCoreKey,
    commit_investment_tab_navigation,
    open_goal_step_navigation,
    request_core_step_navigation,
    workflow_step_visual_states,
    workflow_tab_label_for_core_step,
)

_STEP_LABELS: dict[WorkflowCoreKey, str] = {
    "goal": "Goal",
    "portfolio": "Portfolio",
    "analyze": "Analysis",
    "health": "Health",
    "recommendations": "Recommendations",
}

_VISUAL_META: dict[StepVisual, tuple[str, str, str]] = {
    "complete": ("✓", "#14532d", "#86efac"),
    "current": ("▶", "#1e3a5f", "#4da3ff"),
    "stale": ("⚠", "#422006", "#fbbf24"),
    "available": ("○", "#1e293b", "#94a3b8"),
}

_NAV_CSS = """
<style>
.wf-nav-row { display:flex; gap:0.35rem; align-items:stretch; margin:0.25rem 0 0.85rem 0; flex-wrap:wrap; }
.wf-nav-chip-label { font-size:0.68rem; text-transform:uppercase; letter-spacing:0.06em;
  color:#94a3b8; margin-bottom:0.35rem; font-weight:600; }
</style>
"""


def _chip_caption(visual: StepVisual) -> str:
    if visual == "complete":
        return "Done"
    if visual == "current":
        return "Current"
    if visual == "stale":
        return "Needs refresh"
    return "Ready"


def render_workflow_navigator(
    st_obj: Any,
    *,
    beginner_mode: bool,
    tab_labels: list[str],
    active_tab: str,
) -> bool:
    """
    Render five workflow step buttons. Returns True when navigation should rerun.
    """
    st.markdown(_NAV_CSS, unsafe_allow_html=True)
    states = workflow_step_visual_states(
        st_obj, beginner=beginner_mode, active_tab=active_tab
    )
    st.markdown(
        '<div class="wf-nav-chip-label">Workflow · same plan in Beginner and Advanced</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(WORKFLOW_CORE_STEPS))
    clicked = False
    for col, step in zip(cols, WORKFLOW_CORE_STEPS):
        visual = states[step]
        icon, bg, border = _VISUAL_META[visual]
        label = _STEP_LABELS[step]
        caption = _chip_caption(visual)
        with col:
            st.markdown(
                f"""
                <div style="background:{bg};border:2px solid {border};border-radius:10px;
                padding:0.45rem 0.35rem;text-align:center;min-height:3.25rem;">
                <div style="font-size:1.15rem;line-height:1;">{icon}</div>
                <div style="font-weight:700;color:#f1f5f9;font-size:0.82rem;">{label}</div>
                <div style="font-size:0.65rem;color:#94a3b8;">{caption}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            dest = workflow_tab_label_for_core_step(step, beginner=beginner_mode)
            type_ = "primary" if visual == "current" else "secondary"
            if st.button(
                f"Open {label}",
                key=f"wf_nav_{step}",
                use_container_width=True,
                type=type_,
                help=f"Go to {dest}",
            ):
                if step == "goal":
                    open_goal_step_navigation(st_obj, beginner=beginner_mode)
                elif step == "recommendations":
                    from investment_workflow import request_recommendations_navigation

                    request_recommendations_navigation(st_obj, beginner=beginner_mode)
                else:
                    request_core_step_navigation(step, beginner=beginner_mode, st_obj=st_obj)
                clicked = True
    render_workflow_journey_banner(beginner_mode=beginner_mode)
    return clicked


def render_optional_tools_navigator(
    st_obj: Any,
    *,
    beginner_mode: bool,
    tab_labels: list[str],
    active_tab: str,
) -> bool:
    """Collapsed row for tabs outside the core 5-step workflow."""
    from components.beginner_navigation import ADVANCED_TAB_LABELS, BEGINNER_TAB_LABELS

    labels = BEGINNER_TAB_LABELS if beginner_mode else ADVANCED_TAB_LABELS
    optional: list[tuple[str, str]] = []
    if beginner_mode:
        optional.append((labels[1], "overview"))
    optional.extend(
        [
            (labels[5], "explain"),
            (labels[6], "macro"),
            (labels[7], "scenarios"),
            (labels[8], "optimizer"),
            (labels[9], "frontier"),
        ]
    )
    clicked = False
    with st.expander("Optional tools", expanded=False):
        st.caption("Charts, macro, optimizer, and other tools — not required for the core journey.")
        oc = st.columns(min(len(optional), 3))
        for i, (tab_label, slug) in enumerate(optional):
            with oc[i % len(oc)]:
                is_active = active_tab == tab_label
                if st.button(
                    tab_label,
                    key=f"wf_opt_{slug}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    commit_investment_tab_navigation(
                        st_obj, tab_label, beginner_mode=beginner_mode
                    )
                    clicked = True
    return clicked


def apply_workflow_navigation(
    st_obj: Any,
    *,
    beginner_mode: bool,
    tab_labels: list[str],
) -> bool:
    """Render navigator; return True if a step button requested rerun.

    Pending tab is applied once in ``streamlit_app`` before this runs.
    """
    active = st_obj.session_state.get("investment_active_tab", tab_labels[0])
    nav_clicked = render_workflow_navigator(
        st_obj, beginner_mode=beginner_mode, tab_labels=tab_labels, active_tab=active
    )
    opt_clicked = render_optional_tools_navigator(
        st_obj, beginner_mode=beginner_mode, tab_labels=tab_labels, active_tab=active
    )
    return nav_clicked or opt_clicked
