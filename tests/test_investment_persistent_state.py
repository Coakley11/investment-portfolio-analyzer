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


def test_ensure_experience_mode_widget_wins_when_both_set():
    """Documents init bug: stale widget key overrides restored persisted copy."""
    st = _FakeSt()
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["experience"] = "Beginner Mode"
    ips.ensure_experience_mode(st)
    assert st.session_state["experience"] == "Beginner Mode"
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Beginner Mode"


def test_sync_experience_after_widget_triggers_save_on_change(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"
    saved: list[str] = []

    def _fake_autosave(st_obj, *, end_of_run=False, trigger="unknown"):
        saved.append(f"{ips.current_experience_mode(st_obj)}:{trigger}")

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)
    ips.sync_experience_after_widget(st)
    assert saved == ["Advanced Mode:mode_change"]
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"
    assert st.session_state["_suite_inv_debug_last_mode_switch"]["autosave_triggered"] is True


def test_apply_state_empty_holdings_blob_not_default_portfolio():
    st = _FakeSt()
    ips.apply_investment_disk_state(st, {"holdings_df": []})
    assert st.session_state.holdings_df.empty
    assert st.session_state.get("_suite_inv_holdings_restore_issue") == "empty_saved_holdings"
    assert st.session_state.get("_suite_inv_holdings_from_saved_blob") is True


def test_apply_state_no_holdings_key_uses_factory_default():
    st = _FakeSt()
    ips.apply_investment_disk_state(st, {"experience": "Advanced Mode"})
    assert not st.session_state.holdings_df.empty
    assert len(st.session_state.holdings_df) >= 1
    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"
    needed, detail = ips.investment_cloud_resync_needed(
        st,
        {"experience": "Advanced Mode", "_suite_persisted_experience": "Advanced Mode"},
    )
    assert needed is True
    assert "experience" in detail


def test_investment_cloud_resync_skips_experience_during_pending_local_mode_change():
    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["_suite_inv_pending_experience_mode"] = "Beginner Mode"
    needed, detail = ips.investment_cloud_resync_needed(
        st,
        {"experience": "Advanced Mode", "_suite_persisted_experience": "Advanced Mode"},
    )
    assert needed is False
    assert "experience" not in detail


def test_investment_cloud_resync_detects_experience_when_only_widget_persisted_mismatch():
    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    needed, detail = ips.investment_cloud_resync_needed(
        st,
        {"experience": "Advanced Mode", "_suite_persisted_experience": "Advanced Mode"},
    )
    assert needed is True
    assert "experience" in detail


def test_investment_cloud_resync_false_when_aligned():
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    needed, detail = ips.investment_cloud_resync_needed(
        st,
        {"experience": "Advanced Mode", "_suite_persisted_experience": "Advanced Mode"},
    )
    assert needed is False
    assert detail == ""


def test_sync_experience_mode_change_sets_pending_and_dirty(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"

    def _fake_autosave(st_obj, *, end_of_run=False, trigger="unknown"):
        pass

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)
    ips.sync_experience_after_widget(st)
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Beginner Mode"
    assert st.session_state["_suite_inv_pending_experience_mode"] == "Beginner Mode"
    assert st.session_state["_suite_persist_local_dirty::investment"] is True


def test_sync_experience_skips_autosave_when_mode_unchanged(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    called = {"n": 0}

    def _fake_autosave(st_obj, *, end_of_run=False, trigger="unknown"):
        called["n"] += 1

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)
    ips.sync_experience_after_widget(st)
    assert called["n"] == 0
    switch = st.session_state["_suite_inv_debug_last_mode_switch"]
    assert switch["autosave_triggered"] is False
    assert switch["autosave_skip_reason"] == "prev_equals_mode"
