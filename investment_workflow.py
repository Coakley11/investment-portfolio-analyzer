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
WorkflowCoreKey = Literal["goal", "portfolio", "analyze", "health", "recommendations"]
StepVisual = Literal["complete", "current", "stale", "available"]
WorkflowIntent = Literal["change_goal", "rebuild_portfolio"]

WORKFLOW_UI_BUILD = "2026-06-03-production-cleanup-v1"
_GOAL_SELECTION_DEBUG_KEY = "_goal_selection_debug"
_GOAL_CHANGE_DEBUG_KEY = "_goal_change_workflow_debug"
WORKFLOW_CORE_STEPS: tuple[WorkflowCoreKey, ...] = (
    "goal",
    "portfolio",
    "analyze",
    "health",
    "recommendations",
)

DEV_DIAG_SESSION_KEY = "investment_show_dev_diagnostics"
_PENDING_INVESTMENT_TAB_KEY = "_pending_investment_tab"
WORKFLOW_STATE_BLOB_KEY = "workflow_state"

_WORKFLOW_INTENT_KEY = "_workflow_intent"
_WORKFLOW_STALE_STEPS_KEY = "_workflow_stale_steps"
_WORKFLOW_CHANGE_SNAPSHOT_KEY = "_workflow_change_snapshot"
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

_STEP_TO_WORKFLOW: dict[WorkflowCoreKey, WorkflowStep] = {
    "goal": "goal",
    "portfolio": "portfolio",
    "analyze": "analysis",
    "health": "health",
    "recommendations": "recommendations",
}


def _sess(st_obj: Any | None = None):
    if st_obj is not None:
        return st_obj.session_state
    return st.session_state


def _stale_steps_set(ss: Any) -> set[str]:
    raw = ss.get(_WORKFLOW_STALE_STEPS_KEY)
    if isinstance(raw, set):
        return raw
    if isinstance(raw, (list, tuple)):
        return set(raw)
    return set()


def _mark_downstream_stale(ss: Any, from_step: WorkflowStep) -> None:
    stale = _stale_steps_set(ss)
    if from_step == "goal":
        stale.update({"portfolio", "analyze", "health", "recommendations"})
    elif from_step == "portfolio":
        stale.update({"analyze", "health", "recommendations"})
    elif from_step == "analysis":
        stale.update({"health", "recommendations"})
    ss[_WORKFLOW_STALE_STEPS_KEY] = stale


def _clear_stale_steps(ss: Any, *steps: WorkflowCoreKey) -> None:
    stale = _stale_steps_set(ss)
    for step in steps:
        stale.discard(step)
    if stale:
        ss[_WORKFLOW_STALE_STEPS_KEY] = stale
    else:
        ss.pop(_WORKFLOW_STALE_STEPS_KEY, None)


def build_workflow_persist_blob(st_obj: Any | None = None) -> dict[str, Any]:
    """
    Serializable workflow progress for cloud ``full_session`` (shared Beginner/Advanced + devices).
    """
    ss = _sess(st_obj)
    intent = ss.get(_WORKFLOW_INTENT_KEY)
    blob: dict[str, Any] = {
        "workflow_intent": intent if intent in ("change_goal", "rebuild_portfolio") else None,
        "workflow_stale_steps": sorted(_stale_steps_set(ss)),
        "workflow_health_status": ss.get(_HEALTH_STATUS_KEY),
        "health_result_fingerprint": ss.get("health_result_fingerprint"),
        "health_settings_fingerprint": ss.get("health_settings_fingerprint"),
        "workflow_health_reviewed_fp": ss.get(_HEALTH_VIEWED_FP_KEY),
        "workflow_recommendations_viewed_fp": ss.get(_REC_VIEWED_FP_KEY),
        "workflow_holdings_fp": ss.get(_HOLDINGS_TRACK_KEY),
        "checklist": workflow_checklist(st_obj),
    }
    return blob


def apply_workflow_persist_blob(st_obj: Any, blob: dict[str, Any] | None) -> None:
    """Restore workflow progress from ``workflow_state`` in a persisted session blob."""
    if not isinstance(blob, dict):
        return
    ss = _sess(st_obj)
    intent = blob.get("workflow_intent")
    if intent in ("change_goal", "rebuild_portfolio"):
        ss[_WORKFLOW_INTENT_KEY] = intent
    else:
        ss.pop(_WORKFLOW_INTENT_KEY, None)

    stale_raw = blob.get("workflow_stale_steps")
    if isinstance(stale_raw, (list, tuple)) and stale_raw:
        ss[_WORKFLOW_STALE_STEPS_KEY] = set(str(s) for s in stale_raw)
    elif isinstance(stale_raw, set) and stale_raw:
        ss[_WORKFLOW_STALE_STEPS_KEY] = set(stale_raw)
    else:
        ss.pop(_WORKFLOW_STALE_STEPS_KEY, None)

    for blob_key, session_key in (
        ("workflow_health_status", _HEALTH_STATUS_KEY),
        ("health_result_fingerprint", "health_result_fingerprint"),
        ("health_settings_fingerprint", "health_settings_fingerprint"),
        ("workflow_health_reviewed_fp", _HEALTH_VIEWED_FP_KEY),
        ("workflow_recommendations_viewed_fp", _REC_VIEWED_FP_KEY),
        ("workflow_holdings_fp", _HOLDINGS_TRACK_KEY),
    ):
        val = blob.get(blob_key)
        if val is not None and val != "":
            ss[session_key] = val
        else:
            ss.pop(session_key, None)


