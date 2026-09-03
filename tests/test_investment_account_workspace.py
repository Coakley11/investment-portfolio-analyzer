"""Regression: Investment Account & Workspace consolidation.

Covers opening Account & Workspace, Command Center entry, Saved Sessions,
workspace/session state retention across re-render, logout, and reset-confirm
persistence keys (rerun-safe widget keys).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _ctx(**overrides):
    base = {
        "active_workspace_label": "Daniel",
        "active_workspace_id": "daniel",
        "email_display": "daniel@example.com",
        "email": "daniel@example.com",
    }
    base.update(overrides)
    return base


class _ExpanderCtx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestInvestmentAccountWorkspaceConsolidation(unittest.TestCase):
    def _make_st(self, session: dict | None = None) -> MagicMock:
        st = MagicMock()
        st.session_state = dict(session or {})
        st.sidebar = MagicMock()
        st.sidebar.expander.return_value = _ExpanderCtx()
        st.columns.return_value = (MagicMock(), MagicMock())
        return st

    def test_opens_account_workspace_expander_with_music_label(self) -> None:
        st = self._make_st({"_suite_auth_session": True})
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=True),
            patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
            patch(
                "suite_command_center_link.command_center_url",
                return_value="https://cc.example/?suite_workspace=daniel",
            ),
            patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        st.sidebar.expander.assert_called_once()
        label = st.sidebar.expander.call_args[0][0]
        self.assertIn("Account & Workspace", label)
        self.assertIn("Daniel", label)
        self.assertEqual(
            st.sidebar.expander.call_args.kwargs.get("key"),
            "suite_account_workspace_expander",
        )

    def test_exposes_command_center_inside_control(self) -> None:
        st = self._make_st({"_suite_auth_session": True})
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=True),
            patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
            patch(
                "suite_command_center_link.command_center_url",
                return_value="https://cc.example/?suite_workspace=daniel",
            ) as cc_url,
            patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        cc_url.assert_called()
        st.link_button.assert_called()
        link_label = st.link_button.call_args[0][0]
        self.assertIn("Command Center", link_label)
        self.assertEqual(
            st.link_button.call_args[0][1],
            "https://cc.example/?suite_workspace=daniel",
        )

    def test_exposes_saved_sessions_with_stable_reset_key(self) -> None:
        st = self._make_st({"_suite_auth_session": True})
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=True),
            patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
            patch(
                "suite_command_center_link.command_center_url",
                return_value="https://cc.example/",
            ),
            patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        markdowns = " ".join(str(c.args[0]) for c in st.markdown.call_args_list if c.args)
        self.assertIn("Saved Sessions", markdowns)
        reset_keys = [
            c.kwargs.get("key")
            for c in st.button.call_args_list
            if c.kwargs.get("key")
        ]
        self.assertIn("suite_reset_btn::investment", reset_keys)

    def test_rerender_preserves_workspace_and_session_keys(self) -> None:
        """Re-opening Account & Workspace must not wipe workspace / session state."""
        session = {
            "_suite_auth_session": True,
            "_suite_active_workspace_id": "daniel",
            "investment_active_tab": "Health",
            "some_portfolio_flag": True,
        }
        st = self._make_st(session)
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=True),
            patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
            patch(
                "suite_command_center_link.command_center_url",
                return_value="https://cc.example/",
            ),
            patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)
            snapshot = dict(st.session_state)
            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        self.assertEqual(st.session_state.get("_suite_active_workspace_id"), "daniel")
        self.assertEqual(st.session_state.get("investment_active_tab"), "Health")
        self.assertTrue(st.session_state.get("some_portfolio_flag"))
        self.assertEqual(snapshot.get("investment_active_tab"), "Health")

    def test_logout_uses_suite_key_and_calls_logout(self) -> None:
        st = self._make_st({"_suite_auth_session": True})
        st.button.side_effect = lambda *a, **k: k.get("key") == "suite_account_workspace_logout_btn"
        logout = MagicMock()
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=True),
            patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
            patch("suite_auth.logout", logout),
            patch(
                "suite_command_center_link.command_center_url",
                return_value="https://cc.example/",
            ),
            patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        logout.assert_called_once()
        st.rerun.assert_called_once()
        logout_keys = [
            c.kwargs.get("key")
            for c in st.button.call_args_list
            if c.kwargs.get("key") == "suite_account_workspace_logout_btn"
        ]
        self.assertEqual(len(logout_keys), 1)

    def test_saved_sessions_confirm_pending_survives_rerender(self) -> None:
        """Reset confirm flag is session-keyed so a Streamlit rerun keeps the prompt."""
        from suite_user_persistence import reset_confirm_session_key

        app_id = "investment"
        confirm_key = reset_confirm_session_key(app_id)
        session = {"_suite_auth_session": True, confirm_key: True}
        st = self._make_st(session)
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=True),
            patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
            patch(
                "suite_command_center_link.command_center_url",
                return_value="https://cc.example/",
            ),
            patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        self.assertTrue(st.session_state.get(confirm_key))
        st.warning.assert_called()
        yes_keys = [
            c.kwargs.get("key")
            for c in st.button.call_args_list
            if c.kwargs.get("key") == f"suite_reset_yes::{app_id}"
        ]
        self.assertEqual(len(yes_keys), 1)

    def test_unsigned_user_gets_auth_panel_not_expander(self) -> None:
        st = self._make_st()
        auth_panel = MagicMock()
        with (
            patch("suite_workspace.bootstrap_suite_workspace"),
            patch("suite_account_settings.init_suite_workspace"),
            patch(
                "suite_account_settings.build_account_settings_context",
                return_value=_ctx(),
            ),
            patch("suite_workspace.can_show_developer_tools", return_value=False),
            patch("suite_auth.is_auth_enabled", return_value=True),
            patch("suite_auth.is_authenticated", return_value=False),
            patch("suite_auth.render_auth_panel", auth_panel),
        ):
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

        auth_panel.assert_called_once()
        st.sidebar.expander.assert_not_called()
        st.link_button.assert_not_called()


if __name__ == "__main__":
    unittest.main()
