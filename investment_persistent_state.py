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
_TAB_CHANGE_LOG_KEY = "_suite_inv_tab_change_log"
_GLOBAL_SETTINGS_LOG_KEY = "_suite_inv_global_settings_log"
_PORTFOLIO_CHANGE_LOG_KEY = "_suite_inv_portfolio_change_log"
_PENDING_EXPERIENCE_KEY = "_suite_inv_pending_experience_mode"
_LAST_PERSISTED_TAB_KEY = "_suite_inv_last_persisted_tab"
_LAST_PERSISTED_GLOBAL_KEY = "_suite_inv_last_persisted_global"
_LAST_PERSISTED_PORTFOLIO_FP_KEY = "_suite_inv_last_persisted_portfolio_fp"
_TAB_PAGE_DIRTY_KEY = "_suite_inv_tab_page_dirty"
_GLOBAL_PAGE_DIRTY_KEY = "_suite_inv_global_page_dirty"
_PORTFOLIO_PAGE_DIRTY_KEY = "_suite_inv_portfolio_page_dirty"
_PORTFOLIO_VALUE_USER_SET_KEY = "_suite_inv_portfolio_value_user_set"
_AMI_PERSIST_SESSION_KEYS = (
    "_ami_pending_insight",
    "insight_source_tab",
    "source_investment_tab",
    "_ami_return_page",
)
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
    """Seed the sidebar radio from persisted mode only when the widget key is unset."""
    ss = st.session_state
    if ss.get(EXPERIENCE_KEY) in EXPERIENCE_OPTIONS:
        return
    persisted = ss.get(PERSISTED_EXPERIENCE_KEY)
    if persisted in EXPERIENCE_OPTIONS:
        ss[EXPERIENCE_KEY] = persisted
    else:
        ss[EXPERIENCE_KEY] = EXPERIENCE_OPTIONS[0]
        ss[PERSISTED_EXPERIENCE_KEY] = EXPERIENCE_OPTIONS[0]


def _local_experience_change_in_flight(st: Any) -> bool:
    """True when a local mode change is pending cloud save (do not overwrite from cloud yet)."""
    pending = st.session_state.get(_PENDING_EXPERIENCE_KEY)
    return pending in EXPERIENCE_OPTIONS


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
    ss["_suite_inv_debug_experience_post_click"] = {
        "widget": ss.get(EXPERIENCE_KEY),
        "persisted": ss.get(PERSISTED_EXPERIENCE_KEY),
        "active": current_experience_mode(st),
    }
    if mode_change:
        ss["_suite_inv_experience_user_choice"] = mode
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


def _last_persisted_tab(ss: Any) -> str | None:
    raw = ss.get(_LAST_PERSISTED_TAB_KEY)
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return None


def notify_investment_tab_change(
    st: Any,
    tab: str,
    *,
    source: str = "unknown",
    trigger_save: bool = True,
) -> bool:
    """
    Device A save path: mark tab/page dirty and autosave when ``investment_active_tab`` changes.

    Mirrors ``sync_experience_after_widget`` — immediate ``tab_change`` save bypasses
    end-of-run cloud-drift block and unchanged-fingerprint skip.
    """
    ss = st.session_state
    new_tab = str(tab or "").strip()
    if not new_tab:
        return False

    prev = _last_persisted_tab(ss)
    if ss.get(INVESTMENT_ACTIVE_TAB_KEY) != new_tab:
        ss[INVESTMENT_ACTIVE_TAB_KEY] = new_tab
        ss[_LEGACY_TAB_KEY] = new_tab

    tab_change = prev != new_tab
    switch_evt: dict[str, Any] = {
        "at": _utc_now_iso(),
        "source": source,
        "prev_persisted_tab": prev,
        "new_tab": new_tab,
        "widget_tab": ss.get(INVESTMENT_ACTIVE_TAB_KEY),
        "tab_change_detected": tab_change,
    }
    if not tab_change:
        switch_evt["autosave_triggered"] = False
        switch_evt["autosave_skip_reason"] = "prev_equals_tab"
        _append_diag_log(st, _TAB_CHANGE_LOG_KEY, switch_evt)
        ss["_suite_inv_debug_last_tab_change"] = switch_evt
        return False

    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    ss[dirty_key] = True
    ss[_TAB_PAGE_DIRTY_KEY] = True
    switch_evt["local_dirty_set"] = True
    switch_evt["tab_page_dirty"] = True
    _append_diag_log(st, _TAB_CHANGE_LOG_KEY, switch_evt)
    ss["_suite_inv_debug_last_tab_change"] = switch_evt

    if trigger_save:
        switch_evt["autosave_triggered"] = True
        autosave_investment_state(st, trigger="tab_change")
        last = ss.get("_suite_inv_debug_last_autosave_event")
        if isinstance(last, dict):
            switch_evt["autosave_outcome"] = last.get("outcome")
            switch_evt["saved_tab"] = last.get("blob_tab") or last.get("cloud_readback_tab")
            switch_evt["cloud_readback_tab"] = last.get("cloud_readback_tab")
        ss["_suite_inv_debug_last_tab_change"] = switch_evt
    else:
        switch_evt["autosave_triggered"] = False
    return True


