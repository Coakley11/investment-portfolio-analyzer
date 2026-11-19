"""
Investment → Command Center: meaningful activity, real vs planning, no duplicates, Continue.

Runs the real activity, storage and resume code against the fake Supabase from
``test_account_isolation`` (production keys: resume items unique per
(user_id, app, item_key) behind a generated id). Test data only, two signed-in accounts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_account_isolation import COAKLEY_EMAIL, DANIEL_EMAIL, IsolationHarness, _Browser  # noqa: E402

import portfolio_engine as pe  # noqa: E402


def _txn(action: str, *, ticker: str = "", qty: float, price: float, date: str = "2026-11-18") -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action=action,  # type: ignore[arg-type]
        date=date,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        notes="test",
        company_name="Cash" if not ticker else ticker,
        asset_type="cash" if not ticker else "etf",
    )


class ActivityHarness(IsolationHarness):
    def events(self, browser: _Browser | None = None, app_like: str = "investment") -> list[dict[str, Any]]:
        rows = [r for r in self.cloud.tables["suite_activity_events"] if str(r.get("app", "")).startswith(app_like)]
        if browser is not None:
            uid = self.account_id(browser)
            rows = [r for r in rows if r.get("user_id") == uid]
        return rows

    def set_planning(self, browser: _Browser, weights: dict[str, float]) -> None:
        browser.session_state["holdings_df"] = pd.DataFrame(
            [{"Ticker": t, "Weight (%)": w, "Type": "ETF"} for t, w in weights.items()]
        )

    def call(self, browser: _Browser, fn: str, *args: Any, **kwargs: Any) -> Any:
        import investment_activity

        with self.acting_in(browser):
            return getattr(investment_activity, fn)(browser, *args, **kwargs)


class TestRealPortfolioActivity(ActivityHarness):
    def test_cash_deposit_and_first_vti_purchase(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        dep = _txn("cash_deposit", qty=1.0, price=1.0)
        self.call(a, "log_real_transaction_recorded", dep, transactions_after=[dep])
        buy = _txn("buy", ticker="VTI", qty=0.002, price=361.29)
        self.call(a, "log_real_transaction_recorded", buy, transactions_after=[dep, buy])
        ev = self.events(a)
        self.assertEqual([e["event"] for e in ev], ["real_cash_deposited", "real_investment_purchased"])
        d, b = ev[0]["metrics"], ev[1]["metrics"]
        self.assertEqual(d["portfolio_kind"], "real")
        self.assertEqual(d["amount"], 1.0)
        self.assertEqual(b["ticker"], "VTI")
        self.assertTrue(b["first_real_purchase"])
        self.assertAlmostEqual(b["amount"], 0.72, places=2)
        self.assertAlmostEqual(b["real_cash_balance"], 0.28, places=2)
        self.assertEqual(b["real_tickers"], ["VTI"])
        self.assertEqual(b["resume_page"], "My Portfolio")
        self.assertEqual(b["resume_subtab"], "Transactions")
        state = self.cloud.state_rows("investment__coakley11")[0]
        self.assertIn("Recorded first real VTI purchase — 0.002 shares at $361.29 ($0.72)", state["summary"])

    def test_real_events_never_carry_the_planning_portfolio(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.set_planning(a, {"VTI": 50, "VXUS": 50})
        buy = _txn("buy", ticker="VTI", qty=1, price=300)
        self.call(a, "log_real_transaction_recorded", buy, transactions_after=[buy])
        m = self.events(a)[0]["metrics"]
        self.assertEqual(m["portfolio_kind"], "real")
        self.assertNotIn("tickers", m)
        self.assertNotIn("weights", m)
        self.assertNotIn("holdings_fingerprint", m)

    def test_same_transaction_is_recorded_once_across_sessions(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        dep = _txn("cash_deposit", qty=1.0, price=1.0)
        for _ in range(3):
            self.call(a, "log_real_transaction_recorded", dep, transactions_after=[dep])
        restarted = self.refresh(a)  # new browser session / device
        self.call(restarted, "log_real_transaction_recorded", dep, transactions_after=[dep])
        self.assertEqual(len(self.events(a)), 1)

    def test_contribution_and_strategy_target(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.call(
            a,
            "log_real_contribution_recorded",
            application_id="app-1",
            amount=100.0,
            purchases=[{"ticker": "VTI", "shares": 0.27, "price": 361.0, "cost": 97.47}],
            transactions_after=[],
        )
        self.call(a, "log_real_contribution_recorded", application_id="app-1", amount=100.0, purchases=[], transactions_after=[])
        self.call(a, "log_real_strategy_target_saved", weights={"VTI": 100.0})
        names = [e["event"] for e in self.events(a)]
        self.assertEqual(names, ["real_contribution_recorded", "real_strategy_target_saved"])
        self.assertIn("100% VTI", self.cloud.state_rows("investment__coakley11")[0]["summary"])

    def test_activity_stays_in_its_own_account(self) -> None:
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        buy = _txn("buy", ticker="VTI", qty=0.002, price=361.29)
        self.call(a, "log_real_transaction_recorded", buy, transactions_after=[buy])
        self.assertEqual(len(self.events(a)), 1)
        self.assertEqual(self.events(b), [])
        from suite_storage_supabase import load_events

        with self.acting_in(b):
            self.assertEqual(load_events(), [])
        with self.acting_in(a):
            self.assertEqual([e["event"] for e in load_events()], ["real_investment_purchased"])


class TestPlanningActivity(ActivityHarness):
    def test_planning_change_is_one_confirmed_event_not_per_edit(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.set_planning(a, {"VTI": 40, "VXUS": 30, "VNQ": 15, "BND": 15})
        self.call(a, "note_planning_edit")  # first render: baseline only
        for w in ({"VTI": 60, "VXUS": 40}, {"VTI": 80, "VXUS": 20}, {"VTI": 100}):
            self.set_planning(a, w)
            self.call(a, "note_planning_edit")
        self.assertEqual(self.events(a), [])  # nothing per keystroke
        self.assertTrue(self.call(a, "flush_planning_change", reason="navigation"))
        self.assertFalse(self.call(a, "flush_planning_change", reason="navigation"))
        ev = self.events(a)
        self.assertEqual(len(ev), 1)
        m = ev[0]["metrics"]
        self.assertEqual(ev[0]["event"], "holdings_updated")
        self.assertEqual(m["portfolio_kind"], "planning")
        self.assertEqual(m["weights"], {"VTI": 100.0})
        self.assertEqual(m["removed"], ["BND", "VNQ", "VXUS"])
        summary = self.cloud.state_rows("investment__coakley11")[0]["summary"]
        self.assertEqual(summary, "Updated planning portfolio — 100% VTI (removed BND, VNQ, VXUS)")

    def test_editing_back_to_the_saved_allocation_logs_nothing(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.set_planning(a, {"VTI": 100})
        self.call(a, "note_planning_edit")
        self.set_planning(a, {"VTI": 50, "VXUS": 50})
        self.call(a, "note_planning_edit")
        self.set_planning(a, {"VTI": 100})
        self.call(a, "note_planning_edit")
        self.assertFalse(self.call(a, "flush_planning_change"))
        self.assertEqual(self.events(a), [])

    def test_analysis_runs_flush_the_plan_then_log_once_per_day(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.set_planning(a, {"VTI": 100})
        self.call(a, "note_planning_edit")
        self.set_planning(a, {"VTI": 60, "VXUS": 40})
        self.call(a, "note_planning_edit")
        self.call(a, "log_scenario_run", context="Monte Carlo", detail="Historical")
        self.call(a, "log_scenario_run", context="Monte Carlo", detail="Historical")
        self.call(a, "log_optimizer_run")
        self.call(a, "log_portfolio_health_checked", score=72.0, score_label="Good", tickers=["VTI", "VXUS"])
        names = [e["event"] for e in self.events(a)]
        self.assertEqual(names, ["holdings_updated", "scenario_run", "optimizer_run", "portfolio_health_checked"])
        for e in self.events(a):
            self.assertEqual(e["metrics"]["portfolio_kind"], "planning")


class TestStorageReliability(ActivityHarness):
    def test_repeated_resume_key_no_longer_drops_events(self) -> None:
        """Plain merge-duplicates on the id primary key made the 2nd write of a resume key 409."""
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        for i in range(3):
            dep = _txn("cash_deposit", qty=float(i + 1), price=1.0)
            self.call(a, "log_real_transaction_recorded", dep, transactions_after=[dep])
        self.assertEqual(len(self.events(a)), 3)
        resume = [r for r in self.cloud.tables["suite_resume_items"] if r.get("item_key") == "portfolio:resume"]
        self.assertEqual(len(resume), 1)

    def test_event_is_written_even_if_state_write_is_refused(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        uid_other = "someone-else"
        self.cloud.tables["suite_app_current_state"].append(
            {"app": "investment__coakley11", "user_id": uid_other, "page": "", "summary": "", "metrics": {}}
        )
        dep = _txn("cash_deposit", qty=1.0, price=1.0)
        self.call(a, "log_real_transaction_recorded", dep, transactions_after=[dep])
        self.assertEqual(len(self.events(a)), 1)
        self.assertEqual(self.cloud.state_rows("investment__coakley11")[0]["user_id"], uid_other)

    def test_timestamps_are_utc(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        dep = _txn("cash_deposit", qty=1.0, price=1.0)
        self.call(a, "log_real_transaction_recorded", dep, transactions_after=[dep])
        self.assertTrue(self.events(a)[0]["timestamp"].endswith("Z"))


class TestContinue(ActivityHarness):
    def _position(self, browser: _Browser, tab: str, **subtabs: str) -> None:
        browser.session_state["investment_active_tab"] = tab
        browser.session_state.update(subtabs)

    def _resume_row(self, browser: _Browser) -> dict[str, Any]:
        uid = self.account_id(browser)
        rows = [
            r
            for r in self.cloud.tables["suite_resume_items"]
            if r.get("item_key") == "portfolio:resume" and r.get("user_id") == uid
        ]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_my_portfolio_subtabs_become_continue_targets(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        for subtab in ("Transactions", "Positions", "Dashboard"):
            self._position(a, "My Portfolio", real_portfolio_subtab=subtab)
            self.assertTrue(self.call(a, "track_resume_position"))
            self.assertFalse(self.call(a, "track_resume_position"))  # unchanged: no write
            row = self._resume_row(a)
            q = parse_qs(urlparse(row["action_url"]).query)
            self.assertEqual(q["suite_page"], ["My Portfolio"])
            self.assertEqual(q["suite_subtab"], [subtab])
            self.assertEqual(q["suite_resume"], ["portfolio:resume"])
            self.assertEqual(row["title"], f"My Portfolio → {subtab}")
            self.assertTrue(row["subtitle"].startswith("Real portfolio:"))

    def test_beginner_label_and_planning_context(self) -> None:
        a = _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.set_planning(a, {"VTI": 60, "VXUS": 40})
        self._position(a, "⑨ Optimizer (Optional)")
        self.call(a, "track_resume_position")
        row = self._resume_row(a)
        q = parse_qs(urlparse(row["action_url"]).query)
        self.assertEqual(q["suite_page"], ["Optimization"])
        self.assertIn("60% VTI, 40% VXUS", row["subtitle"])

    def test_continue_link_reopens_page_and_subtab_in_either_mode(self) -> None:
        from suite_resume_launch import _apply_investment
        from investment_persistent_state import apply_suite_investment_resume

        for mode, expected_tab in (("Beginner", "⑪ My Portfolio"), ("Advanced", "My Portfolio")):
            br = _Browser()
            br.query_params = {"suite_subtab": "Positions"}
            with self.acting_in(br):
                _apply_investment(br, "portfolio:resume", "My Portfolio")
                with __import__("unittest.mock").mock.patch(
                    "investment_persistent_state.current_experience_mode",
                    return_value="Beginner" if mode == "Beginner" else "Advanced",
                ), __import__("unittest.mock").mock.patch(
                    "investment_persistent_state.EXPERIENCE_OPTIONS", ("Beginner", "Advanced")
                ):
                    apply_suite_investment_resume(br)
            self.assertEqual(br.session_state["investment_active_tab"], expected_tab, mode)
            self.assertEqual(br.session_state["real_portfolio_subtab"], "Positions", mode)

    def test_unknown_subtab_is_ignored(self) -> None:
        from investment_persistent_state import _apply_resume_subtab

        br = _Browser()
        _apply_resume_subtab(br, "My Portfolio", "Nonexistent")
        self.assertNotIn("real_portfolio_subtab", br.session_state)

    def test_continue_items_are_per_account(self) -> None:
        a, b = _Browser(), _Browser()
        self.sign_in(a, COAKLEY_EMAIL)
        self.sign_in(b, DANIEL_EMAIL)
        self._position(a, "My Portfolio", real_portfolio_subtab="Transactions")
        self._position(b, "Monte Carlo")
        self.call(a, "track_resume_position")
        self.call(b, "track_resume_position")
        self.assertEqual(self._resume_row(a)["title"], "My Portfolio → Transactions")
        self.assertEqual(self._resume_row(b)["title"], "Monte Carlo")
        from suite_storage_supabase import load_active_resume_items

        with self.acting_in(b):
            titles = [r["title"] for r in load_active_resume_items()]
        self.assertEqual(titles, ["Monte Carlo"])
