"""Ticker identity correction (VN! → VNQ) and entry validation guardrails."""

from __future__ import annotations

import copy
import unittest

import portfolio_engine as pe

from investment_ami.decision_support.contribution_advisor import (
    STATUS_MISSING_PRICES,
    recommend_contribution_allocation,
)
from investment_ami.decision_support.real_portfolio_snapshot import (
    build_real_portfolio_snapshot,
    unpriced_holding_tickers,
)


def _buy_record(
    ticker: str,
    qty: float,
    price: float,
    *,
    txn_id: str,
    day: str = "2024-06-01",
    notes: str = "seed buy",
    asset_type: str = "etf",
) -> dict:
    return {
        "id": txn_id,
        "action": "buy",
        "date": day,
        "ticker": ticker,
        "quantity": qty,
        "execution_price": price,
        "notes": notes,
        "company_name": ticker,
        "asset_type": asset_type,
    }


def _deposit_record(amount: float, *, txn_id: str = "dep1") -> dict:
    return {
        "id": txn_id,
        "action": "cash_deposit",
        "date": "2024-01-01",
        "ticker": "",
        "quantity": amount,
        "execution_price": 1.0,
        "notes": "funding",
        "company_name": "Cash",
        "asset_type": "cash",
    }


class TestTradeTickerValidation(unittest.TestCase):
    def test_rejects_malformed_vn_bang(self) -> None:
        ok, normalized, err = pe.validate_trade_ticker("VN!")
        self.assertFalse(ok)
        self.assertEqual(normalized, "")
        self.assertIn("!", err)

    def test_accepts_vnq(self) -> None:
        ok, normalized, err = pe.validate_trade_ticker("vnq")
        self.assertTrue(ok)
        self.assertEqual(normalized, "VNQ")
        self.assertEqual(err, "")

    def test_accepts_share_class_separators(self) -> None:
        self.assertTrue(pe.validate_trade_ticker("BRK.B")[0])
        self.assertTrue(pe.validate_trade_ticker("BF-B")[0])

    def test_rejects_other_punctuation(self) -> None:
        for raw in ("VTI@", "BND#", "VXUS$", "A/B", "VOO!"):
            ok, _, err = pe.validate_trade_ticker(raw)
            self.assertFalse(ok, raw)
            self.assertTrue(err)


