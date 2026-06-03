"""Disk and cloud persistence for Investment Portfolio Analyzer."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

import pandas as pd

from suite_user_persistence import (
    autosave_if_changed,
    load_user_state,
    reset_user_state,
    restore_once,
)

APP_ID = "investment"

# Bump when changing persistence diagnostics UI (visible in-app to confirm deploy).
PERSISTENCE_DEBUG_BUILD_ID = "2026-06-03-diagnostic-v1"

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
    "overview_subtab": None,
    "overview_show_extended_metrics": False,
    "mc_assumption_mode": "Historical returns",
    "plan_total_cash": None,
    "plan_emergency": 20_000,
    "plan_near_term": 0,
    "plan_debt": 0,
    "plan_expenses": 0,
    "plan_monthly": 0,
    "investment_plan_generated": False,
    "holdings_df": "default holdings",
    "health_summary": None,
}


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
    persisted = ss.get(PERSISTED_EXPERIENCE_KEY)
    widget = ss.get(EXPERIENCE_KEY)
    if persisted in EXPERIENCE_OPTIONS and widget not in EXPERIENCE_OPTIONS:
        ss[EXPERIENCE_KEY] = persisted
    elif widget in EXPERIENCE_OPTIONS:
        ss[PERSISTED_EXPERIENCE_KEY] = widget
    default = persisted if persisted in EXPERIENCE_OPTIONS else EXPERIENCE_OPTIONS[0]
    validate_state_option(st, EXPERIENCE_KEY, EXPERIENCE_OPTIONS, default)
    ss[PERSISTED_EXPERIENCE_KEY] = ss[EXPERIENCE_KEY]


def sync_experience_after_widget(st: Any) -> None:
    """Keep persisted copy aligned with the sidebar radio; autosave immediately on change."""
    ss = st.session_state
    mode = ss.get(EXPERIENCE_KEY)
    if mode not in EXPERIENCE_OPTIONS:
        return
    prev = ss.get(PERSISTED_EXPERIENCE_KEY)
    ss[PERSISTED_EXPERIENCE_KEY] = mode
    ss["_suite_inv_debug_mode_final"] = mode
    if prev != mode:
        ss["_suite_inv_debug_mode_saved"] = mode
        autosave_investment_state(st)


def ensure_analysis_date_defaults(st: Any) -> None:
    end_default = dt.date.today()
    start_default = end_default - dt.timedelta(days=365 * 5)
    if "analysis_start_date" not in st.session_state:
        st.session_state["analysis_start_date"] = start_default
    if "analysis_end_date" not in st.session_state:
        st.session_state["analysis_end_date"] = end_default


def ensure_investment_active_tab(st: Any, tab_labels: list[str]) -> None:
    if not tab_labels:
        return
    if INVESTMENT_ACTIVE_TAB_KEY not in st.session_state and _LEGACY_TAB_KEY in st.session_state:
        st.session_state[INVESTMENT_ACTIVE_TAB_KEY] = st.session_state[_LEGACY_TAB_KEY]
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


def build_investment_disk_state(st: Any) -> dict[str, Any]:
    ss = st.session_state
    state: dict[str, Any] = {}
    mode = current_experience_mode(st)
    state[EXPERIENCE_KEY] = mode
    state[PERSISTED_EXPERIENCE_KEY] = mode
    for key in _PERSIST_SCALAR_KEYS:
        if key in (EXPERIENCE_KEY, PERSISTED_EXPERIENCE_KEY):
            continue
        if key in ss:
            val = ss[key]
            if isinstance(val, dt.date):
                state[key] = val.isoformat()
            else:
                state[key] = copy.deepcopy(val)
    if INVESTMENT_ACTIVE_TAB_KEY in state:
        state[_LEGACY_TAB_KEY] = state[INVESTMENT_ACTIVE_TAB_KEY]
    if "holdings_df" in ss and isinstance(ss["holdings_df"], pd.DataFrame):
        state["holdings_df"] = _df_to_records(ss["holdings_df"])
    summary = ss.get("health_summary")
    if isinstance(summary, dict):
        state["health_summary"] = copy.deepcopy(summary)
    _snapshot_mode_debug(st, saved=mode)
    return state


def apply_investment_disk_state(st: Any, state: dict[str, Any]) -> None:
    import portfolio_core as core

    state = _normalize_restored_state(state)
    _record_restore_debug(st, state)
    st.session_state["_suite_inv_debug_picked_experience"] = state.get(EXPERIENCE_KEY)

    for key, val in state.items():
        if key == _LEGACY_TAB_KEY:
            continue
        if key == "holdings_df":
            if val:
                st.session_state.holdings_df = pd.DataFrame(val)
            continue
        if key in ("analysis_start_date", "analysis_end_date") and isinstance(val, str):
            try:
                st.session_state[key] = dt.date.fromisoformat(val)
            except ValueError:
                continue
            continue
        st.session_state[key] = copy.deepcopy(val)

    exp = state.get(EXPERIENCE_KEY)
    if exp in EXPERIENCE_OPTIONS:
        st.session_state[EXPERIENCE_KEY] = exp
        st.session_state[PERSISTED_EXPERIENCE_KEY] = exp

    if "holdings_df" not in st.session_state:
        st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)

    st.session_state["_suite_inv_debug_mode_after_restore"] = current_experience_mode(st)


def restore_investment_disk_state_once(st: Any) -> bool:
    st.session_state["_suite_inv_debug_cloud_experience"] = None
    st.session_state["_suite_inv_debug_disk_experience"] = None
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, _cloud_ts = load_cloud_full_session(APP_ID)
        if cloud_state:
            st.session_state["_suite_inv_debug_cloud_experience"] = cloud_state.get(EXPERIENCE_KEY)
    except Exception as exc:
        st.session_state["_suite_persist_cloud_peek_error"] = str(exc)

    disk_state, _disk_warn = load_user_state(APP_ID)
    if disk_state:
        st.session_state["_suite_inv_debug_disk_experience"] = disk_state.get(EXPERIENCE_KEY)

    restored = restore_once(
        st,
        APP_ID,
        apply_state=lambda st_obj, s: apply_investment_disk_state(st_obj, s),
    )
    st.session_state["_suite_inv_debug_restore_ran"] = restored
    st.session_state["_suite_inv_debug_restore_source"] = st.session_state.get(
        "_suite_persist_last_restore_source"
    )
    if not restored:
        ensure_experience_mode(st)
        st.session_state["_suite_inv_debug_mode_after_restore"] = current_experience_mode(st)
    return restored


def autosave_investment_state(st: Any) -> None:
    autosave_if_changed(st, APP_ID, build_state=build_investment_disk_state)


def finalize_persistence_debug(st: Any) -> None:
    _snapshot_mode_debug(st)


def experience_mode_trace_lines(st: Any) -> list[str]:
    ss = st.session_state
    return [
        f"build: {PERSISTENCE_DEBUG_BUILD_ID}",
        f"cloud blob: {ss.get('_suite_inv_debug_cloud_experience')!r}",
        f"disk blob: {ss.get('_suite_inv_debug_disk_experience')!r}",
        f"picked blob: {ss.get('_suite_inv_debug_picked_experience')!r}",
        f"after restore: {ss.get('_suite_inv_debug_mode_after_restore')!r}",
        f"saved to cloud: {ss.get('_suite_inv_debug_mode_saved')!r}",
        f"after init: {ss.get('_suite_inv_debug_mode_final')!r}",
        f"restore ran: {ss.get('_suite_inv_debug_restore_ran')!r}",
    ]


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
    """Shared debug body (main page + sidebar)."""
    ss = st.session_state
    save_at = ss.get("_suite_persist_last_save_at")
    restore_at = ss.get("_suite_persist_last_restore_at")
    source = ss.get("_suite_persist_last_restore_source") or "—"
    st.caption(f"Diagnostic build **{PERSISTENCE_DEBUG_BUILD_ID}**")
    st.caption(f"Last cloud save: **{save_at or '—'}** · restore: **{restore_at or '—'}** ({source})")
    st.markdown("**Experience mode trace**")
    st.code("\n".join(experience_mode_trace_lines(st)), language=None)
    st.markdown("**Account scope**")
    st.code("\n".join(_persistence_account_lines(st)), language=None)
    import_err = ss.get("_suite_persist_import_error")
    restore_err = ss.get("_suite_persist_restore_error")
    cloud_err = ss.get("_suite_persist_cloud_peek_error")
    if import_err:
        st.warning(f"Persistence import error: {import_err}")
    if restore_err:
        st.warning(f"Persistence restore error: {restore_err}")
    if cloud_err:
        st.caption(f"Cloud peek error: {cloud_err}")


def render_persistence_debug_sidebar(st: Any) -> None:
    """Top of sidebar — expanded so mobile users see it without hunting."""
    with st.sidebar.expander("Persistence diagnostics", expanded=True):
        render_persistence_debug_content(st)


def render_persistence_debug_main(st: Any) -> None:
    """Main page banner — filled from a top-of-page empty slot after init completes."""
    with st.expander("Persistence diagnostics (experience mode)", expanded=True):
        render_persistence_debug_content(st)


def render_persistence_debug(st: Any, *, final: bool = False) -> None:
    """Legacy entry point; sidebar-only partial view before init completes."""
    del final
    render_persistence_debug_sidebar(st)


def default_reset_investment_session(st: Any) -> None:
    import portfolio_core as core

    reset_user_state(APP_ID)
    for key in list(st.session_state.keys()):
        if str(key).startswith("_suite_"):
            st.session_state.pop(key, None)
    st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)
    st.session_state[EXPERIENCE_KEY] = EXPERIENCE_OPTIONS[0]
    st.session_state[PERSISTED_EXPERIENCE_KEY] = EXPERIENCE_OPTIONS[0]
    st.session_state.sidebar_portfolio_value = 100_000
    for k in (
        "health_result",
        "health_summary",
        "health_result_fingerprint",
        "health_settings_fingerprint",
        "preset_applied",
        INVESTMENT_ACTIVE_TAB_KEY,
        _LEGACY_TAB_KEY,
    ):
        st.session_state.pop(k, None)
