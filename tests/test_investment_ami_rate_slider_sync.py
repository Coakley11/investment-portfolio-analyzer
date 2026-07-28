"""Slider ↔ scenario_params sync for signed macro rate shock."""

from __future__ import annotations

from types import SimpleNamespace

from investment_ami_sliders import (
    _seed_macro_rate_shock_params,
    build_scenario_params_from_sliders,
    slider_specs_for,
)


class _FakeSessionState(dict):
    pass


def test_first_bind_seeds_negative_rate_shock_for_cut_question() -> None:
    st = SimpleNamespace(session_state=_FakeSessionState())
    insight = {
        "question_id": "q-cut-1",
        "question": "What happens if the Federal Reserve cuts interest rates?",
        "scenario_params": {"rate_shock_pp": -2.0, "rate_shock": "Falling"},
    }
    params = _seed_macro_rate_shock_params(
        insight,
        {"rate_rise_pct": 2.0},
        scope_id="q-cut-1",
        st=st,
        first_bind=True,
    )
    assert params["rate_shock_pp"] == -2.0
    assert st.session_state["ami_slider_q-cut-1_rate_shock_pp"] == -2.0

    specs = slider_specs_for("macro_rates", insight)
    values = {s.key: params[s.key] for s in specs}
    merged = build_scenario_params_from_sliders(specs, values, problem_type="macro_rates")
    assert merged["rate_shock_pp"] == -2.0
