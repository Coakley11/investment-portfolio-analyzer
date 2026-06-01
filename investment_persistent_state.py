"""Disk persistence for Investment Portfolio Analyzer."""

from __future__ import annotations

import copy
from typing import Any

import pandas as pd

from suite_user_persistence import (
    autosave_if_changed,
    reset_user_state,
    restore_once,
    save_user_state,
)

APP_ID = "investment"

_PERSIST_SCALAR_KEYS = (
    "experience",
    "sidebar_portfolio_value",
    "preset_applied",
    "health_rate_env",
    "health_inflation",
    "health_recession",
    "health_valuation",
    "health_regime",
    "health_objective",
    "health_bond_min",
    "health_active_tab",
    "beginner_objective",
    "invest_plan_horizon_years",
    "invest_plan_monthly_contrib",
    "invest_plan_target_value",
)


def _df_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    return df.to_dict(orient="records")


def build_investment_disk_state(st: Any) -> dict[str, Any]:
    ss = st.session_state
    state: dict[str, Any] = {}
    for key in _PERSIST_SCALAR_KEYS:
        if key in ss:
            state[key] = copy.deepcopy(ss[key])
    if "holdings_df" in ss and isinstance(ss["holdings_df"], pd.DataFrame):
        state["holdings_df"] = _df_to_records(ss["holdings_df"])
    summary = ss.get("health_summary")
    if isinstance(summary, dict):
        state["health_summary"] = copy.deepcopy(summary)
    return state


def apply_investment_disk_state(st: Any, state: dict[str, Any]) -> None:
    import portfolio_core as core

    for key, val in state.items():
        if key == "holdings_df":
            if val:
                st.session_state.holdings_df = pd.DataFrame(val)
            continue
        st.session_state[key] = copy.deepcopy(val)
    if "holdings_df" not in st.session_state:
        st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)


def restore_investment_disk_state_once(st: Any) -> bool:
    return restore_once(
        st,
        APP_ID,
        apply_state=lambda st_obj, s: apply_investment_disk_state(st_obj, s),
    )


def autosave_investment_state(st: Any) -> None:
    autosave_if_changed(st, APP_ID, build_state=build_investment_disk_state)


def default_reset_investment_session(st: Any) -> None:
    import portfolio_core as core

    reset_user_state(APP_ID)
    for key in list(st.session_state.keys()):
        if str(key).startswith("_suite_"):
            st.session_state.pop(key, None)
    st.session_state.holdings_df = pd.DataFrame(core.DEFAULT_HOLDINGS)
    st.session_state.experience = "Beginner Mode"
    st.session_state.sidebar_portfolio_value = 100_000
    for k in (
        "health_result",
        "health_summary",
        "health_result_fingerprint",
        "health_settings_fingerprint",
        "preset_applied",
    ):
        st.session_state.pop(k, None)
