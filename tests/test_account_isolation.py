"""
Regression tests: every signed-in account has fully independent saved data.

Runs the real identity, workspace, disk and cloud code against an in-memory fake of the
Supabase REST API that keeps the production table keys, including the one that caused
silent overwrites: ``suite_app_current_state`` is keyed by ``app`` alone, so a plain
upsert by a second account replaces the first account's row.

Sessions are a ``MutableMapping`` that is *not* a ``dict``, like Streamlit's
``SessionStateProxy``. Code that only accepted ``dict`` sessions skipped every
ownership check in the deployed app and put every account on the ``daniel`` workspace.
"""

from __future__ import annotations

import copy
import itertools
import os
import tempfile
import unittest
import uuid
from collections.abc import MutableMapping
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

APP = "investment"
COAKLEY_EMAIL = "coakley11@example.com"
DANIEL_EMAIL = "daniel.cohen11@example.com"


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------


class ProxySession(MutableMapping):
    """Mapping-only session, like ``streamlit.runtime.state.SessionStateProxy``."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._d: dict[str, Any] = dict(initial or {})

    def __getitem__(self, key: str) -> Any:
        return self._d[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._d[key] = value

    def __delitem__(self, key: str) -> None:
        del self._d[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)


class _Conflict(RuntimeError):
    pass


class FakeSupabase:
    """Minimal PostgREST over in-memory tables, with the production keys."""

    # Conflict target used by a plain upsert (no ``on_conflict``): the primary key.
    PRIMARY_KEYS = {
        "suite_users": ("id",),
        "suite_app_current_state": ("app",),  # production today: app alone
        "suite_user_settings": ("user_id", "app"),
        "suite_saved_items": ("id",),
        "suite_activity_events": ("id",),
        "suite_resume_items": ("id",),
    }
    UNIQUE = {
        "suite_users": [("external_id",)],
        "suite_saved_items": [("user_id", "app", "item_type", "item_key")],
        "suite_resume_items": [("user_id", "app", "item_key")],
    }

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {t: [] for t in self.PRIMARY_KEYS}
        self._ids = itertools.count(1)
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    # -- filters -----------------------------------------------------------------------
    @staticmethod
    def _match_one(row: dict[str, Any], col: str, expr: str) -> bool:
        val = row.get(col)
        if expr.startswith("eq."):
            return val is not None and str(val) == expr[3:]
        if expr == "is.null":
            return val is None
        if expr.startswith("in.(") and expr.endswith(")"):
            return str(val) in expr[4:-1].split(",")
        raise AssertionError(f"unsupported filter {col}={expr}")

    def _matches(self, row: dict[str, Any], params: dict[str, str]) -> bool:
        for key, expr in params.items():
            if key in ("select", "limit", "order", "on_conflict"):
                continue
            if key == "or":
                parts = expr.strip("()").split(",")
                ok = False
                for part in parts:
                    col, rest = part.split(".", 1)
                    if self._match_one(row, col, rest):
                        ok = True
                if not ok:
                    return False
                continue
            if not self._match_one(row, key, expr):
                return False
        return True

    def _select(self, rows: list[dict[str, Any]], params: dict[str, str]) -> list[dict[str, Any]]:
        out = [r for r in rows if self._matches(r, params)]
        if "limit" in params:
            out = out[: int(params["limit"])]
        cols = params.get("select", "*")
        if cols != "*":
            names = [c.strip() for c in cols.split(",")]
            out = [{n: r.get(n) for n in names} for r in out]
        return copy.deepcopy(out)

    # -- writes ------------------------------------------------------------------------
    def _defaults(self, table: str, body: dict[str, Any]) -> dict[str, Any]:
        row = dict(body)
        if table == "suite_users":
            row.setdefault("id", str(uuid.uuid4()))
        elif self.PRIMARY_KEYS[table] == ("id",):
            row.setdefault("id", next(self._ids))
        row.setdefault("user_id", None) if table != "suite_users" else None
        return row

    def _find(self, table: str, row: dict[str, Any], cols: tuple[str, ...]) -> dict[str, Any] | None:
        for existing in self.tables[table]:
            if all(existing.get(c) == row.get(c) for c in cols) and all(row.get(c) is not None for c in cols):
                return existing
        return None

    def _insert(self, table: str, body: dict[str, Any], *, prefer: str, on_conflict: str | None) -> dict[str, Any]:
        row = self._defaults(table, body)
        target = tuple(on_conflict.split(",")) if on_conflict else self.PRIMARY_KEYS[table]
        existing = self._find(table, row, target)
        if existing is not None:
            if "ignore-duplicates" in prefer:
                return existing
            if "merge-duplicates" in prefer:
                existing.update({k: v for k, v in body.items()})
                return existing
            raise _Conflict(f"Supabase POST {table} failed (409): duplicate key")
        for cols in self.UNIQUE.get(table, []) + [self.PRIMARY_KEYS[table]]:
            if self._find(table, row, cols) is not None:
                raise _Conflict(f"Supabase POST {table} failed (409): duplicate key value violates unique constraint")
        self.tables[table].append(row)
        return row

    def request(
        self,
        method: str,
        path: str,
        *,
        cfg: Any = None,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str = "return=minimal",
    ) -> Any:
        params = dict(params or {})
        table = str(path).split("/", 1)[0]
        method = method.upper()
        self.requests.append((method, table, params))
        if method == "GET":
            return self._select(self.tables[table], params)
        if method == "POST":
            row = self._insert(table, dict(json_body or {}), prefer=prefer, on_conflict=params.get("on_conflict"))
            return [copy.deepcopy(row)] if "representation" in prefer else None
        if method == "PATCH":
            for row in self.tables[table]:
                if self._matches(row, params):
                    row.update(dict(json_body or {}))
            return None
        raise AssertionError(method)

    # -- helpers -----------------------------------------------------------------------
    def user_id(self, external_id: str) -> str | None:
        for row in self.tables["suite_users"]:
            if row.get("external_id") == external_id:
                return str(row["id"])
        return None

    def state_rows(self, app_key: str) -> list[dict[str, Any]]:
        return [r for r in self.tables["suite_app_current_state"] if r.get("app") == app_key]


# --------------------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------------------


class _Browser:
    """One browser tab: its own Streamlit session state and URL query params."""

    def __init__(self) -> None:
        self.session_state = ProxySession()
        self.query_params: dict[str, str] = {}


class IsolationHarness(unittest.TestCase):
    def setUp(self) -> None:
        self._stack = ExitStack()
        self.addCleanup(self._stack.close)
        tmp = Path(self._stack.enter_context(tempfile.TemporaryDirectory()))
        self.data_dir = tmp
        self.cloud = FakeSupabase()
        self.current: _Browser | None = None
        self.auth_uids: dict[str, str] = {}

        cfg = SimpleNamespace(url="https://fake.supabase.local", key="service-key-not-real")
        p = self._stack.enter_context
        p(patch.dict(os.environ, {"SUITE_AUTH_ENABLED": "1"}, clear=False))
        os.environ.pop("SUITE_PROFILE_EMAILS", None)
        os.environ.pop("SUITE_USER_ID", None)
        p(patch("suite_storage_config.get_cloud_config", return_value=cfg))
        p(patch("suite_user.get_cloud_config", return_value=cfg))
        p(patch("suite_storage_supabase._request", side_effect=self.cloud.request))
        p(patch("suite_auth._configured_profile_emails", return_value={}, create=True))
        # Disk: everything under a temp data dir (shared by all "browsers": one server).
        p(patch("suite_workspace.DATA_DIR", tmp))
        p(patch("suite_workspace._PERSISTED_FILE", tmp / "suite_active_workspace.json"))
        p(patch("suite_workspace_registry.DATA_DIR", tmp))
        p(patch("suite_workspace_registry.REGISTRY_FILE", tmp / "workspaces" / "_ownership_registry.json"))
        p(patch("suite_workspace_registry.ACTIVE_DIR", tmp / "workspaces" / "_active"))
        p(patch("suite_user_persistence.DATA_DIR", tmp))
        p(patch("suite_user_persistence._LEGACY_COMBINED_FILE", tmp / "app_state.json"))
        p(patch("suite_auth_browser.save_browser_auth_tokens"))
        # The "current" browser is whichever this test is acting in.
        import streamlit

        self._st_session_patch = p(patch.object(streamlit, "session_state", ProxySession()))
        from suite_user import reset_account_cache

        reset_account_cache()
        self.addCleanup(reset_account_cache)

    # -- browser / auth ----------------------------------------------------------------
    @contextmanager
    def acting_in(self, browser: _Browser) -> Iterator[_Browser]:
        import streamlit

        prev = self.current
        with patch.object(streamlit, "session_state", browser.session_state):
            self.current = browser
            try:
                yield browser
            finally:
                self.current = prev

    def auth_uid_for(self, email: str) -> str:
        return self.auth_uids.setdefault(email, str(uuid.uuid4()))

    def sign_in(self, browser: _Browser, email: str) -> None:
        """Sign-in as the app does: apply the Auth user, then bootstrap the workspace."""
        from suite_auth import _apply_authenticated_user, enforce_workspace_ownership
        from suite_workspace import init_suite_workspace

        user = {"id": self.auth_uid_for(email), "email": email}
        tokens = {"access_token": f"a-{email}", "refresh_token": f"r-{email}", "expires_at": 0}
        with self.acting_in(browser):
            _apply_authenticated_user(browser.session_state, user, tokens=tokens)
            enforce_workspace_ownership(browser.session_state)
            init_suite_workspace(browser)

    def refresh(self, browser: _Browser) -> _Browser:
        """Browser refresh / restart: a new Streamlit session restored from the Auth tokens."""
        email = str(browser.session_state.get("_suite_auth_user_email") or "")
        fresh = _Browser()
        fresh.query_params = dict(browser.query_params)
        self.sign_in(fresh, email)
        return fresh

    def log_out(self, browser: _Browser) -> None:
        from suite_auth import logout

        with self.acting_in(browser):
            with patch("suite_auth._auth_api", side_effect=RuntimeError("offline")):
                logout(browser.session_state, st=None)

    # -- app persistence (the same calls the Investment app makes) ----------------------
    def save_portfolio(self, browser: _Browser, state: dict[str, Any]) -> tuple[bool, bool]:
        from suite_cloud_state import save_cloud_full_session
        from suite_user_persistence import save_user_state

        with self.acting_in(browser):
            disk_ok = save_user_state(APP, state)
            cloud_ok = save_cloud_full_session(APP, state, summary="Last session")
        return disk_ok, cloud_ok

    def load_portfolio(self, browser: _Browser) -> tuple[dict[str, Any], dict[str, Any]]:
        from suite_cloud_state import load_cloud_full_session
        from suite_user_persistence import load_user_state

        with self.acting_in(browser):
            disk, _ = load_user_state(APP)
            cloud, _ = load_cloud_full_session(APP, force=True)
        return disk, cloud

    def active_workspace(self, browser: _Browser) -> str:
        from suite_workspace import get_active_workspace_id

        with self.acting_in(browser):
            return get_active_workspace_id(browser)

    def account_id(self, browser: _Browser) -> str:
        from suite_user import get_account_user_id

        with self.acting_in(browser):
            return get_account_user_id()


def _portfolio(tag: str, *, transactions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "portfolio_built": True,
        "holdings_fingerprint": f"fp-{tag}",
        "holdings_df": [{"Ticker": "VTI" if tag == "coakley" else "BND", "Dollars": 1.0}],
        "portfolio_transactions": list(transactions or []),
        "owner_tag": tag,
    }


# --------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------


class TestIdentityResolution(IsolationHarness):
    def test_named_accounts_keep_their_existing_profiles(self) -> None:
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        self.assertEqual(a.session_state["_suite_auth_external_id"], "coakley11")
        self.assertEqual(b.session_state["_suite_auth_external_id"], "daniel")
        self.assertNotEqual(self.account_id(a), self.account_id(b))
        self.assertEqual(self.account_id(a), self.cloud.user_id("coakley11"))
        self.assertEqual(self.account_id(b), self.cloud.user_id("daniel"))

    def test_account_id_is_not_shared_across_sessions_on_one_process(self) -> None:
        """The old ``lru_cache(maxsize=1)`` returned the first account to every session."""
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        first = self.account_id(a)
        self.sign_in(b, DANIEL_EMAIL)
        for _ in range(3):
            self.assertEqual(self.account_id(a), first)
            self.assertNotEqual(self.account_id(b), first)

    def test_email_substrings_never_map_to_preset_profiles(self) -> None:
        for email in ("danielle@example.com", "mydaniel@example.com", "mariel@example.com", "x@daniel.example"):
            br = _Browser()
            self.sign_in(br, email)
            ext = br.session_state["_suite_auth_external_id"]
            self.assertNotIn(ext, ("daniel", "ariel"), email)

    def test_protected_local_parts_get_their_own_profile(self) -> None:
        br = _Browser()
        self.sign_in(br, "daniel@other.example")
        self.assertEqual(br.session_state["_suite_auth_external_id"], "user_daniel")
        br2 = _Browser()
        self.sign_in(br2, "guest@other.example")
        self.assertEqual(br2.session_state["_suite_auth_external_id"], "user_guest")

    def test_second_auth_user_cannot_claim_a_bound_profile(self) -> None:
        owner = _Browser()
        self.sign_in(owner, DANIEL_EMAIL)
        impostor = _Browser()
        self.sign_in(impostor, "daniel.cohen11@lookalike.example")  # same local part
        ext = impostor.session_state["_suite_auth_external_id"]
        self.assertNotEqual(ext, "daniel")
        self.assertTrue(ext.startswith("daniel_"))
        self.assertNotEqual(self.account_id(impostor), self.account_id(owner))

    def test_same_local_part_new_users_do_not_share(self) -> None:
        a, b = _Browser(), _Browser()
        self.sign_in(a, "sam@one.example")
        self.sign_in(b, "sam@two.example")
        self.assertEqual(a.session_state["_suite_auth_external_id"], "sam")
        self.assertNotEqual(b.session_state["_suite_auth_external_id"], "sam")
        self.assertNotEqual(self.account_id(a), self.account_id(b))

    def test_profile_emails_for_other_addresses_do_not_move_existing_accounts(self) -> None:
        with patch("suite_auth._configured_profile_emails", return_value={"ariel@example.com": "ariel"}):
            a, b, c = _Browser(), _Browser(), _Browser()
            self.sign_in(a, COAKLEY_EMAIL)
            self.sign_in(b, DANIEL_EMAIL)
            self.sign_in(c, "ariel@example.com")
        self.assertEqual(a.session_state["_suite_auth_external_id"], "coakley11")
        self.assertEqual(b.session_state["_suite_auth_external_id"], "daniel")
        self.assertEqual(c.session_state["_suite_auth_external_id"], "ariel")

    def test_signed_out_session_has_no_account(self) -> None:
        br = _Browser()
        self.assertEqual(self.account_id(br), "")
        from suite_user import get_external_user_id

        with self.acting_in(br):
            with patch.dict(os.environ, {"SUITE_USER_ID": "daniel"}):
                self.assertEqual(get_external_user_id(), "")


class TestWorkspaceOwnership(IsolationHarness):
    def test_proxy_session_gets_its_own_workspace(self) -> None:
        """Root cause: with a non-dict session every account was clamped to ``daniel``."""
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.assertEqual(self.active_workspace(a), "coakley11")
        b = _Browser()
        self.sign_in(b, DANIEL_EMAIL)
        self.assertEqual(self.active_workspace(b), "daniel")

    def test_coakley_admin_cannot_open_daniels_workspace(self) -> None:
        from suite_auth import allowed_workspaces_for_session
        from suite_workspace import set_active_workspace_id
        from suite_workspace_registry import workspace_access_allowed

        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        with self.acting_in(a):
            self.assertNotIn("daniel", allowed_workspaces_for_session(a.session_state))
            self.assertFalse(workspace_access_allowed("daniel", session_state=a.session_state))
            self.assertEqual(set_active_workspace_id(a, "daniel"), "coakley11")
        b = _Browser()
        self.sign_in(b, DANIEL_EMAIL)
        with self.acting_in(b):
            self.assertIn("daniel", allowed_workspaces_for_session(b.session_state))

    def test_foreign_workspace_query_param_is_ignored(self) -> None:
        a = _Browser()
        a.query_params = {"suite_workspace": "daniel"}
        self.sign_in(a, COAKLEY_EMAIL)
        self.assertEqual(self.active_workspace(a), "coakley11")

    def test_stale_registry_row_is_superseded(self) -> None:
        import json

        uid = self.auth_uid_for(COAKLEY_EMAIL)
        reg = self.data_dir / "workspaces" / "_ownership_registry.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(
            json.dumps({"by_owner": {uid: {"owner_user_id": uid, "workspace_id": "daniel", "label": "Daniel"}}}),
            encoding="utf-8",
        )
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.assertEqual(self.active_workspace(a), "coakley11")
        record = json.loads(reg.read_text(encoding="utf-8"))["by_owner"][uid]
        self.assertEqual(record["workspace_id"], "coakley11")
        self.assertEqual(record["superseded_workspace_id"], "daniel")


class TestIndependentPortfolios(IsolationHarness):
    def _two_accounts(self) -> tuple[_Browser, _Browser]:
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        return a, b

    def test_each_account_saves_and_sees_only_its_own_portfolio(self) -> None:
        a, b = self._two_accounts()
        self.assertEqual(self.save_portfolio(a, _portfolio("coakley")), (True, True))
        self.assertEqual(self.save_portfolio(b, _portfolio("daniel")), (True, True))
        disk_a, cloud_a = self.load_portfolio(a)
        disk_b, cloud_b = self.load_portfolio(b)
        self.assertEqual(disk_a["owner_tag"], "coakley")
        self.assertEqual(cloud_a["owner_tag"], "coakley")
        self.assertEqual(disk_b["owner_tag"], "daniel")
        self.assertEqual(cloud_b["owner_tag"], "daniel")

    def test_transaction_in_one_account_is_absent_from_the_other(self) -> None:
        a, b = self._two_accounts()
        self.save_portfolio(b, _portfolio("daniel"))
        txn = {"date": "2026-11-18", "type": "deposit", "amount": 1.0, "ticker": "VTI", "broker": "Fidelity"}
        self.save_portfolio(a, _portfolio("coakley", transactions=[txn]))
        disk_b, cloud_b = self.load_portfolio(b)
        self.assertEqual(disk_b["portfolio_transactions"], [])
        self.assertEqual(cloud_b["portfolio_transactions"], [])
        disk_a, cloud_a = self.load_portfolio(a)
        self.assertEqual(cloud_a["portfolio_transactions"], [txn])

    def test_disk_files_are_per_account_even_for_the_same_workspace_slug(self) -> None:
        """Both admins may use the demo ``guest`` workspace; it is a sandbox per account."""
        from suite_workspace import set_active_workspace_id
        from suite_user_persistence import state_file_path

        a, b = self._two_accounts()
        with self.acting_in(a):
            set_active_workspace_id(a, "guest")
            path_a = state_file_path(APP)
        with self.acting_in(b):
            set_active_workspace_id(b, "guest")
            path_b = state_file_path(APP)
        self.assertNotEqual(path_a, path_b)
        from suite_user_persistence import load_user_state, save_user_state

        with self.acting_in(a):
            save_user_state(APP, _portfolio("coakley"))
        with self.acting_in(b):
            self.assertEqual(load_user_state(APP)[0], {})

    def test_cloud_row_of_another_account_is_never_taken_over(self) -> None:
        """With the key on ``app`` alone, a second account's upsert replaced the first's row."""
        from suite_storage_supabase import AccountScopeError, save_current_state
        from suite_workspace import scoped_cloud_app_id

        a, b = self._two_accounts()
        self.save_portfolio(b, _portfolio("daniel"))
        self.assertEqual(scoped_cloud_app_id(APP, "daniel"), "investment")
        with self.acting_in(a):
            # Normal path: coakley11's key is its own.
            self.assertEqual(scoped_cloud_app_id(APP), "investment__coakley11")
            # The deployed bug's state: coakley11's session sitting on workspace ``daniel``.
            a.session_state["_suite_active_workspace_id"] = "daniel"
            with self.assertRaises(AccountScopeError):
                save_current_state(APP, summary="x", metrics={"full_session": _portfolio("coakley")})
            self.assertFalse(self.save_portfolio(a, _portfolio("coakley"))[1])
            # Reads are filtered by account, so daniel's row is not visible either.
            self.assertEqual(self.load_portfolio(a)[1], {})
        rows = self.cloud.state_rows("investment")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_id"], self.cloud.user_id("daniel"))
        self.assertEqual(rows[0]["metrics"]["full_session"]["owner_tag"], "daniel")

    def test_demo_workspace_collision_refuses_instead_of_overwriting(self) -> None:
        from suite_workspace import set_active_workspace_id

        a, b = self._two_accounts()
        with self.acting_in(b):
            set_active_workspace_id(b, "guest")
        with self.acting_in(a):
            set_active_workspace_id(a, "guest")
        self.assertEqual(self.save_portfolio(b, _portfolio("daniel")), (True, True))
        disk_ok, cloud_ok = self.save_portfolio(a, _portfolio("coakley"))
        self.assertTrue(disk_ok)
        self.assertFalse(cloud_ok)  # refused: row investment__guest belongs to daniel
        _, cloud_b = self.load_portfolio(b)
        self.assertEqual(cloud_b["owner_tag"], "daniel")
        _, cloud_a = self.load_portfolio(a)
        self.assertEqual(cloud_a, {})

    def test_new_account_starts_empty(self) -> None:
        a, b = self._two_accounts()
        self.save_portfolio(a, _portfolio("coakley"))
        self.save_portfolio(b, _portfolio("daniel"))
        new = _Browser()
        self.sign_in(new, "brand.new@example.com")
        self.assertEqual(self.load_portfolio(new), ({}, {}))
        self.assertEqual(self.save_portfolio(new, _portfolio("new")), (True, True))
        self.assertEqual(self.load_portfolio(a)[1]["owner_tag"], "coakley")
        self.assertEqual(self.load_portfolio(b)[1]["owner_tag"], "daniel")

    def test_settings_and_saved_items_are_per_account(self) -> None:
        import suite_account

        a, b = self._two_accounts()
        with self.acting_in(a):
            suite_account.save_settings("_global", {"goal": "coakley-goal"})
            suite_account.remember_saved_item(APP, "analysis", "k1", title="Coakley analysis", payload={"x": 1})
        with self.acting_in(b):
            self.assertEqual(suite_account.load_settings("_global"), {})
            self.assertEqual(suite_account.load_saved_items(app=APP), [])
            suite_account.save_settings("_global", {"goal": "daniel-goal"})
        with self.acting_in(a):
            self.assertEqual(suite_account.load_settings("_global"), {"goal": "coakley-goal"})


class TestSessionLifecycle(IsolationHarness):
    def test_logout_then_login_as_other_account_in_same_browser(self) -> None:
        br = _Browser()
        self.sign_in(br, COAKLEY_EMAIL)
        self.save_portfolio(br, _portfolio("coakley"))
        br.session_state["portfolio_transactions"] = [{"amount": 1.0}]
        br.session_state["_suite_full_session_blob_investment"] = {"owner_tag": "coakley"}
        self.log_out(br)
        for key in (
            "portfolio_transactions",
            "_suite_full_session_blob_investment",
            "_suite_active_workspace_id",
            "_suite_owned_workspace_id",
            "_suite_auth_external_id",
        ):
            self.assertNotIn(key, br.session_state, key)
        self.assertEqual(self.load_portfolio(br), ({}, {}))  # signed out: nothing readable
        self.sign_in(br, DANIEL_EMAIL)
        self.assertEqual(self.active_workspace(br), "daniel")
        self.assertEqual(self.load_portfolio(br), ({}, {}))
        self.save_portfolio(br, _portfolio("daniel"))
        self.log_out(br)
        self.sign_in(br, COAKLEY_EMAIL)
        disk, cloud = self.load_portfolio(br)
        self.assertEqual((disk["owner_tag"], cloud["owner_tag"]), ("coakley", "coakley"))

    def test_login_as_other_account_without_logout_clears_previous_data(self) -> None:
        br = _Browser()
        self.sign_in(br, COAKLEY_EMAIL)
        br.session_state["holdings_df"] = "coakley-holdings"
        br.session_state["_suite_full_session_blob_investment"] = {"owner_tag": "coakley"}
        self.sign_in(br, DANIEL_EMAIL)
        self.assertNotIn("holdings_df", br.session_state)
        self.assertNotIn("_suite_full_session_blob_investment", br.session_state)

    def test_refresh_and_browser_restart_restore_the_same_account(self) -> None:
        br = _Browser()
        self.sign_in(br, COAKLEY_EMAIL)
        self.save_portfolio(br, _portfolio("coakley"))
        restarted = self.refresh(br)
        self.assertEqual(self.active_workspace(restarted), "coakley11")
        disk, cloud = self.load_portfolio(restarted)
        self.assertEqual((disk["owner_tag"], cloud["owner_tag"]), ("coakley", "coakley"))

    def test_cloud_restore_on_new_server_disk(self) -> None:
        """Redeploy / new container: disk is empty, each account restores its own cloud row."""
        import shutil

        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        self.save_portfolio(a, _portfolio("coakley"))
        self.save_portfolio(b, _portfolio("daniel"))
        for child in self.data_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        a2, b2 = self.refresh(a), self.refresh(b)
        self.assertEqual(self.load_portfolio(a2), ({}, _portfolio("coakley")))
        self.assertEqual(self.load_portfolio(b2), ({}, _portfolio("daniel")))

    def test_simultaneous_sessions_interleaved(self) -> None:
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        for i in range(4):
            self.save_portfolio(a, _portfolio("coakley", transactions=[{"n": i}]))
            self.save_portfolio(b, _portfolio("daniel", transactions=[{"n": -i}]))
            self.assertEqual(self.load_portfolio(a)[1]["portfolio_transactions"], [{"n": i}])
            self.assertEqual(self.load_portfolio(b)[1]["portfolio_transactions"], [{"n": -i}])

    def test_restore_once_picks_only_this_accounts_state(self) -> None:
        from suite_user_persistence import restore_once

        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        self.save_portfolio(a, _portfolio("coakley"))
        fresh_b = self.refresh(b)
        applied: list[dict[str, Any]] = []
        with self.acting_in(fresh_b):
            restore_once(fresh_b, APP, apply_state=lambda _st, s: applied.append(dict(s)))
        self.assertTrue(all(s.get("owner_tag") != "coakley" for s in applied))


class TestAdminAuthorization(IsolationHarness):
    def _is_admin(self, browser: _Browser) -> bool:
        from suite_workspace_registry import is_admin_user

        with self.acting_in(browser):
            return is_admin_user(session_state=browser.session_state)

    def test_the_two_owner_accounts_are_admin(self) -> None:
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        self.assertTrue(self._is_admin(a))
        self.assertTrue(self._is_admin(b))

    def test_same_local_part_at_another_domain_is_not_admin(self) -> None:
        real = _Browser()
        self.sign_in(real, COAKLEY_EMAIL)
        impostor = _Browser()
        self.sign_in(impostor, "coakley11@lookalike.example")
        self.assertNotEqual(impostor.session_state["_suite_auth_external_id"], "coakley11")
        self.assertFalse(self._is_admin(impostor))
        self.assertTrue(self._is_admin(real))

    def test_email_containing_admin_names_is_not_admin(self) -> None:
        for email in ("daniel@example.com", "danielle@example.com", "x.coakley11@example.com"):
            br = _Browser()
            self.sign_in(br, email)
            self.assertFalse(self._is_admin(br), email)

    def test_forged_session_external_id_without_matching_email_is_not_admin(self) -> None:
        br = _Browser()
        self.sign_in(br, "someone@example.com")
        br.session_state["_suite_auth_external_id"] = "coakley11"
        self.assertFalse(self._is_admin(br))

    def test_configured_admin_emails_is_an_exact_allow_list(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        with patch.dict(os.environ, {"SUITE_ADMIN_EMAILS": DANIEL_EMAIL}):
            self.assertFalse(self._is_admin(a))
        with patch.dict(os.environ, {"SUITE_ADMIN_EMAILS": f"{DANIEL_EMAIL}, {COAKLEY_EMAIL.upper()}"}):
            self.assertTrue(self._is_admin(a))

    def test_binding_falls_back_when_on_conflict_is_unsupported(self) -> None:
        real_request = self.cloud.request

        def no_on_conflict(method: str, path: str, **kw: Any) -> Any:
            if method == "POST" and path == "suite_user_settings" and (kw.get("params") or {}).get("on_conflict"):
                raise RuntimeError(
                    "Supabase POST suite_user_settings failed (400): {\"code\":\"42P10\",\"message\":"
                    "\"there is no unique or exclusion constraint matching the ON CONFLICT specification\"}"
                )
            return real_request(method, path, **kw)

        with patch("suite_storage_supabase._request", side_effect=no_on_conflict):
            a = _Browser()
            self.sign_in(a, COAKLEY_EMAIL)
            self.assertEqual(a.session_state["_suite_auth_external_id"], "coakley11")
            impostor = _Browser()
            self.sign_in(impostor, "coakley11@lookalike.example")
            self.assertNotEqual(impostor.session_state["_suite_auth_external_id"], "coakley11")


class TestUnauthorizedAccess(IsolationHarness):
    def test_signed_out_session_cannot_read_or_write_any_account(self) -> None:
        from suite_storage_supabase import AccountScopeError, load_current_states, save_current_state

        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.save_portfolio(a, _portfolio("coakley"))
        anon = _Browser()
        with self.acting_in(anon):
            self.assertEqual(load_current_states(include_metrics=True), {})
            with self.assertRaises(AccountScopeError):
                save_current_state(APP, summary="x", metrics={"full_session": {"evil": True}})
        self.assertEqual(self.load_portfolio(anon), ({}, {}))
        self.assertEqual(self.save_portfolio(anon, {"evil": True}), (False, False))
        self.assertEqual(self.load_portfolio(a)[1]["owner_tag"], "coakley")

    def test_signed_out_session_never_writes_the_global_workspace_file(self) -> None:
        from suite_workspace import init_suite_workspace

        anon = _Browser()
        with self.acting_in(anon):
            init_suite_workspace(anon)
        self.assertFalse((self.data_dir / "suite_active_workspace.json").exists())
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.assertFalse((self.data_dir / "suite_active_workspace.json").exists())

    def test_ownerless_legacy_rows_are_not_shown_to_any_account(self) -> None:
        from suite_storage_supabase import AccountScopeError, load_events, save_current_state

        self.cloud.tables["suite_activity_events"].append(
            {"id": 999, "app": "investment__coakley11", "event": "legacy", "page": "", "timestamp": "2026-06-01T00:00:00", "metrics": {}, "user_id": None}
        )
        self.cloud.tables["suite_app_current_state"].append(
            {"app": "investment__coakley11", "page": "", "summary": "legacy", "metrics": {"full_session": {"legacy": True}}, "user_id": None}
        )
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        with self.acting_in(a):
            self.assertEqual([e for e in load_events() if e["event"] == "legacy"], [])
            with self.assertRaises(AccountScopeError):
                save_current_state(APP, summary="x", metrics={"full_session": {"mine": True}})
        self.assertEqual(self.cloud.state_rows("investment__coakley11")[0]["summary"], "legacy")

    def test_auth_gate_error_fails_closed(self) -> None:
        from suite_app_shell import apply_suite_auth_gate

        st = MagicMock()
        st.session_state = ProxySession()
        st.stop.side_effect = SystemExit("stopped")
        with patch("suite_auth.render_auth_gate", side_effect=RuntimeError("supabase down")):
            with self.assertRaises(SystemExit):
                apply_suite_auth_gate(st)
        st.stop.assert_called_once()

    def test_every_state_read_filters_by_account(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.save_portfolio(a, _portfolio("coakley"))
        self.load_portfolio(a)
        uid = self.account_id(a)
        reads = [
            params
            for method, table, params in self.cloud.requests
            if method == "GET" and table == "suite_app_current_state" and params.get("select") != "user_id"
        ]
        self.assertTrue(reads)
        for params in reads:
            self.assertEqual(params.get("user_id"), f"eq.{uid}", params)


if __name__ == "__main__":
    unittest.main()
