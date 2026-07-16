"""Regression: developer UI only for authorized admin accounts with dev mode enabled."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from suite_workspace import (
    can_show_developer_tools,
    is_developer_workspace,
    set_active_workspace_id,
)


class _FakeSt:
    def __init__(self, workspace: str = "daniel", *, dev_query: bool = False) -> None:
        self.session_state: dict = {}
        self.query_params = {"dev": "1"} if dev_query else {}
        set_active_workspace_id(self, workspace)  # type: ignore[arg-type]


class TestDeveloperWorkspaceGating(unittest.TestCase):
    def test_daniel_workspace_without_admin_hides_tools(self) -> None:
        st = _FakeSt("daniel", dev_query=True)
        with patch("suite_workspace.is_admin_session", return_value=False):
            self.assertTrue(is_developer_workspace(st=st))  # type: ignore[arg-type]
            self.assertFalse(can_show_developer_tools(st=st))  # type: ignore[arg-type]

    def test_admin_without_dev_mode_hides_tools(self) -> None:
        st = _FakeSt("daniel", dev_query=False)
        with patch("suite_workspace.is_admin_session", return_value=True):
            self.assertFalse(can_show_developer_tools(st=st))  # type: ignore[arg-type]

    def test_admin_with_dev_query_shows_tools(self) -> None:
        st = _FakeSt("daniel", dev_query=True)
        with patch("suite_workspace.is_admin_session", return_value=True):
            self.assertTrue(can_show_developer_tools(st=st))  # type: ignore[arg-type]

    def test_ariel_with_dev_query_hides_tools(self) -> None:
        st = _FakeSt("ariel", dev_query=True)
        with patch("suite_workspace.is_admin_session", return_value=False):
            self.assertFalse(can_show_developer_tools(st=st))  # type: ignore[arg-type]

    def test_guest_with_dev_query_hides_tools(self) -> None:
        st = _FakeSt("guest", dev_query=True)
        with patch("suite_workspace.is_admin_session", return_value=False):
            self.assertFalse(can_show_developer_tools(st=st))  # type: ignore[arg-type]

    def test_investment_trace_blocked_for_non_admin(self) -> None:
        from investment_persistence_trace import investment_trace_enabled

        st = _FakeSt("ariel", dev_query=True)
        st.session_state["investment_show_dev_diagnostics"] = True
        with patch("suite_workspace.is_admin_session", return_value=False):
            self.assertFalse(investment_trace_enabled(st, persistence_ok=True))  # type: ignore[arg-type]

    def test_investment_trace_allowed_for_admin_dev(self) -> None:
        from investment_persistence_trace import investment_trace_enabled

        st = _FakeSt("daniel", dev_query=True)
        with patch("suite_workspace.is_admin_session", return_value=True):
            self.assertTrue(investment_trace_enabled(st, persistence_ok=True))  # type: ignore[arg-type]

    def test_pr1_verification_sidebar_skips_non_admin(self) -> None:
        from investment_persistence_trace import render_pr1_verification_sidebar

        st = _FakeSt("ariel", dev_query=True)
        st.sidebar = MagicMock()
        with patch("suite_workspace.is_admin_session", return_value=False):
            render_pr1_verification_sidebar(st, persistence_ok=True)  # type: ignore[arg-type]
        st.sidebar.expander.assert_not_called()

    def test_developer_diagnostics_gate(self) -> None:
        from investment_workflow import developer_access_available, developer_diagnostics_enabled

        daniel = _FakeSt("daniel", dev_query=True)
        ariel = _FakeSt("ariel", dev_query=True)
        with patch("suite_workspace.is_admin_session", side_effect=lambda st=None: st is daniel):
            self.assertTrue(developer_diagnostics_enabled(daniel))  # type: ignore[arg-type]
            self.assertFalse(developer_diagnostics_enabled(ariel))  # type: ignore[arg-type]
            self.assertTrue(developer_access_available(daniel))  # type: ignore[arg-type]
            self.assertFalse(developer_access_available(ariel))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
