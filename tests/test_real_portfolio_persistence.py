"""Regression tests for Real Portfolio transaction ledger persistence."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import investment_persistent_state as ips
import portfolio_engine as pe
from applied_math_context import build_investment_applied_math_context
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self, **session) -> None:
        self.session_state = _FakeSessionState(session)


def _sample_txn_records() -> list[dict]:
    return [
        {
            "id": "t-deposit",
            "action": "cash_deposit",
            "date": "2024-01-01",
            "ticker": "",
            "quantity": 10000.0,
            "execution_price": 1.0,
            "fees": 0.0,
            "notes": "",
        },
        {
            "id": "t-buy-spy",
            "action": "buy",
            "date": "2024-01-02",
            "ticker": "SPY",
            "quantity": 10.0,
            "execution_price": 400.0,
            "fees": 0.0,
            "notes": "",
        },
    ]


class RealPortfolioPersistenceTests(unittest.TestCase):
    def test_build_state_persists_empty_ledger_when_touched(self) -> None:
        st = _FakeSt(_real_portfolio_ledger_touched=True, portfolio_transactions=[])
        state = ips.build_investment_disk_state(st)
        self.assertEqual(state[ips.PORTFOLIO_TRANSACTIONS_KEY], [])
        meta = state[ips.REAL_PORTFOLIO_LEDGER_META_KEY]
        self.assertEqual(meta["schema_version"], ips.REAL_PORTFOLIO_LEDGER_SCHEMA_VERSION)
        self.assertEqual(meta["transaction_count"], 0)

    def test_build_state_persists_nonempty_ledger_with_meta(self) -> None:
        txns = _sample_txn_records()
        st = _FakeSt(portfolio_transactions=txns)
        state = ips.build_investment_disk_state(st)
        self.assertEqual(len(state[ips.PORTFOLIO_TRANSACTIONS_KEY]), 2)
        self.assertIn("updated_at", state[ips.REAL_PORTFOLIO_LEDGER_META_KEY])

    def test_build_state_omits_ledger_before_user_touches_real_portfolio(self) -> None:
        st = _FakeSt()
        state = ips.build_investment_disk_state(st)
        self.assertNotIn(ips.PORTFOLIO_TRANSACTIONS_KEY, state)

    def test_apply_restore_sets_ledger_flags(self) -> None:
        st = _FakeSt()
        txns = _sample_txn_records()
        ips.apply_investment_disk_state(
            st,
            {
                ips.PORTFOLIO_TRANSACTIONS_KEY: txns,
                ips.REAL_PORTFOLIO_LEDGER_META_KEY: {
                    "schema_version": 1,
                    "transaction_count": 2,
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            },
        )
        self.assertEqual(st.session_state[ips.PORTFOLIO_TRANSACTIONS_KEY], txns)
        self.assertTrue(st.session_state[ips.REAL_PORTFOLIO_LEDGER_RESTORED_FLAG])
        self.assertTrue(st.session_state[ips.REAL_PORTFOLIO_LEDGER_TOUCHED_KEY])

    def test_finalize_holdings_skips_default_when_ledger_saved(self) -> None:
        st = _FakeSt()
        ips._finalize_holdings_restore(
            st,
            {
                ips.PORTFOLIO_TRANSACTIONS_KEY: _sample_txn_records(),
                ips.REAL_PORTFOLIO_LEDGER_META_KEY: {"schema_version": 1, "transaction_count": 2},
            },
        )
        import pandas as pd

        df = st.session_state.get("holdings_df")
        self.assertIsInstance(df, pd.DataFrame)
        self.assertTrue(df.empty)
        self.assertFalse(st.session_state.get("default_holdings_applied"))

    def test_init_defaults_skipped_when_session_has_ledger(self) -> None:
        st = _FakeSt(portfolio_transactions=_sample_txn_records())
        ips.finalize_init_holdings_defaults(st)
        self.assertNotIn("default_holdings_applied", st.session_state)

    def test_clobber_guard_allows_ledger_save_with_empty_holdings(self) -> None:
        st = _FakeSt(default_holdings_applied=True)
        cloud = {
            "holdings_fingerprint": "BND:50.0:Bonds",
            "holdings_df": [{"Ticker": "BND", "Weight (%)": 50.0, "Asset Type": "Bonds"}],
        }
        payload = {
            ips.PORTFOLIO_TRANSACTIONS_KEY: _sample_txn_records(),
            ips.REAL_PORTFOLIO_LEDGER_META_KEY: {"schema_version": 1, "transaction_count": 2},
        }
        with patch.object(ips, "_cloud_has_saved_portfolio", return_value=(cloud, "ts")):
            blocked, _ = ips._autosave_would_clobber_saved_portfolio(st, payload)
        self.assertFalse(blocked)

    def test_clobber_guard_skipped_for_transaction_trigger(self) -> None:
        st = _FakeSt(default_holdings_applied=True)
        cloud = {"holdings_fingerprint": "x", "holdings_df": [{"Ticker": "SPY"}]}
        with patch.object(ips, "_cloud_has_saved_portfolio", return_value=(cloud, "ts")):
            blocked, _ = ips._autosave_would_clobber_saved_portfolio(
                st, {}, trigger="portfolio_transactions_change"
            )
        self.assertFalse(blocked)

    def test_migrate_legacy_blob_adds_meta_without_duplicating_txns(self) -> None:
        txns = _sample_txn_records()
        blob = {ips.PORTFOLIO_TRANSACTIONS_KEY: copy.deepcopy(txns)}
        out = ips._normalize_restored_state(blob)
        self.assertEqual(out[ips.PORTFOLIO_TRANSACTIONS_KEY], txns)
        self.assertEqual(out[ips.REAL_PORTFOLIO_LEDGER_META_KEY]["transaction_count"], 2)

    def test_hydrate_replay_cost_basis_and_ami_match(self) -> None:
        txns = _sample_txn_records()
        st = _FakeSt()
        ips.apply_investment_disk_state(st, {ips.PORTFOLIO_TRANSACTIONS_KEY: txns})
        prices = {"SPY": 450.0}
        result = build_real_portfolio_snapshot(st.session_state, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        snap = result.snapshot
        self.assertAlmostEqual(snap.cash, 6000.0, places=2)
        spy = next(h for h in snap.holdings if h.ticker == "SPY")
        self.assertAlmostEqual(spy.shares, 10.0)
        self.assertAlmostEqual(spy.average_cost, 400.0)
        ctx = build_investment_applied_math_context("Real Portfolio", st.session_state)
        real = ctx.get("real_portfolio") or {}
        self.assertAlmostEqual(real.get("cash_balance", 0.0), 6000.0, places=2)

    def test_autosave_persist_success_message(self) -> None:
        st = _FakeSt(
            portfolio_transactions=_sample_txn_records(),
            _real_portfolio_ledger_touched=True,
            _suite_inv_persistence_bootstrapped=True,
        )
        with patch.object(ips, "autosave_investment_state") as autosave_mock:
            autosave_mock.side_effect = lambda st_obj, **kw: st_obj.session_state.update(
                {
                    "_suite_inv_debug_last_autosave_event": {
                        "outcome": "saved",
                    }
                }
            )
            ok, msg = ips.persist_portfolio_transactions_after_change(st)
        self.assertTrue(ok)
        self.assertEqual(msg, "Changes saved.")

    def test_autosave_failure_surfaces_error(self) -> None:
        st = _FakeSt(
            portfolio_transactions=_sample_txn_records(),
            _real_portfolio_ledger_touched=True,
        )

        def _fail_save(st_obj, **kw):
            st_obj.session_state["_suite_inv_debug_last_autosave_event"] = {
                "outcome": "save_failed",
                "cloud_save_error": "network down",
            }

        with patch.object(ips, "autosave_investment_state", side_effect=_fail_save):
            ok, msg = ips.persist_portfolio_transactions_after_change(st)
        self.assertFalse(ok)
        self.assertIn("network down", msg)
        self.assertEqual(st.session_state[ips.REAL_PORTFOLIO_SAVE_STATUS_KEY], "error")

    def test_clear_auth_boundary_drops_ledger_and_bootstrap(self) -> None:
        ss = _FakeSessionState(
            portfolio_transactions=_sample_txn_records(),
            _suite_inv_persistence_bootstrapped=True,
            **{f"_suite_disk_state_restored::{ips.APP_ID}": True},
        )
        ips.clear_investment_session_for_auth_boundary(ss)
        self.assertNotIn("portfolio_transactions", ss)
        self.assertNotIn("_suite_inv_persistence_bootstrapped", ss)
        self.assertNotIn(f"_suite_disk_state_restored::{ips.APP_ID}", ss)

    def test_cloud_resync_detects_ledger_drift(self) -> None:
        st = _FakeSt(portfolio_transactions=[])
        cloud = {ips.PORTFOLIO_TRANSACTIONS_KEY: _sample_txn_records()}
        needed, detail = ips.investment_cloud_resync_needed(st, cloud)
        self.assertTrue(needed)
        self.assertIn(ips.PORTFOLIO_TRANSACTIONS_KEY, detail)

    def test_stable_ids_after_roundtrip(self) -> None:
        txns = _sample_txn_records()
        parsed = pe.transactions_from_records(txns)
        roundtrip = pe.transactions_to_records(parsed)
        self.assertEqual([t["id"] for t in txns], [t["id"] for t in roundtrip])


if __name__ == "__main__":
    unittest.main()
