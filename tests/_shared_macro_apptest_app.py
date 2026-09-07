"""Minimal Streamlit app for shared-macro AppTest persistence regressions."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from components.macro_engine import (
    ensure_shared_macro_session_defaults,
    harvest_shared_macro_widgets_to_persist,
    macro_assumptions_from_session,
    macro_widget_key,
    render_shared_macro_assumption_controls,
)

ensure_shared_macro_session_defaults()
harvest_shared_macro_widgets_to_persist()

page = st.radio("page", ["health", "macro"], key="page")
# Optional gate: skip Health controls on a post-select run (real nav / early rerun).
render_health = page == "health" and not st.session_state.get("_force_skip_health")
if render_health:
    render_shared_macro_assumption_controls()

st.write("persist=" + str(st.session_state.get("health_valuation")))
st.write("widget=" + str(st.session_state.get(macro_widget_key("health_valuation"))))
st.write("forward=" + str(macro_assumptions_from_session().valuation))
st.write("rates=" + str(st.session_state.get("health_rate_env")))
st.write("inflation=" + str(st.session_state.get("health_inflation")))
st.write("recession=" + str(st.session_state.get("health_recession")))
st.write("regime=" + str(st.session_state.get("health_regime")))
