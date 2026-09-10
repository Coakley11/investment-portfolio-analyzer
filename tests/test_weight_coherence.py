"""Regression: real-portfolio holding weights stay coherent (sum ~100%)."""

from __future__ import annotations

import copy
import unittest

import portfolio_engine as pe

from investment_ami.decision_support.contribution_advisor import (
    recommend_contribution_allocation,
)
from investment_ami.decision_support.real_portfolio_snapshot import (
    build_real_portfolio_snapshot,
)


def _buy(
    ticker: str,
    qty: float,
    price: float,
    *,
    txn_id: str,
    day: str = "2024-06-01",
) -> dict:
    return {
        "id": txn_id,
        "action": "buy",
        "date": day,
        "ticker": ticker,
        "quantity": qty,
        "execution_price": price,
        "notes": "",
        "company_name": ticker,
        "asset_type": "etf",
    }


def _deposit(amount: float, *, txn_id: str = "dep1") -> dict:
    return {
        "id": txn_id,
        "action": "cash_deposit",
        "date": "2024-01-01",
        "ticker": "",
        "quantity": amount,
        "execution_price": 1.0,
        "notes": "",
        "company_name": "Cash",
        "asset_type": "cash",
    }


# Manual case that produced 33.25 + 9.97 + 44.34 + 22.41 = 109.97%:
# four holdings with securities mix ≈ 40.32/20.38/30.24/9.07 and cash ≈ −VNQ MV.
# Old weight denom = securities + negative cash → factor 1.0997; the three
# non-VNQ weights sum to 100% and VNQ appears as an extra ~9.97%.
_MANUAL_PRICES = {"VTI": 100.800218, "VXUS": 50.945712, "BND": 80.62805, "VNQ": 90.661089}
_MANUAL_SHARES = {"VTI": 40.0, "VXUS": 40.0, "BND": 37.5, "VNQ": 10.0}


def _manual_unfunded_vnq_ledger(*, vnq_ticker: str = "VNQ") -> list[dict]:
    costs = {
        "VTI": _MANUAL_SHARES["VTI"] * _MANUAL_PRICES["VTI"],
        "VXUS": _MANUAL_SHARES["VXUS"] * _MANUAL_PRICES["VXUS"],
        "BND": _MANUAL_SHARES["BND"] * _MANUAL_PRICES["BND"],
        "VNQ": _MANUAL_SHARES["VNQ"] * _MANUAL_PRICES["VNQ"],
    }
    securities = sum(costs.values())
    vnq_mv = costs["VNQ"]
    # Deposit covers everything except VNQ → cash = −VNQ MV at these marks.
    deposit = securities - vnq_mv
    return [
        _deposit(deposit),
        _buy("VTI", _MANUAL_SHARES["VTI"], _MANUAL_PRICES["VTI"], txn_id="t_vti"),
        _buy("VXUS", _MANUAL_SHARES["VXUS"], _MANUAL_PRICES["VXUS"], txn_id="t_vxus"),
        _buy("BND", _MANUAL_SHARES["BND"], _MANUAL_PRICES["BND"], txn_id="t_bnd"),
        _buy(vnq_ticker, _MANUAL_SHARES["VNQ"], _MANUAL_PRICES["VNQ"], txn_id="t_vnq"),
    ]