def sync_investment_active_tab_after_widget(st: Any) -> None:
    """Autosave when the section radio changes ``investment_active_tab`` (Advanced fallback path)."""
    ss = st.session_state
    tab = ss.get(INVESTMENT_ACTIVE_TAB_KEY)
    if not tab:
        return
    prev = _last_persisted_tab(ss)
    if prev != str(tab).strip():
        notify_investment_tab_change(st, str(tab), source="section_radio")


def _normalize_global_settings_value(key: str, val: Any) -> Any:
    if isinstance(val, dt.date):
        return val.isoformat()
    if key == "sidebar_portfolio_value" and val is not None:
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return val
    if key == "risk_free_pct" and val is not None:
        try:
            return round(float(val), 4)
        except (TypeError, ValueError):
            return val
    return copy.deepcopy(val) if val is not None else None


def global_settings_payload_from_session(ss: Any) -> dict[str, Any]:
    """Normalized global settings snapshot for dirty detection and save traces."""
    start = ss.get("analysis_start_date")
    end = ss.get("analysis_end_date")
    return {
        "experience": ss.get(EXPERIENCE_KEY),
        "_suite_persisted_experience": ss.get(PERSISTED_EXPERIENCE_KEY),
        "sidebar_portfolio_value": _normalize_global_settings_value(
            "sidebar_portfolio_value", ss.get("sidebar_portfolio_value")
        ),
        "analysis_start_date": _normalize_global_settings_value("analysis_start_date", start),
        "analysis_end_date": _normalize_global_settings_value("analysis_end_date", end),
        "risk_free_pct": _normalize_global_settings_value("risk_free_pct", ss.get("risk_free_pct")),
        "portfolio_preset": ss.get("portfolio_preset"),
    }


def seed_last_persisted_global_from_state(st: Any, state: dict[str, Any] | None) -> None:
    if not isinstance(state, dict):
        return
    ss = st.session_state
    payload = {
        "experience": state.get(EXPERIENCE_KEY),
        "_suite_persisted_experience": state.get(PERSISTED_EXPERIENCE_KEY),
        "sidebar_portfolio_value": _normalize_global_settings_value(
            "sidebar_portfolio_value", state.get("sidebar_portfolio_value")
        ),
        "analysis_start_date": state.get("analysis_start_date"),
        "analysis_end_date": state.get("analysis_end_date"),
        "risk_free_pct": _normalize_global_settings_value("risk_free_pct", state.get("risk_free_pct")),
        "portfolio_preset": state.get("portfolio_preset"),
    }
    ss[_LAST_PERSISTED_GLOBAL_KEY] = payload


def ensure_sidebar_portfolio_value_default(st: Any) -> None:
    ss = st.session_state
    if "sidebar_portfolio_value" not in ss:
        ss["sidebar_portfolio_value"] = PERSIST_FIELD_DEFAULTS["sidebar_portfolio_value"]


def ensure_risk_free_pct_default(st: Any) -> None:
    ss = st.session_state
    if "risk_free_pct" not in ss:
        ss["risk_free_pct"] = PERSIST_FIELD_DEFAULTS["risk_free_pct"]


