"""Portfolio demo state loaders — investment app. Presentation only."""

from __future__ import annotations

import pandas as pd

import portfolio_core as core
import portfolio_polish as pp
from components.beginner_navigation import ADVANCED_TAB_LABELS
from investment_persistent_state import EXPERIENCE_KEY


def load_sample_portfolio(st) -> None:
    """Load diversified Balanced preset and open Overview with analytics ready."""
    st.session_state[EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS["Balanced"])
    st.session_state.portfolio_preset = "Balanced"
    st.session_state.preset_applied = "Balanced"
    st.session_state.portfolio_analyzed = True
    st.session_state.run_health = True
    st.session_state.request_portfolio_analyze = True
    st.session_state.investment_active_tab = ADVANCED_TAB_LABELS[1]
    st.session_state.sidebar_portfolio_value = 100_000
    pp.mark_demo_applied(st, "portfolio")


def apply_auto_demo(st) -> None:
    if pp.is_demo_mode(st) and not pp.demo_applied(st, "portfolio"):
        load_sample_portfolio(st)


def render_sample_portfolio_button(st) -> None:
    if st.button("Load Sample Portfolio", type="primary", key="pp_load_sample_portfolio"):
        load_sample_portfolio(st)
        st.rerun()
