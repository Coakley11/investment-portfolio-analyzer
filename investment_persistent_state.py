"""Disk and cloud persistence for Investment Portfolio Analyzer."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

import pandas as pd

from suite_user_persistence import (
    load_user_state,
    reset_user_state,
    restore_once,
    state_file_path,
)

APP_ID = "investment"

# Bump when changing persistence diagnostics UI (visible in-app to confirm deploy).
PERSISTENCE_DEBUG_BUILD_ID = "2026-06-03-production-cleanup-v1"

_MODE_SWITCH_LOG_KEY = "_suite_inv_mode_switch_log"
_AUTOSAVE_LOG_KEY = "_suite_inv_autosave_log"
_PENDING_EXPERIENCE_KEY = "_suite_inv_pending_experience_mode"
_MAX_DIAG_LOG_ENTRIES = 8

INVESTMENT_ACTIVE_TAB_KEY = "investment_active_tab"
EXPERIENCE_KEY = "experience"
# Non-widget copy of mode — survives Streamlit widget init quirks; always in cloud blob.
PERSISTED_EXPERIENCE_KEY = "_suite_persisted_experience"
EXPERIENCE_OPTIONS = ("Beginner Mode", "Advanced Mode")

_MODE_DEBUG_KEYS = (
    "_suite_inv_debug_cloud_experience",
    "_suite_inv_debug_disk_experience",
    "_suite_inv_debug_picked_experience",
    "_suite_inv_debug_mode_after_restore",
    "_suite_inv_debug_mode_saved",
    "_suite_inv_debug_mode_final",
    "_suite_inv_debug_restore_ran",
    "_suite_inv_debug_restore_source",
)

# Scalar session keys included in cloud/local autosave.
_PERSIST_SCALAR_KEYS = (
    EXPERIENCE_KEY,
    PERSISTED_EXPERIENCE_KEY,
    INVESTMENT_ACTIVE_TAB_KEY,
    "sidebar_portfolio_value",
    "portfolio_preset",
    "preset_applied",
    "analysis_start_date",
    "analysis_end_date",
    "risk_free_pct",
    "asset_preset",
    "frontier_points",
    "health_rate_env",
    "health_inflation",
    "health_recession",
    "health_valuation",
    "health_regime",
    "macro_scenario_id",
    "macro_scenario_mode",
    "macro_auto_initialized",
    "health_objective",
    "health_bond_min",
    "health_run_optimizer",
    "beginner_objective",
    "guide_goal_choice",
    "beginner_goal_card",
    "guide_last_applied_goal",
    "guide_portfolio_loaded",
    "portfolio_built",
    "portfolio_analyzed",
    "portfolio_health_reviewed",
    "recommendations_displayed",
    "overview_subtab",
    "overview_show_extended_metrics",
    "mc_assumption_mode",
    "plan_total_cash",
    "plan_emergency",
    "plan_near_term",
    "plan_debt",
    "plan_expenses",
    "plan_monthly",
    "investment_plan_generated",
    "visited_explain",
    "visited_risk",
    "visited_forward",
    "visited_mc",
    "visited_implement",
    "run_risk_macro",
)

_LEGACY_TAB_KEY = "health_active_tab"

PERSIST_FIELD_DEFAULTS: dict[str, Any] = {
    EXPERIENCE_KEY: EXPERIENCE_OPTIONS[0],
    INVESTMENT_ACTIVE_TAB_KEY: None,
    "sidebar_portfolio_value": 100_000,
    "portfolio_preset": "— custom —",
    "preset_applied": None,
    "analysis_start_date": None,
    "analysis_end_date": None,
    "risk_free_pct": 4.0,
    "asset_preset": "—",
    "frontier_points": 2000,
    "health_rate_env": "Stable Rates",
    "health_inflation": "Moderate Inflation",
    "health_recession": 25,
    "health_valuation": "Fair Value",
    "health_regime": "Expansion",
    "macro_scenario_id": "current",
    "macro_scenario_mode": "current",
    "macro_auto_initialized": False,
    "health_objective": "balanced growth",
    "health_bond_min": 0,
    "health_run_optimizer": False,
    "beginner_objective": None,
    "guide_goal_choice": None,
    "beginner_goal_card": None,
    "guide_last_applied_goal": None,
    "guide_portfolio_loaded": False,
    "portfolio_built": False,
    "portfolio_analyzed": False,
    "portfolio_health_reviewed": False,
    "recommendations_displayed": False,
    "overview_subtab": None,
    "overview_show_extended_metrics": False,
    "mc_assumption_mode": "Historical returns",
    "plan_total_cash": 100_000,
    "plan_emergency": 20_000,
    "plan_near_term": 0,
    "plan_debt": 0,
    "plan_expenses": 0,
    "plan_monthly": 0,
    "investment_plan_generated": False,
    "visited_explain": False,
    "visited_risk": False,
    "visited_forward": False,
    "visited_mc": False,
    "visited_implement": False,
    "run_risk_macro": False,
    "holdings_df": "default holdings",
    "health_summary": None,
}

# Ephemeral keys cleared on Reset to Default (not written to cloud/disk).
_EXTRA_RESET_SESSION_KEYS = (
    "guide_auto_applied_preset",
    "guide_suggested_preset",
    "visited_risk",
    "visited_explain",
    "run_risk_macro",
    "run_health",
    "health_result",
    "health_result_fingerprint",
    "health_settings_fingerprint",
    "health_summary",
    "request_portfolio_analyze",
    "health_refresh",
    "macro_live_snapshot",
    "_activity_health_objective",
    "_activity_holdings_fp",
    "plan_compare_return",
    "mc_cached_summary",
    "investment_show_dev_diagnostics",
)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _append_diag_log(st: Any, key: str, entry: dict[str, Any]) -> None:
    ss = st.session_state
    log = ss.get(key)
    if not isinstance(log, list):
        log = []
    log.append(entry)
    ss[key] = log[-_MAX_DIAG_LOG_ENTRIES:]


def _stage_experience_value(st: Any, snap_key: str) -> str | None:
    snap = st.session_state.get(snap_key)
    if isinstance(snap, dict):
        val = snap.get("widget")
        if val not in EXPERIENCE_OPTIONS:
            val = snap.get("persisted")
        return str(val) if val in EXPERIENCE_OPTIONS else None
    return None


def current_experience_mode(st: Any) -> str:
    ss = st.session_state
    for key in (EXPERIENCE_KEY, PERSISTED_EXPERIENCE_KEY):
        val = ss.get(key)
        if val in EXPERIENCE_OPTIONS:
            return str(val)
    return EXPERIENCE_OPTIONS[0]


def validate_state_option(st: Any, key: str, options: list[str] | tuple[str, ...], default: str | None = None) -> None:
    opts = list(options)
    if not opts:
        return
    fallback = default if default is not None and default in opts else opts[0]
    if key not in st.session_state:
        st.session_state[key] = fallback
    elif st.session_state[key] not in opts:
        st.session_state[key] = fallback


def ensure_experience_mode(st: Any) -> None:
    """Seed the sidebar radio from persisted/cloud mode before the widget renders."""
    ss = st.session_state
    ss["_suite_inv_debug_experience_pre_ensure"] = {
        "widget": ss.get(EXPERIENCE_KEY),
        "persisted": ss.get(PERSISTED_EXPERIENCE_KEY),
    }
    persisted = ss.get(PERSISTED_EXPERIENCE_KEY)
    widget = ss.get(EXPERIENCE_KEY)
    if persisted in EXPERIENCE_OPTIONS and widget not in EXPERIENCE_OPTIONS:
        ss[EXPERIENCE_KEY] = persisted
    elif widget in EXPERIENCE_OPTIONS:
        ss[PERSISTED_EXPERIENCE_KEY] = widget
    default = persisted if persisted in EXPERIENCE_OPTIONS else EXPERIENCE_OPTIONS[0]
    validate_state_option(st, EXPERIENCE_KEY, EXPERIENCE_OPTIONS, default)
    ss[PERSISTED_EXPERIENCE_KEY] = ss[EXPERIENCE_KEY]
    ss["_suite_inv_debug_experience_post_ensure"] = {
        "widget": ss.get(EXPERIENCE_KEY),
        "persisted": ss.get(PERSISTED_EXPERIENCE_KEY),
    }


def _local_experience_change_in_flight(st: Any) -> bool:
    """True when the user just changed mode locally and cloud must not overwrite it yet."""
    ss = st.session_state
    widget = ss.get(EXPERIENCE_KEY)
    persisted = ss.get(PERSISTED_EXPERIENCE_KEY)
    pending = ss.get(_PENDING_EXPERIENCE_KEY)
    if pending in EXPERIENCE_OPTIONS:
        return True
    return (
        widget in EXPERIENCE_OPTIONS
        and persisted in EXPERIENCE_OPTIONS
        and widget != persisted
    )


def sync_experience_after_widget(st: Any) -> None:
    """Keep persisted copy aligned with the sidebar radio; autosave immediately on change."""
    ss = st.session_state
    mode = ss.get(EXPERIENCE_KEY)
    if mode not in EXPERIENCE_OPTIONS:
        return
    prev = ss.get(PERSISTED_EXPERIENCE_KEY)
    mode_change = prev != mode
    switch_evt: dict[str, Any] = {
        "at": _utc_now_iso(),
        "prev_persisted": prev,
        "widget_mode": mode,
        "mode_change_detected": mode_change,
        "pre_ensure_experience": _stage_experience_value(st, "_suite_inv_debug_experience_pre_ensure"),
        "post_ensure_experience": _stage_experience_value(st, "_suite_inv_debug_experience_post_ensure"),
    }
    ss[PERSISTED_EXPERIENCE_KEY] = mode
    ss["_suite_inv_debug_mode_final"] = mode
    ss["_suite_inv_debug_experience_post_widget"] = {
        "widget": ss.get(EXPERIENCE_KEY),
        "persisted": ss.get(PERSISTED_EXPERIENCE_KEY),
        "active": current_experience_mode(st),
    }
    switch_evt["post_widget_experience"] = mode
    if mode_change:
        ss[_PENDING_EXPERIENCE_KEY] = mode
        ss[f"_suite_persist_local_dirty::{APP_ID}"] = True
        switch_evt["local_dirty_set"] = True
        switch_evt["pending_experience_mode"] = mode
        try:
            from components.beginner_navigation import normalize_tab_label_for_mode

            raw_tab = ss.get(INVESTMENT_ACTIVE_TAB_KEY)
            if raw_tab:
                ss[INVESTMENT_ACTIVE_TAB_KEY] = normalize_tab_label_for_mode(
                    str(raw_tab),
                    beginner=(mode == "Beginner Mode"),
                )
        except ImportError:
            pass
        ss["_suite_inv_debug_mode_saved"] = mode
        switch_evt["autosave_triggered"] = True
        autosave_investment_state(st, trigger="mode_change")
    else:
        switch_evt["autosave_triggered"] = False
        switch_evt["autosave_skip_reason"] = "prev_equals_mode"
    _append_diag_log(st, _MODE_SWITCH_LOG_KEY, switch_evt)
    ss["_suite_inv_debug_last_mode_switch"] = switch_evt


def ensure_analysis_date_defaults(st: Any) -> None:
    end_default = dt.date.today()
    start_default = end_default - dt.timedelta(days=365 * 5)
    if "analysis_start_date" not in st.session_state:
        st.session_state["analysis_start_date"] = start_default
    if "analysis_end_date" not in st.session_state:
        st.session_state["analysis_end_date"] = end_default


def ensure_investment_active_tab(st: Any, tab_labels: list[str], *, beginner_mode: bool = False) -> None:
    if not tab_labels:
        return
    if INVESTMENT_ACTIVE_TAB_KEY not in st.session_state and _LEGACY_TAB_KEY in st.session_state:
        st.session_state[INVESTMENT_ACTIVE_TAB_KEY] = st.session_state[_LEGACY_TAB_KEY]
    raw = st.session_state.get(INVESTMENT_ACTIVE_TAB_KEY)
    if raw:
        try:
            from components.beginner_navigation import normalize_tab_label_for_mode

            st.session_state[INVESTMENT_ACTIVE_TAB_KEY] = normalize_tab_label_for_mode(
                str(raw),
                beginner=beginner_mode,
            )
        except ImportError:
            pass
    validate_state_option(st, INVESTMENT_ACTIVE_TAB_KEY, tab_labels, tab_labels[0])


def _df_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    return df.to_dict(orient="records")


def _normalize_restored_state(state: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(state)
    if INVESTMENT_ACTIVE_TAB_KEY not in out and _LEGACY_TAB_KEY in out:
        out[INVESTMENT_ACTIVE_TAB_KEY] = out[_LEGACY_TAB_KEY]
    exp = out.get(EXPERIENCE_KEY) or out.get(PERSISTED_EXPERIENCE_KEY)
    if exp in EXPERIENCE_OPTIONS:
        out[EXPERIENCE_KEY] = exp
        out[PERSISTED_EXPERIENCE_KEY] = exp
    return out


def investment_cloud_resync_needed(
    st: Any,
    cloud_state: dict[str, Any],
    cloud_ts: str | None = None,
) -> tuple[bool, str]:
    """
    True when live session drifts from cloud ``full_session`` (cross-device re-sync).

    Compares experience, goal/portfolio/workflow scalars, holdings fingerprint,
    and workflow blob — same fields persisted for phone ↔ Dell sync.
    """
    del cloud_ts
    if not isinstance(cloud_state, dict) or not cloud_state:
        return False, ""
    cloud = _normalize_restored_state(cloud_state)
    reasons: list[str] = []
    widget = st.session_state.get(EXPERIENCE_KEY)
    persisted = st.session_state.get(PERSISTED_EXPERIENCE_KEY)

    if not _local_experience_change_in_flight(st):
        cloud_exp = cloud.get(EXPERIENCE_KEY)
        live_exp = current_experience_mode(st)
        if cloud_exp in EXPERIENCE_OPTIONS and live_exp != cloud_exp:
            reasons.append("experience")

    for key in (
        "beginner_goal_card",
        "guide_goal_choice",
        "health_objective",
        "preset_applied",
        "portfolio_built",
        "portfolio_analyzed",
        "portfolio_health_reviewed",
        "recommendations_displayed",
        "investment_active_tab",
    ):
        if key not in cloud:
            continue
        live_val = st.session_state.get(key)
        if live_val is None and key in PERSIST_FIELD_DEFAULTS:
            live_val = PERSIST_FIELD_DEFAULTS[key]
        if cloud.get(key) != live_val:
            reasons.append(key)

    cloud_hfp = cloud.get("holdings_fingerprint")
    if cloud_hfp:
        try:
            from components.beginner_navigation import _holdings_fingerprint

            df = st.session_state.get("holdings_df")
            if isinstance(df, pd.DataFrame) and _holdings_fingerprint(df) != cloud_hfp:
                reasons.append("holdings_fingerprint")
        except ImportError:
            pass

    try:
        import json

        from investment_workflow import WORKFLOW_STATE_BLOB_KEY, build_workflow_persist_blob

        cloud_wf = cloud.get(WORKFLOW_STATE_BLOB_KEY)
        if isinstance(cloud_wf, dict) and cloud_wf:
            live_wf = build_workflow_persist_blob(st)
            if json.dumps(cloud_wf, sort_keys=True, default=str) != json.dumps(
                live_wf, sort_keys=True, default=str
            ):
                reasons.append("workflow_state")
    except ImportError:
        pass

    detail = ",".join(reasons)
    return bool(reasons), detail


def reconcile_investment_cloud_drift_if_needed(st: Any) -> bool:
    """
    Re-apply cloud ``full_session`` when in-memory state drifted (cross-device refresh).

    Safe to call every script run; skipped when local edits or mode change are in flight.
    """
    ss = st.session_state
    if _local_experience_change_in_flight(st):
        return False
    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    if ss.get(dirty_key):
        return False
    try:
        from suite_cloud_state import load_cloud_full_session
        from suite_user_persistence import _applied_cloud_ts_key

        cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        if not isinstance(cloud_state, dict) or not cloud_state:
            return False
        needed, detail = investment_cloud_resync_needed(st, cloud_state, cloud_ts)
        if not needed:
            return False
        apply_investment_disk_state(st, cloud_state)
        if cloud_ts:
            ss[_applied_cloud_ts_key(APP_ID)] = cloud_ts
        ss["_suite_inv_debug_cloud_reconcile"] = detail or "drift"
        _record_session_sync_debug(st)
        return True
    except Exception:
        return False


def _end_of_run_autosave_blocked(st: Any) -> tuple[bool, str]:
    """Block end-of-run autosave when cloud has newer authoritative state than memory."""
    ss = st.session_state
    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    if ss.get(dirty_key) or _local_experience_change_in_flight(st):
        return False, ""
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        if isinstance(cloud_state, dict) and cloud_state:
            needed, detail = investment_cloud_resync_needed(st, cloud_state, cloud_ts)
            if needed:
                return True, detail or "cloud drift"
    except Exception:
        pass
    cloud_exp = ss.get("_suite_inv_debug_cloud_experience")
    attempt = current_experience_mode(st)
    if cloud_exp in EXPERIENCE_OPTIONS and attempt != cloud_exp:
        return True, "experience mismatch vs cloud peek"
    return False, ""


def _record_restore_debug(st: Any, restored_blob: dict[str, Any]) -> None:
    restored_keys: list[str] = []
    default_keys: list[str] = []
    for field in PERSIST_FIELD_DEFAULTS:
        if field in restored_blob and restored_blob[field] is not None:
            if field == "holdings_df":
                if restored_blob[field]:
                    restored_keys.append(field)
                else:
                    default_keys.append(field)
            else:
                restored_keys.append(field)
        else:
            default_keys.append(field)
    st.session_state["_suite_persist_restored_fields"] = restored_keys
    st.session_state["_suite_persist_default_fields"] = default_keys


def _snapshot_mode_debug(st: Any, *, saved: str | None = None) -> None:
    ss = st.session_state
    if saved is not None:
        ss["_suite_inv_debug_mode_saved"] = saved
    ss["_suite_inv_debug_mode_final"] = current_experience_mode(st)


def _persist_scalar_value(ss: Any, key: str) -> Any:
    if key in ss:
        val = ss[key]
        if isinstance(val, dt.date):
            return val.isoformat()
        return copy.deepcopy(val)
    if key in PERSIST_FIELD_DEFAULTS:
        default = PERSIST_FIELD_DEFAULTS[key]
        if isinstance(default, dt.date):
            return default.isoformat()
        return copy.deepcopy(default)
    return None


def build_investment_disk_state(st: Any) -> dict[str, Any]:
    ss = st.session_state
    state: dict[str, Any] = {}
    mode = current_experience_mode(st)
    state[EXPERIENCE_KEY] = mode
    state[PERSISTED_EXPERIENCE_KEY] = mode
    for key in _PERSIST_SCALAR_KEYS:
        if key in (EXPERIENCE_KEY, PERSISTED_EXPERIENCE_KEY):
            continue
        val = _persist_scalar_value(ss, key)
        if val is not None or key in PERSIST_FIELD_DEFAULTS:
            state[key] = val
    if INVESTMENT_ACTIVE_TAB_KEY in state:
        state[_LEGACY_TAB_KEY] = state[INVESTMENT_ACTIVE_TAB_KEY]
    if "holdings_df" in ss and isinstance(ss["holdings_df"], pd.DataFrame):
        state["holdings_df"] = _df_to_records(ss["holdings_df"])
        try:
            from components.beginner_navigation import _holdings_fingerprint

            state["holdings_fingerprint"] = _holdings_fingerprint(ss["holdings_df"])
        except Exception:
            pass
    summary = ss.get("health_summary")
    if isinstance(summary, dict):
        state["health_summary"] = copy.deepcopy(summary)
    try:
        from investment_workflow import WORKFLOW_STATE_BLOB_KEY, build_workflow_persist_blob

        state[WORKFLOW_STATE_BLOB_KEY] = build_workflow_persist_blob(st)
    except ImportError:
        pass
    _snapshot_mode_debug(st, saved=mode)
    return state


def apply_investment_disk_state(st: Any, state: dict[str, Any]) -> None:
    import portfolio_core as core

    state = _normalize_restored_state(state)
    _record_restore_debug(st, state)
    st.session_state["_suite_inv_debug_picked_experience"] = state.get(EXPERIENCE_KEY)

    try:
        from investment_workflow import WORKFLOW_STATE_BLOB_KEY as _WF_BLOB
    except ImportError:
        _WF_BLOB = "workflow_state"

    for key, val in state.items():
        if key in (_LEGACY_TAB_KEY, _WF_BLOB, "holdings_fingerprint"):
            continue
        if key == "holdings_df":
            st.session_state["_suite_inv_holdings_from_saved_blob"] = True
            if val:
                try:
                    df = pd.DataFrame(val)
                except Exception:
                    st.session_state.holdings_df = pd.DataFrame()
                    st.session_state["_suite_inv_holdings_restore_issue"] = "invalid_saved_holdings"
                    continue
                if df.empty:
                    st.session_state.holdings_df = df
                    st.session_state["_suite_inv_holdings_restore_issue"] = "empty_saved_holdings"
                else:
                    st.session_state.holdings_df = df
                    st.session_state.pop("_suite_inv_holdings_restore_issue", None)
            else:
                st.session_state.holdings_df = pd.DataFrame()
                st.session_state["_suite_inv_holdings_restore_issue"] = "empty_saved_holdings"
            continue
        if key in ("analysis_start_date", "analysis_end_date") and isinstance(val, str):
            try:
                st.session_state[key] = dt.date.fromisoformat(val)
            except ValueError:
                continue
            continue
        st.session_state[key] = copy.deepcopy(val)

    exp = state.get(EXPERIENCE_KEY)
    preserve_exp: str | None = None
    if _local_experience_change_in_flight(st):
        preserve_exp = current_experience_mode(st)
    if exp in EXPERIENCE_OPTIONS and preserve_exp is None:
        st.session_state[EXPERIENCE_KEY] = exp
        st.session_state[PERSISTED_EXPERIENCE_KEY] = exp
    elif preserve_exp in EXPERIENCE_OPTIONS:
        st.session_state[EXPERIENCE_KEY] = preserve_exp
        st.session_state[PERSISTED_EXPERIENCE_KEY] = preserve_exp

    if "holdings_df" not in st.session_state:
        st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)
        st.session_state.pop("_suite_inv_holdings_from_saved_blob", None)
        st.session_state.pop("_suite_inv_holdings_restore_issue", None)

    try:
        from components.beginner_navigation import sync_beginner_goal_keys_from_portfolio

        sync_beginner_goal_keys_from_portfolio(st)
    except ImportError:
        pass

    try:
        from investment_workflow import WORKFLOW_STATE_BLOB_KEY, apply_workflow_persist_blob

        apply_workflow_persist_blob(st, state.get(WORKFLOW_STATE_BLOB_KEY))
    except ImportError:
        pass

    try:
        from investment_workflow import reconcile_workflow_after_restore

        reconcile_workflow_after_restore(st)
    except ImportError:
        pass

    try:
        from components.investment_planning import sanitize_plan_session_integers

        sanitize_plan_session_integers(st.session_state, PERSIST_FIELD_DEFAULTS)
    except ImportError:
        pass

    st.session_state["_suite_inv_debug_mode_after_restore"] = current_experience_mode(st)


def _record_session_sync_debug(st: Any) -> None:
    """Capture whether this Streamlit session skipped cloud re-sync (stale in-memory mode)."""
    ss = st.session_state
    try:
        from suite_cloud_state import parse_persist_timestamp
    except ImportError:
        parse_persist_timestamp = lambda _ts: 0.0  # type: ignore

    cloud_ts = ss.get("_suite_persist_debug_cloud_ts")
    applied = ss.get("_suite_applied_cloud_ts::investment")
    cloud_epoch = parse_persist_timestamp(cloud_ts)
    applied_epoch = parse_persist_timestamp(applied)
    cloud_exp = ss.get("_suite_inv_debug_cloud_experience")
    in_mem = current_experience_mode(st)
    already = bool(ss.get("_suite_disk_state_restored::investment"))
    skip_reason = ss.get("_suite_persist_restore_skip_reason")
    restore_ran = ss.get("_suite_inv_debug_restore_ran")
    cloud_newer = cloud_epoch > applied_epoch
    skip_not_newer = bool(
        already
        and cloud_ts
        and cloud_epoch <= applied_epoch
        and not ss.get("_suite_persist_local_dirty::investment")
    )
    memory_cloud_mismatch = (
        cloud_exp in EXPERIENCE_OPTIONS and in_mem in EXPERIENCE_OPTIONS and in_mem != cloud_exp
    )

    ss["_suite_inv_debug_session_sync"] = {
        "already_restored_flag": already,
        "restore_ran_this_script": restore_ran,
        "last_applied_cloud_ts": applied,
        "cloud_ts_peek": cloud_ts,
        "cloud_newer_than_applied": cloud_newer,
        "skip_resync_not_newer": skip_not_newer,
        "in_memory_experience": in_mem,
        "cloud_peek_experience": cloud_exp,
        "memory_cloud_mismatch": memory_cloud_mismatch,
        "restore_skip_reason": skip_reason,
        "local_dirty": ss.get("_suite_persist_local_dirty::investment"),
        "content_resync_needed": ss.get("_suite_persist_content_resync_needed"),
        "content_resync_detail": ss.get("_suite_persist_content_resync_detail"),
        "pending_experience_mode": ss.get(_PENDING_EXPERIENCE_KEY),
        "local_experience_change_in_flight": _local_experience_change_in_flight(st),
        "stale_session_likely": bool(
            memory_cloud_mismatch and (skip_not_newer or not restore_ran)
            and not ss.get("_suite_persist_content_resync_needed")
        ),
    }


def restore_investment_disk_state_once(st: Any) -> bool:
    st.session_state["_suite_inv_debug_cloud_experience"] = None
    st.session_state["_suite_inv_debug_disk_experience"] = None
    st.session_state["_suite_inv_debug_disk_file_exists"] = state_file_path(APP_ID).is_file()

    try:
        from suite_cloud_state import load_cloud_full_session, probe_cloud_restore_diagnostics

        diag = probe_cloud_restore_diagnostics(st, APP_ID)
        st.session_state["_suite_inv_debug_cloud_probe"] = diag

        cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        if cloud_state:
            st.session_state["_suite_inv_debug_cloud_experience"] = cloud_state.get(EXPERIENCE_KEY)
            st.session_state["_suite_inv_debug_cloud_persisted_experience"] = cloud_state.get(
                PERSISTED_EXPERIENCE_KEY
            )
        elif diag.get("cloud_has_full_session") is False and diag.get("cloud_row_found"):
            st.session_state["_suite_persist_cloud_peek_error"] = (
                "cloud row exists but metrics.full_session is empty"
            )
    except Exception as exc:
        st.session_state["_suite_persist_cloud_peek_error"] = str(exc)

    disk_state, _disk_warn = load_user_state(APP_ID)
    if disk_state:
        st.session_state["_suite_inv_debug_disk_experience"] = disk_state.get(EXPERIENCE_KEY)
        st.session_state["_suite_inv_debug_disk_persisted_experience"] = disk_state.get(
            PERSISTED_EXPERIENCE_KEY
        )

    restored = restore_once(
        st,
        APP_ID,
        apply_state=lambda st_obj, s: apply_investment_disk_state(st_obj, s),
        cloud_resync_needed=investment_cloud_resync_needed,
    )
    st.session_state["_suite_inv_debug_restore_ran"] = restored
    st.session_state["_suite_inv_debug_restore_source"] = st.session_state.get(
        "_suite_persist_last_restore_source"
    )
    st.session_state["_suite_inv_debug_pick_reason"] = st.session_state.get(
        "_suite_persist_last_restore_reason"
    )
    if not restored and not st.session_state.get("_suite_disk_state_restored::investment"):
        ensure_experience_mode(st)
        st.session_state["_suite_inv_debug_mode_after_restore"] = current_experience_mode(st)
    elif restored:
        st.session_state["_suite_inv_debug_mode_after_restore"] = current_experience_mode(st)
    _record_session_sync_debug(st)
    apply_suite_investment_resume(st)
    return restored


def apply_suite_investment_resume(st: Any) -> None:
    """Apply Command Center deep-link tab + holdings fingerprint validation after restore."""
    page = st.session_state.pop("_suite_investment_page", None)
    expected_fp = str(st.session_state.pop("_suite_holdings_fp", "") or "").strip()

    if page:
        tab = str(page).strip()
        if tab:
            try:
                from components.beginner_navigation import normalize_tab_label_for_mode

                beginner = current_experience_mode(st) == EXPERIENCE_OPTIONS[0]
                tab = normalize_tab_label_for_mode(tab, beginner=beginner)
            except Exception:
                pass
            st.session_state[INVESTMENT_ACTIVE_TAB_KEY] = tab
            st.session_state[_LEGACY_TAB_KEY] = tab

    if not expected_fp:
        return

    try:
        from components.beginner_navigation import _holdings_fingerprint

        df = st.session_state.get("holdings_df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            actual_fp = str(_holdings_fingerprint(df))
            if actual_fp == expected_fp:
                st.session_state["_suite_holdings_fp_confirmed"] = True
            else:
                st.session_state["_suite_holdings_fp_mismatch"] = {
                    "expected": expected_fp,
                    "actual": actual_fp,
                }
    except Exception:
        pass


def autosave_investment_state(st: Any, *, end_of_run: bool = False, trigger: str = "unknown") -> None:
    """Persist session snapshot with detailed autosave diagnostics (phone + Dell)."""
    import hashlib
    import json

    from suite_user_persistence import (
        _LOCAL_DIRTY_PREFIX,
        _SESSION_SAVED_FLASH_KEY,
        _applied_cloud_ts_key,
        _restored_fp_key,
        save_user_state,
    )

    ss = st.session_state
    fp_key = f"_suite_autosave_fp::{APP_ID}"
    dirty_key = f"{_LOCAL_DIRTY_PREFIX}{APP_ID}"
    restored_fp_key = _restored_fp_key(APP_ID)
    applied_cloud_key = _applied_cloud_ts_key(APP_ID)

    attempt_mode = current_experience_mode(st)
    if end_of_run:
        ss["_suite_inv_debug_eor_autosave_attempt_mode"] = attempt_mode
        blocked, block_reason = _end_of_run_autosave_blocked(st)
        if blocked:
            event = {
                "at": _utc_now_iso(),
                "trigger": trigger,
                "end_of_run": True,
                "mode_at_autosave": attempt_mode,
                "outcome": "skipped_eor_cloud_drift",
                "skip_reason": block_reason,
            }
            _append_diag_log(st, _AUTOSAVE_LOG_KEY, event)
            ss["_suite_inv_debug_last_autosave_event"] = event
            return
    else:
        ss["_suite_inv_debug_autosave_attempt_mode"] = attempt_mode

    event: dict[str, Any] = {
        "at": _utc_now_iso(),
        "trigger": trigger,
        "end_of_run": end_of_run,
        "mode_at_autosave": attempt_mode,
        "widget_at_autosave": ss.get(EXPERIENCE_KEY),
        "persisted_at_autosave": ss.get(PERSISTED_EXPERIENCE_KEY),
    }

    try:
        state = build_investment_disk_state(st)
        event["blob_experience"] = state.get(EXPERIENCE_KEY)
        event["blob_persisted"] = state.get(PERSISTED_EXPERIENCE_KEY)

        blob = json.dumps(state, sort_keys=True, default=str)
        fp = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
        fp_before = ss.get(fp_key)
        event["fp_before"] = fp_before
        event["fp_after"] = fp

        restored_fp = ss.get(restored_fp_key)
        if restored_fp and fp != restored_fp:
            ss[dirty_key] = True

        if ss.get(fp_key) == fp:
            event["outcome"] = "skipped_fp_unchanged"
            if trigger == "mode_change":
                ss[dirty_key] = True
            _append_diag_log(st, _AUTOSAVE_LOG_KEY, event)
            ss["_suite_inv_debug_last_autosave_event"] = event
            return

        saved_disk = save_user_state(APP_ID, state)
        saved_cloud = False
        try:
            from suite_cloud_state import load_cloud_full_session, save_cloud_full_session, session_page_summary

            page, summary = session_page_summary(APP_ID, state)
            save_cloud_full_session(APP_ID, state, page=page, summary=summary)
            saved_cloud = True
            cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
            if cloud_state:
                event["cloud_readback_experience"] = cloud_state.get(EXPERIENCE_KEY)
                event["cloud_readback_persisted"] = cloud_state.get(PERSISTED_EXPERIENCE_KEY)
            event["cloud_readback_ts"] = cloud_ts
        except Exception as exc:
            event["cloud_save_error"] = str(exc)

        event["saved_disk"] = saved_disk
        event["saved_cloud"] = saved_cloud
        event["outcome"] = "saved" if (saved_disk or saved_cloud) else "save_failed"

        if saved_disk or saved_cloud:
            ss[fp_key] = fp
            ss[restored_fp_key] = fp
            readback_exp = event.get("cloud_readback_experience")
            mode_saved_to_cloud = (
                trigger == "mode_change"
                and saved_cloud
                and readback_exp == attempt_mode
            )
            if trigger == "mode_change" and not mode_saved_to_cloud:
                ss[dirty_key] = True
            else:
                ss[dirty_key] = False
            if mode_saved_to_cloud:
                ss.pop(_PENDING_EXPERIENCE_KEY, None)
            readback_ts = event.get("cloud_readback_ts")
            if saved_cloud and readback_ts:
                ss[applied_cloud_key] = readback_ts
                event["applied_cloud_ts"] = readback_ts
                event["applied_cloud_ts_source"] = "cloud_readback"
            else:
                ss[applied_cloud_key] = event["at"]
                event["applied_cloud_ts"] = event["at"]
                event["applied_cloud_ts_source"] = "local_fallback"
            ss["_suite_persist_last_save_at"] = event["at"]
            ss[_SESSION_SAVED_FLASH_KEY] = True
            written_key = (
                "_suite_inv_debug_eor_autosave_written_mode"
                if end_of_run
                else "_suite_inv_debug_autosave_written_mode"
            )
            ss[written_key] = attempt_mode
            if end_of_run:
                cloud_at_open = ss.get("_suite_inv_debug_cloud_experience")
                ss["_suite_inv_debug_autosave_wrote_beginner_over_cloud_advanced"] = (
                    cloud_at_open == "Advanced Mode" and attempt_mode == EXPERIENCE_OPTIONS[0]
                )
    except Exception as exc:
        event["outcome"] = "exception"
        event["error"] = str(exc)

    _append_diag_log(st, _AUTOSAVE_LOG_KEY, event)
    ss["_suite_inv_debug_last_autosave_event"] = event


def finalize_persistence_debug(st: Any) -> None:
    _snapshot_mode_debug(st)


def _restore_probe_lines(st: Any) -> list[str]:
    ss = st.session_state
    probe = ss.get("_suite_inv_debug_cloud_probe")
    if not isinstance(probe, dict):
        return ["cloud probe: not run"]
    lines = [
        f"cloud enabled: {probe.get('cloud_enabled')!r}",
        f"storage module: {probe.get('storage_module')!r}",
        f"cloud row found: {probe.get('cloud_row_found')!r}",
        f"cloud has full_session: {probe.get('cloud_has_full_session')!r}",
        f"cloud updated_at: {probe.get('cloud_updated_at')!r}",
        f"skip resume params: {probe.get('skip_resume_params')!r}",
        f"resume launch flag: {probe.get('resume_launch_flag')!r}",
        f"disk file exists: {ss.get('_suite_inv_debug_disk_file_exists')!r}",
        f"session restored flag: {ss.get('_suite_disk_state_restored::investment')!r}",
        f"restore skip reason: {ss.get('_suite_persist_restore_skip_reason')!r}",
    ]
    if probe.get("cloud_load_error"):
        lines.append(f"cloud probe error: {probe.get('cloud_load_error')!r}")
    return lines


def session_sync_trace_lines(st: Any) -> list[str]:
    """Streamlit session re-sync gate (stale in-memory mode vs newer cloud)."""
    ss = st.session_state
    sync = ss.get("_suite_inv_debug_session_sync")
    if not isinstance(sync, dict):
        return ["session sync: not recorded"]
    lines = [f"build: {PERSISTENCE_DEBUG_BUILD_ID}"]
    for key in (
        "already_restored_flag",
        "restore_ran_this_script",
        "last_applied_cloud_ts",
        "cloud_ts_peek",
        "cloud_newer_than_applied",
        "skip_resync_not_newer",
        "in_memory_experience",
        "cloud_peek_experience",
        "memory_cloud_mismatch",
        "restore_skip_reason",
        "local_dirty",
        "content_resync_needed",
        "content_resync_detail",
        "pending_experience_mode",
        "local_experience_change_in_flight",
        "stale_session_likely",
    ):
        lines.append(f"{key}: {sync.get(key)!r}")
    lines.append(
        "note: content_resync_needed bypasses timestamp skip; last_applied uses cloud readback after save"
    )
    return lines


def experience_mode_trace_lines(st: Any) -> list[str]:
    ss = st.session_state
    pick_source = ss.get("_suite_persist_debug_pick_source")
    pick_reason = ss.get("_suite_persist_debug_pick_reason")
    cloud_exp = ss.get("_suite_inv_debug_cloud_experience")
    disk_exp = ss.get("_suite_inv_debug_disk_experience")
    restored = ss.get("_suite_inv_debug_mode_after_restore")
    pre_ensure = _stage_experience_value(st, "_suite_inv_debug_experience_pre_ensure")
    post_ensure = _stage_experience_value(st, "_suite_inv_debug_experience_post_ensure")
    post_widget = _stage_experience_value(st, "_suite_inv_debug_experience_post_widget")
    final = ss.get("_suite_inv_debug_mode_final") or current_experience_mode(st)
    disk_won = pick_source == "disk"
    cloud_disk_mismatch = (
        cloud_exp in EXPERIENCE_OPTIONS
        and disk_exp in EXPERIENCE_OPTIONS
        and cloud_exp != disk_exp
    )
    hypothesis_a = bool(disk_won and cloud_disk_mismatch)
    hypothesis_b = bool(
        restored in EXPERIENCE_OPTIONS
        and post_widget in EXPERIENCE_OPTIONS
        and restored != post_widget
    )
    hypothesis_c = bool(ss.get("_suite_inv_debug_autosave_wrote_beginner_over_cloud_advanced"))

    return [
        f"build: {PERSISTENCE_DEBUG_BUILD_ID}",
        f"cloud experience: {cloud_exp!r}",
        f"disk experience: {disk_exp!r}",
        f"picked source: {pick_source!r}",
        f"picked reason: {pick_reason!r}",
        f"restored experience: {restored!r}",
        f"pre-ensure experience: {pre_ensure!r}",
        f"post-ensure experience: {post_ensure!r}",
        f"post-widget experience: {post_widget!r}",
        f"final active experience: {final!r}",
        f"disk won over cloud: {disk_won} (cloud={cloud_exp!r}, disk={disk_exp!r}, reason={pick_reason!r})",
        f"end-run autosave attempt mode: {ss.get('_suite_inv_debug_eor_autosave_attempt_mode')!r}",
        f"end-run autosave wrote mode: {ss.get('_suite_inv_debug_eor_autosave_written_mode')!r}",
        f"end-run autosave wrote Beginner over cloud Advanced: {hypothesis_c}",
        f"hypothesis A (disk beat newer cloud): {hypothesis_a}",
        f"hypothesis B (widget overwrote restore): {hypothesis_b}",
        f"hypothesis C (end-run autosave clobbered cloud): {hypothesis_c}",
        f"cloud timestamp: {ss.get('_suite_persist_debug_cloud_ts')!r}",
        f"disk timestamp: {ss.get('_suite_persist_debug_disk_ts')!r}",
        f"local dirty: {ss.get('_suite_persist_local_dirty::investment')!r}",
        f"restore ran: {ss.get('_suite_inv_debug_restore_ran')!r}",
    ]


def _format_diag_event(prefix: str, evt: dict[str, Any]) -> list[str]:
    lines = [f"{prefix} @ {evt.get('at')!r}"]
    for key in sorted(evt):
        if key == "at":
            continue
        lines.append(f"  {key}: {evt.get(key)!r}")
    return lines


def mode_switch_and_autosave_trace_lines(st: Any) -> list[str]:
    """Phone-side mode switch + autosave trail (last events in this session)."""
    ss = st.session_state
    lines = [f"build: {PERSISTENCE_DEBUG_BUILD_ID}", "— mode switch events —"]
    switch_log = ss.get(_MODE_SWITCH_LOG_KEY)
    if isinstance(switch_log, list) and switch_log:
        for idx, evt in enumerate(switch_log, start=1):
            if isinstance(evt, dict):
                lines.extend(_format_diag_event(f"switch #{idx}", evt))
    else:
        lines.append("  (none yet — toggle Experience radio to populate)")

    lines.append("— autosave events —")
    autosave_log = ss.get(_AUTOSAVE_LOG_KEY)
    if isinstance(autosave_log, list) and autosave_log:
        for idx, evt in enumerate(autosave_log, start=1):
            if isinstance(evt, dict):
                lines.extend(_format_diag_event(f"autosave #{idx}", evt))
    else:
        lines.append("  (none yet)")

    last_switch = ss.get("_suite_inv_debug_last_mode_switch")
    last_autosave = ss.get("_suite_inv_debug_last_autosave_event")
    if isinstance(last_switch, dict):
        lines.append("— last mode switch summary —")
        lines.append(f"  mode_change_detected: {last_switch.get('mode_change_detected')!r}")
        lines.append(f"  autosave_triggered: {last_switch.get('autosave_triggered')!r}")
        lines.append(f"  autosave_skip_reason: {last_switch.get('autosave_skip_reason')!r}")
        lines.append(f"  post_widget_experience: {last_switch.get('post_widget_experience')!r}")
    if isinstance(last_autosave, dict):
        lines.append("— last autosave summary —")
        lines.append(f"  trigger: {last_autosave.get('trigger')!r}")
        lines.append(f"  outcome: {last_autosave.get('outcome')!r}")
        lines.append(f"  blob_experience: {last_autosave.get('blob_experience')!r}")
        lines.append(f"  blob_persisted: {last_autosave.get('blob_persisted')!r}")
        lines.append(f"  cloud_readback_experience: {last_autosave.get('cloud_readback_experience')!r}")
        lines.append(f"  cloud_readback_persisted: {last_autosave.get('cloud_readback_persisted')!r}")
        lines.append(f"  cloud_readback_ts: {last_autosave.get('cloud_readback_ts')!r}")
        if last_autosave.get("cloud_save_error"):
            lines.append(f"  cloud_save_error: {last_autosave.get('cloud_save_error')!r}")
    return lines


def restore_diagnostics_lines(st: Any) -> list[str]:
    return _restore_probe_lines(st)


def _persistence_account_lines(st: Any) -> list[str]:
    try:
        from suite_user import account_mode, get_account_user_id, get_external_user_id

        return [
            f"suite_user_id: {get_external_user_id()!r}",
            f"account_user_id: {get_account_user_id()!r}",
            f"account_mode: {account_mode()!r}",
        ]
    except Exception as exc:
        return [f"account info error: {exc}"]


def render_persistence_debug_content(st: Any) -> None:
    """Shared debug body (main page + sidebar). Requires developer diagnostics enabled."""
    try:
        from investment_workflow import developer_diagnostics_enabled

        if not developer_diagnostics_enabled(st):
            return
    except ImportError:
        return
    ss = st.session_state
    save_at = ss.get("_suite_persist_last_save_at")
    restore_at = ss.get("_suite_persist_last_restore_at")
    source = ss.get("_suite_persist_last_restore_source") or "—"
    st.caption(f"Diagnostic build **{PERSISTENCE_DEBUG_BUILD_ID}**")
    st.caption(f"Last cloud save: **{save_at or '—'}** · restore: **{restore_at or '—'}** ({source})")
    st.markdown("**Session sync trace (stale in-memory vs cloud)**")
    st.code("\n".join(session_sync_trace_lines(st)), language=None)
    st.markdown("**Experience mode trace (restore / Dell)**")
    st.code("\n".join(experience_mode_trace_lines(st)), language=None)
    st.markdown("**Mode switch + autosave trace (phone / save path)**")
    st.code("\n".join(mode_switch_and_autosave_trace_lines(st)), language=None)
    st.markdown("**Restore diagnostics**")
    st.code("\n".join(restore_diagnostics_lines(st)), language=None)
    holdings_issue = ss.get("_suite_inv_holdings_restore_issue")
    if holdings_issue:
        st.warning(
            f"Saved holdings restore issue (developer): **{holdings_issue}** — "
            "portfolio was not replaced with SPY/BND defaults."
        )
    st.markdown("**Account scope**")
    st.code("\n".join(_persistence_account_lines(st)), language=None)
    import_err = ss.get("_suite_persist_import_error")
    restore_err = ss.get("_suite_persist_restore_error")
    cloud_err = ss.get("_suite_persist_cloud_peek_error")
    if import_err:
        st.warning(f"Persistence import error: {import_err}")
    if restore_err:
        st.warning(f"Persistence restore error: {restore_err}")
    try:
        from investment_workflow import workflow_persist_audit

        st.markdown("**Workflow full_session audit (live vs saved)**")
        audit = workflow_persist_audit(st)
        st.code("\n".join(f"{k}: {v}" for k, v in audit.items()), language=None)
    except ImportError:
        pass
    if cloud_err:
        st.caption(f"Cloud peek error: {cloud_err}")
    try:
        from components.beginner_navigation import goal_workflow_debug_lines

        if current_experience_mode(st) == "Beginner Mode":
            st.markdown("**Goal workflow trace**")
            st.code("\n".join(goal_workflow_debug_lines(st)), language=None)
    except Exception:
        pass


def render_persistence_debug_sidebar(st: Any) -> None:
    """Sidebar persistence trace (developer toggle must be on)."""
    try:
        from investment_workflow import developer_diagnostics_enabled

        if not developer_diagnostics_enabled(st):
            return
    except ImportError:
        return
    with st.sidebar.expander("Persistence diagnostics", expanded=False):
        render_persistence_debug_content(st)


def render_persistence_debug_main(st: Any) -> None:
    """Main page persistence trace (developer toggle must be on)."""
    try:
        from investment_workflow import developer_diagnostics_enabled

        if not developer_diagnostics_enabled(st):
            return
    except ImportError:
        return
    with st.expander("Persistence diagnostics (developer)", expanded=False):
        render_persistence_debug_content(st)


def render_persistence_debug(st: Any, *, final: bool = False) -> None:
    """Legacy entry point; sidebar-only partial view before init completes."""
    del final
    render_persistence_debug_sidebar(st)


def apply_investment_session_defaults(st: Any) -> None:
    """Apply first-run defaults to ``st.session_state`` (goal tab, empty workflow)."""
    import portfolio_core as core

    from components.beginner_navigation import ADVANCED_TAB_LABELS, BEGINNER_TAB_LABELS

    try:
        from investment_workflow import reset_investment_workflow_state

        reset_investment_workflow_state(st)
    except ImportError:
        pass

    ss = st.session_state
    for key in list(ss.keys()):
        if str(key).startswith("_suite_"):
            ss.pop(key, None)
    for key in _EXTRA_RESET_SESSION_KEYS:
        ss.pop(key, None)

    for key, default in PERSIST_FIELD_DEFAULTS.items():
        if key == "holdings_df":
            ss["holdings_df"] = pd.DataFrame(core.DEFAULT_HOLDINGS)
        elif default is None:
            ss.pop(key, None)
        else:
            ss[key] = copy.deepcopy(default)

    mode = ss.get(EXPERIENCE_KEY)
    if mode not in EXPERIENCE_OPTIONS:
        mode = EXPERIENCE_OPTIONS[0]
    ss[EXPERIENCE_KEY] = mode
    ss[PERSISTED_EXPERIENCE_KEY] = mode
    ss[INVESTMENT_ACTIVE_TAB_KEY] = (
        BEGINNER_TAB_LABELS[0] if mode == EXPERIENCE_OPTIONS[0] else ADVANCED_TAB_LABELS[0]
    )
    ss.pop(_LEGACY_TAB_KEY, None)
    ensure_analysis_date_defaults(st)
    try:
        from components.investment_planning import sanitize_plan_session_integers

        sanitize_plan_session_integers(ss, PERSIST_FIELD_DEFAULTS)
    except ImportError:
        pass


def default_reset_investment_session(st: Any) -> None:
    """
    Full Investment reset: session, local disk, and cloud ``full_session``.

    Called from sidebar Reset after ``reset_user_state`` deletes the disk file.
    """
    from suite_user_persistence import (
        _LOCAL_DIRTY_PREFIX,
        _SESSION_RESTORED_PREFIX,
        _restored_fp_key,
        save_user_state,
    )

    apply_investment_session_defaults(st)

    fresh = build_investment_disk_state(st)
    save_user_state(APP_ID, fresh)

    try:
        from suite_cloud_state import clear_cloud_full_session, save_cloud_full_session

        clear_cloud_full_session(APP_ID)
        tab = st.session_state.get(INVESTMENT_ACTIVE_TAB_KEY, "")
        save_cloud_full_session(
            APP_ID,
            fresh,
            page=str(tab),
            summary="Reset to defaults",
        )
    except Exception as exc:
        st.session_state["_suite_persist_reset_cloud_error"] = str(exc)

    flag = f"{_SESSION_RESTORED_PREFIX}{APP_ID}"
    st.session_state[flag] = True
    try:
        import hashlib
        import json

        blob = json.dumps(fresh, sort_keys=True, default=str)
        st.session_state[_restored_fp_key(APP_ID)] = hashlib.sha256(blob.encode("utf-8")).hexdigest()[
            :20
        ]
    except Exception:
        pass
    st.session_state[f"{_LOCAL_DIRTY_PREFIX}{APP_ID}"] = False
