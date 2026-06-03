"""Tests for investment cloud/disk persistence."""

from __future__ import annotations

import datetime as dt

import pandas as pd

import investment_persistent_state as ips


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


def test_build_state_always_includes_experience_mode():
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    state = ips.build_investment_disk_state(st)
    assert state["experience"] == "Advanced Mode"
    assert state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"


def test_build_state_defaults_experience_when_missing():
    st = _FakeSt()
    state = ips.build_investment_disk_state(st)
    assert state["experience"] == ips.EXPERIENCE_OPTIONS[0]


def test_apply_state_restores_experience_to_widget_and_persisted_keys():
    st = _FakeSt()
    ips.apply_investment_disk_state(
        st,
        {
            "experience": "Advanced Mode",
            "health_active_tab": "Portfolio Health",
            "holdings_df": [{"Ticker": "SPY", "Weight (%)": 100.0, "Asset Type": "Equity"}],
        },
    )
    assert st.session_state["experience"] == "Advanced Mode"
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"
    assert st.session_state["investment_active_tab"] == "Portfolio Health"
    assert st.session_state["_suite_inv_debug_mode_after_restore"] == "Advanced Mode"


def test_apply_state_serializes_dates():
    st = _FakeSt()
    start = dt.date(2020, 1, 1)
    end = dt.date(2024, 12, 31)
    ips.apply_investment_disk_state(
        st,
        {"analysis_start_date": start.isoformat(), "analysis_end_date": end.isoformat()},
    )
    assert st.session_state["analysis_start_date"] == start
    assert st.session_state["analysis_end_date"] == end


def test_ensure_experience_mode_seeds_widget_from_persisted_copy():
    st = _FakeSt()
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    ips.ensure_experience_mode(st)
    assert st.session_state["experience"] == "Advanced Mode"


def test_sync_experience_after_widget_triggers_save_on_change(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"
    saved: list[str] = []

    def _fake_autosave(st_obj):
        saved.append(ips.current_experience_mode(st_obj))

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)
    ips.sync_experience_after_widget(st)
    assert saved == ["Advanced Mode"]
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"
