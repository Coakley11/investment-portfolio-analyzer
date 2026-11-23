"""Security hotfix 2026-11-23: a copied ``suite_sid`` URL can never restore a sign-in or reach stored tokens."""

from __future__ import annotations

import unittest
from unittest import mock

import suite_auth_browser as sab
import suite_storage_supabase as ss


def _st(query=None, session=None):
    st = mock.Mock()
    st.query_params = dict(query or {})
    st.session_state = dict(session or {})
    return st


class SuiteSidDisabledTests(unittest.TestCase):
    def test_flag_is_off(self):
        self.assertFalse(sab.url_auth_restore_enabled())

    def test_copied_url_never_loads_tokens_and_is_revoked(self):
        st = _st({"suite_sid": "copied-sid"})
        with mock.patch("suite_storage_supabase.load_browser_auth_session") as load, \
                mock.patch("suite_storage_supabase.invalidate_browser_auth_session") as inv:
            self.assertIsNone(sab.load_browser_auth_tokens(st))
        load.assert_not_called()
        inv.assert_called_once_with("copied-sid")
        self.assertNotIn("suite_sid", st.query_params)
        self.assertNotIn(sab.SESSION_STATE_SID_KEY, st.session_state)

    def test_left_over_session_sid_is_ignored(self):
        st = _st({}, {sab.SESSION_STATE_SID_KEY: "left-over"})
        with mock.patch("suite_storage_supabase.load_browser_auth_session") as load:
            self.assertIsNone(sab.load_browser_auth_tokens(st))
        load.assert_not_called()

    def test_sign_in_never_writes_tokens_or_sets_a_url_id(self):
        st = _st({})
        with mock.patch("suite_storage_supabase.save_browser_auth_session") as save:
            sab.save_browser_auth_tokens(st, {"access_token": "a", "refresh_token": "r"}, auth_user_id="u")
        save.assert_not_called()
        self.assertNotIn("suite_sid", st.query_params)

    def test_revocation_runs_once_per_session(self):
        st = _st({"suite_sid": "s1"})
        with mock.patch("suite_storage_supabase.invalidate_browser_auth_session") as inv:
            sab.strip_url_auth_param(st)
            st.query_params["suite_sid"] = "s1"
            sab.strip_url_auth_param(st)
        self.assertEqual(inv.call_count, 1)

    def test_storage_layer_refuses_bridge_reads_and_writes(self):
        with mock.patch.object(ss, "_request") as req:
            self.assertIsNone(ss.load_browser_auth_session("sid"))
            ss.save_browser_auth_session("sid", user_id="u", tokens={"access_token": "a", "refresh_token": "r"})
        req.assert_not_called()

    def test_invalidation_erases_stored_tokens(self):
        with mock.patch.object(ss, "_request") as req:
            ss.invalidate_browser_auth_session("sid")
        body = req.call_args.kwargs["json_body"]
        self.assertFalse(body["valid"])
        self.assertNotIn("access_token", body["payload"])
        self.assertNotIn("refresh_token", body["payload"])


if __name__ == "__main__":
    unittest.main()
