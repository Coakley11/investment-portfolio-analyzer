"""Test local experience mode is not clobbered by per-run cloud reconcile."""

from __future__ import annotations

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


def test_reconcile_skips_after_first_bootstrap_attempt(monkeypatch):
    """Per-session reconcile must not re-run and overwrite widget edits."""
    st = _FakeSt()
    st.session_state["experience"] = "Advanced Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Advanced Mode"
    st.session_state["_suite_inv_experience_user_choice"] = "Advanced Mode"
    st.session_state["_suite_inv_cloud_reconcile_done"] = True

    def _should_not_apply(st_obj, state):
        st_obj.session_state["experience"] = "Beginner Mode"
        return None

    monkeypatch.setattr(ips, "apply_investment_disk_state", _should_not_apply)
    monkeypatch.setattr(ips, "investment_cloud_resync_needed", lambda *a, **k: (True, "experience"))
    assert ips.reconcile_investment_cloud_drift_if_needed(st) is False
    assert st.session_state["experience"] == "Advanced Mode"


def test_experience_mode_switch_sequence(monkeypatch):
    """Simulate Beginner → Advanced widget change without reconcile clobber."""
    st = _FakeSt()
    st.session_state["experience"] = "Beginner Mode"
    st.session_state[ips.PERSISTED_EXPERIENCE_KEY] = "Beginner Mode"
    st.session_state["_suite_inv_cloud_reconcile_done"] = True

    saved_modes: list[str] = []

    def _fake_autosave(st_obj, *, end_of_run=False, trigger="unknown"):
        saved_modes.append(ips.current_experience_mode(st_obj))

    monkeypatch.setattr(ips, "autosave_investment_state", _fake_autosave)

    st.session_state["experience"] = "Advanced Mode"
    ips.sync_experience_after_widget(st)

    ips.ensure_experience_mode(st)
    assert st.session_state["experience"] == "Advanced Mode"
    assert st.session_state[ips.PERSISTED_EXPERIENCE_KEY] == "Advanced Mode"
    assert saved_modes == ["Advanced Mode"]

    ips.reconcile_investment_cloud_drift_if_needed(st)
    assert st.session_state["experience"] == "Advanced Mode"
