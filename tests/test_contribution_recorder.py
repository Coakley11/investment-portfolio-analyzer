"""Contribution Advisor → ledger recorder (deposit + simulated buys)."""

from __future__ import annotations

import copy
import unittest

import portfolio_engine as pe

from investment_ami.decision_support.contribution_allocation_engine import (
    allocate_contribution_new_money_only,
)
from investment_ami.decision_support.contribution_recorder import (
    STATUS_ALREADY_APPLIED,
    STATUS_MISSING_QUOTES,
    STATUS_OK,
    STATUS_STALE,
    apply_contribution_plan_to_records,
    attach_application_metadata_to_payload,
    build_simulated_application_plan,
    event_already_applied,
    fingerprints_match,
    ledger_state_fingerprint,
    recommendation_fingerprint,
)
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


def _deposit(amount: float, *, day: str = "2024-01-01", txn_id: str = "dep") -> dict:
    return pe.PortfolioTransaction(
        id=txn_id,
        action="cash_deposit",
        date=day,
        ticker="",
        quantity=amount,
        execution_price=1.0,
        company_name="Cash",
        asset_type="cash",
    ).to_record()


def _buy(ticker: str, qty: float, price: float, *, day: str = "2024-01-02", txn_id: str = "") -> dict:
    return pe.PortfolioTransaction(
        id=txn_id or pe._new_id(),
        action="buy",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        company_name=ticker,
        asset_type="etf",
    ).to_record()