class TestHoldingWeightCoherence(unittest.TestCase):
    def test_four_priced_holdings_weights_sum_to_100(self) -> None:
        # Fund buys exactly so cash ≈ 0 and holding weights are a complete pie.
        buy_cost = 40 * 100.0 + 20 * 50.0 + 30 * 80.0 + 10 * 90.0
        txns = pe.transactions_from_records(
            [
                _deposit(buy_cost),
                _buy("VTI", 40, 100.0, txn_id="a"),
                _buy("VXUS", 20, 50.0, txn_id="b"),
                _buy("BND", 30, 80.0, txn_id="c"),
                _buy("VNQ", 10, 90.0, txn_id="d"),
            ]
        )
        prices = {"VTI": 110.0, "VXUS": 55.0, "BND": 78.0, "VNQ": 95.0}
        positions, cash = pe.build_positions(txns, prices=prices)
        self.assertAlmostEqual(cash, 0.0, places=2)
        self.assertEqual({p.ticker for p in positions}, {"VTI", "VXUS", "BND", "VNQ"})
        self.assertAlmostEqual(sum(p.weight_pct for p in positions), 100.0, places=2)
        # No hard-coded 40/20/30/10 — live marks move weights.
        by = {p.ticker: p.weight_pct for p in positions}
        self.assertNotAlmostEqual(by["VTI"], 40.0, places=0)

    def test_manual_10997_case_negative_cash_no_longer_inflates(self) -> None:
        txns = pe.transactions_from_records(_manual_unfunded_vnq_ledger())
        positions, cash = pe.build_positions(txns, prices=_MANUAL_PRICES)
        self.assertLess(cash, 0)
        weights = {p.ticker: p.weight_pct for p in positions}
        self.assertAlmostEqual(sum(weights.values()), 100.0, places=2)
        displayed = {t: round(w, 2) for t, w in weights.items()}
        # Reproduce the broken pattern under the OLD formula (exact manual case).
        sec = sum(p.market_value for p in positions)
        old = {
            p.ticker: round(p.market_value / (sec + cash) * 100.0, 2) for p in positions
        }
        self.assertEqual(old["BND"], 33.25)
        self.assertEqual(old["VNQ"], 9.97)
        self.assertEqual(old["VTI"], 44.34)
        self.assertEqual(old["VXUS"], 22.41)
        self.assertAlmostEqual(sum(old.values()), 109.97, places=2)
        self.assertAlmostEqual(old["VTI"] + old["VXUS"] + old["BND"], 100.0, places=2)
        # Corrected: securities-only mix (≈40/20/30/10 at these marks; not hard-coded).
        self.assertAlmostEqual(displayed["VTI"], 40.32, places=1)
        self.assertAlmostEqual(displayed["VXUS"], 20.38, places=1)
        self.assertAlmostEqual(displayed["BND"], 30.24, places=1)
        self.assertAlmostEqual(displayed["VNQ"], 9.07, places=1)

    def test_unpriced_then_priced_recomputes_all_weights(self) -> None:
        records = _manual_unfunded_vnq_ledger(vnq_ticker="VN!")
        # Snapshot while VN! unpriced: three holdings carry weight; VN! at 0.
        prices_partial = {"VTI": 100.0, "VXUS": 50.0, "BND": 80.0}
        r1 = build_real_portfolio_snapshot(
            {"portfolio_transactions": copy.deepcopy(records)},
            prices=prices_partial,
        )
        self.assertTrue(r1.ok)
        assert r1.snapshot is not None
        # Identity correction + full marks.
        fixed, notes = pe.apply_known_ticker_identity_corrections(records)
        self.assertTrue(notes)
        r2 = build_real_portfolio_snapshot(
            {"portfolio_transactions": fixed},
            prices=_MANUAL_PRICES,
        )
        self.assertTrue(r2.ok)
        assert r2.snapshot is not None
        snap = r2.snapshot
        tickers = {h.ticker for h in snap.holdings}
        self.assertEqual(tickers, {"VTI", "VXUS", "BND", "VNQ"})
        self.assertNotIn("VN!", tickers)
        sec_weights = [
            h.current_weight for h in snap.holdings if h.ticker not in ("$CASH", "CASH")
        ]
        self.assertAlmostEqual(sum(sec_weights), 100.0, places=2)
        # Partial-state weights must not permanently stick after quote available.
        w_before = {
            h.ticker: h.current_weight
            for h in r1.snapshot.holdings
            if h.current_weight > 0
        }
        w_after = {h.ticker: h.current_weight for h in snap.holdings}
        self.assertNotAlmostEqual(w_before.get("VTI", 0), w_after["VTI"], places=1)

    def test_no_double_count_vn_bang_and_vnq(self) -> None:
        records = _manual_unfunded_vnq_ledger(vnq_ticker="VN!")
        fixed, _ = pe.apply_known_ticker_identity_corrections(records)
        positions, _ = pe.build_positions(
            pe.transactions_from_records(fixed), prices=_MANUAL_PRICES
        )
        tickers = [p.ticker for p in positions]
        self.assertEqual(tickers.count("VNQ"), 1)
        self.assertNotIn("VN!", tickers)
        self.assertAlmostEqual(sum(p.weight_pct for p in positions), 100.0, places=2)

    def test_canonical_total_equals_sum_of_position_values(self) -> None:
        txns = pe.transactions_from_records(_manual_unfunded_vnq_ledger())
        positions, cash = pe.build_positions(txns, prices=_MANUAL_PRICES)
        securities = sum(p.market_value for p in positions)
        summary = pe.compute_portfolio_summary(txns, prices=_MANUAL_PRICES)
        self.assertAlmostEqual(summary.total_portfolio_value, securities + cash, places=4)
        self.assertAlmostEqual(securities, sum(p.market_value for p in positions), places=6)

    def test_positions_and_contribution_advisor_agree(self) -> None:
        records = _manual_unfunded_vnq_ledger()
        txns = pe.transactions_from_records(records)
        positions, cash = pe.build_positions(txns, prices=_MANUAL_PRICES)
        result = build_real_portfolio_snapshot(
            {"portfolio_transactions": records},
            prices=_MANUAL_PRICES,
        )
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        snap = result.snapshot
        pos_by = {p.ticker: p for p in positions}
        for h in snap.holdings:
            self.assertIn(h.ticker, pos_by)
            p = pos_by[h.ticker]
            self.assertAlmostEqual(h.current_price or 0.0, p.current_price, places=4)
            self.assertAlmostEqual(h.current_value, p.market_value, places=4)
            self.assertAlmostEqual(h.current_weight, p.weight_pct, places=2)
        self.assertAlmostEqual(snap.cash, cash, places=4)
        self.assertAlmostEqual(
            snap.total_market_value,
            sum(p.market_value for p in positions) + cash,
            places=4,
        )

        rec = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=1000.0,
            target_source="user_explicit",
            explicit_holding_targets={
                "VTI": 40.0,
                "VXUS": 20.0,
                "BND": 30.0,
                "VNQ": 10.0,
            },
        )
        self.assertTrue(rec.ok)
        eng_w = {r.ticker: r.current_weight * 100.0 for r in rec.rows if r.ticker != "$CASH"}
        for t, w in eng_w.items():
            self.assertAlmostEqual(w, pos_by[t].weight_pct, places=2)
        self.assertAlmostEqual(sum(eng_w.values()), 100.0, places=2)

    def test_ticker_order_does_not_affect_totals(self) -> None:
        base = _manual_unfunded_vnq_ledger()
        shuffled = [base[0], base[4], base[2], base[1], base[3]]
        p1, c1 = pe.build_positions(
            pe.transactions_from_records(base), prices=_MANUAL_PRICES
        )
        p2, c2 = pe.build_positions(
            pe.transactions_from_records(shuffled), prices=_MANUAL_PRICES
        )
        self.assertAlmostEqual(c1, c2)
        self.assertAlmostEqual(sum(p.market_value for p in p1), sum(p.market_value for p in p2))
        self.assertAlmostEqual(sum(p.weight_pct for p in p1), sum(p.weight_pct for p in p2))
        w1 = {p.ticker: p.weight_pct for p in p1}
        w2 = {p.ticker: p.weight_pct for p in p2}
        self.assertEqual(set(w1), set(w2))
        for t in w1:
            self.assertAlmostEqual(w1[t], w2[t], places=6)

    def test_transaction_economics_unchanged_by_weight_fix(self) -> None:
        records = _manual_unfunded_vnq_ledger(vnq_ticker="VN!")
        before = copy.deepcopy(records)
        fixed, n_notes = pe.apply_known_ticker_identity_corrections(records)
        self.assertTrue(n_notes)
        for orig, new in zip(before, fixed):
            self.assertEqual(orig["id"], new["id"])
            self.assertEqual(orig["action"], new["action"])
            self.assertEqual(orig["date"], new["date"])
            self.assertEqual(orig["quantity"], new["quantity"])
            self.assertEqual(orig["execution_price"], new["execution_price"])
            if orig["action"] in ("buy", "sell") and orig["ticker"] == "VN!":
                self.assertEqual(new["ticker"], "VNQ")
            elif orig["action"] in ("buy", "sell"):
                self.assertEqual(orig["ticker"], new["ticker"])


if __name__ == "__main__":
    unittest.main()
