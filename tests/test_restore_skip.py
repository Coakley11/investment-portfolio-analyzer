"""Tests for restore_once skip reasons and storage shim."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from suite_user_persistence import restore_once, state_file_path


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
        self.query_params: dict[str, str] = {}


class TestRestoreOnceSkip(unittest.TestCase):
    def test_empty_sources_sets_skip_reason_and_does_not_mark_restored(self) -> None:
        st = _FakeSt()
        with patch("suite_cloud_state.load_cloud_full_session", return_value=({}, None)):
            with patch("suite_user_persistence._load_raw", return_value=({}, None, None)):
                restored = restore_once(st, "investment", apply_state=lambda _s, _d: None)
        self.assertFalse(restored)
        self.assertIn("no restore source loaded", st.session_state["_suite_persist_restore_skip_reason"])
        self.assertNotIn("_suite_disk_state_restored::investment", st.session_state)

    def test_resume_query_params_skip_with_reason(self) -> None:
        st = _FakeSt()
        st.query_params = {"suite_page": "overview"}
        with patch("suite_user_persistence._load_raw", return_value=({}, None, None)):
            restored = restore_once(st, "investment", apply_state=lambda _s, _d: None)
        self.assertFalse(restored)
        self.assertIn("resume query params", st.session_state["_suite_persist_restore_skip_reason"])
        self.assertTrue(st.session_state["_suite_disk_state_restored::investment"])

    def test_successful_restore_sets_flag(self) -> None:
        st = _FakeSt()

        def _apply(_st, state):
            _st.session_state["experience"] = state["experience"]

        with patch(
            "suite_cloud_state.load_cloud_full_session",
            return_value=({"experience": "Advanced Mode"}, "2026-06-03T12:00:00+00:00"),
        ):
            with patch("suite_user_persistence._load_raw", return_value=({}, None, None)):
                restored = restore_once(st, "investment", apply_state=_apply)
        self.assertTrue(restored)
        self.assertEqual(st.session_state["experience"], "Advanced Mode")
        self.assertTrue(st.session_state["_suite_disk_state_restored::investment"])


class TestStorageShim(unittest.TestCase):
    def test_suite_storage_imports_load_current_states(self) -> None:
        import suite_storage

        self.assertTrue(hasattr(suite_storage, "load_current_states"))
        self.assertTrue(hasattr(suite_storage, "save_current_state"))
        self.assertTrue(callable(suite_storage.normalize_app_key))

    def test_investment_state_file_path(self) -> None:
        self.assertTrue(str(state_file_path("investment")).endswith("investment_user_state.json"))


if __name__ == "__main__":
    unittest.main()