class TestCorrectTransactionTickerIdentity(unittest.TestCase):
    def test_preserves_economics_and_ids_no_synthetic_trades(self) -> None:
        txns = [
            _deposit_record(100_000.0),
            _buy_record("VTI", 40, 100.0, txn_id="t_vti"),
            _buy_record("VXUS", 20, 50.0, txn_id="t_vxus"),
            _buy_record("BND", 30, 80.0, txn_id="t_bnd"),
            _buy_record("VN!", 10, 90.0, txn_id="t_vn_bad", notes="reit sleeve"),
        ]
        before = copy.deepcopy(txns)
        corrected, n = pe.correct_transaction_ticker_identity(
            txns, from_ticker="VN!", to_ticker="VNQ"
        )
        self.assertEqual(n, 1)
        self.assertEqual(len(corrected), len(before))
        bad = next(r for r in corrected if r["id"] == "t_vn_bad")
        self.assertEqual(bad["ticker"], "VNQ")
        self.assertEqual(bad["date"], "2024-06-01")
        self.assertEqual(bad["action"], "buy")
        self.assertEqual(bad["quantity"], 10.0)
        self.assertEqual(bad["execution_price"], 90.0)
        self.assertEqual(bad["notes"], "reit sleeve")
        self.assertEqual(bad["asset_type"], "etf")
        self.assertEqual(bad["id"], "t_vn_bad")
        # No synthetic sell/buy rows
        actions = [r["action"] for r in corrected]
        self.assertEqual(actions.count("buy"), 4)
        self.assertEqual(actions.count("sell"), 0)
        # Other holdings unchanged
        for tid in ("t_vti", "t_vxus", "t_bnd"):
            orig = next(r for r in before if r["id"] == tid)
            now = next(r for r in corrected if r["id"] == tid)
            self.assertEqual(orig, now)

        prices = {"VTI": 100.0, "VXUS": 50.0, "BND": 80.0, "VNQ": 90.0}
        pos_before, cash_before = pe.build_positions(
            pe.transactions_from_records(before),
            prices={"VTI": 100.0, "VXUS": 50.0, "BND": 80.0, "VN!": 90.0},
        )
        pos_after, cash_after = pe.build_positions(
            pe.transactions_from_records(corrected), prices=prices
        )
        self.assertAlmostEqual(cash_before, cash_after)
        cost_before = sum(p.shares_owned * p.average_cost_basis for p in pos_before)
        cost_after = sum(p.shares_owned * p.average_cost_basis for p in pos_after)
        self.assertAlmostEqual(cost_before, cost_after)
        tickers_after = {p.ticker for p in pos_after}
        self.assertEqual(tickers_after, {"VTI", "VXUS", "BND", "VNQ"})
        self.assertNotIn("VN!", tickers_after)

    def test_known_corrections_and_malformed_scan(self) -> None:
        txns = [
            _buy_record("VN!", 1, 10.0, txn_id="a"),
            _buy_record("VTI", 1, 10.0, txn_id="b"),
        ]
        self.assertEqual(pe.find_malformed_trade_tickers(txns), ["VN!"])
        fixed, notes = pe.apply_known_ticker_identity_corrections(txns)
        self.assertTrue(notes)
        self.assertEqual(pe.find_malformed_trade_tickers(fixed), [])
        self.assertEqual(fixed[0]["ticker"], "VNQ")


class TestSnapshotAndContributionAfterCorrection(unittest.TestCase):
    def test_snapshot_quotes_vnq_and_clears_missing_vn_bang(self) -> None:
        txns = [
            _deposit_record(100_000.0),
            _buy_record("VTI", 40, 100.0, txn_id="t_vti"),
            _buy_record("VXUS", 20, 50.0, txn_id="t_vxus"),
            _buy_record("BND", 30, 80.0, txn_id="t_bnd"),
            _buy_record("VN!", 10, 90.0, txn_id="t_vn_bad"),
        ]
        session = {"portfolio_transactions": copy.deepcopy(txns)}
        prices = {"VTI": 100.0, "VXUS": 50.0, "BND": 80.0, "VNQ": 95.0}
        result = build_real_portfolio_snapshot(session, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        snap = result.snapshot
        tickers = {h.ticker for h in snap.holdings}
        self.assertEqual(tickers, {"VTI", "VXUS", "BND", "VNQ"})
        self.assertNotIn("VN!", tickers)
        self.assertEqual(unpriced_holding_tickers(snap), ())
        vnq = next(h for h in snap.holdings if h.ticker == "VNQ")
        self.assertAlmostEqual(vnq.current_price or 0.0, 95.0)
        self.assertNotEqual(vnq.price_source, "avg_cost")
        self.assertNotIn("avg_cost", (vnq.price_source or "").lower())
        # Session ledger identity updated in place (authoritative for this session)
        self.assertEqual(session["portfolio_transactions"][4]["ticker"], "VNQ")
        self.assertEqual(session["portfolio_transactions"][4]["id"], "t_vn_bad")

        rec = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=1000.0,
            target_source="user_explicit",
            explicit_holding_targets={
                "VTI": 0.40,
                "VXUS": 0.20,
                "BND": 0.30,
                "VNQ": 0.10,
            },
        )
        self.assertTrue(rec.ok)
        self.assertNotEqual(rec.status, STATUS_MISSING_PRICES)
        self.assertFalse(any("VN!" in w for w in rec.warnings))


if __name__ == "__main__":
    unittest.main()
