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


def test_ensure_experience_mode_leaves_widget_untouched_when_set():
    """Streamlit widget key must not be overwritten before the radio renders."""
    st = _FakeSt()
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["experience"] = "Beginner Mode"
    ips.ensure_experience_mode(st)
    assert st.session_state["experience"] == "Beginner Mode"
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"


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


def test_sync_experience_mode_change_sets_user_choice(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"

    def _fake_autosave(st_obj, *, end_of_run=False, trigger="unknown"):
        pass

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)
    ips.sync_experience_after_widget(st)
    assert st.session_state["_suite_inv_experience_user_choice"] == "Advanced Mode"
    assert st.session_state["experience"] == "Advanced Mode"


def test_apply_state_respects_user_choice_over_cloud():
    st = _FakeSt()
    st.session_state["_suite_inv_experience_user_choice"] = "Advanced Mode"
    ips.apply_investment_disk_state(
        st,
        {
            "experience": "Beginner Mode",
            "_suite_persisted_experience": "Beginner Mode",
        },
    )
    assert st.session_state["experience"] == "Advanced Mode"


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


def test_apply_state_overrides_widget_with_cloud_experience():
    """Cross-device restore must apply cloud mode even when widget already has a value."""
    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"
    ips.apply_investment_disk_state(
        st,
        {
            "experience": "Advanced Mode",
            "_suite_persisted_experience": "Advanced Mode",
        },
    )
    assert st.session_state["experience"] == "Advanced Mode"
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"


def test_apply_state_preserves_widget_when_pending_local_mode_change():
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["_suite_inv_pending_experience_mode"] = "Advanced Mode"
    ips.apply_investment_disk_state(
        st,
        {
            "experience": "Beginner Mode",
            "_suite_persisted_experience": "Beginner Mode",
        },
    )
    assert st.session_state["experience"] == "Advanced Mode"
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"


def test_notify_tab_change_sets_dirty_and_autosaves(monkeypatch):
    from components.beginner_navigation import BEGINNER_TAB_LABELS

    st = _FakeSt()
    st.session_state["investment_active_tab"] = BEGINNER_TAB_LABELS[0]
    st.session_state[ips._LAST_PERSISTED_TAB_KEY] = BEGINNER_TAB_LABELS[0]
    triggers: list[str] = []

    def _fake_autosave(st_obj, *, end_of_run=False, trigger="unknown"):
        triggers.append(trigger)

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)
    changed = ips.notify_investment_tab_change(
        st,
        BEGINNER_TAB_LABELS[2],
        source="test",
    )
    assert changed is True
    assert triggers == ["tab_change"]
    assert st.session_state["_suite_persist_local_dirty::investment"] is True
    assert st.session_state[ips._TAB_PAGE_DIRTY_KEY] is True
    assert st.session_state["investment_active_tab"] == BEGINNER_TAB_LABELS[2]
    evt = st.session_state["_suite_inv_debug_last_tab_change"]
    assert evt["tab_change_detected"] is True
    assert evt["autosave_triggered"] is True


def test_notify_tab_change_skips_when_tab_unchanged(monkeypatch):
    from components.beginner_navigation import BEGINNER_TAB_LABELS

    st = _FakeSt()
    st.session_state["investment_active_tab"] = BEGINNER_TAB_LABELS[2]
    st.session_state[ips._LAST_PERSISTED_TAB_KEY] = BEGINNER_TAB_LABELS[2]
    triggers: list[str] = []

    monkeypatch.setattr(
        ips,
        "autosave_investment_state",
        lambda *a, **k: triggers.append(k.get("trigger", "unknown")),
    )
    changed = ips.notify_investment_tab_change(st, BEGINNER_TAB_LABELS[2], source="test")
    assert changed is False
    assert triggers == []


