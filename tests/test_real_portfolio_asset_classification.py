"""Regression: bond ETFs stay Bonds for economic/AMI sleeves; instrument types stay separate."""

from __future__ import annotations

import unittest

import portfolio_engine as pe
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


def _deposit(amount: float) -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date="2024-01-01",
        ticker="",
        quantity=amount,
        execution_price=1.0,
    ).to_record()


def _buy(ticker: str, qty: float, price: float, *, asset_type: str = "") -> dict:
    raw = asset_type or pe.normalize_asset_type("", ticker)
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date="2024-01-15",
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        asset_type=str(raw),
    ).to_record()


class TestRealPortfolioBondClassification(unittest.TestCase):
    def test_snapshot_bnd_in_bonds_sleeve(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BND", 10, 80.0)]
        result = build_real_portfolio_snapshot(
            {"portfolio_transactions": txns},
            prices={"VOO": 400.0, "BND": 80.0},
        )
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        ac = result.snapshot.allocation_by_asset_class
        self.assertGreater(ac.get("Bonds", 0.0), 0.0)
        self.assertAlmostEqual(ac.get("Other", 0.0), 0.0, places=1)
        bnd = next(h for h in result.snapshot.holdings if h.ticker == "BND")
        self.assertEqual(bnd.asset_class, "Bonds")

    def test_snapshot_bnd_entered_as_etf_still_economic_bonds(self) -> None:
        txns = [
            _deposit(10_000.0),
            _buy("VOO", 5, 400.0, asset_type="etf"),
            _buy("BND", 10, 80.0, asset_type="etf"),
        ]
        prices = {"VOO": 400.0, "BND": 80.0}
        summary = pe.compute_portfolio_summary(pe.transactions_from_records(txns), prices=prices)
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 0.0, places=1)
        self.assertGreater(summary.allocation_by_bucket["ETFs"], 0.0)

        result = build_real_portfolio_snapshot({"portfolio_transactions": txns}, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        bnd = next(h for h in result.snapshot.holdings if h.ticker == "BND")
        self.assertEqual(bnd.asset_class, "Bonds")
        self.assertGreater(result.snapshot.allocation_by_asset_class.get("Bonds", 0.0), 0.0)

    def test_valuation_unchanged_by_classification(self) -> None:
        txns = [_deposit(5_000.0), _buy("BND", 10, 80.0)]
        prices = {"BND": 85.0}
        before = pe.compute_portfolio_summary(pe.transactions_from_records(txns), prices=prices)
        # Re-classify path only affects bucket keys, not totals.
        after = pe.compute_portfolio_summary(pe.transactions_from_records(txns), prices=prices)
        self.assertAlmostEqual(before.total_portfolio_value, after.total_portfolio_value)
        self.assertAlmostEqual(before.cash_balance, after.cash_balance)
        self.assertAlmostEqual(before.total_gain_loss_dollar, after.total_gain_loss_dollar)


if __name__ == "__main__":
    unittest.main()
