"""Portfolio demo state loaders — investment app. Presentation only."""

from __future__ import annotations

import pandas as pd

import portfolio_core as core
import portfolio_polish as pp
from components.beginner_navigation import ADVANCED_TAB_LABELS
from components.ui_helpers import (
    PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY,
    apply_pending_sidebar_portfolio_value,
)
from investment_persistent_state import (
    EXPERIENCE_KEY,
    EXPERIENCE_OPTIONS,
    PERSISTED_EXPERIENCE_KEY,
)
from investment_workflow import _PENDING_INVESTMENT_TAB_KEY

PENDING_DEMO_EXPERIENCE_KEY = "_pp_demo_pending_experience"
PENDING_DEMO_PRESET_KEY = "_pp_demo_pending_portfolio_preset"
DEMO_PORTFOLIO_VALUE = 100_000
DEMO_PRESET = "Balanced"
DEMO_OVERVIEW_TAB = ADVANCED_TAB_LABELS[1]


def _apply_demo_holdings_and_analytics(ss) -> None:
    """Keys with no sidebar widget conflict on this run."""
    ss.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[DEMO_PRESET])
    ss.preset_applied = DEMO_PRESET
    ss.portfolio_analyzed = True
    ss.run_health = True
    ss.request_portfolio_analyze = True


def apply_pending_portfolio_demo(st) -> None:
    """Apply deferred demo widget values before their Streamlit widgets render."""
    ss = st.session_state
    apply_pending_sidebar_portfolio_value()

    pending_mode = ss.pop(PENDING_DEMO_EXPERIENCE_KEY, None)
    if pending_mode in EXPERIENCE_OPTIONS:
        ss[EXPERIENCE_KEY] = pending_mode
        ss[PERSISTED_EXPERIENCE_KEY] = pending_mode

    pending_preset = ss.pop(PENDING_DEMO_PRESET_KEY, None)
    if pending_preset is not None:
        ss.portfolio_preset = pending_preset


def schedule_sample_portfolio_demo(st) -> None:
    """
    Seed demo state before sidebar widgets are created (auto demo on toggle).

    Safe to set widget-bound keys here because render_sidebar() has not run yet.
    """
    if pp.demo_applied(st, "portfolio"):
        return
    ss = st.session_state
    ss[EXPERIENCE_KEY] = "Advanced Mode"
    ss[PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    ss.sidebar_portfolio_value = DEMO_PORTFOLIO_VALUE
    ss.portfolio_preset = DEMO_PRESET
    ss[_PENDING_INVESTMENT_TAB_KEY] = DEMO_OVERVIEW_TAB
    _apply_demo_holdings_and_analytics(ss)
    pp.mark_demo_applied(st, "portfolio")


def request_sample_portfolio_demo(st) -> None:
    """
    Queue demo state when triggered from a button after widgets already exist.

    Values are applied on the next rerun via apply_pending_portfolio_demo().
    """
    ss = st.session_state
    ss[PENDING_DEMO_EXPERIENCE_KEY] = "Advanced Mode"
    ss[PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY] = DEMO_PORTFOLIO_VALUE
    ss[PENDING_DEMO_PRESET_KEY] = DEMO_PRESET
    ss[_PENDING_INVESTMENT_TAB_KEY] = DEMO_OVERVIEW_TAB
    _apply_demo_holdings_and_analytics(ss)
    pp.mark_demo_applied(st, "portfolio")


def render_sample_portfolio_button(st) -> None:
    if st.button("Load Sample Portfolio", type="primary", key="pp_load_sample_portfolio"):
        request_sample_portfolio_demo(st)
        st.rerun()