def notify_global_settings_change(
    st: Any,
    *,
    source: str = "unknown",
    trigger_save: bool = True,
    overwrite_source: str | None = None,
) -> bool:
    """
    Device A save path for Test B globals — immediate ``global_setting_change`` autosave.
    """
    ss = st.session_state
    current = global_settings_payload_from_session(ss)
    prev_raw = ss.get(_LAST_PERSISTED_GLOBAL_KEY)
    prev = dict(prev_raw) if isinstance(prev_raw, dict) else {}
    changed = current != prev
    switch_evt: dict[str, Any] = {
        "at": _utc_now_iso(),
        "source": source,
        "prev_global": prev,
        "new_global": current,
        "global_change_detected": changed,
        "global_setting_overwrite_source": overwrite_source or source,
    }
    if not changed:
        switch_evt["autosave_triggered"] = False
        switch_evt["autosave_skip_reason"] = "prev_equals_global"
        _append_diag_log(st, _GLOBAL_SETTINGS_LOG_KEY, switch_evt)
        ss["_suite_inv_debug_last_global_change"] = switch_evt
        return False

    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    ss[dirty_key] = True
    ss[_GLOBAL_PAGE_DIRTY_KEY] = True
    switch_evt["local_dirty_set"] = True
    _append_diag_log(st, _GLOBAL_SETTINGS_LOG_KEY, switch_evt)
    ss["_suite_inv_debug_last_global_change"] = switch_evt

    if trigger_save:
        switch_evt["autosave_triggered"] = True
        autosave_investment_state(st, trigger="global_setting_change")
        last = ss.get("_suite_inv_debug_last_autosave_event")
        if isinstance(last, dict):
            switch_evt["autosave_outcome"] = last.get("outcome")
            switch_evt["save_global_portfolio_value"] = last.get("payload_global_portfolio_value")
            switch_evt["cloud_readback_portfolio_value"] = last.get("cloud_readback_portfolio_value")
            switch_evt["save_risk_free_pct"] = last.get("payload_risk_free_pct")
            switch_evt["cloud_readback_risk_free_pct"] = last.get("cloud_readback_risk_free_pct")
        ss["_suite_inv_debug_last_global_change"] = switch_evt
    else:
        switch_evt["autosave_triggered"] = False
    return True


def sync_global_settings_after_widgets(st: Any) -> None:
    """After sidebar global widgets render, autosave when live values drift from last persisted."""
    notify_global_settings_change(st, source="sidebar_widgets")


