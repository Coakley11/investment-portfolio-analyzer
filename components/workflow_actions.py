"""Explicit workflow step actions — one click per step, visible completion."""

from __future__ import annotations

from typing import Any

import streamlit as st

from components.ui_helpers import RUN_PORTFOLIO_ANALYSIS_LABEL

_WORKFLOW_CARD_CSS = """
<style>
.wf-step-card {
  background: linear-gradient(135deg, #0f2847 0%, #141c2b 100%);
  border: 2px solid rgba(77, 163, 255, 0.4);
  border-radius: 12px;
  padding: 0.9rem 1rem;
  margin: 0.5rem 0 0.85rem 0;
}
.wf-step-kicker { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.07em;
  color: #4da3ff; font-weight: 700; margin-bottom: 0.35rem; }
.wf-step-title { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; margin: 0 0 0.35rem 0; }
.wf-step-hint { font-size: 0.88rem; color: #94a3b8; margin: 0; line-height: 1.45; }
.wf-step-done {
  background: #14532d; border: 2px solid #86efac; border-radius: 10px;
  padding: 0.65rem 0.85rem; color: #bbf7d0; font-weight: 600; margin: 0.5rem 0 0.85rem 0;
}
</style>
"""


def render_workflow_step_card(
    *,
    step: int,
    total: int,
    title: str,
    hint: str,
) -> None:
    """Compact visual card for the active workflow step."""
    st.markdown(_WORKFLOW_CARD_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="wf-step-card">
          <div class="wf-step-kicker">Step {step} of {total}</div>
          <div class="wf-step-title">{title}</div>
          <p class="wf-step-hint">{hint}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workflow_step_complete(message: str) -> None:
    st.markdown(_WORKFLOW_CARD_CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="wf-step-done">✓ {message}</div>', unsafe_allow_html=True)


def _checklist(st_obj: Any | None = None) -> dict[str, bool]:
    try:
        from investment_workflow import workflow_checklist

        return workflow_checklist(st_obj)
    except ImportError:
        return {}


def render_analysis_workflow_cta(
    st_obj: Any | None = None,
    *,
    key: str,
    beginner: bool,
    step: int = 3,
    total: int = 5,
) -> bool:
    """
    Primary **Run Portfolio Analysis** button for the workflow Analysis step.

    Returns True when analysis was requested (caller should evaluate + rerun).
    """
    _st = st_obj or st
    state = _checklist(_st)
    if state.get("analyze"):
        render_workflow_step_complete("Analysis complete — open Portfolio Health next.")
        return False

    if beginner:
        hint = "Scores your holdings. Takes about one click."
    else:
        hint = (
            f"Click **{RUN_PORTFOLIO_ANALYSIS_LABEL}** to score your portfolio. "
            "This is separate from the optional Risk & Macro charts below."
        )
    render_workflow_step_card(
        step=step,
        total=total,
        title=RUN_PORTFOLIO_ANALYSIS_LABEL,
        hint=hint,
    )
    if _st.button(
        RUN_PORTFOLIO_ANALYSIS_LABEL,
        type="primary",
        key=key,
        use_container_width=True,
    ):
        _st.session_state.run_health = True
        _st.session_state.health_refresh = _st.session_state.get("health_refresh", 0) + 1
        return True
    return False


def render_health_review_action(
    st_obj: Any | None,
    tickers: list[str],
    weights: Any,
    *,
    key: str,
    health_loaded: bool,
    beginner: bool,
    step: int = 4,
    total: int = 5,
) -> bool:
    """Mark Health workflow step complete — one explicit click."""
    _st = st_obj or st
    state = _checklist(_st)
    if state.get("health"):
        render_workflow_step_complete("Health review complete.")
        return False

    if not health_loaded:
        render_workflow_step_card(
            step=step,
            total=total,
            title="Review Portfolio Health",
            hint="Run portfolio analysis first, or click **Refresh Portfolio Health** below.",
        )
        return False

    render_workflow_step_card(
        step=step,
        total=total,
        title="Review Portfolio Health",
        hint="Read your score and summary, then click below to mark this step done."
        if beginner
        else "Confirm you have reviewed the health score and status for this portfolio.",
    )
    if _st.button(
        "Review Portfolio Health",
        type="primary",
        key=key,
        use_container_width=True,
    ):
        try:
            from investment_workflow import mark_health_reviewed_for_portfolio

            mark_health_reviewed_for_portfolio(tickers, weights, _st)
        except ImportError:
            _st.session_state.portfolio_health_reviewed = True
        return True
    return False


def render_recommendations_review_action(
    st_obj: Any | None = None,
    *,
    key: str,
    beginner: bool,
    step: int = 5,
    total: int = 5,
) -> bool:
    """Mark Recommendations workflow step complete — does not change allocations."""
    _st = st_obj or st
    state = _checklist(_st)
    if state.get("recommendations"):
        render_workflow_step_complete("Recommendations reviewed.")
        return False

    try:
        from investment_workflow import _health_is_fresh
    except ImportError:
        _health_is_fresh = lambda *_a, **_k: bool(_st.session_state.get("health_result"))  # noqa: E731

    if not _health_is_fresh(_st):
        render_workflow_step_card(
            step=step,
            total=total,
            title="Review Recommendations",
            hint="Complete Analysis and Health first to unlock coaching cards.",
        )
        return False

    render_workflow_step_card(
        step=step,
        total=total,
        title="Review Recommendations",
        hint="Read the suggestions below. This does not change your portfolio — it only marks the step complete."
        if beginner
        else "Confirm you have read the model recommendations for this analysis run.",
    )
    if _st.button(
        "I've Reviewed These Recommendations",
        type="primary",
        key=key,
        use_container_width=True,
    ):
        try:
            from investment_workflow import mark_recommendations_if_current

            mark_recommendations_if_current(_st)
        except ImportError:
            _st.session_state.recommendations_displayed = True
        return True
    return False
