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
        # Suite header (Music Practice Coach / Baseball Explorer); workspace lives inside.
        self.assertEqual(label, "Account & Workspace")
        captions = [str(c.args[0]) for c in st.caption.call_args_list if c.args]
        self.assertIn("Workspace: **Daniel**", captions)
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
        # The approved logo is the control: no heading, no text button.
        st.link_button.assert_not_called()
        markdowns = [str(c.args[0]) for c in st.markdown.call_args_list if c.args]
        self.assertNotIn("**Command Center**", markdowns)
        logo = [m for m in markdowns if 'class="bx-cc-logo"' in m]
        self.assertEqual(len(logo), 1)
        self.assertIn('href="https://cc.example/?suite_workspace=daniel"', logo[0])
        self.assertIn('target="_blank"', logo[0])
        self.assertIn('aria-label="Open Command Center"', logo[0])
        self.assertIn('title="Open Command Center"', logo[0])
        self.assertIn("data:image/png;base64,", logo[0])

    def _render_signed_in(self, st, *extra_patches):
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in (
                patch("suite_workspace.bootstrap_suite_workspace"),
                patch("suite_account_settings.init_suite_workspace"),
                patch("suite_account_settings.build_account_settings_context", return_value=_ctx()),
                patch("suite_workspace.can_show_developer_tools", return_value=False),
                patch("suite_auth.is_auth_enabled", return_value=True),
                patch("suite_auth.is_authenticated", return_value=True),
                patch("suite_auth.current_auth_email", return_value="daniel@example.com"),
                patch(
                    "suite_command_center_link.command_center_url",
                    return_value="https://cc.example/?suite_workspace=daniel",
                ),
                patch("suite_workspace.get_active_workspace_id", return_value="daniel"),
                *extra_patches,
            ):
                stack.enter_context(p)
            from investment_account_workspace import render_investment_account_workspace_control

            render_investment_account_workspace_control(st, on_reset=lambda _s: None)

    def test_command_center_falls_back_to_button_without_logo_asset(self) -> None:
        st = self._make_st({"_suite_auth_session": True})
        self._render_signed_in(st, patch("suite_brand_assets.brand_data_uri", return_value=""))
        st.link_button.assert_called_once()
        self.assertEqual(st.link_button.call_args[0][1], "https://cc.example/?suite_workspace=daniel")

    def test_logout_button_shows_logout_icon_and_reset_stays_distinct(self) -> None:
        st = self._make_st({"_suite_auth_session": True})
        st.button.return_value = False
        self._render_signed_in(st)
        logout_calls = [
            c for c in st.button.call_args_list if c.kwargs.get("key") == "suite_account_workspace_logout_btn"
        ]
        self.assertEqual(len(logout_calls), 1)
        self.assertEqual(logout_calls[0].args[0], "Log out")
        self.assertEqual(logout_calls[0].kwargs.get("icon"), ":material/logout:")
        reset_calls = [c for c in st.button.call_args_list if c.kwargs.get("key") == "suite_reset_btn::investment"]
        self.assertEqual(len(reset_calls), 1)
        self.assertEqual(reset_calls[0].args[0], "Reset to default")
        self.assertIsNone(reset_calls[0].kwargs.get("icon"))
        # Separate sections: a divider between Saved Sessions and Log out.
        self.assertGreaterEqual(st.divider.call_count, 2)

    def test_no_logout_or_trailing_divider_when_sign_in_is_off(self) -> None:
        st = self._make_st({})
        st.button.return_value = False
        self._render_signed_in(
            st,
            patch("investment_account_workspace._auth_session_active", return_value=False),
        )
        keys = [c.kwargs.get("key") for c in st.button.call_args_list]
        self.assertNotIn("suite_account_workspace_logout_btn", keys)

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
