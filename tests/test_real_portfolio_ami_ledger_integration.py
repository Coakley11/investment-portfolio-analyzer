"""Integration: Real Portfolio tab ledger must reach AMI submit context."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import investment_persistent_state as ips
import portfolio_engine as pe
from applied_math_context import (
    build_investment_applied_math_context,
    real_portfolio_ami_ledger_diagnostics,
)
from investment_ami.decision_support.real_portfolio_advisor import run_real_portfolio_advisor
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot
from suite_analytical_question import build_submit_context


def _vti_bnd_txns() -> list[dict]:
    return [
        pe.PortfolioTransaction(
            id="t1",
            action="cash_deposit",
            date="2025-01-01",
            ticker="",
            quantity=27_220.0,
            execution_price=1.0,
        ).to_record(),
        pe.PortfolioTransaction(
            id="t2",
            action="buy",
            date="2025-01-02",
            ticker="VTI",
            quantity=25.0,
            execution_price=340.0,
            asset_type="etf",
        ).to_record(),
        pe.PortfolioTransaction(
            id="t3",
            action="buy",
            date="2025-01-03",
            ticker="BND",
            quantity=30.0,
            execution_price=74.0,
            asset_type="bond",
        ).to_record(),
    ]


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


class TestRealPortfolioTabToAmi(unittest.TestCase):
    """Test A — tab ledger → persist → navigate → AMI context."""

    def test_ami_context_includes_transactions_after_tab_edit(self) -> None:
        st = _FakeSt()
        st.session_state["portfolio_transactions"] = _vti_bnd_txns()
        st.session_state["_real_portfolio_ledger_touched"] = True
        self.assertEqual(len(st.session_state["portfolio_transactions"]), 3)

        with patch.object(ips, "autosave_investment_state") as autosave:
            autosave.side_effect = lambda st_obj, **kw: st_obj.session_state.update(
                {"_suite_inv_debug_last_autosave_event": {"outcome": "saved"}}
            )
            ok, _ = ips.persist_portfolio_transactions_after_change(st)
        self.assertTrue(ok)

        st.session_state["investment_active_tab"] = "Portfolio Health"
        ctx = build_investment_applied_math_context("Portfolio Health", st.session_state)
        self.assertEqual(len(ctx.get("portfolio_transactions") or []), 3)
        build = build_real_portfolio_snapshot(st.session_state, context=ctx, prices={"VTI": 368.21, "BND": 72.23})
        self.assertTrue(build.ok, build.failure.message if build.failure else "")

        _resp, payload = run_real_portfolio_advisor(ctx, question="How is my portfolio doing right now?")
        self.assertNotIn("no transaction-backed", payload["short_answer"].lower())


class TestHydrationAmiSubmit(unittest.TestCase):
    """Test B — persist, fresh session, hydrate, advisor."""

    def test_hydrated_session_reaches_advisor(self) -> None:
        blob = {
            ips.PORTFOLIO_TRANSACTIONS_KEY: _vti_bnd_txns(),
            ips.REAL_PORTFOLIO_LEDGER_META_KEY: {
                "schema_version": 1,
                "transaction_count": 3,
            },
        }
        st = _FakeSt()
        ips.apply_investment_disk_state(st, blob)
        ctx = build_investment_applied_math_context("Real Portfolio", st.session_state)
        self.assertEqual(len(ctx["portfolio_transactions"]), 3)
        _resp, payload = run_real_portfolio_advisor(
            ctx,
            question="How is my portfolio doing right now?",
        )
        self.assertNotIn("no transaction-backed", payload["short_answer"].lower())


class TestWorkspaceIsolationLedgerDiag(unittest.TestCase):
    """Test C — empty vs populated session (workspace-scoped persistence is disk-level)."""

    def test_empty_session_yields_no_ledger_in_advisor(self) -> None:
        st_b = _FakeSt(_suite_active_workspace_id="bob")
        ctx = build_investment_applied_math_context("Portfolio Health", st_b.session_state)
        _resp, payload = run_real_portfolio_advisor(ctx, question="How is my portfolio doing right now?")
        self.assertIn("no transaction-backed", payload["short_answer"].lower())

    def test_populated_session_yields_advisor(self) -> None:
        st_a = _FakeSt(
            portfolio_transactions=_vti_bnd_txns(),
            _suite_active_workspace_id="alice",
        )
        ctx = build_investment_applied_math_context("Real Portfolio", st_a.session_state)
        _resp, payload = run_real_portfolio_advisor(ctx, question="How is my portfolio doing right now?")
        self.assertNotIn("no transaction-backed", payload["short_answer"].lower())


class TestNoFalseNoLedger(unittest.TestCase):
    """Test D — positions in tab ⇒ advisor must not no_ledger."""

    def test_submit_context_pipeline(self) -> None:
        st = _FakeSt(portfolio_transactions=_vti_bnd_txns())
        st.session_state["investment_active_tab"] = "Real Portfolio"

        def _builder():
            return build_investment_applied_math_context("Real Portfolio", st.session_state)

        ctx = build_submit_context("investment", "Real Portfolio", st.session_state, context_extra_builder=_builder)
        self.assertEqual(len(ctx.get("portfolio_transactions") or []), 3)
        diag = real_portfolio_ami_ledger_diagnostics(st.session_state, ctx)
        self.assertEqual(diag["session_transaction_count"], 3)
        self.assertEqual(diag["ami_context_transaction_count"], 3)
        self.assertNotEqual(diag["snapshot_failure_code"], "no_real_ledger")


class TestDeployMarkerDiagnostics(unittest.TestCase):
    """Test E — deploy commit visible in ledger diagnostics."""

    def test_diagnostics_include_deploy_commit(self) -> None:
        st = _FakeSt(portfolio_transactions=_vti_bnd_txns())
        ctx = build_investment_applied_math_context("Real Portfolio", st.session_state)
        diag = real_portfolio_ami_ledger_diagnostics(st.session_state, ctx)
        self.assertIn("deploy_commit", diag)
        self.assertTrue(diag["deploy_commit"])


class TestAppliedMathContextRegression(unittest.TestCase):
    def test_context_without_merge_would_fail_snapshot(self) -> None:
        """Documents root cause: advisor passes context-only dict without session ledger."""
        ctx_before = {"page": "Real Portfolio"}
        fail = build_real_portfolio_snapshot({}, context=ctx_before, prices={"VTI": 368.21, "BND": 72.23})
        self.assertFalse(fail.ok)
        self.assertEqual(fail.failure.code if fail.failure else "", "no_real_ledger")
        ctx = build_investment_applied_math_context("Real Portfolio", {"portfolio_transactions": _vti_bnd_txns()})
        ok = build_real_portfolio_snapshot({}, context=ctx, prices={"VTI": 368.21, "BND": 72.23})
        self.assertTrue(ok.ok)


if __name__ == "__main__":
    unittest.main()
