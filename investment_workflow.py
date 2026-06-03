"""
Beginner workflow checklist, downstream invalidation, and developer diagnostics gate.

One investment plan is shared across Beginner and Advanced; this module only manages
completion flags and analysis cache coherence — not separate mode-specific portfolios.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core

WorkflowStep = Literal["goal", "portfolio", "analysis", "health", "recommendations"]

WORKFLOW_UI_BUILD = "2026-06-03-workflow-ui-v1"
DEV_DIAG_SESSION_KEY = "investment_show_dev_diagnostics"
_HOLDINGS_TRACK_KEY = "_workflow_holdings_fp"
_HEALTH_STATUS_KEY = "_workflow_health_status"
_HEALTH_VIEWED_FP_KEY = "_workflow_health_reviewed_fp"
_REC_VIEWED_FP_KEY = "_workflow_recommendations_viewed_fp"

_ANALYSIS_FLAG_KEYS = (
    "portfolio_analyzed",
    "portfolio_health_reviewed",
    "recommendations_displayed",
)

_ANALYSIS_CACHE_KEYS = (
    "run_health",
    "health_result",
    "health_result_fingerprint",
    "health_settings_fingerprint",
    "health_summary",
    "request_portfolio_analyze",
)


def _sess(st_obj: Any | None = None):
    if st_obj is not None:
        return st_obj.session_state
    return st.session_state


def developer_diagnostics_enabled(st_obj: Any | None = None) -> bool:
    """True when dev diagnostics should render (default off for normal users)."""
    ss = _sess(st_obj)
    if ss.get(DEV_DIAG_SESSION_KEY):
        return True
    try:
        if str(st.secrets.get("investment_dev_mode", "")).strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return True
    except Exception:
        pass
    try:
        raw = st.query_params.get("dev")
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        if str(raw or "").strip().lower() in ("1", "true", "yes"):
            return True
    except Exception:
        pass
    return False


def render_developer_sidebar_controls(st_obj: Any | None = None) -> None:
    """Collapsed sidebar toggle; persistence/workflow traces only when enabled."""
    with st.sidebar.expander("Developer", expanded=False):
        st.checkbox(
            "Show persistence & workflow diagnostics",
            key=DEV_DIAG_SESSION_KEY,
            help="Cloud restore traces, timestamps, and goal-workflow debug. Off by default.",
        )


def portfolio_analysis_fingerprint(tickers: list[str], weights: Any) -> str:
    """Match streamlit health cache fingerprint (ticker:weight pairs)."""
    w = core.normalize_weights(np.asarray(weights, dtype=float))
    return "|".join(f"{t}:{float(w[i]):.4f}" for i, t in enumerate(tickers))


def _clear_analysis_cache(ss: Any) -> None:
    ss["run_health"] = False
    for key in _ANALYSIS_CACHE_KEYS:
        ss.pop(key, None)


def _clear_downstream_completion(ss: Any) -> None:
    for key in _ANALYSIS_FLAG_KEYS:
        ss[key] = False
    ss.pop(_HEALTH_VIEWED_FP_KEY, None)
    ss.pop(_REC_VIEWED_FP_KEY, None)


def invalidate_workflow_from(step: WorkflowStep, st_obj: Any | None = None) -> None:
    """
    Invalidate workflow completion from ``step`` onward.

    - ``goal``: clear analysis / health / recommendations (keep goal & portfolio complete).
    - ``portfolio``: same downstream clear (keep goal & portfolio complete).
    - ``analysis``: clear health & recommendations only.
    """
    ss = _sess(st_obj)
    if step in ("goal", "portfolio"):
        _clear_downstream_completion(ss)
        _clear_analysis_cache(ss)
    elif step == "analysis":
        ss["portfolio_health_reviewed"] = False
        ss["recommendations_displayed"] = False


def mark_analysis_complete(st_obj: Any | None = None) -> None:
    """Call when a fresh health evaluation is cached."""
    ss = _sess(st_obj)
    ss["portfolio_analyzed"] = True


def mark_health_reviewed(st_obj: Any | None = None) -> None:
    ss = _sess(st_obj)
    ss["portfolio_health_reviewed"] = True


def mark_recommendations_viewed(st_obj: Any | None = None) -> None:
    ss = _sess(st_obj)
    ss["recommendations_displayed"] = True


def track_holdings_dataframe(df: pd.DataFrame, st_obj: Any | None = None) -> None:
    """Invalidate downstream steps when holdings table changes (any tab/mode)."""
    from components.beginner_navigation import _holdings_fingerprint

    ss = _sess(st_obj)
    fp = _holdings_fingerprint(df)
    prev = ss.get(_HOLDINGS_TRACK_KEY)
    if prev is not None and prev != fp:
        invalidate_workflow_from("portfolio", st_obj)
    ss[_HOLDINGS_TRACK_KEY] = fp


def reconcile_workflow_after_restore(st_obj: Any | None = None) -> None:
    """
    Align checklist flags with restored analysis cache.

    Clears stale analysis/health/rec flags when health blob is missing or fingerprint
    no longer matches holdings (using last known analysis fingerprint only).
    """
    ss = _sess(st_obj)
    if not ss.get("portfolio_analyzed") and not ss.get("health_result"):
        return
    if not ss.get("health_result"):
        if any(ss.get(k) for k in _ANALYSIS_FLAG_KEYS):
            invalidate_workflow_from("portfolio", st_obj)
        return
    # Holdings-based reconcile runs after tickers are parsed (see reconcile_workflow_health).
    if ss.get("portfolio_analyzed") and not ss.get("health_result_fingerprint"):
        invalidate_workflow_from("portfolio", st_obj)


def reconcile_workflow_health(
    tickers: list[str],
    weights: Any,
    st_obj: Any | None = None,
) -> None:
    """Drop downstream completion when cached health does not match current portfolio."""
    ss = _sess(st_obj)
    fp = portfolio_analysis_fingerprint(tickers, weights)
    cached_fp = ss.get("health_result_fingerprint")
    if ss.get("health_result") and cached_fp and cached_fp != fp:
        invalidate_workflow_from("portfolio", st_obj)
        return
    if ss.get("portfolio_analyzed") and not ss.get("health_result"):
        invalidate_workflow_from("portfolio", st_obj)
        return
    if ss.get("health_result") and cached_fp == fp:
        ss["portfolio_analyzed"] = True


def record_workflow_health_status(status: str, st_obj: Any | None = None) -> None:
    _sess(st_obj)[_HEALTH_STATUS_KEY] = str(status or "missing")


def _health_is_fresh(st_obj: Any | None = None) -> bool:
    return _sess(st_obj).get(_HEALTH_STATUS_KEY) == "fresh"


def goal_display_label(st_obj: Any | None = None) -> str:
    ss = _sess(st_obj)
    label = ss.get("guide_goal_choice")
    if label:
        return str(label)
    objective = str(ss.get("health_objective") or "").strip()
    if objective:
        return objective.replace("_", " ").title()
    return "Not chosen yet"


def portfolio_display_label(st_obj: Any | None = None) -> str:
    ss = _sess(st_obj)
    preset = ss.get("preset_applied")
    if preset:
        return str(preset)
    return "Custom holdings"


def analysis_status_label(st_obj: Any | None = None) -> str:
    ss = _sess(st_obj)
    status = ss.get(_HEALTH_STATUS_KEY, "missing")
    if status == "fresh":
        return "Up to date"
    if status == "settings_stale":
        return "Stale (settings changed)"
    if status == "portfolio_stale":
        return "Stale (portfolio changed)"
    if ss.get("run_health"):
        return "Running…"
    return "Not run yet"


def recommendations_status_label(st_obj: Any | None = None) -> str:
    ss = _sess(st_obj)
    if not _health_is_fresh(st_obj):
        return "Needs fresh analysis"
    if ss.get(_REC_VIEWED_FP_KEY) == ss.get("health_result_fingerprint") and ss.get(
        "recommendations_displayed"
    ):
        return "Shown for current portfolio"
    return "Open Health → Recommendations"


def navigate_workflow_tab(step: WorkflowStep, *, beginner: bool) -> None:
    from components.beginner_navigation import ADVANCED_TAB_LABELS, BEGINNER_TAB_LABELS, STEP_TAB_LABEL

    ss = st.session_state
    if step == "goal":
        ss["investment_active_tab"] = (
            STEP_TAB_LABEL["goal"] if beginner else ADVANCED_TAB_LABELS[0]
        )
    elif step == "portfolio":
        ss["investment_active_tab"] = (
            STEP_TAB_LABEL["portfolio"] if beginner else ADVANCED_TAB_LABELS[2]
        )
    elif step == "analyze":
        ss["investment_active_tab"] = (
            STEP_TAB_LABEL["analyze"] if beginner else ADVANCED_TAB_LABELS[3]
        )
    elif step in ("health", "recommendations"):
        ss["investment_active_tab"] = (
            STEP_TAB_LABEL["health"] if beginner else ADVANCED_TAB_LABELS[4]
        )


def workflow_checklist(st_obj: Any | None = None) -> dict[str, bool]:
    """Sidebar checklist driven by completion flags + fresh health cache."""
    from components.beginner_navigation import _goal_step_complete, _portfolio_built

    ss = _sess(st_obj)
    fresh = _health_is_fresh(st_obj)
    fp = ss.get("health_result_fingerprint")

    goal_done = _goal_step_complete(st_obj)
    portfolio_done = _portfolio_built(st_obj) or bool(ss.get("portfolio_built"))

    analyze_done = bool(ss.get("portfolio_analyzed")) and fresh and bool(ss.get("health_result"))
    health_done = (
        fresh
        and bool(ss.get("portfolio_health_reviewed"))
        and ss.get(_HEALTH_VIEWED_FP_KEY) == fp
        and fp
    )
    rec_done = (
        fresh
        and bool(ss.get("recommendations_displayed"))
        and ss.get(_REC_VIEWED_FP_KEY) == fp
        and fp
    )
    return {
        "goal": goal_done,
        "portfolio": portfolio_done,
        "analyze": analyze_done,
        "health": health_done,
        "recommendations": rec_done,
    }


def mark_health_reviewed_for_portfolio(
    tickers: list[str],
    weights: Any,
    st_obj: Any | None = None,
) -> None:
    """Call when Portfolio Health UI is shown for the current holdings."""
    if not _health_is_fresh(st_obj):
        return
    ss = _sess(st_obj)
    fp = portfolio_analysis_fingerprint(tickers, weights)
    if ss.get("health_result_fingerprint") != fp:
        return
    mark_health_reviewed(st_obj)
    ss[_HEALTH_VIEWED_FP_KEY] = fp


def mark_recommendations_if_current(st_obj: Any | None = None) -> None:
    """Call when recommendations panel renders for the current cached health run."""
    if not _health_is_fresh(st_obj):
        return
    ss = _sess(st_obj)
    fp = ss.get("health_result_fingerprint")
    if not fp:
        return
    mark_recommendations_viewed(st_obj)
    ss[_REC_VIEWED_FP_KEY] = fp


def render_plan_context_banner(st_obj: Any, *, beginner: bool) -> None:
    """Always-visible summary of the single shared investment plan."""
    ss = _sess(st_obj)
    fresh = _health_is_fresh(st_obj)
    analysis = analysis_status_label(st_obj)
    recs = recommendations_status_label(st_obj)
    mode = "Beginner view" if beginner else "Advanced view"
    st.markdown(
        f"""
        <div style="background:rgba(20,28,43,0.95);border:1px solid #334155;border-radius:12px;
        padding:0.85rem 1rem;margin:0 0 1rem 0;">
        <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:#94a3b8;
        margin-bottom:0.45rem;">Your investment plan · {mode} · {WORKFLOW_UI_BUILD}</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:0.5rem 1rem;
        font-size:0.9rem;color:#e2e8f0;">
        <div><span style="color:#94a3b8;">Goal</span><br><strong>{goal_display_label(st_obj)}</strong></div>
        <div><span style="color:#94a3b8;">Portfolio</span><br><strong>{portfolio_display_label(st_obj)}</strong></div>
        <div><span style="color:#94a3b8;">Analysis</span><br><strong>{analysis}</strong></div>
        <div><span style="color:#94a3b8;">Recommendations</span><br><strong>{recs}</strong></div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not fresh and ss.get("health_result"):
        st.caption("Portfolio or settings changed — re-run **Analyze Portfolio** or **Refresh Portfolio Health**.")


