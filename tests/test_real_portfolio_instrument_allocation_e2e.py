"""
Integration: Add Transaction UI path → persist/reload → Dashboard allocation.

Mirrors components.real_portfolio save/reload without Streamlit widgets:
  selectbox instrument value → canonicalize (no ticker) → to_record → session
  reload via transactions_from_records → compute_portfolio_summary (Dashboard).
"""

from __future__ import annotations

import unittest

import portfolio_engine as pe
from components import real_portfolio as rp
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


def _ui_add_buy(
    *,
    ticker: str,
    quantity: float,
    price: float,
    asset_type_select: str,
    day: str = "2024-01-15",
) -> pe.PortfolioTransaction:
    """Same classification rules as render_portfolio_transactions submit path."""
    instrument = pe.canonicalize_instrument_type(asset_type_select)
    if instrument is None:
        instrument = pe.resolve_instrument_type(asset_type_select, "")
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date=day,
        ticker=str(ticker).strip().upper(),
        quantity=float(quantity),
        execution_price=float(price),
        company_name=pe.infer_company_name(ticker),
        asset_type=instrument,
    )


def _deposit(amount: float) -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date="2024-01-01",
        ticker="",
        quantity=float(amount),
        execution_price=1.0,
        asset_type="cash",
    )


class TestTransactionSaveReloadDashboardAllocation(unittest.TestCase):
    def test_bnd_saved_as_etf_survives_reload_and_dashboard(self) -> None:
        # Selectbox options are lowercase instrument tokens (see _BUY_SELL_ASSET_TYPES).
        self.assertEqual(rp._BUY_SELL_ASSET_TYPES, ("stock", "etf", "bond", "other"))

        live = [
            _deposit(8_000.0),
            _ui_add_buy(ticker="BND", quantity=100, price=80.0, asset_type_select="etf"),
        ]
        # Persist as session/cloud records (set_portfolio_transactions path).
        records = pe.transactions_to_records(live)
        bnd_rec = next(r for r in records if r["ticker"] == "BND")
        self.assertEqual(bnd_rec["asset_type"], "etf")

        # Hydrate exactly as get_portfolio_transactions() does.
        reloaded = pe.transactions_from_records(records)
        bnd_txn = next(t for t in reloaded if t.ticker == "BND")
        self.assertEqual(bnd_txn.asset_type, "etf")

        prices = {"BND": 80.0}
        positions, _cash = pe.build_positions(reloaded, prices=prices)
        self.assertEqual(positions[0].asset_type, "etf")

        # Dashboard cards = compute_portfolio_summary.allocation_by_bucket
        summary = pe.compute_portfolio_summary(reloaded, prices=prices)
        self.assertAlmostEqual(summary.allocation_by_bucket["ETFs"], 100.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 0.0, places=1)

    def test_four_etf_shadow_portfolio_dashboard_100_pct_etf(self) -> None:
        # Fully invested 40/30/20/10 weights at mark=cost.
        live = [
            _deposit(10_000.0),
            _ui_add_buy(ticker="VTI", quantity=40, price=100.0, asset_type_select="etf"),
            _ui_add_buy(ticker="BND", quantity=30, price=100.0, asset_type_select="etf"),
            _ui_add_buy(ticker="VXUS", quantity=20, price=100.0, asset_type_select="etf"),
            _ui_add_buy(ticker="VNQ", quantity=10, price=100.0, asset_type_select="etf"),
        ]
        records = pe.transactions_to_records(live)
        for tick in ("VTI", "VXUS", "BND", "VNQ"):
            self.assertEqual(
                next(r for r in records if r["ticker"] == tick)["asset_type"],
                "etf",
            )

        reloaded = pe.transactions_from_records(records)
        prices = {"VTI": 100.0, "BND": 100.0, "VXUS": 100.0, "VNQ": 100.0}
        summary = pe.compute_portfolio_summary(reloaded, prices=prices)
        self.assertAlmostEqual(summary.allocation_by_bucket["ETFs"], 100.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 0.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Stocks"], 0.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Cash"], 0.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["Other"], 0.0, places=1)

        positions, _ = pe.build_positions(reloaded, prices=prices)
        by_ticker = {p.ticker: p for p in positions}
        self.assertEqual(by_ticker["BND"].asset_type, "etf")
        self.assertAlmostEqual(by_ticker["VTI"].weight_pct, 40.0, places=1)
        self.assertAlmostEqual(by_ticker["BND"].weight_pct, 30.0, places=1)
        self.assertAlmostEqual(by_ticker["VXUS"].weight_pct, 20.0, places=1)
        self.assertAlmostEqual(by_ticker["VNQ"].weight_pct, 10.0, places=1)

        # Economic / AMI path still maps BND → Bonds without corrupting instrument view.
        snap = build_real_portfolio_snapshot(
            {"portfolio_transactions": records},
            prices=prices,
        )
        self.assertTrue(snap.ok)
        assert snap.snapshot is not None
        bnd_h = next(h for h in snap.snapshot.holdings if h.ticker == "BND")
        self.assertEqual(bnd_h.asset_class, "Bonds")
        self.assertGreater(snap.snapshot.allocation_by_asset_class.get("Bonds", 0.0), 0.0)

    def test_explicit_bond_select_still_bonds_on_dashboard(self) -> None:
        live = [
            _deposit(8_000.0),
            _ui_add_buy(ticker="BND", quantity=100, price=80.0, asset_type_select="bond"),
        ]
        reloaded = pe.transactions_from_records(pe.transactions_to_records(live))
        summary = pe.compute_portfolio_summary(reloaded, prices={"BND": 80.0})
        self.assertAlmostEqual(summary.allocation_by_bucket["Bonds"], 100.0, places=1)
        self.assertAlmostEqual(summary.allocation_by_bucket["ETFs"], 0.0, places=1)

    def test_build_id_bumped_for_deploy_verification(self) -> None:
        self.assertIn("instrument-alloc", rp.REAL_PORTFOLIO_BUILD_ID)


if __name__ == "__main__":
    unittest.main()
