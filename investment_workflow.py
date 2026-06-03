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

WorkflowStep = Literal["goal", "portfolio", "analysis"]

DEV_DIAG_SESSION_KEY = "investment_show_dev_diagnostics"
_HOLDINGS_TRACK_KEY = "_workflow_holdings_fp"

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
