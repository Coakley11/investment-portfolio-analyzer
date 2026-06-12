"""Investment startup restore must not be blocked by stale AMI flags."""

from __future__ import annotations

import unittest

from suite_cloud_state import has_resume_query_params, reconcile_stale_resume_session_flags


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


if __name__ == "__main__":
    unittest.main()