def workflow_persist_audit(st_obj: Any | None = None) -> dict[str, str]:
    """Compare live session vs what would be written to ``full_session`` (developer diagnostics)."""
    ss = _sess(st_obj)
    try:
        from investment_persistent_state import build_investment_disk_state

        blob = build_investment_disk_state(st_obj)
    except Exception as exc:
        return {"error": str(exc)}
    wf = blob.get(WORKFLOW_STATE_BLOB_KEY) if isinstance(blob, dict) else {}
    if not isinstance(wf, dict):
        wf = {}
    lines: dict[str, str] = {}
    for label, live_key, blob_key in (
        ("beginner_goal_card", "beginner_goal_card", "beginner_goal_card"),
        ("guide_goal_choice", "guide_goal_choice", "guide_goal_choice"),
        ("health_objective", "health_objective", "health_objective"),
        ("preset_applied", "preset_applied", "preset_applied"),
        ("portfolio_built", "portfolio_built", "portfolio_built"),
        ("portfolio_analyzed", "portfolio_analyzed", "portfolio_analyzed"),
        ("portfolio_health_reviewed", "portfolio_health_reviewed", "portfolio_health_reviewed"),
        ("recommendations_displayed", "recommendations_displayed", "recommendations_displayed"),
        ("investment_active_tab", "investment_active_tab", "investment_active_tab"),
        ("experience", "experience", "experience"),
        ("health_result_fingerprint", "health_result_fingerprint", "health_result_fingerprint"),
        ("workflow_health_status", _HEALTH_STATUS_KEY, "workflow_health_status"),
        ("stale_steps", _WORKFLOW_STALE_STEPS_KEY, "workflow_stale_steps"),
        ("health_reviewed_fp", _HEALTH_VIEWED_FP_KEY, "workflow_health_reviewed_fp"),
    ):
        live = ss.get(live_key)
        saved = wf.get(blob_key) if blob_key in wf else blob.get(live_key)
        if label in ("beginner_goal_card", "guide_goal_choice", "health_objective", "preset_applied"):
            saved = blob.get(live_key)
        lines[label] = f"live={live!r} · cloud_blob={saved!r}"
    lines["holdings_df"] = "live=DataFrame · cloud_blob=records" if blob.get("holdings_df") else "live=… · cloud_blob=missing"
    lines["health_result_object"] = (
        "live=present" if ss.get("health_result") else "live=missing (expected after cross-device restore)"
    )
    return lines


def _restored_analysis_without_object(st_obj: Any | None = None) -> bool:
    """True when analyze completed on another device but ``health_result`` was not restored."""
    ss = _sess(st_obj)
    return (
        bool(ss.get("portfolio_analyzed"))
        and bool(ss.get("health_result_fingerprint"))
        and isinstance(ss.get("health_summary"), dict)
        and not ss.get("health_result")
    )


def clear_workflow_intent(st_obj: Any | None = None) -> None:
    ss = _sess(st_obj)
    ss.pop(_WORKFLOW_INTENT_KEY, None)
    ss.pop(_WORKFLOW_CHANGE_SNAPSHOT_KEY, None)


def reset_investment_workflow_state(st_obj: Any | None = None) -> None:
    """Clear workflow intents, stale flags, analysis cache, and checklist completion."""
    ss = _sess(st_obj)
    for key in (
        _WORKFLOW_INTENT_KEY,
        _WORKFLOW_STALE_STEPS_KEY,
        _WORKFLOW_CHANGE_SNAPSHOT_KEY,
        _PENDING_INVESTMENT_TAB_KEY,
        _HOLDINGS_TRACK_KEY,
        _HEALTH_STATUS_KEY,
        _HEALTH_VIEWED_FP_KEY,
        _REC_VIEWED_FP_KEY,
        _GOAL_SELECTION_DEBUG_KEY,
        _GOAL_CHANGE_DEBUG_KEY,
        "_workflow_last_goal_change",
        "request_portfolio_analyze",
        "health_refresh",
    ):
        ss.pop(key, None)
    for key in _ANALYSIS_FLAG_KEYS:
        ss[key] = False
    _clear_analysis_cache(ss)
    ss.pop("health_summary", None)


def snapshot_plan_labels(st_obj: Any | None = None) -> dict[str, str]:
    ss = _sess(st_obj)
    return {
        "goal": goal_display_label(st_obj),
        "goal_banner": goal_display_label(st_obj),
        "beginner_goal_card": str(ss.get("beginner_goal_card") or ""),
        "guide_goal_choice": str(ss.get("guide_goal_choice") or ""),
        "portfolio": portfolio_display_label(st_obj),
        "preset_applied": str(ss.get("preset_applied") or ""),
        "objective": str(ss.get("health_objective") or ""),
        "holdings_fp": _holdings_fingerprint_safe(st_obj),
    }


def _holdings_fingerprint_safe(st_obj: Any | None = None) -> str:
    try:
        from components.beginner_navigation import _holdings_fingerprint

        df = _sess(st_obj).get("holdings_df")
        if df is None:
            return ""
        return _holdings_fingerprint(df)
    except Exception:
        return ""


def classify_goal_change_verdict(before: dict[str, str], after: dict[str, str]) -> str:
    """
    Classify goal-selection outcome for diagnostics.

    A — goal keys did not change
    B — goal changed but portfolio preset / holdings fingerprint unchanged
    C — goal and portfolio changed; banner may still look unchanged (display mismatch)
    OK — goal and portfolio both changed as expected
    """
    g_before = before.get("guide_goal_choice") or before.get("goal")
    g_after = after.get("guide_goal_choice") or after.get("goal")
    card_before = before.get("beginner_goal_card", "")
    card_after = after.get("beginner_goal_card", "")
    preset_before = before.get("preset_applied") or before.get("portfolio")
    preset_after = after.get("preset_applied") or after.get("portfolio")
    fp_before = before.get("holdings_fp", "")
    fp_after = after.get("holdings_fp", "")
    obj_before = before.get("objective", "")
    obj_after = after.get("objective", "")

    goal_changed = (g_before != g_after) or (card_before != card_after) or (obj_before != obj_after)
    portfolio_changed = (preset_before != preset_after) or (
        fp_before != fp_after and bool(fp_before or fp_after)
    )

    if not goal_changed:
        return "A"
    if goal_changed and not portfolio_changed:
        return "B"
    if goal_changed and portfolio_changed:
        banner_before = before.get("goal_banner") or g_before
        banner_after = after.get("goal_banner") or g_after
        if banner_before == banner_after:
            return "C"
        return "OK"
    return "?"


