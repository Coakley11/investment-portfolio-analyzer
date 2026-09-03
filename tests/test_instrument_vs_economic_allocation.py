"""Instrument-type Dashboard allocation must not mix in economic bond-ETF overrides."""

from __future__ import annotations

import unittest

import portfolio_engine as pe
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


def _deposit(amount: float) -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date="2024-01-01",
        ticker="",
        quantity=amount,
        execution_price=1.0,
        asset_type="cash",
    )


def _buy(
    ticker: str,
    qty: float,
    price: float,
    *,
    asset_type: str,
    day: str = "2024-01-15",
) -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        asset_type=asset_type,
    )


class TestInstrumentTypeAllocation(unittest.TestCase):
    def test_four_etfs_including_bnd_are_100_pct_etf(self) -> None:
        """Shadow-portfolio shape: VTI/VXUS/BND/VNQ all entered as ETF → 100% ETFs."""
        # 20k + 5k + 15k + 4k = 44k fully invested
        txns = [
            _deposit(44_000.0),
            _buy("VTI", 100, 200.0, asset_type="etf"),
            _buy("VXUS", 100, 50.0, asset_type="etf"),
            _buy("BND", 200, 75.0, asset_type="etf"),
            _buy("VNQ", 50, 80.0, asset_type="etf"),
        ]
        prices = {"VTI": 200.0, "VXUS": 50.0, "BND": 75.0, "VNQ": 80.0}
        summary = pe.compute_portfolio_summary(txns, prices=prices)
        self.assertAlmostEqual(summary.allocation_by_bucket["ETFs"], 100.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Stocks"], 0.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 0.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Cash"], 0.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Other"], 0.0, places=1)
        positions, _ = pe.build_positions(txns, prices=prices)
        by_ticker = {p.ticker: p.asset_type for p in positions}
        self.assertEqual(by_ticker["BND"], "etf")
        self.assertEqual(by_ticker["VTI"], "etf")

    def test_direct_bond_position_in_bond_bucket(self) -> None:
        txns = [
            _deposit(10_000.0),
            _buy("BND", 10, 80.0, asset_type="bond"),
            _buy("VOO", 5, 400.0, asset_type="etf"),
        ]
        prices = {"BND": 80.0, "VOO": 400.0}
        summary = pe.compute_portfolio_summary(txns, prices=prices)
        self.assertGreater(summary.allocation_by_bucket["Bonds"], 0.0)
        self.assertGreater(summary.allocation_by_bucket["ETFs"], 0.0)
        self.assertAlmostEqual(summary.allocation_by_bucket["Other"], 0.0, places=1)

    def test_mixed_stock_etf_bond_other_aggregate(self) -> None:
        txns = [
            _deposit(40_000.0),
            _buy("AAPL", 10, 100.0, asset_type="stock"),  # 1_000
            _buy("VTI", 10, 100.0, asset_type="etf"),  # 1_000
            _buy("BND", 10, 100.0, asset_type="bond"),  # 1_000
            _buy("XYZ", 10, 100.0, asset_type="other"),  # 1_000
        ]
        prices = {"AAPL": 100.0, "VTI": 100.0, "BND": 100.0, "XYZ": 100.0}
        summary = pe.compute_portfolio_summary(txns, prices=prices)
        # 4k securities + 36k cash remaining
        self.assertAlmostEqual(summary.allocation_by_bucket["Stocks"], 2.5, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["ETFs"], 2.5, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 2.5, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Other"], 2.5, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Cash"], 90.0, places=1)


class TestEconomicExposureSeparateFromInstrument(unittest.TestCase):
    def test_bnd_etf_instrument_but_bonds_economic_in_snapshot(self) -> None:
        # VTI 2k + BND 2k = 4k fully invested
        records = [
            _deposit(4_000.0).to_record(),
            _buy("VTI", 10, 200.0, asset_type="etf").to_record(),
            _buy("BND", 25, 80.0, asset_type="etf").to_record(),
        ]
        prices = {"VTI": 200.0, "BND": 80.0}
        # Instrument Dashboard view
        summary = pe.compute_portfolio_summary(
            pe.transactions_from_records(records), prices=prices
        )
        self.assertGreater(summary.allocation_by_bucket["ETFs"], 99.0)
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 0.0, places=1)

        # Economic / AMI snapshot still identifies BND as fixed income
        result = build_real_portfolio_snapshot(
            {"portfolio_transactions": records},
            prices=prices,
        )
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        bnd = next(h for h in result.snapshot.holdings if h.ticker == "BND")
        self.assertEqual(bnd.asset_class, "Bonds")
        self.assertGreater(result.snapshot.allocation_by_asset_class.get("Bonds", 0.0), 0.0)
        vti = next(h for h in result.snapshot.holdings if h.ticker == "VTI")
        self.assertEqual(vti.asset_class, "ETFs")

    def test_economic_helper_without_corrupting_normalize(self) -> None:
        self.assertEqual(pe.normalize_asset_type("etf", "BND"), "etf")
        self.assertEqual(pe.economic_exposure_bucket("etf", "BND"), "Bonds")
        self.assertEqual(pe.normalize_asset_type("bond", "BND"), "bond")
        self.assertEqual(pe.allocation_bucket("bond"), "Bonds")


if __name__ == "__main__":
    unittest.main()