def render_rebuild_portfolio_panel(st_obj: Any, *, beginner: bool) -> bool:
    """
    Clear actions to rebuild holdings while keeping the goal.

    Returns True if a navigation rerun was requested.
    """
    from components.beginner_navigation import STEP_TAB_LABEL

    st.markdown("#### Rebuild / rebalance portfolio")
    st.caption(
        "Your goal stays the same. Rebuilding clears analysis, health, and recommendation checkmarks "
        "until you run them again on the new mix."
    )
    c1, c2 = st.columns(2)
    clicked = False
    tab_label = STEP_TAB_LABEL["portfolio"] if beginner else "Portfolio Inputs"
    with c1:
        if st.button(
            "Edit holdings & weights",
            key="wf_rebuild_edit_holdings",
            use_container_width=True,
            type="primary",
        ):
            navigate_workflow_tab("portfolio", beginner=beginner)
            clicked = True
    with c2:
        if st.button(
            "Change goal (Step 1)",
            key="wf_rebuild_change_goal",
            use_container_width=True,
        ):
            navigate_workflow_tab("goal", beginner=beginner)
            clicked = True
    preset = _sess(st_obj).get("preset_applied")
    if preset:
        st.caption(f"Current preset: **{preset}** — pick a new goal card or preset to reload a template.")
    return clicked
