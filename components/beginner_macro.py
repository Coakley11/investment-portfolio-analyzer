"""Beginner Mode — automatic macro defaults and simple economic environment UI."""

from __future__ import annotations

import streamlit as st

from components.macro_data import (
    CUSTOM_SCENARIOS,
    SCENARIO_LABELS,
    apply_current_environment_from_live,
    apply_custom_scenario,
    beginner_friendly_labels,
    get_macro_snapshot,
    macro_data_source_note,
    map_snapshot_to_assumptions,
)


def _pct(x: float) -> str:
    return f"{x:.1f}%"


def _session_mapping_summary() -> str:
    rate = st.session_state.get("health_rate_env", "Stable Rates")
    infl = st.session_state.get("health_inflation", "Moderate Inflation")
    rec = st.session_state.get("health_recession", 25)
    regime = st.session_state.get("health_regime", "Expansion")
    return f"{rate} · {infl} · {rec}% recession est. · {regime}"


def render_beginner_macro_panel(*, key_prefix: str = "beg_macro") -> None:
    """Current economic data, summary card, and scenario picker for Beginner Mode."""
    st.markdown("#### Current economic environment")
    st.caption(
        "The app loads public U.S. economic data so you do not need to guess interest rates or inflation."
    )

    if "macro_live_snapshot" not in st.session_state:
        st.session_state.macro_live_snapshot = get_macro_snapshot()

    snapshot = st.session_state.macro_live_snapshot
    if snapshot.fetch_warnings:
        for w in snapshot.fetch_warnings:
            st.warning(w)

    mapping = map_snapshot_to_assumptions(snapshot)
    labels = beginner_friendly_labels(mapping, snapshot)
    active_id = st.session_state.get("macro_scenario_id", "current")
    mode = st.session_state.get("macro_scenario_mode", "current")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Current Interest Rate Environment**")
        st.markdown(
            f"Federal Funds Rate: **{_pct(snapshot.federal_funds)}**  \n"
            f"10-Year Treasury Yield: **{_pct(snapshot.treasury_10y)}**  \n"
            f"3-Month Treasury Yield: **{_pct(snapshot.treasury_3m)}**  \n"
            f"Last updated: {snapshot.as_of_date}"
        )
    with c2:
        st.markdown("**Current Inflation Environment**")
        core_line = (
            f"Core CPI (YoY): **{_pct(snapshot.core_cpi_yoy)}**  \n"
            if snapshot.core_cpi_yoy is not None
            else ""
        )
        st.markdown(
            f"CPI Inflation (YoY): **{_pct(snapshot.cpi_yoy)}**  \n"
            f"{core_line}"
            f"Last updated: {snapshot.as_of_date}"
        )
    with c3:
        st.markdown("**Current Labor Market**")
        st.markdown(
            f"Unemployment Rate: **{_pct(snapshot.unemployment)}**  \n"
            f"Last updated: {snapshot.as_of_date}"
        )

    st.markdown(
        f"""
        <div style="background:#141c2b;border:1px solid #334155;border-radius:12px;
        padding:1rem 1.1rem;margin:0.75rem 0;">
        <div style="font-weight:700;color:#f1f5f9;font-size:1.05rem;margin-bottom:0.5rem;">
        Current Economic Environment</div>
        <div style="color:#e2e8f0;line-height:1.6;font-size:0.92rem;">
        <b>Interest Rates:</b> {labels['interest']}<br>
        <b>Inflation:</b> {labels['inflation']}<br>
        <b>Labor Market:</b> {labels['labor']}<br><br>
        <b>Overall Environment:</b><br>
        {labels['overall']}
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(f"Model assumptions in use: {_session_mapping_summary()}")
    if mode == "custom":
        st.info(f"Custom scenario active: **{SCENARIO_LABELS.get(active_id, active_id)}**")

    st.markdown("##### Economic scenario")
    choice = st.radio(
        "Assumption source",
        ["current", "custom"],
        format_func=lambda x: "Use Current Environment" if x == "current" else "Create Custom Scenario",
        horizontal=True,
        key=f"{key_prefix}_mode",
        index=0 if mode != "custom" else 1,
    )

    if choice == "current":
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Apply current economic data", type="primary", key=f"{key_prefix}_apply_current"):
                snap = apply_current_environment_from_live(force_refresh=False)
                st.session_state.macro_live_snapshot = snap
                st.rerun()
        with b2:
            if st.button("Refresh live data", key=f"{key_prefix}_refresh_live"):
                snap = apply_current_environment_from_live(force_refresh=True)
                st.session_state.macro_live_snapshot = snap
                st.rerun()
    else:
        scenario = st.selectbox(
            "Choose a scenario to explore",
            options=[k for k in SCENARIO_LABELS if k != "current"],
            format_func=lambda k: SCENARIO_LABELS[k],
            key=f"{key_prefix}_scenario_pick",
        )
        if st.button("Apply this scenario", type="primary", key=f"{key_prefix}_apply_scenario"):
            apply_custom_scenario(scenario)
            st.rerun()
        st.caption(CUSTOM_SCENARIOS[scenario].rate_environment + " · " + CUSTOM_SCENARIOS[scenario].inflation)

    with st.expander("Where do these numbers come from?", expanded=False):
        st.markdown(
            f"""
            The app uses **publicly available U.S. economic data** (primarily [FRED](https://fred.stlouisfed.org/))
            to populate default assumptions:

            - Federal Funds Rate, Treasury yields, CPI, and unemployment
            - Values are mapped into simple categories the portfolio model understands

            **Source for this session:** {macro_data_source_note(snapshot)}

            These values are updated when you refresh live data and can be changed with a custom scenario.
            They are **not** a forecast — they are a starting point for educational stress tests.

            Advanced Mode still lets you edit every assumption manually on the Portfolio Health tab.
            """
        )