def portfolio_fingerprint_from_session(ss: Any) -> str:
    """Holdings fingerprint from live session (Test D save/readback)."""
    try:
        from components.beginner_navigation import _holdings_fingerprint

        df = ss.get("holdings_df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            return str(_holdings_fingerprint(df))
    except Exception:
        pass
    return str(ss.get("holdings_fingerprint") or "").strip()


def seed_last_persisted_portfolio_from_state(st: Any, state: dict[str, Any] | None) -> None:
    if not isinstance(state, dict):
        return
    fp = str(state.get("holdings_fingerprint") or "").strip()
    if not fp:
        records = state.get("holdings_df")
        if isinstance(records, list) and records:
            try:
                from components.beginner_navigation import _holdings_fingerprint

                fp = str(_holdings_fingerprint(pd.DataFrame(records)))
            except Exception:
                fp = ""
    if fp:
        st.session_state[_LAST_PERSISTED_PORTFOLIO_FP_KEY] = fp


def notify_portfolio_change(
    st: Any,
    *,
    source: str = "unknown",
    trigger_save: bool = True,
) -> bool:
    """
    Device A save path for Test D holdings — immediate ``portfolio_change`` autosave.
    """
    ss = st.session_state
    current_fp = portfolio_fingerprint_from_session(ss)
    prev = str(ss.get(_LAST_PERSISTED_PORTFOLIO_FP_KEY) or "").strip()
    changed = bool(current_fp) and current_fp != prev
    switch_evt: dict[str, Any] = {
        "at": _utc_now_iso(),
        "source": source,
        "prev_holdings_fingerprint": prev or None,
        "new_holdings_fingerprint": current_fp or None,
        "portfolio_change_detected": changed,
    }
    if not changed:
        switch_evt["autosave_triggered"] = False
        switch_evt["autosave_skip_reason"] = "prev_equals_portfolio_fp"
        _append_diag_log(st, _PORTFOLIO_CHANGE_LOG_KEY, switch_evt)
        ss["_suite_inv_debug_last_portfolio_change"] = switch_evt
        return False

    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    ss[dirty_key] = True
    ss[_PORTFOLIO_PAGE_DIRTY_KEY] = True
    switch_evt["local_dirty_set"] = True
    _append_diag_log(st, _PORTFOLIO_CHANGE_LOG_KEY, switch_evt)
    ss["_suite_inv_debug_last_portfolio_change"] = switch_evt

    if trigger_save:
        switch_evt["autosave_triggered"] = True
        autosave_investment_state(st, trigger="portfolio_change")
        last = ss.get("_suite_inv_debug_last_autosave_event")
        if isinstance(last, dict):
            switch_evt["autosave_outcome"] = last.get("outcome")
            switch_evt["saved_holdings_fingerprint"] = last.get("payload_holdings_fingerprint")
            switch_evt["cloud_readback_holdings_fingerprint"] = last.get(
                "cloud_readback_holdings_fingerprint"
            )
        ss["_suite_inv_debug_last_portfolio_change"] = switch_evt
    else:
        switch_evt["autosave_triggered"] = False
    return True


def notify_pending_insight_change(
    st: Any,
    *,
    source: str = "insight_hydrate",
    trigger_save: bool = True,
) -> None:
    """Persist pending AMI insight into ``full_session`` for cross-device phone refresh."""
    ss = st.session_state
    pending = ss.get("_ami_pending_insight")
    if not isinstance(pending, dict) or not (pending.get("conclusion") or pending.get("question")):
        return
    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    ss[dirty_key] = True
    if trigger_save:
        autosave_investment_state(st, trigger=source)


def _coerce_persisted_analysis_date(val: Any) -> dt.date | None:
    """Normalize restored sidebar lookback dates to ``datetime.date``."""
    if val is None:
        return None
    if isinstance(val, dt.datetime):
        return val.date()
    if isinstance(val, dt.date):
        return val
    to_pydatetime = getattr(val, "to_pydatetime", None)
    if callable(to_pydatetime):
        try:
            return to_pydatetime().date()
        except (TypeError, ValueError, AttributeError):
            return None
    if isinstance(val, str):
        try:
            return dt.date.fromisoformat(val.strip()[:10])
        except ValueError:
            return None
    return None


def ensure_analysis_date_defaults(st: Any) -> None:
    end_default = dt.date.today()
    start_default = end_default - dt.timedelta(days=365 * 5)
    for key, default in (
        ("analysis_start_date", start_default),
        ("analysis_end_date", end_default),
    ):
        if key not in st.session_state:
            st.session_state[key] = default
            continue
        coerced = _coerce_persisted_analysis_date(st.session_state[key])
        if coerced is not None:
            st.session_state[key] = coerced
        elif st.session_state[key] is not None:
            st.session_state[key] = default


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


def _holdings_records_from_blob(val: Any) -> list[dict[str, Any]]:
    if isinstance(val, list) and val:
        return [row for row in val if isinstance(row, dict)]
    return []


def _apply_holdings_df_records(st: Any, records: list[dict[str, Any]], *, source: str) -> bool:
    if not records:
        return False
    try:
        df = pd.DataFrame(records)
    except Exception:
        st.session_state["_suite_inv_holdings_restore_issue"] = "invalid_saved_holdings"
        return False
    if df.empty or "Ticker" not in df.columns:
        st.session_state["_suite_inv_holdings_restore_issue"] = "empty_saved_holdings"
        return False
    st.session_state.holdings_df = df
    st.session_state["_suite_inv_holdings_from_saved_blob"] = True
    st.session_state["holdings_restore_source"] = source
    st.session_state.pop("_suite_inv_holdings_restore_issue", None)
    st.session_state["default_holdings_applied"] = False
    st.session_state.pop("default_holdings_apply_reason", None)
    return True


def _cloud_holdings_refetch(blob_fingerprint: str = "") -> tuple[list[dict[str, Any]], str]:
    """Load holdings_df records from cloud full_session when restore blob omitted them."""
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, _ = load_cloud_full_session(APP_ID)
        if not isinstance(cloud_state, dict):
            return [], ""
        cloud_fp = str(cloud_state.get("holdings_fingerprint") or "").strip()
        if blob_fingerprint and cloud_fp and cloud_fp != blob_fingerprint:
            return [], cloud_fp
        records = _holdings_records_from_blob(cloud_state.get("holdings_df"))
        return records, cloud_fp
    except Exception:
        return [], ""


def _finalize_holdings_restore(st: Any, state: dict[str, Any]) -> None:
    """Apply DEFAULT_HOLDINGS only when no saved portfolio exists in the restore blob."""
    import portfolio_core as core

    ss = st.session_state
    if isinstance(ss.get("holdings_df"), pd.DataFrame):
        return

    blob_fp = str(state.get("holdings_fingerprint") or "").strip()
    portfolio_built = bool(state.get("portfolio_built"))
    saved_portfolio = bool(blob_fp or portfolio_built)

    if saved_portfolio:
        records, cloud_fp = _cloud_holdings_refetch(blob_fp)
        if records and _apply_holdings_df_records(st, records, source="cloud_refetch"):
            ss["cloud_fetch_holdings_fingerprint"] = cloud_fp or blob_fp
            ss["default_holdings_applied"] = False
            ss.pop("default_holdings_apply_reason", None)
            return
        ss["holdings_df"] = pd.DataFrame()
        ss["_suite_inv_holdings_restore_issue"] = "holdings_missing_after_portfolio_save"
        ss["default_holdings_applied"] = False
        ss["default_holdings_apply_reason"] = "missing_holdings_with_fingerprint"
        return

    ss["holdings_df"] = pd.DataFrame(core.DEFAULT_HOLDINGS)
    ss["default_holdings_applied"] = True
    ss["default_holdings_apply_reason"] = "no_saved_portfolio"
    ss.pop("_suite_inv_holdings_from_saved_blob", None)
    ss.pop("_suite_inv_holdings_restore_issue", None)
    ss.pop("holdings_restore_source", None)


def _cloud_has_saved_portfolio() -> tuple[dict[str, Any] | None, str]:
    """Return cloud full_session when it records a built/saved portfolio."""
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        if not isinstance(cloud_state, dict) or not cloud_state:
            return None, ""
        cloud_hfp = str(cloud_state.get("holdings_fingerprint") or "").strip()
        if cloud_hfp or cloud_state.get("portfolio_built"):
            return cloud_state, cloud_ts or ""
    except Exception:
        pass
    return None, ""


def _session_holdings_aligned_with_cloud(st: Any, cloud_state: dict[str, Any]) -> bool:
    cloud_hfp = str(cloud_state.get("holdings_fingerprint") or "").strip()
    if not cloud_hfp and not cloud_state.get("portfolio_built"):
        return True
    live_hfp = portfolio_fingerprint_from_session(st.session_state)
    df = st.session_state.get("holdings_df")
    has_rows = isinstance(df, pd.DataFrame) and not df.empty
    if not has_rows:
        return False
    if cloud_hfp and live_hfp != cloud_hfp:
        return False
    return True


def align_session_holdings_with_cloud(
    st: Any,
    cloud_state: dict[str, Any] | None,
    *,
    source: str,
) -> bool:
    """
    Re-apply cloud holdings when restore picked incomplete disk state or left rows missing.

    Safe at bootstrap: cloud is authoritative when ``holdings_fingerprint`` / ``portfolio_built``
    exist in cloud but live session has defaults, empty rows, or fingerprint drift.
    """
    if not isinstance(cloud_state, dict) or not cloud_state:
        return False
    if _session_holdings_aligned_with_cloud(st, cloud_state):
        return False
    ss = st.session_state
    pick = str(ss.get("_suite_persist_last_restore_source") or "unknown").strip()
    ss["startup_holdings_fixup_source"] = source
    ss["startup_holdings_fixup_pick"] = pick
    apply_investment_disk_state(st, cloud_state)
    ss["holdings_restore_source"] = source
    ss["workflow_restore_source"] = pick
    _record_holdings_restore_trace(st, cloud_state)
    return True


def finalize_startup_holdings_restore(st: Any) -> bool:
    """
    One-shot post-``init_holdings`` guard for Dell startup restore.

    ``reconcile_investment_cloud_drift_if_needed`` runs before sidebar/init; when restore
    leaves no ``holdings_df``, early reconcile could not detect fingerprint drift. This
    re-checks cloud after init and overrides defaults before end-of-run autosave.
    """
    ss = st.session_state
    if ss.get("_suite_inv_startup_holdings_finalized"):
        return False
    ss["_suite_inv_startup_holdings_finalized"] = True
    cloud_state, _cloud_ts = _cloud_has_saved_portfolio()
    if not cloud_state:
        ss["startup_holdings_finalize_source"] = "no_cloud_saved_portfolio"
        return False
    if _session_holdings_aligned_with_cloud(st, cloud_state):
        ss["startup_holdings_finalize_source"] = "session_already_aligned"
        return False
    aligned = align_session_holdings_with_cloud(
        st,
        cloud_state,
        source="startup_post_init_cloud",
    )
    ss["startup_holdings_finalize_source"] = (
        "startup_post_init_cloud" if aligned else "startup_post_init_cloud_failed"
    )
    try:
        from investment_persistence_trace import record_holdings_restore_trace, record_startup_restore_trace

        record_holdings_restore_trace(st)
        record_startup_restore_trace(st)
    except Exception:
        pass
    return aligned


def _record_holdings_restore_trace(st: Any, state: dict[str, Any]) -> None:
    ss = st.session_state
    records = _holdings_records_from_blob(state.get("holdings_df"))
    blob_fp = str(state.get("holdings_fingerprint") or "").strip()
    cloud_fp = ""
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, _ = load_cloud_full_session(APP_ID)
        if isinstance(cloud_state, dict):
            cloud_fp = str(cloud_state.get("holdings_fingerprint") or "").strip()
            ss["cloud_fetch_holdings_fingerprint"] = cloud_fp
            ss["cloud_blob_has_holdings_df"] = bool(_holdings_records_from_blob(cloud_state.get("holdings_df")))
            ss["cloud_blob_holdings_row_count"] = len(
                _holdings_records_from_blob(cloud_state.get("holdings_df"))
            )
    except Exception:
        pass
    ss["cloud_blob_has_holdings_df"] = bool(records) if "cloud_blob_has_holdings_df" not in ss else ss.get(
        "cloud_blob_has_holdings_df"
    )
    if "cloud_blob_holdings_row_count" not in ss:
        ss["cloud_blob_holdings_row_count"] = len(records)
    ss["restored_holdings_fingerprint"] = blob_fp or None
    ss["portfolio_built_restored"] = bool(state.get("portfolio_built"))
    ss["workflow_restore_source"] = ss.get("_suite_persist_last_restore_source")
    ss["final_holdings_fingerprint"] = portfolio_fingerprint_from_session(ss) or None
    try:
        from investment_persistence_trace import record_holdings_restore_trace

        record_holdings_restore_trace(st)
    except Exception:
        pass


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

    cloud_hfp = str(cloud.get("holdings_fingerprint") or "").strip()
    if cloud_hfp:
        live_hfp = portfolio_fingerprint_from_session(st.session_state)
        df = st.session_state.get("holdings_df")
        has_rows = isinstance(df, pd.DataFrame) and not df.empty
        if not live_hfp or not has_rows or live_hfp != cloud_hfp:
            reasons.append("holdings_fingerprint")

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

    Called once per session at bootstrap only — not every rerun (would overwrite local widget edits).
    """
    ss = st.session_state
    if ss.get("_suite_inv_cloud_reconcile_done"):
        return False
    ss["_suite_inv_cloud_reconcile_done"] = True
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
    if ss.get("default_holdings_applied"):
        return True, "default_holdings_applied_after_restore"
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, _ = load_cloud_full_session(APP_ID)
        if isinstance(cloud_state, dict) and cloud_state:
            cloud_hfp = str(cloud_state.get("holdings_fingerprint") or "").strip()
            live_hfp = portfolio_fingerprint_from_session(ss)
            if cloud_hfp and live_hfp and cloud_hfp != live_hfp:
                return True, "holdings_fingerprint mismatch vs cloud"
    except Exception:
        pass
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
    df = ss.get("holdings_df")
    if isinstance(df, pd.DataFrame):
        if not df.empty:
            state["holdings_df"] = _df_to_records(df)
        try:
            from components.beginner_navigation import _holdings_fingerprint

            if not df.empty:
                state["holdings_fingerprint"] = _holdings_fingerprint(df)
            elif ss.get("portfolio_built"):
                fp = portfolio_fingerprint_from_session(ss)
                if fp:
                    state["holdings_fingerprint"] = fp
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
    for key in _AMI_PERSIST_SESSION_KEYS:
        val = ss.get(key)
        if val is not None and val != "":
            state[key] = copy.deepcopy(val)
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

    ami_skip_tab = str(st.session_state.get("_skip_page_restore_for") or "").strip()
    ami_expected_fp = str(st.session_state.get("_suite_holdings_fp") or "").strip()
    blob_holdings_fp = str(state.get("holdings_fingerprint") or "").strip()

    for key, val in state.items():
        if key in (_LEGACY_TAB_KEY, _WF_BLOB, "holdings_fingerprint", EXPERIENCE_KEY, PERSISTED_EXPERIENCE_KEY):
            continue
        if key == INVESTMENT_ACTIVE_TAB_KEY and ami_skip_tab:
            st.session_state["_suite_page_overwrite_source"] = "ami_return_deferred_tab"
            continue
        if key == "holdings_df":
            if ami_expected_fp and blob_holdings_fp and blob_holdings_fp != ami_expected_fp:
                st.session_state["_suite_page_overwrite_source"] = "ami_return_deferred_holdings"
                continue
            records = _holdings_records_from_blob(val)
            if records:
                _apply_holdings_df_records(st, records, source="restore_blob")
            continue
        if key in ("analysis_start_date", "analysis_end_date"):
            coerced = _coerce_persisted_analysis_date(val)
            if coerced is not None:
                st.session_state[key] = coerced
            continue
        st.session_state[key] = copy.deepcopy(val)

    exp = state.get(EXPERIENCE_KEY) or state.get(PERSISTED_EXPERIENCE_KEY)
    user_choice = st.session_state.get("_suite_inv_experience_user_choice")
    if _local_experience_change_in_flight(st):
        pending = st.session_state.get(_PENDING_EXPERIENCE_KEY)
        preserve_exp = pending if pending in EXPERIENCE_OPTIONS else current_experience_mode(st)
        st.session_state[EXPERIENCE_KEY] = preserve_exp
        st.session_state[PERSISTED_EXPERIENCE_KEY] = preserve_exp
    elif user_choice in EXPERIENCE_OPTIONS:
        st.session_state[EXPERIENCE_KEY] = user_choice
        st.session_state[PERSISTED_EXPERIENCE_KEY] = user_choice
    elif exp in EXPERIENCE_OPTIONS:
        st.session_state[EXPERIENCE_KEY] = exp
        st.session_state[PERSISTED_EXPERIENCE_KEY] = exp

    _finalize_holdings_restore(st, state)
    _record_holdings_restore_trace(st, state)

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
    restored_tab = state.get(INVESTMENT_ACTIVE_TAB_KEY) or state.get(_LEGACY_TAB_KEY)
    if restored_tab is not None and str(restored_tab).strip():
        st.session_state[_LAST_PERSISTED_TAB_KEY] = str(restored_tab).strip()
    seed_last_persisted_global_from_state(st, state)
    seed_last_persisted_portfolio_from_state(st, state)


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


def _overlay_cloud_experience_if_authoritative(
    st: Any,
    cloud_state: dict[str, Any] | None,
    cloud_ts: str | None,
    disk_ts: str | None,
) -> None:
    """When disk wins restore but cloud has a newer/equal experience, apply cloud mode."""
    if _local_experience_change_in_flight(st):
        return
    dirty_key = f"_suite_persist_local_dirty::{APP_ID}"
    if st.session_state.get(dirty_key):
        return
    if not isinstance(cloud_state, dict) or not cloud_state:
        return
    cloud = _normalize_restored_state(cloud_state)
    cloud_exp = cloud.get(EXPERIENCE_KEY)
    if cloud_exp not in EXPERIENCE_OPTIONS:
        return
    if current_experience_mode(st) == cloud_exp:
        return
    pick = str(st.session_state.get("_suite_persist_debug_pick_source") or "")
    try:
        from suite_cloud_state import parse_persist_timestamp

        cloud_epoch = parse_persist_timestamp(cloud_ts)
        disk_epoch = parse_persist_timestamp(disk_ts)
    except ImportError:
        cloud_epoch = 0.0
        disk_epoch = 0.0
    if pick == "disk" and cloud_epoch >= disk_epoch:
        st.session_state[EXPERIENCE_KEY] = cloud_exp
        st.session_state[PERSISTED_EXPERIENCE_KEY] = cloud_exp
        st.session_state["_suite_inv_debug_experience_overlay"] = cloud_exp


def restore_investment_disk_state_once(st: Any) -> bool:
    st.session_state["_suite_inv_debug_cloud_experience"] = None
    st.session_state["_suite_inv_debug_disk_experience"] = None
    st.session_state["_suite_inv_debug_disk_file_exists"] = state_file_path(APP_ID).is_file()

    cloud_state: dict[str, Any] | None = None
    cloud_ts: str | None = None

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
    if isinstance(cloud_state, dict) and cloud_state:
        align_session_holdings_with_cloud(
            st,
            cloud_state,
            source="post_restore_cloud_align",
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
    _overlay_cloud_experience_if_authoritative(
        st,
        cloud_state if isinstance(cloud_state, dict) else None,
        cloud_ts,
        st.session_state.get("_suite_persist_debug_disk_ts"),
    )
    st.session_state["_suite_inv_debug_mode_after_restore"] = current_experience_mode(st)
    _record_session_sync_debug(st)
    apply_suite_investment_resume(st)
    try:
        from investment_persistence_trace import record_restore_trace

        record_restore_trace(st)
    except Exception:
        pass
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

    state: dict[str, Any] | None = None
    try:
        state = build_investment_disk_state(st)
        event["blob_experience"] = state.get(EXPERIENCE_KEY)
        event["blob_persisted"] = state.get(PERSISTED_EXPERIENCE_KEY)
        event["blob_tab"] = state.get(INVESTMENT_ACTIVE_TAB_KEY)
        event["payload_global_portfolio_value"] = state.get("sidebar_portfolio_value")
        event["payload_risk_free_pct"] = state.get("risk_free_pct")
        holdings_records = state.get("holdings_df") if isinstance(state.get("holdings_df"), list) else []
        event["payload_holdings_fingerprint"] = state.get("holdings_fingerprint")
        event["blob_holdings_fingerprint"] = state.get("holdings_fingerprint")
        event["payload_holdings_row_count"] = len(holdings_records)
        event["cloud_blob_has_holdings_df"] = bool(holdings_records)

        blob = json.dumps(state, sort_keys=True, default=str)
        fp = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
        fp_before = ss.get(fp_key)
        event["fp_before"] = fp_before
        event["fp_after"] = fp

        restored_fp = ss.get(restored_fp_key)
        if restored_fp and fp != restored_fp:
            ss[dirty_key] = True

        if ss.get(fp_key) == fp and trigger not in (
            "mode_change",
            "tab_change",
            "global_setting_change",
            "portfolio_change",
            "insight_hydrate",
            "insight_store",
        ):
            event["outcome"] = "skipped_fp_unchanged"
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
                event["cloud_readback_tab"] = cloud_state.get(INVESTMENT_ACTIVE_TAB_KEY)
                event["cloud_readback_portfolio_value"] = cloud_state.get("sidebar_portfolio_value")
                event["cloud_readback_risk_free_pct"] = cloud_state.get("risk_free_pct")
                event["cloud_readback_holdings_fingerprint"] = cloud_state.get("holdings_fingerprint")
                readback_records = _holdings_records_from_blob(cloud_state.get("holdings_df"))
                event["cloud_readback_holdings_row_count"] = len(readback_records)
                event["cloud_readback_has_holdings_df"] = bool(readback_records)
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
            readback_tab = event.get("cloud_readback_tab")
            attempt_tab = state.get(INVESTMENT_ACTIVE_TAB_KEY)
            mode_saved_to_cloud = (
                trigger == "mode_change"
                and saved_cloud
                and readback_exp == attempt_mode
            )
            tab_saved_to_cloud = (
                trigger == "tab_change"
                and saved_cloud
                and readback_tab == attempt_tab
            )
            global_saved_to_cloud = trigger == "global_setting_change" and saved_cloud
            readback_hfp = event.get("cloud_readback_holdings_fingerprint")
            attempt_hfp = state.get("holdings_fingerprint")
            portfolio_saved_to_cloud = (
                trigger == "portfolio_change"
                and saved_cloud
                and readback_hfp
                and attempt_hfp
                and readback_hfp == attempt_hfp
            )
            if trigger == "mode_change" and not mode_saved_to_cloud:
                ss[dirty_key] = True
            elif trigger == "tab_change" and not tab_saved_to_cloud:
                ss[dirty_key] = True
            elif trigger == "global_setting_change" and not global_saved_to_cloud:
                ss[dirty_key] = True
            elif trigger == "portfolio_change" and not portfolio_saved_to_cloud:
                ss[dirty_key] = True
            else:
                ss[dirty_key] = False
            if tab_saved_to_cloud and attempt_tab:
                ss[_LAST_PERSISTED_TAB_KEY] = str(attempt_tab)
                ss.pop(_TAB_PAGE_DIRTY_KEY, None)
            elif (saved_disk or saved_cloud) and attempt_tab:
                ss[_LAST_PERSISTED_TAB_KEY] = str(attempt_tab)
            if global_saved_to_cloud or (saved_disk or saved_cloud):
                seed_last_persisted_global_from_state(st, state)
                ss.pop(_GLOBAL_PAGE_DIRTY_KEY, None)
            if portfolio_saved_to_cloud or (
                (saved_disk or saved_cloud) and attempt_hfp
            ):
                seed_last_persisted_portfolio_from_state(st, state)
                if portfolio_saved_to_cloud:
                    ss.pop(_PORTFOLIO_PAGE_DIRTY_KEY, None)
            if trigger == "mode_change" and (saved_disk or saved_cloud):
                ss.pop(_PENDING_EXPERIENCE_KEY, None)
                if readback_exp in EXPERIENCE_OPTIONS:
                    ss["_suite_inv_experience_user_choice"] = readback_exp
            elif mode_saved_to_cloud:
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
    try:
        from investment_persistence_trace import record_save_trace

        record_save_trace(st, event=event, state=state)
    except Exception:
        pass


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
        f"cloud resync ran: {ss.get('_suite_inv_cloud_resync_ran')!r}",
        f"user experience choice: {ss.get('_suite_inv_experience_user_choice')!r}",
        f"end-of-sidebar trace: {ss.get('_suite_inv_debug_experience_end_of_sidebar')!r}",
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
        from investment_workflow import workflow_persist_audit, render_workflow_state_trace

        st.markdown("**Workflow full_session audit (live vs saved)**")
        audit = workflow_persist_audit(st)
        st.code("\n".join(f"{k}: {v}" for k, v in audit.items()), language=None)
        render_workflow_state_trace(st, beginner=current_experience_mode(st) == EXPERIENCE_OPTIONS[0])
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
