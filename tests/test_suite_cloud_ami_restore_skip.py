"""Investment startup restore must not be blocked by stale AMI flags."""

from __future__ import annotations

import unittest

from suite_cloud_state import (
    has_resume_query_params,
    list_workspace_restore_blocking_params,
    purge_stale_investment_ami_restore_blockers,
    reconcile_stale_resume_session_flags,
)


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self, params: dict[str, str] | None = None) -> None:
        self.session_state = _FakeSessionState()
        self.query_params = dict(params or {})


class TestSuiteCloudAmiRestoreSkip(unittest.TestCase):
    def test_stale_ami_context_does_not_block_restore(self) -> None:
        st = _FakeSt()
        st.session_state["_ami_return_context"] = {"source_page": "Portfolio Health"}
        st.session_state["_skip_page_restore_for"] = "Portfolio Health"
        self.assertFalse(has_resume_query_params(st, "investment"))

    def test_reconcile_clears_stale_skip_page_restore_for(self) -> None:
        st = _FakeSt()
        st.session_state["_skip_page_restore_for"] = "Portfolio Health"
        st.session_state["_ami_return_context"] = {"source_page": "Portfolio Health"}
        cleared = reconcile_stale_resume_session_flags(st, "investment")
        self.assertIn("_skip_page_restore_for", cleared)
        self.assertNotIn("_skip_page_restore_for", st.session_state)

    def test_purge_clears_stale_flags_and_records_emergency_trace(self) -> None:
        st = _FakeSt()
        st.session_state["_skip_page_restore_for"] = "Portfolio Health"
        st.session_state["_ami_return_context"] = {"source_page": "Portfolio Health"}
        st.session_state["_ami_pending_insight"] = {"conclusion": "test"}
        diag = purge_stale_investment_ami_restore_blockers(st, "investment")
        self.assertFalse(has_resume_query_params(st, "investment"))
        self.assertNotIn("_skip_page_restore_for", st.session_state)
        self.assertNotIn("_ami_return_context", st.session_state)
        self.assertIs(st.session_state.get("has_suite_ami_insight"), False)
        self.assertIs(st.session_state.get("has_suite_ai_question_id"), False)
        self.assertIn("_skip_page_restore_for", diag.get("stale_ami_flags_detected") or [])
        self.assertIn("_skip_page_restore_for", diag.get("stale_ami_flags_cleared") or [])

    def test_purge_does_not_clear_when_live_ami_insight_on_url(self) -> None:
        st = _FakeSt({"suite_ami_insight": "live-id"})
        st.session_state["_skip_page_restore_for"] = "Portfolio Health"
        purge_stale_investment_ami_restore_blockers(st, "investment")
        self.assertIn("suite_ami_insight", list_workspace_restore_blocking_params(st, "investment"))
        self.assertIn("_skip_page_restore_for", st.session_state)


if __name__ == "__main__":
    unittest.main()