class TestContributionRecorder(unittest.TestCase):
    """Shadow-shaped $1,000 exact-reach case with simulated marks."""

    VALUES = {"BND": 1273.76, "VNQ": 420.92, "VTI": 1693.51, "VXUS": 853.91}
    TARGETS = {"BND": 30, "VNQ": 10, "VTI": 35, "VXUS": 25}
    # Marks used as simulated execution prices (distinct from current values).
    QUOTES = {"BND": 72.0, "VNQ": 88.0, "VTI": 250.0, "VXUS": 60.0}

    def _seed_ledger(self) -> list[dict]:
        # Cost basis equal to VALUES at $1/share for simple share counts.
        return [
            _deposit(sum(self.VALUES.values()), txn_id="seed_dep"),
            _buy("BND", self.VALUES["BND"], 1.0, txn_id="seed_bnd"),
            _buy("VNQ", self.VALUES["VNQ"], 1.0, txn_id="seed_vnq"),
            _buy("VTI", self.VALUES["VTI"], 1.0, txn_id="seed_vti"),
            _buy("VXUS", self.VALUES["VXUS"], 1.0, txn_id="seed_vxus"),
        ]

    def _recommendation(self):
        return allocate_contribution_new_money_only(
            current_values=self.VALUES,
            target_weights=self.TARGETS,
            contribution=1000.0,
        )

    def _plan(self, records: list[dict], rec):
        payload = attach_application_metadata_to_payload(
            rec.to_dict(),
            records=records,
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
            workspace_token="test-ws",
        )
        adds = {r["ticker"]: r["recommended_add"] for r in payload["rows"]}
        built = build_simulated_application_plan(
            application_id=payload["meta"]["application_id"],
            contribution_amount=1000.0,
            recommended_adds=adds,
            quotes=self.QUOTES,
            fingerprint=payload["meta"]["recommendation_fingerprint"],
        )
        self.assertTrue(built.ok, built.message)
        assert built.plan is not None
        return payload, built.plan

    def test_calculate_writes_nothing(self) -> None:
        records = self._seed_ledger()
        before = copy.deepcopy(records)
        rec = self._recommendation()
        self.assertTrue(rec.ok)
        attach_application_metadata_to_payload(
            rec.to_dict(),
            records=records,
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
        )
        self.assertEqual(records, before)

    def test_cancel_path_is_plan_only(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        # Building a plan must not mutate the ledger list.
        self.assertFalse(event_already_applied(records, plan.application_id))
        self.assertEqual(len(records), 5)

    def test_confirm_records_deposit_and_buys(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        result = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.status, STATUS_OK)
        out = list(result.transactions)
        self.assertEqual(len(out), len(records) + 1 + len(plan.purchases))
        deposits = [t for t in out if t["action"] == "cash_deposit" and t.get("contribution_event_id")]
        buys = [t for t in out if t["action"] == "buy" and t.get("contribution_event_id")]
        self.assertEqual(len(deposits), 1)
        self.assertAlmostEqual(float(deposits[0]["quantity"]), 1000.0, places=2)
        self.assertEqual(len(buys), 4)
        self.assertAlmostEqual(sum(float(b["quantity"]) * float(b["execution_price"]) for b in buys), 1000.0, delta=0.02)

    def test_buy_dollars_match_contribution(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        self.assertAlmostEqual(plan.total_purchase_cost, 1000.0, delta=0.02)

    def test_contribution_is_not_investment_return(self) -> None:
        records = self._seed_ledger()
        prices = {"BND": 1.0, "VNQ": 1.0, "VTI": 1.0, "VXUS": 1.0}
        before = pe.compute_portfolio_summary(
            pe.transactions_from_records(records), prices=prices
        )
        cash_before = pe.compute_cash_ledger_summary(pe.transactions_from_records(records))
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        self.assertTrue(applied.ok)
        after_txns = pe.transactions_from_records(list(applied.transactions))
        cash_after = pe.compute_cash_ledger_summary(after_txns)
        self.assertAlmostEqual(cash_after.total_deposits - cash_before.total_deposits, 1000.0, places=2)
        self.assertAlmostEqual(cash_after.total_buy_cost - cash_before.total_buy_cost, 1000.0, delta=0.02)
        # Mark each holding at its own average cost → unrealized gain ~0 (contribution ≠ profit).
        tmp_pos, _ = pe.build_positions(after_txns, prices=self.QUOTES)
        cost_marks = {p.ticker: p.average_cost_basis for p in tmp_pos}
        after = pe.compute_portfolio_summary(after_txns, prices=cost_marks)
        self.assertAlmostEqual(before.total_gain_loss_dollar, 0.0, places=2)
        self.assertAlmostEqual(after.total_gain_loss_dollar, 0.0, places=2)

    def test_cash_returns_near_prior_after_full_invest(self) -> None:
        records = self._seed_ledger()
        before_cash = pe.compute_cash_ledger_summary(
            pe.transactions_from_records(records)
        ).net_cash
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        after_cash = pe.compute_cash_ledger_summary(
            pe.transactions_from_records(list(applied.transactions))
        ).net_cash
        self.assertAlmostEqual(after_cash, before_cash, delta=0.02)

    def test_cost_basis_and_shares_increase(self) -> None:
        records = self._seed_ledger()
        before_pos, _ = pe.build_positions(
            pe.transactions_from_records(records), prices={"BND": 1, "VNQ": 1, "VTI": 1, "VXUS": 1}
        )
        before_shares = {p.ticker: p.shares_owned for p in before_pos}
        before_cost = {p.ticker: p.shares_owned * p.average_cost_basis for p in before_pos}
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        after_pos, _ = pe.build_positions(
            pe.transactions_from_records(list(applied.transactions)),
            prices=self.QUOTES,
        )
        after_shares = {p.ticker: p.shares_owned for p in after_pos}
        after_cost = {p.ticker: p.shares_owned * p.average_cost_basis for p in after_pos}
        for p in plan.purchases:
            self.assertGreater(after_shares[p.ticker], before_shares[p.ticker])
            self.assertGreater(after_cost[p.ticker], before_cost[p.ticker] - 1e-6)

    def test_positions_rebuild_from_ledger(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        snap = build_real_portfolio_snapshot(
            {"portfolio_transactions": list(applied.transactions)},
            prices=self.QUOTES,
        )
        self.assertTrue(snap.ok)
        assert snap.snapshot is not None
        tickers = {h.ticker for h in snap.snapshot.holdings}
        self.assertEqual(tickers, {"BND", "VNQ", "VTI", "VXUS"})

    def test_double_apply_is_idempotent(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        first = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        self.assertTrue(first.ok)
        second = apply_contribution_plan_to_records(
            list(first.transactions), plan, current_fingerprint=plan.fingerprint, require_fingerprint_match=False
        )
        self.assertTrue(second.ok)
        self.assertTrue(second.already_applied or second.status == STATUS_ALREADY_APPLIED)
        self.assertEqual(len(second.transactions), len(first.transactions))

    def test_invalid_plan_writes_nothing(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        payload, plan = self._plan(records, rec)
        # Corrupt purchase costs so validation fails.
        bad_buys = list(plan.buy_records)
        bad_buys[0] = dict(bad_buys[0])
        bad_buys[0]["execution_price"] = 0.01
        from investment_ami.decision_support.contribution_recorder import ContributionApplicationPlan

        bad_plan = ContributionApplicationPlan(
            application_id=plan.application_id,
            contribution_amount=plan.contribution_amount,
            trade_date=plan.trade_date,
            execution_policy=plan.execution_policy,
            deposit_record=plan.deposit_record,
            buy_records=tuple(bad_buys),
            purchases=plan.purchases,
            fingerprint=plan.fingerprint,
        )
        before = copy.deepcopy(records)
        result = apply_contribution_plan_to_records(
            records, bad_plan, current_fingerprint=plan.fingerprint
        )
        self.assertFalse(result.ok)
        self.assertEqual(records, before)
        self.assertEqual(result.transactions, ())

    def test_stale_ledger_blocks_apply(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        mutated = records + [_deposit(50.0, txn_id="extra")]
        result = apply_contribution_plan_to_records(
            mutated, plan, current_fingerprint=plan.fingerprint
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, STATUS_STALE)
        self.assertEqual(result.transactions, ())

    def test_changed_target_fingerprint_mismatch(self) -> None:
        records = self._seed_ledger()
        fp1 = recommendation_fingerprint(
            ledger_fp=ledger_state_fingerprint(records),
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
            recommended_adds={"VTI": 100.0},
            portfolio_value_before=4242.1,
        )
        fp2 = recommendation_fingerprint(
            ledger_fp=ledger_state_fingerprint(records),
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets={"BND": 25, "VNQ": 10, "VTI": 40, "VXUS": 25},
            recommended_adds={"VTI": 100.0},
            portfolio_value_before=4242.1,
        )
        self.assertFalse(fingerprints_match(fp1, fp2))

    def test_changed_contribution_amount_fingerprint_mismatch(self) -> None:
        records = self._seed_ledger()
        fp1 = recommendation_fingerprint(
            ledger_fp=ledger_state_fingerprint(records),
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
            recommended_adds={"VTI": 100.0},
            portfolio_value_before=4242.1,
        )
        fp2 = recommendation_fingerprint(
            ledger_fp=ledger_state_fingerprint(records),
            contribution_amount=1500.0,
            target_source="user_explicit",
            targets=self.TARGETS,
            recommended_adds={"VTI": 100.0},
            portfolio_value_before=4242.1,
        )
        self.assertFalse(fingerprints_match(fp1, fp2))

    def test_missing_quote_blocks_plan(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        payload = attach_application_metadata_to_payload(
            rec.to_dict(),
            records=records,
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
        )
        adds = {r["ticker"]: r["recommended_add"] for r in payload["rows"]}
        quotes = dict(self.QUOTES)
        del quotes["VNQ"]
        built = build_simulated_application_plan(
            application_id=payload["meta"]["application_id"],
            contribution_amount=1000.0,
            recommended_adds=adds,
            quotes=quotes,
            fingerprint=payload["meta"]["recommendation_fingerprint"],
        )
        self.assertFalse(built.ok)
        self.assertEqual(built.status, STATUS_MISSING_QUOTES)

    def test_workspace_token_in_fingerprint(self) -> None:
        records = self._seed_ledger()
        a = recommendation_fingerprint(
            ledger_fp=ledger_state_fingerprint(records),
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
            recommended_adds={"VTI": 1.0},
            portfolio_value_before=1.0,
            workspace_token="alice",
        )
        b = recommendation_fingerprint(
            ledger_fp=ledger_state_fingerprint(records),
            contribution_amount=1000.0,
            target_source="user_explicit",
            targets=self.TARGETS,
            recommended_adds={"VTI": 1.0},
            portfolio_value_before=1.0,
            workspace_token="bob",
        )
        self.assertFalse(fingerprints_match(a, b))

    def test_metadata_links_buys_to_contribution_event(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        linked = [
            t
            for t in applied.transactions
            if t.get("contribution_event_id") == plan.application_id
        ]
        self.assertEqual(len(linked), 1 + len(plan.purchases))
        self.assertTrue(all(t.get("source") == "contribution_advisor" for t in linked))

    def test_metadata_survives_round_trip(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        round_tripped = pe.transactions_to_records(
            pe.transactions_from_records(list(applied.transactions))
        )
        self.assertTrue(event_already_applied(round_tripped, plan.application_id))

    def test_subsequent_advisor_uses_new_holdings(self) -> None:
        records = self._seed_ledger()
        rec = self._recommendation()
        _, plan = self._plan(records, rec)
        applied = apply_contribution_plan_to_records(
            records, plan, current_fingerprint=plan.fingerprint
        )
        # Economics after exact-reach contribution = projected values from the recommendation.
        projected = {
            r.ticker: r.current_value + r.recommended_add for r in rec.rows if r.ticker != "$CASH"
        }
        again = allocate_contribution_new_money_only(
            current_values=projected,
            target_weights=self.TARGETS,
            contribution=0.0,
        )
        self.assertTrue(again.ok)
        self.assertLess(again.aggregate_drift_before, 1e-3)
        self.assertTrue(event_already_applied(list(applied.transactions), plan.application_id))
        self.assertGreater(len(applied.transactions), len(records))

    def test_no_default_holdings_fallback(self) -> None:
        from investment_ami.decision_support.contribution_advisor import (
            STATUS_NO_REAL_PORTFOLIO,
            recommend_contribution_allocation_from_session,
        )
        import portfolio_core as core

        result = recommend_contribution_allocation_from_session(
            {
                "holdings_df": __import__("pandas").DataFrame(core.DEFAULT_HOLDINGS),
                "portfolio_transactions": [],
            },
            contribution_amount=1000.0,
            target_source="current_mix",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, STATUS_NO_REAL_PORTFOLIO)

    def test_manual_transactions_remain_compatible(self) -> None:
        manual = [
            _deposit(5000.0, txn_id="m1"),
            _buy("VTI", 10, 100.0, txn_id="m2"),
        ]
        # Old records without contribution_event_id still load.
        txns = pe.transactions_from_records(manual)
        self.assertEqual(txns[0].contribution_event_id, "")
        self.assertEqual(txns[1].source, "")
        positions, cash = pe.build_positions(txns, prices={"VTI": 110.0})
        self.assertEqual(len(positions), 1)
        self.assertAlmostEqual(cash, 4000.0, places=2)


if __name__ == "__main__":
    unittest.main()