def capture_goal_selection_debug(
    st_obj: Any,
    *,
    before: dict[str, str],
    card: dict[str, str] | None = None,
    source: str = "beginner_card",
) -> None:
    """Store before/after session snapshots for temporary goal-change diagnostics."""
    ss = _sess(st_obj)
    after = snapshot_plan_labels(st_obj)
    after["beginner_goal_card"] = str(ss.get("beginner_goal_card") or "")
    verdict = classify_goal_change_verdict(before, after)
    ss[_GOAL_SELECTION_DEBUG_KEY] = {
        "source": source,
        "verdict": verdict,
        "verdict_label": {
            "A": "Goal did not change in session",
            "B": "Goal changed but portfolio preset/holdings did not",
            "C": "Goal and portfolio changed; plan banner goal line may look unchanged",
            "OK": "Goal and portfolio both changed",
        }.get(verdict, "Unknown"),
        "before": before,
        "after": after,
        "card": dict(card) if card else None,
        "last_goal_change_record": ss.get("_workflow_last_goal_change"),
        "plan_banner_goal_line": goal_display_label(st_obj),
    }


def goal_card_collision_rows() -> list[dict[str, str]]:
    """Rows showing beginner cards that share preset or guide_goal_choice."""
    try:
        from components.beginner_coach import GOAL_CARDS
    except ImportError:
        return []
    rows: list[dict[str, str]] = []
    for card in GOAL_CARDS:
        rows.append(
            {
                "card_id": card["id"],
                "title": card["title"],
                "goal_key": card["goal_key"],
                "preset": card["preset"],
                "objective": card["objective"],
            }
        )
    return rows


def render_goal_selection_diagnostics(
    st_obj: Any, *, beginner_mode: bool, expanded: bool = False
) -> None:
    """Goal-change diagnostics (developer mode only)."""
    if not developer_diagnostics_enabled(st_obj):
        return
    ss = _sess(st_obj)
    with st.expander("Goal change diagnostics", expanded=expanded):
        st.caption(
            "Verdict: **A** = goal not changing · **B** = goal changed, same portfolio · "
            "**C** = data changed but banner looks the same · **OK** = expected change"
        )
        dbg = ss.get(_GOAL_SELECTION_DEBUG_KEY)
        if dbg:
            verdict = dbg.get("verdict", "?")
            st.warning(f"**Last selection verdict: {verdict}** — {dbg.get('verdict_label', '')}")
            st.markdown("**Before → after (last goal card click or Advanced radio change)**")
            b = dbg.get("before") or {}
            a = dbg.get("after") or {}
            st.table(
                [
                    {
                        "field": "guide_goal_choice",
                        "before": b.get("guide_goal_choice"),
                        "after": a.get("guide_goal_choice"),
                        "changed": b.get("guide_goal_choice") != a.get("guide_goal_choice"),
                    },
                    {
                        "field": "beginner_goal_card",
                        "before": b.get("beginner_goal_card"),
                        "after": a.get("beginner_goal_card"),
                        "changed": b.get("beginner_goal_card") != a.get("beginner_goal_card"),
                    },
                    {
                        "field": "health_objective",
                        "before": b.get("objective"),
                        "after": a.get("objective"),
                        "changed": b.get("objective") != a.get("objective"),
                    },
                    {
                        "field": "preset_applied",
                        "before": b.get("preset_applied"),
                        "after": a.get("preset_applied"),
                        "changed": b.get("preset_applied") != a.get("preset_applied"),
                    },
                    {
                        "field": "holdings fingerprint",
                        "before": b.get("holdings_fp"),
                        "after": a.get("holdings_fp"),
                        "changed": b.get("holdings_fp") != a.get("holdings_fp"),
                    },
                    {
                        "field": "plan banner goal line",
                        "before": b.get("goal_banner"),
                        "after": a.get("goal_banner"),
                        "changed": b.get("goal_banner") != a.get("goal_banner"),
                    },
                ]
            )
            if dbg.get("card"):
                st.markdown("**Card clicked**")
                st.json(dbg["card"])
            if dbg.get("last_goal_change_record"):
                st.markdown("**`_workflow_last_goal_change` record** (banner footer)")
                st.json(dbg["last_goal_change_record"])
        else:
            st.info("Select a goal card to populate before/after snapshots.")

        st.markdown("**Current session (live)**")
        live = snapshot_plan_labels(st_obj)
        live["beginner_goal_card"] = str(ss.get("beginner_goal_card") or "")
        st.json(live)

        st.markdown("**Beginner cards that share the same preset or goal key**")
        collisions = goal_card_collision_rows()
        if collisions:
            st.dataframe(collisions, use_container_width=True, hide_index=True)
            st.caption(
                "⚠️ **Long-Term Growth** and **Balanced** both use preset **Balanced** and "
                "goal key **Grow my money long term** — switching between them changes the "
                "highlighted card only, not the plan banner or holdings."
            )

        if not beginner_mode:
            st.markdown("**Advanced** uses the same `guide_goal_choice` session key as Beginner.")
            st.write(f"Radio value now: `{ss.get('guide_goal_choice')!r}`")


def _dev_query_param_enabled(st_obj: Any | None = None) -> bool:
    for host in (st_obj, st):
        if host is None:
            continue
        try:
            qp = getattr(host, "query_params", None)
            if qp is None:
                continue
            raw = qp.get("dev")
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            if str(raw or "").strip().lower() in ("1", "true", "yes"):
                return True
        except Exception:
            continue
    return False


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
    return _dev_query_param_enabled(st_obj)