def test_autosave_tab_change_writes_tab_and_readback(monkeypatch):
    from components.beginner_navigation import BEGINNER_TAB_LABELS

    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"
    st.session_state["investment_active_tab"] = BEGINNER_TAB_LABELS[2]
    st.session_state[ips._LAST_PERSISTED_TAB_KEY] = BEGINNER_TAB_LABELS[0]

    import copy
    import hashlib
    import json

    old_state = ips.build_investment_disk_state(st)
    old_state["investment_active_tab"] = BEGINNER_TAB_LABELS[0]
    old_fp = hashlib.sha256(
        json.dumps(old_state, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:20]
    st.session_state["_suite_autosave_fp::investment"] = old_fp

    saved_payloads: list[dict] = []

    def _fake_save_disk(app_id, payload):
        saved_payloads.append(copy.deepcopy(payload))
        return True

    def _fake_save_cloud(app_id, payload, *, page="", summary=""):
        saved_payloads.append(copy.deepcopy(payload))

    def _fake_load_cloud(app_id):
        return copy.deepcopy(saved_payloads[-1]), "2026-06-11T12:00:00Z"

    monkeypatch.setattr("suite_user_persistence.save_user_state", _fake_save_disk)
    monkeypatch.setattr("suite_cloud_state.save_cloud_full_session", _fake_save_cloud)
    monkeypatch.setattr("suite_cloud_state.load_cloud_full_session", _fake_load_cloud)
    monkeypatch.setattr("suite_cloud_state.session_page_summary", lambda *a, **k: ("tab", "summary"))

    ips.autosave_investment_state(st, trigger="tab_change")
    event = st.session_state["_suite_inv_debug_last_autosave_event"]
    assert event["outcome"] != "skipped_fp_unchanged"
    assert event["blob_tab"] == BEGINNER_TAB_LABELS[2]
    assert event["cloud_readback_tab"] == BEGINNER_TAB_LABELS[2]
    assert st.session_state[ips._LAST_PERSISTED_TAB_KEY] == BEGINNER_TAB_LABELS[2]


def test_build_state_includes_risk_free_pct_from_session():
    st = _FakeSt()
    st.session_state["risk_free_pct"] = 3.5
    state = ips.build_investment_disk_state(st)
    assert state["risk_free_pct"] == 3.5


def test_notify_global_settings_change_triggers_autosave(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["sidebar_portfolio_value"] = 100_000
    st.session_state["risk_free_pct"] = 4.0
    ips.seed_last_persisted_global_from_state(
        st,
        ips.build_investment_disk_state(st),
    )
    st.session_state["sidebar_portfolio_value"] = 250_000
    st.session_state["risk_free_pct"] = 3.5
    triggers: list[str] = []

    monkeypatch.setattr(
        ips,
        "autosave_investment_state",
        lambda *a, **k: triggers.append(k.get("trigger", "unknown")),
    )
    changed = ips.notify_global_settings_change(st, source="test")
    assert changed is True
    assert triggers == ["global_setting_change"]
    assert st.session_state["_suite_persist_local_dirty::investment"] is True


def test_autosave_global_setting_change_writes_portfolio_and_risk_free(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["sidebar_portfolio_value"] = 250_000
    st.session_state["risk_free_pct"] = 3.5
    st.session_state["analysis_start_date"] = dt.date(2020, 1, 1)
    st.session_state["analysis_end_date"] = dt.date(2025, 12, 31)

    import copy

    saved_payloads: list[dict] = []

    def _fake_save_disk(app_id, payload):
        saved_payloads.append(copy.deepcopy(payload))
        return True

    def _fake_save_cloud(app_id, payload, *, page="", summary=""):
        saved_payloads.append(copy.deepcopy(payload))

    def _fake_load_cloud(app_id):
        return copy.deepcopy(saved_payloads[-1]), "2026-06-11T14:00:00Z"

    monkeypatch.setattr("suite_user_persistence.save_user_state", _fake_save_disk)
    monkeypatch.setattr("suite_cloud_state.save_cloud_full_session", _fake_save_cloud)
    monkeypatch.setattr("suite_cloud_state.load_cloud_full_session", _fake_load_cloud)
    monkeypatch.setattr("suite_cloud_state.session_page_summary", lambda *a, **k: ("tab", "summary"))

    ips.autosave_investment_state(st, trigger="global_setting_change")
    event = st.session_state["_suite_inv_debug_last_autosave_event"]
    assert event["outcome"] != "skipped_fp_unchanged"
    assert event["payload_global_portfolio_value"] == 250_000
    assert event["payload_risk_free_pct"] == 3.5
    assert event["cloud_readback_portfolio_value"] == 250_000
    assert event["cloud_readback_risk_free_pct"] == 3.5


def test_notify_portfolio_change_triggers_autosave(monkeypatch):
    st = _FakeSt()
    st.session_state["holdings_df"] = pd.DataFrame(
        [{"Ticker": "VTI", "Weight (%)": 100.0, "Asset Type": "Equity"}]
    )
    ips.seed_last_persisted_portfolio_from_state(st, ips.build_investment_disk_state(st))
    st.session_state["holdings_df"] = pd.DataFrame(
        [
            {"Ticker": "VYM", "Weight (%)": 50.0, "Asset Type": "Dividend ETF"},
            {"Ticker": "BND", "Weight (%)": 50.0, "Asset Type": "Bonds"},
        ]
    )
    triggers: list[str] = []

    monkeypatch.setattr(
        ips,
        "autosave_investment_state",
        lambda *a, **k: triggers.append(k.get("trigger", "unknown")),
    )
    changed = ips.notify_portfolio_change(st, source="test")
    assert changed is True
    assert triggers == ["portfolio_change"]
    assert st.session_state["_suite_persist_local_dirty::investment"] is True


def test_autosave_portfolio_change_writes_holdings_fingerprint_readback(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["holdings_df"] = pd.DataFrame(
        [
            {"Ticker": "VYM", "Weight (%)": 50.0, "Asset Type": "Dividend ETF"},
            {"Ticker": "BND", "Weight (%)": 50.0, "Asset Type": "Bonds"},
        ]
    )

    import copy

    saved_payloads: list[dict] = []

    def _fake_save_disk(app_id, payload):
        saved_payloads.append(copy.deepcopy(payload))
        return True

    def _fake_save_cloud(app_id, payload, *, page="", summary=""):
        saved_payloads.append(copy.deepcopy(payload))

    def _fake_load_cloud(app_id):
        return copy.deepcopy(saved_payloads[-1]), "2026-06-11T15:00:00Z"

    monkeypatch.setattr("suite_user_persistence.save_user_state", _fake_save_disk)
    monkeypatch.setattr("suite_cloud_state.save_cloud_full_session", _fake_save_cloud)
    monkeypatch.setattr("suite_cloud_state.load_cloud_full_session", _fake_load_cloud)
    monkeypatch.setattr("suite_cloud_state.session_page_summary", lambda *a, **k: ("tab", "summary"))

    ips.autosave_investment_state(st, trigger="portfolio_change")
    event = st.session_state["_suite_inv_debug_last_autosave_event"]
    assert event["outcome"] != "skipped_fp_unchanged"
    expected_fp = event["payload_holdings_fingerprint"]
    assert "VYM:50.0:Dividend ETF" in expected_fp
    assert "BND:50.0:Bonds" in expected_fp
    assert event["cloud_readback_holdings_fingerprint"] == expected_fp


def test_apply_state_sets_last_persisted_tab():
    from components.beginner_navigation import BEGINNER_TAB_LABELS

    st = _FakeSt()
    ips.apply_investment_disk_state(
        st,
        {
            "experience": "Beginner Mode",
            "investment_active_tab": BEGINNER_TAB_LABELS[0],
            "holdings_df": [{"Ticker": "SPY", "Weight (%)": 100.0, "Asset Type": "Equity"}],
        },
    )
    assert st.session_state[ips._LAST_PERSISTED_TAB_KEY] == BEGINNER_TAB_LABELS[0]


def test_autosave_mode_change_does_not_skip_when_fp_unchanged(monkeypatch):
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"

    import hashlib
    import json

    state = ips.build_investment_disk_state(st)
    blob = json.dumps(state, sort_keys=True, default=str)
    fp = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
    st.session_state["_suite_autosave_fp::investment"] = fp

    saved = {"disk": 0, "cloud": 0}

    def _fake_save_disk(app_id, payload):
        saved["disk"] += 1
        return True

    def _fake_save_cloud(app_id, payload, *, page="", summary=""):
        saved["cloud"] += 1

    def _fake_load_cloud(app_id):
        return payload_copy(state), "2026-06-07T12:00:00Z"

    def payload_copy(s):
        import copy
        return copy.deepcopy(s)

    monkeypatch.setattr("suite_user_persistence.save_user_state", _fake_save_disk)
    monkeypatch.setattr("suite_cloud_state.save_cloud_full_session", _fake_save_cloud)
    monkeypatch.setattr("suite_cloud_state.load_cloud_full_session", _fake_load_cloud)
    monkeypatch.setattr("suite_cloud_state.session_page_summary", lambda *a, **k: ("tab", "summary"))

    ips.autosave_investment_state(st, trigger="mode_change")
    event = st.session_state["_suite_inv_debug_last_autosave_event"]
    assert event["outcome"] != "skipped_fp_unchanged"
    assert saved["disk"] == 1 or saved["cloud"] == 1