def developer_access_available(st_obj: Any | None = None) -> bool:
    """True when the Developer sidebar section should be visible (admin entry points)."""
    if developer_diagnostics_enabled(st_obj):
        return True
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
    return _dev_query_param_enabled(st_obj)


def render_developer_sidebar_controls(st_obj: Any | None = None) -> None:
    """Collapsed sidebar toggle; persistence/workflow traces only when enabled."""
    if not developer_access_available(st_obj):
        return
    with st.sidebar.expander("Developer", expanded=False):
        st.checkbox(
            "Show diagnostics",
            key=DEV_DIAG_SESSION_KEY,
            help="Persistence traces and workflow debug panels. Off by default.",
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


def _sync_health_status_after_invalidate(step: WorkflowStep, st_obj: Any | None = None) -> None:
    ss = _sess(st_obj)
    if step in ("goal", "portfolio"):
        if ss.get("health_result"):
            record_workflow_health_status("portfolio_stale", st_obj)
        else:
            record_workflow_health_status("missing", st_obj)
    elif step == "analysis":
        status = ss.get(_HEALTH_STATUS_KEY, "missing")
        if status == "fresh":
            record_workflow_health_status("settings_stale", st_obj)


def invalidate_workflow_from(step: WorkflowStep, st_obj: Any | None = None) -> None:
    """
    Invalidate workflow completion from ``step`` onward.

    - ``goal``: clear downstream completion; portfolio must be re-confirmed for the new goal.
    - ``portfolio``: same downstream clear (keep goal & portfolio complete after confirm).
    - ``analysis``: clear health & recommendations only.
    """
    ss = _sess(st_obj)
    if step in ("goal", "portfolio"):
        _clear_downstream_completion(ss)
        _clear_analysis_cache(ss)
        if step == "goal":
            ss["portfolio_built"] = False
            ss["guide_portfolio_loaded"] = False
            ss.pop("_portfolio_confirmed_fp", None)
        _mark_downstream_stale(ss, step)
    elif step == "analysis":
        ss["portfolio_health_reviewed"] = False
        ss["recommendations_displayed"] = False
        _mark_downstream_stale(ss, step)
    _sync_health_status_after_invalidate(step, st_obj)
    _autosave_after_workflow_change(st_obj)


def begin_goal_change_workflow(st_obj: Any, *, beginner: bool) -> None:
    """
    Start a real goal-change workflow (not navigation-only).

    Clears downstream analysis/health/rec state, shows the change-goal banner, and
    opens Step 1. The new goal is applied when the user picks a goal card or Advanced radio.
    """
    import datetime as dt

    ss = _sess(st_obj)
    ss[_WORKFLOW_CHANGE_SNAPSHOT_KEY] = snapshot_plan_labels(st_obj)
    invalidate_workflow_from("goal", st_obj)
    ss[_WORKFLOW_INTENT_KEY] = "change_goal"
    request_workflow_tab_navigation("goal", beginner=beginner, st_obj=st_obj)
    dbg = dict(ss.get(_GOAL_CHANGE_DEBUG_KEY) or {})
    dbg["change_goal_clicked_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    ss[_GOAL_CHANGE_DEBUG_KEY] = dbg
    _refresh_goal_change_debug_snapshot(st_obj)


def persist_plan_after_goal_selection(st_obj: Any | None = None) -> bool:
    """Write goal/portfolio/holdings to local + cloud persistence immediately after a goal pick."""
    ok = False
    try:
        from investment_persistent_state import autosave_investment_state

        autosave_investment_state(st_obj)
        ok = True
    except Exception:
        ok = False
    try:
        dbg = dict(_sess(st_obj).get(_GOAL_CHANGE_DEBUG_KEY) or {})
        dbg["autosave_ok"] = ok
        _sess(st_obj)[_GOAL_CHANGE_DEBUG_KEY] = dbg
    except Exception:
        pass
    return ok


def begin_portfolio_rebuild_workflow(st_obj: Any, *, beginner: bool) -> None:
    """Start rebuild flow: invalidate downstream, navigate to portfolio, set intent banner."""
    ss = _sess(st_obj)
    ss[_WORKFLOW_CHANGE_SNAPSHOT_KEY] = snapshot_plan_labels(st_obj)
    invalidate_workflow_from("portfolio", st_obj)
    ss[_WORKFLOW_INTENT_KEY] = "rebuild_portfolio"
    request_workflow_tab_navigation("portfolio", beginner=beginner, st_obj=st_obj)


def record_goal_selection(
    st_obj: Any,
    *,
    goal_title: str,
    preset: str | None,
    objective: str,
    beginner: bool,
    prior: dict[str, str] | None = None,
) -> None:
    """Call after user confirms a new goal; clears change-goal intent and records what changed."""
    ss = _sess(st_obj)
    before = prior or ss.get(_WORKFLOW_CHANGE_SNAPSHOT_KEY) or {}
    ss["_workflow_last_goal_change"] = {
        "from_goal": before.get("guide_goal_choice") or before.get("goal"),
        "from_portfolio": before.get("preset_applied") or before.get("portfolio"),
        "from_objective": before.get("objective"),
        "to_goal": str(_sess(st_obj).get("guide_goal_choice") or goal_title),
        "to_goal_title": goal_title,
        "to_preset": preset or portfolio_display_label(st_obj),
        "to_objective": objective,
    }
    clear_workflow_intent(st_obj)
    _clear_stale_steps(ss, "goal")
    persist_plan_after_goal_selection(st_obj)
    _refresh_goal_change_debug_snapshot(st_obj, goal_selected=True)


def mark_analysis_complete(st_obj: Any | None = None) -> None:
    """Call when a fresh health evaluation is cached."""
    ss = _sess(st_obj)
    ss["portfolio_analyzed"] = True
    _clear_stale_steps(ss, "analyze")
    _autosave_after_workflow_change(st_obj)


def _autosave_after_workflow_change(st_obj: Any | None = None) -> None:
    try:
        from investment_persistent_state import autosave_investment_state

        autosave_investment_state(st_obj)
    except Exception:
        pass


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
        if ss.get(_WORKFLOW_INTENT_KEY) != "rebuild_portfolio":
            ss[_WORKFLOW_INTENT_KEY] = "rebuild_portfolio"
    ss[_HOLDINGS_TRACK_KEY] = fp


def reconcile_workflow_after_restore(st_obj: Any | None = None) -> None:
    """
    Align checklist flags with restored analysis cache.

    Trusts persisted fingerprints + ``health_summary`` when the in-memory
    ``health_result`` object is absent after cross-device restore.
    """
    ss = _sess(st_obj)
    if _restored_analysis_without_object(st_obj):
        if ss.get(_HEALTH_STATUS_KEY) != "fresh":
            record_workflow_health_status("fresh", st_obj)
        return
    if not ss.get("portfolio_analyzed") and not ss.get("health_result"):
        return
    if not ss.get("health_result"):
        if any(ss.get(k) for k in _ANALYSIS_FLAG_KEYS):
            invalidate_workflow_from("portfolio", st_obj)
        return
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
        if _restored_analysis_without_object(st_obj) and cached_fp == fp:
            record_workflow_health_status("fresh", st_obj)
            ss["portfolio_analyzed"] = True
            _clear_stale_steps(ss, "analyze")
            return
        invalidate_workflow_from("portfolio", st_obj)
        return
    if ss.get("health_result") and cached_fp == fp:
        ss["portfolio_analyzed"] = True
        _clear_stale_steps(ss, "analyze")
        record_workflow_health_status("fresh", st_obj)
        return
    if not ss.get("health_result"):
        record_workflow_health_status("missing", st_obj)


def record_workflow_health_status(status: str, st_obj: Any | None = None) -> None:
    status = str(status or "missing")
    ss = _sess(st_obj)
    ss[_HEALTH_STATUS_KEY] = status
    if status == "portfolio_stale":
        _mark_downstream_stale(ss, "portfolio")
    elif status == "settings_stale":
        _mark_downstream_stale(ss, "analysis")


def _health_is_fresh(st_obj: Any | None = None) -> bool:
    """Workflow health is fresh when status and fingerprint/summary agree."""
    ss = _sess(st_obj)
    if ss.get(_HEALTH_STATUS_KEY) != "fresh":
        return False
    if not ss.get("health_result_fingerprint"):
        return False
    if ss.get("health_result"):
        return True
    return _restored_analysis_without_object(st_obj)


def goal_display_label(st_obj: Any | None = None) -> str:
    """Prefer active beginner card title, then guide goal text, then objective."""
    ss = _sess(st_obj)
    card_id = ss.get("beginner_goal_card")
    if card_id:
        try:
            from components.beginner_coach import GOAL_CARDS

            for card in GOAL_CARDS:
                if card.get("id") == card_id:
                    return str(card["title"])
        except ImportError:
            pass
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
    if status == "fresh" and workflow_checklist(st_obj)["analyze"]:
        return "Up to date"
    if status == "fresh":
        return "Run Analyze to refresh"
    if status == "settings_stale":
        return "Stale (settings changed)"
    if status == "portfolio_stale":
        return "Stale (portfolio changed)"
    if "analyze" in _stale_steps_set(ss):
        return "Needs refresh"
    if ss.get("run_health"):
        return "Running…"
    return "Not run yet"


def recommendations_status_label(st_obj: Any | None = None) -> str:
    ss = _sess(st_obj)
    if not _health_is_fresh(st_obj) or "recommendations" in _stale_steps_set(ss):
        return "Needs fresh analysis"
    if ss.get(_REC_VIEWED_FP_KEY) == ss.get("health_result_fingerprint") and ss.get(
        "recommendations_displayed"
    ):
        return "Shown for current portfolio"
    return "Open Health → Recommendations"


def workflow_tab_label_for_step(step: WorkflowStep, *, beginner: bool) -> str:
    from components.beginner_navigation import ADVANCED_TAB_LABELS, BEGINNER_TAB_LABELS, STEP_TAB_LABEL

    if step == "goal":
        return STEP_TAB_LABEL["goal"] if beginner else ADVANCED_TAB_LABELS[0]
    if step == "portfolio":
        return STEP_TAB_LABEL["portfolio"] if beginner else ADVANCED_TAB_LABELS[2]
    if step == "analysis":
        return STEP_TAB_LABEL["analyze"] if beginner else ADVANCED_TAB_LABELS[3]
    if step in ("health", "recommendations"):
        return STEP_TAB_LABEL["health"] if beginner else ADVANCED_TAB_LABELS[4]
    return BEGINNER_TAB_LABELS[0] if beginner else ADVANCED_TAB_LABELS[0]


def workflow_tab_label_for_core_step(step: WorkflowCoreKey, *, beginner: bool) -> str:
    return workflow_tab_label_for_step(_STEP_TO_WORKFLOW[step], beginner=beginner)


def commit_investment_tab_navigation(
    st_obj: Any,
    label: str,
    *,
    beginner_mode: bool,
) -> str:
    """
    Set both pending and active tab keys (no bound section radio in the main workflow path).

    Call before the workflow navigator renders so the next rerun lands on the right step.
    """
    from components.beginner_navigation import normalize_tab_label_for_mode
    from investment_persistent_state import INVESTMENT_ACTIVE_TAB_KEY

    ss = _sess(st_obj)
    normalized = normalize_tab_label_for_mode(str(label).strip(), beginner=beginner_mode)
    ss[_PENDING_INVESTMENT_TAB_KEY] = normalized
    ss[INVESTMENT_ACTIVE_TAB_KEY] = normalized
    return normalized


def _refresh_goal_change_debug_snapshot(
    st_obj: Any | None = None,
    *,
    goal_selected: bool = False,
) -> None:
    """Keep the temporary goal-change debug panel in sync with live session state."""
    import datetime as dt

    ss = _sess(st_obj)
    dbg = dict(ss.get(_GOAL_CHANGE_DEBUG_KEY) or {})
    if goal_selected:
        dbg["goal_selected_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    dbg["_workflow_intent"] = ss.get(_WORKFLOW_INTENT_KEY)
    dbg["_pending_investment_tab"] = ss.get(_PENDING_INVESTMENT_TAB_KEY)
    dbg["investment_active_tab"] = ss.get("investment_active_tab")
    dbg["beginner_goal_card"] = str(ss.get("beginner_goal_card") or "")
    dbg["guide_goal_choice"] = str(ss.get("guide_goal_choice") or "")
    dbg["health_objective"] = str(ss.get("health_objective") or "")
    dbg["preset_applied"] = str(ss.get("preset_applied") or "")
    dbg["holdings_fp"] = _holdings_fingerprint_safe(st_obj)
    dbg["checklist"] = workflow_checklist(st_obj)
    dbg["stale_steps"] = sorted(_stale_steps_set(ss))
    ss[_GOAL_CHANGE_DEBUG_KEY] = dbg


def render_health_workflow_debug(
    st_obj: Any,
    *,
    beginner_mode: bool,
    tickers: list[str],
    weights: Any,
    cache_status: str,
    health_loaded: bool,
) -> None:
    """Portfolio Health step diagnostics (developer mode only)."""
    if not developer_diagnostics_enabled(st_obj):
        return
    ss = _sess(st_obj)
    fp = portfolio_analysis_fingerprint(tickers, weights)
    checklist = workflow_checklist(st_obj)
    with st.expander("Health step diagnostics", expanded=False):
        st.caption(f"Build **{WORKFLOW_UI_BUILD}** (dev only)")
        st.markdown(f"**`get_health_cache_status`:** `{cache_status}`")
        st.markdown(f"**`_workflow_health_status`:** `{ss.get(_HEALTH_STATUS_KEY)!r}`")
        st.markdown(f"**`_health_is_fresh`:** `{_health_is_fresh(st_obj)}`")
        st.markdown(f"**`portfolio_analyzed`:** `{ss.get('portfolio_analyzed')!r}`")
        st.markdown(f"**`portfolio_health_reviewed`:** `{ss.get('portfolio_health_reviewed')!r}`")
        st.markdown(f"**`health_result` present:** `{bool(ss.get('health_result'))}`")
        st.markdown(f"**Cached fingerprint:** `{ss.get('health_result_fingerprint')!r}`")
        st.markdown(f"**Current fingerprint:** `{fp!r}`")
        st.markdown(f"**Fingerprints match:** `{ss.get('health_result_fingerprint') == fp}`")
        st.markdown(f"**`run_health`:** `{ss.get('run_health')!r}`")
        st.markdown(f"**Health panel rendered:** `{health_loaded}`")
        st.markdown(f"**`investment_active_tab`:** `{ss.get('investment_active_tab')!r}`")
        goal_tab = workflow_tab_label_for_step("goal", beginner=beginner_mode)
        health_tab = workflow_tab_label_for_step("health", beginner=beginner_mode)
        st.markdown(f"**On Health tab:** `{ss.get('investment_active_tab') == health_tab}` (expect `{health_tab}`)")
        st.json(
            {
                "checklist_analyze": checklist.get("analyze"),
                "checklist_health": checklist.get("health"),
                "checklist_recommendations": checklist.get("recommendations"),
                "stale_steps": sorted(_stale_steps_set(ss)),
                "health_viewed_fp": ss.get(_HEALTH_VIEWED_FP_KEY),
            }
        )


def render_goal_change_workflow_debug(
    st_obj: Any,
    *,
    beginner_mode: bool,
    tab_labels: list[str],
    expanded: bool = False,
) -> None:
    """Change Goal workflow diagnostics (developer mode only)."""
    if not developer_diagnostics_enabled(st_obj):
        return
    ss = _sess(st_obj)
    _refresh_goal_change_debug_snapshot(st_obj)
    dbg = ss.get(_GOAL_CHANGE_DEBUG_KEY) or {}
    checklist = dbg.get("checklist") or workflow_checklist(st_obj)
    with st.expander("Goal workflow diagnostics", expanded=expanded):
        st.caption(f"Build **{WORKFLOW_UI_BUILD}** (dev only)")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f"**Change Goal clicked (UTC):** `{dbg.get('change_goal_clicked_at') or '—'}`"
            )
            st.markdown(
                f"**Goal card picked (UTC):** `{dbg.get('goal_selected_at') or '—'}`"
            )
            st.markdown(f"**`_workflow_intent`:** `{dbg.get('_workflow_intent') or '—'}`")
            st.markdown(
                f"**`_pending_investment_tab`:** `{dbg.get('_pending_investment_tab') or '—'}`"
            )
            st.markdown(
                f"**`investment_active_tab`:** `{dbg.get('investment_active_tab') or '—'}`"
            )
            goal_tab = workflow_tab_label_for_step("goal", beginner=beginner_mode)
            on_goal = dbg.get("investment_active_tab") == goal_tab
            st.markdown(
                f"**On Goal step now:** {'yes' if on_goal else 'no'} "
                f"(expected `{goal_tab}`)"
            )
        with c2:
            st.markdown(f"**`beginner_goal_card`:** `{dbg.get('beginner_goal_card') or '—'}`")
            st.markdown(f"**`guide_goal_choice`:** `{dbg.get('guide_goal_choice') or '—'}`")
            st.markdown(f"**`health_objective`:** `{dbg.get('health_objective') or '—'}`")
            st.markdown(f"**`preset_applied`:** `{dbg.get('preset_applied') or '—'}`")
            st.markdown(f"**Holdings fingerprint:** `{dbg.get('holdings_fp') or '—'}`")
        st.markdown("**Downstream checklist (unchecked = stale/needs rerun)**")
        st.json(
            {
                "goal": checklist.get("goal"),
                "portfolio": checklist.get("portfolio"),
                "analyze": checklist.get("analyze"),
                "health": checklist.get("health"),
                "recommendations": checklist.get("recommendations"),
                "stale_steps": dbg.get("stale_steps") or [],
            }
        )
        if dbg.get("autosave_ok") is not None:
            st.markdown(f"**Last cloud autosave after goal pick:** `{dbg.get('autosave_ok')}`")


def open_goal_step_navigation(st_obj: Any, *, beginner: bool) -> None:
    """
    Navigator **Open Goal** — resume change-goal mode or start it when downstream is stale.
    """
    ss = _sess(st_obj)
    if ss.get(_WORKFLOW_INTENT_KEY) == "change_goal":
        request_workflow_tab_navigation("goal", beginner=beginner, st_obj=st_obj)
        return
    stale = _stale_steps_set(ss) & {"analyze", "health", "recommendations"}
    if stale and workflow_checklist(st_obj).get("goal"):
        begin_goal_change_workflow(st_obj, beginner=beginner)
    else:
        request_workflow_tab_navigation("goal", beginner=beginner, st_obj=st_obj)


def request_workflow_tab_navigation(
    step: WorkflowStep,
    *,
    beginner: bool,
    st_obj: Any | None = None,
) -> None:
    """Schedule and commit a section tab change (safe before the workflow navigator renders)."""
    label = workflow_tab_label_for_step(step, beginner=beginner)
    commit_investment_tab_navigation(st_obj, label, beginner_mode=beginner)


def request_core_step_navigation(
    step: WorkflowCoreKey,
    *,
    beginner: bool,
    st_obj: Any | None = None,
) -> None:
    request_workflow_tab_navigation(_STEP_TO_WORKFLOW[step], beginner=beginner, st_obj=st_obj)


def apply_pending_investment_tab(
    st_obj: Any,
    tab_labels: list[str],
    *,
    beginner_mode: bool,
) -> bool:
    """
    Apply deferred navigation immediately before the section navigator.

    Returns True when a pending tab was applied to session state.
    """
    from components.beginner_navigation import normalize_tab_label_for_mode
    from investment_persistent_state import INVESTMENT_ACTIVE_TAB_KEY

    ss = _sess(st_obj)
    pending = ss.get(_PENDING_INVESTMENT_TAB_KEY)
    if not pending:
        return False
    label = normalize_tab_label_for_mode(str(pending).strip(), beginner=beginner_mode)
    if label not in tab_labels:
        return False
    ss.pop(_PENDING_INVESTMENT_TAB_KEY, None)
    if ss.get(INVESTMENT_ACTIVE_TAB_KEY) != label:
        ss[INVESTMENT_ACTIVE_TAB_KEY] = label
    return True


def navigate_workflow_tab(
    step: WorkflowStep,
    *,
    beginner: bool,
    st_obj: Any | None = None,
) -> None:
    """Schedule safe tab navigation (use ``apply_pending_investment_tab`` before the navigator)."""
    request_workflow_tab_navigation(step, beginner=beginner, st_obj=st_obj)


def needs_analytics_load(
    active_tab: str,
    tab_labels: list[str],
    st_obj: Any | None = None,
) -> bool:
    """
    True when this run should download market data and compute portfolio metrics.

    Goal and portfolio-edit tabs stay fast unless analysis is explicitly requested.
    """
    ss = _sess(st_obj)
    if ss.get("run_health") or ss.get("request_portfolio_analyze"):
        return True
    try:
        idx = tab_labels.index(active_tab)
    except ValueError:
        return True
    # Goal (0) and Portfolio Inputs / Build (2) — holdings only
    if idx in (0, 2):
        return False
    return True


def workflow_checklist(st_obj: Any | None = None) -> dict[str, bool]:
    """Sidebar checklist driven by completion flags + fresh health cache."""
    from components.beginner_navigation import _goal_step_complete, _portfolio_built

    ss = _sess(st_obj)
    fresh = _health_is_fresh(st_obj)
    fp = ss.get("health_result_fingerprint")

    goal_done = _goal_step_complete(st_obj)
    portfolio_done = _portfolio_built(st_obj)

    analyze_done = bool(ss.get("portfolio_analyzed")) and fresh
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


def _core_step_for_tab(active_tab: str, *, beginner: bool) -> WorkflowCoreKey | None:
    from components.beginner_navigation import ADVANCED_TAB_LABELS, BEGINNER_TAB_LABELS, STEP_TAB_LABEL

    labels = BEGINNER_TAB_LABELS if beginner else ADVANCED_TAB_LABELS
    mapping = {
        STEP_TAB_LABEL["goal"]: "goal",
        STEP_TAB_LABEL["portfolio"]: "portfolio",
        STEP_TAB_LABEL["analyze"]: "analyze",
        STEP_TAB_LABEL["health"]: "health",
        labels[0]: "goal",
        labels[2]: "portfolio",
        labels[3]: "analyze",
        labels[4]: "health",
    }
    return mapping.get(active_tab)  # type: ignore[return-value]


def workflow_step_visual_states(
    st_obj: Any | None = None,
    *,
    beginner: bool,
    active_tab: str | None = None,
) -> dict[WorkflowCoreKey, StepVisual]:
    """
    Visual state per core workflow step. No hard locks — stale steps remain navigable.
    """
    checklist = workflow_checklist(st_obj)
    stale = _stale_steps_set(_sess(st_obj))
    status = _sess(st_obj).get(_HEALTH_STATUS_KEY, "missing")

    first_open = 0
    for i, key in enumerate(WORKFLOW_CORE_STEPS):
        if not checklist[key]:
            first_open = i
            break
    else:
        first_open = len(WORKFLOW_CORE_STEPS) - 1

    active_step = _core_step_for_tab(active_tab, beginner=beginner) if active_tab else None
    states: dict[WorkflowCoreKey, StepVisual] = {}
    intent = _sess(st_obj).get(_WORKFLOW_INTENT_KEY)

    for i, key in enumerate(WORKFLOW_CORE_STEPS):
        if intent == "change_goal" and key == "goal":
            states[key] = "current" if active_step == "goal" else "stale"
            continue
        is_stale = key in stale or (
            key == "analyze"
            and status in ("portfolio_stale", "settings_stale")
        ) or (
            key in ("health", "recommendations")
            and (not _health_is_fresh(st_obj) or "analyze" in stale or not checklist["analyze"])
            and (checklist["portfolio"] or stale)
        )
        if active_step == key:
            states[key] = "current"
            continue
        if checklist[key] and not is_stale:
            states[key] = "complete"
        elif is_stale:
            states[key] = "stale"
        elif i <= first_open:
            states[key] = "available"
        else:
            states[key] = "available"
    return states


def mark_health_reviewed_for_portfolio(
    tickers: list[str],
    weights: Any,
    st_obj: Any | None = None,
) -> None:
    """Call when Portfolio Health UI is shown for the current holdings."""
    ss = _sess(st_obj)
    if not ss.get("health_result"):
        return
    fp = portfolio_analysis_fingerprint(tickers, weights)
    if ss.get("health_result_fingerprint") != fp:
        return
    record_workflow_health_status("fresh", st_obj)
    mark_health_reviewed(st_obj)
    ss[_HEALTH_VIEWED_FP_KEY] = fp
    _clear_stale_steps(ss, "health")
    _autosave_after_workflow_change(st_obj)


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
    _clear_stale_steps(ss, "recommendations")
    _autosave_after_workflow_change(st_obj)


def render_plan_context_banner(st_obj: Any, *, beginner: bool) -> None:
    """Always-visible summary of the single shared investment plan."""
    ss = _sess(st_obj)
    analysis = analysis_status_label(st_obj)
    recs = recommendations_status_label(st_obj)
    mode = "Beginner" if beginner else "Advanced"
    goal_line = goal_display_label(st_obj)
    port_line = portfolio_display_label(st_obj)

    last_change = ss.get("_workflow_last_goal_change")
    change_note = ""
    if isinstance(last_change, dict) and last_change.get("to_goal"):
        change_note = (
            f'<div style="color:#86efac;font-size:0.82rem;margin-top:0.45rem;">'
            f'Goal updated to <strong>{last_change.get("to_goal") or "—"}</strong></div>'
        )

    analysis_color = "#86efac" if "Up to date" in analysis else (
        "#fbbf24" if "Stale" in analysis or "Needs" in analysis else "#e2e8f0"
    )
    st.markdown(
        f"""
        <div style="background:rgba(20,28,43,0.95);border:1px solid #334155;border-radius:12px;
        padding:0.85rem 1rem;margin:0 0 0.75rem 0;">
        <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:#94a3b8;
        margin-bottom:0.45rem;">Your investment plan · {mode} view · same plan on every device</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:0.5rem 1rem;
        font-size:0.9rem;color:#e2e8f0;">
        <div><span style="color:#94a3b8;">Goal</span><br><strong>{goal_line}</strong></div>
        <div><span style="color:#94a3b8;">Portfolio</span><br><strong>{port_line}</strong></div>
        <div><span style="color:#94a3b8;">Analysis</span><br>
        <strong style="color:{analysis_color};">{analysis}</strong></div>
        <div><span style="color:#94a3b8;">Recommendations</span><br><strong>{recs}</strong></div>
        </div>
        {change_note}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workflow_intent_banner(st_obj: Any, *, beginner: bool) -> None:
    """Banner for active change-goal or rebuild-portfolio workflow."""
    ss = _sess(st_obj)
    intent = ss.get(_WORKFLOW_INTENT_KEY)
    if intent not in ("change_goal", "rebuild_portfolio"):
        return
    snap = ss.get(_WORKFLOW_CHANGE_SNAPSHOT_KEY) or {}
    if intent == "change_goal":
        st.info(
            f"**Change your goal** — Pick a new goal below. "
            f"Current: **{snap.get('goal', '—')}** · Portfolio: **{snap.get('portfolio', '—')}**. "
            f"Analysis, health, and recommendations were cleared and need to be run again."
        )
    else:
        tab = workflow_tab_label_for_core_step("portfolio", beginner=beginner)
        st.info(
            f"**Rebuild portfolio** — Adjust holdings on **{tab}** (or load a preset). "
            f"Goal stays **{snap.get('goal', goal_display_label(st_obj))}**. "
            f"Analysis, health, and recommendations were cleared."
        )


def render_rebuild_portfolio_panel(st_obj: Any, *, beginner: bool) -> bool:
    """
    Clear actions to rebuild holdings or change goal.

    Returns True if a navigation rerun was requested.
    """
    st.markdown("#### Rebuild / rebalance portfolio")
    st.caption(
        "**Change goal** starts goal-change mode (clears analysis progress, opens Step 1) — "
        "pick a new goal card to apply. **Edit holdings** starts rebuild mode on the portfolio step."
    )
    c1, c2 = st.columns(2)
    clicked = False
    with c1:
        if st.button(
            "Edit holdings & weights",
            key="wf_rebuild_edit_holdings",
            use_container_width=True,
            type="primary",
        ):
            begin_portfolio_rebuild_workflow(st_obj, beginner=beginner)
            clicked = True
    with c2:
        if st.button(
            "Change goal",
            key="wf_rebuild_change_goal",
            use_container_width=True,
            help="Starts goal-change mode: clears analysis/health/rec checkmarks and opens Step 1. "
            "Your new goal applies when you pick a goal card.",
        ):
            begin_goal_change_workflow(st_obj, beginner=beginner)
            clicked = True
    preset = _sess(st_obj).get("preset_applied")
    if preset:
        st.caption(f"Current preset: **{preset}** — choose a different goal card to load another template.")
    return clicked
