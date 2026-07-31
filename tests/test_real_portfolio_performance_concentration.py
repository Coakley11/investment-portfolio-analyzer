"""Phase B — performance and concentration analysis on RealPortfolioSnapshot."""

from __future__ import annotations

import copy
import unittest

import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_concentration import (
    analyze_real_portfolio_concentration,
)
from investment_ami.decision_support.real_portfolio_models import RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import (
    FLAT_RETURN_THRESHOLD_PCT,
    METRIC_LABEL_UNREALIZED,
    analyze_real_portfolio_performance,
)
from investment_ami.decision_support.real_portfolio_security_types import classify_holding_security
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


def _buy(ticker: str, qty: float, price: float, *, asset_type: str = "etf") -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date="2024-01-15",
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        company_name=ticker,
        asset_type=asset_type,
    ).to_record()


def _deposit(amount: float) -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date="2024-01-01",
        ticker="",
        quantity=amount,
        execution_price=1.0,
    ).to_record()


def _snap(txns: list, prices: dict[str, float], **session_extra: object) -> RealPortfolioSnapshot:
    ss = {"portfolio_transactions": txns, **session_extra}
    result = build_real_portfolio_snapshot(ss, prices=prices)
    assert result.ok and result.snapshot is not None
    return result.snapshot


class TestRealPortfolioPerformance(unittest.TestCase):
    def test_positive_portfolio_metrics_and_ranking(self) -> None:
        txns = [_deposit(50_000.0), _buy("VOO", 10, 400.0), _buy("BND", 20, 80.0)]
        snap = _snap(txns, {"VOO": 450.0, "BND": 82.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertEqual(perf.metric_label, METRIC_LABEL_UNREALIZED)
        self.assertIsNotNone(perf.total_gain_loss_dollars)
        self.assertIsNotNone(perf.total_gain_loss_pct)
        self.assertGreater(perf.total_gain_loss_dollars or 0, 0)
        self.assertEqual(perf.performance_status, "positive_unrealized_gain")
        self.assertEqual(perf.positive_contributors[0].ticker, "VOO")

    def test_negative_portfolio(self) -> None:
        txns = [_deposit(20_000.0), _buy("VOO", 10, 500.0)]
        snap = _snap(txns, {"VOO": 450.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertLess(perf.total_gain_loss_dollars or 0, 0)
        self.assertEqual(perf.performance_status, "negative_unrealized_loss")
        self.assertEqual(perf.negative_contributors[0].ticker, "VOO")

    def test_dollar_not_percentage_drives_ranking(self) -> None:
        txns = [
            _deposit(100_000.0),
            _buy("XTNY", 10, 10.0, asset_type="stock"),
            _buy("VOO", 100, 400.0),
        ]
        # XTNY: +50% but only $50 unrealized; VOO: ~0.25% but ~$100 unrealized.
        snap = _snap(txns, {"XTNY": 15.0, "VOO": 401.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertEqual(perf.positive_contributors[0].ticker, "VOO")
        self.assertGreater(
            perf.positive_contributors[0].contribution_to_total_gain_loss_dollars or 0,
            perf.positive_contributors[1].contribution_to_total_gain_loss_dollars or 0,
        )

    def test_approximately_flat(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 10, 450.0)]
        snap = _snap(txns, {"VOO": 450.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertEqual(perf.performance_status, "approximately_flat")
        self.assertIsNotNone(perf.total_gain_loss_pct)
        assert perf.total_gain_loss_pct is not None
        self.assertLess(abs(perf.total_gain_loss_pct), FLAT_RETURN_THRESHOLD_PCT)

    def test_partial_prices(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BAD", 3, 10.0)]
        snap = _snap(txns, {"VOO": 450.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertIsNone(perf.total_gain_loss_pct)
        self.assertIsNotNone(perf.priced_holdings_gain_loss_pct)
        self.assertEqual(perf.performance_status, "partial_data")
        self.assertEqual(perf.unpriced_holdings_count, 1)
        tickers = {c.ticker for c in perf.positive_contributors + perf.negative_contributors}
        self.assertNotIn("BAD", tickers)

    def test_cash_excluded_from_contributors(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0)]
        snap = _snap(txns, {"VOO": 450.0})
        perf = analyze_real_portfolio_performance(snap)
        all_contrib = perf.positive_contributors + perf.negative_contributors
        self.assertTrue(all(c.ticker != "$CASH" for c in all_contrib))
        self.assertGreater(snap.cash, 0)

    def test_unpriced_holding_not_treated_as_zero_gain(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BAD", 3, 10.0)]
        snap = _snap(txns, {"VOO": 450.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertIsNone(perf.total_gain_loss_pct)
        bad = next(h for h in snap.holdings if h.ticker == "BAD")
        self.assertIsNone(bad.gain_loss_dollars)
        self.assertEqual(bad.current_value, 0.0)

        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0)]
        snap = _snap(txns, {"VOO": 450.0})
        before = copy.deepcopy(snap)
        analyze_real_portfolio_performance(snap)
        analyze_real_portfolio_concentration(snap)
        self.assertEqual(snap.total_market_value, before.total_market_value)
        self.assertEqual(len(snap.holdings), len(before.holdings))

    def test_modules_do_not_use_model_portfolio_inputs(self) -> None:
        from pathlib import Path

        forbidden = ("holdings_df", "sidebar_portfolio_value", "DEFAULT_HOLDINGS", "demo_holdings")
        for name in ("real_portfolio_performance.py", "real_portfolio_concentration.py"):
            text = Path(f"investment_ami/decision_support/{name}").read_text(encoding="utf-8")
            for line in text.splitlines():
                if "holdings_df_mismatch" in line:
                    continue
                for token in forbidden:
                    self.assertNotIn(token, line, msg=f"{name}: {line}")
            self.assertNotIn("import streamlit", text)


class TestRealPortfolioConcentration(unittest.TestCase):
    def test_single_stock_material_flag(self) -> None:
        txns = [_deposit(50_000.0), _buy("AAPL", 100, 150.0, asset_type="stock")]
        prices = {"AAPL": 200.0}
        snap = _snap(txns, prices)
        conc = analyze_real_portfolio_concentration(snap)
        self.assertTrue(
            any("material_single" in f for f in conc.single_security_concentration_flags)
            or any(o.code == "material_single_security_weight" for o in conc.observations)
        )

    def test_broad_etf_not_single_company_flag(self) -> None:
        txns = [_deposit(20_000.0), _buy("VOO", 30, 400.0)]
        snap = _snap(txns, {"VOO": 450.0})
        conc = analyze_real_portfolio_concentration(snap)
        self.assertFalse(any("material_single_security" in f for f in conc.single_security_concentration_flags))
        self.assertTrue(any(o.code == "broad_market_etf_weight" for o in conc.observations))

    def test_narrow_etf_observation(self) -> None:
        txns = [_deposit(30_000.0), _buy("QQQ", 40, 300.0)]
        snap = _snap(txns, {"QQQ": 350.0})
        conc = analyze_real_portfolio_concentration(snap)
        clf = classify_holding_security(snap.holdings[0])
        self.assertEqual(clf.kind, "narrow_or_thematic_etf")
        self.assertTrue(any(o.code == "narrow_or_thematic_etf_weight" for o in conc.observations))

    def test_top_n_and_hhi(self) -> None:
        txns = [
            _deposit(100_000.0),
            _buy("VOO", 10, 400.0),
            _buy("BND", 10, 80.0),
            _buy("VXUS", 10, 50.0),
        ]
        snap = _snap(txns, {"VOO": 450.0, "BND": 82.0, "VXUS": 55.0})
        conc = analyze_real_portfolio_concentration(snap)
        self.assertGreater(conc.largest_holding_weight, 0)
        self.assertGreaterEqual(conc.top_three_weight, conc.largest_holding_weight)
        self.assertGreaterEqual(conc.top_five_weight, conc.top_three_weight)
        self.assertGreater(conc.hhi, 0)
        self.assertIsNotNone(conc.effective_number_of_positions)

    def test_unknown_metadata_low_confidence(self) -> None:
        from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot
        from datetime import datetime, timezone

        holding = RealHoldingSnapshot(
            ticker="ZZZZ",
            name="ZZZZ",
            shares=10,
            average_cost=10,
            total_cost_basis=100,
            current_price=12,
            current_value=120,
            gain_loss_dollars=20,
            gain_loss_pct=20,
            current_weight=100,
            target_weight=None,
            asset_class="Crypto",
            price_source="test",
            price_as_of=datetime.now(timezone.utc),
        )
        snap = RealPortfolioSnapshot(
            as_of=datetime.now(timezone.utc),
            market_data_status="fresh",
            market_data_age_seconds=0,
            data_source="real_portfolio_engine",
            total_market_value=120,
            total_cost_basis=100,
            total_gain_loss_dollars=20,
            total_gain_loss_pct=20,
            priced_holdings_gain_loss_pct=20,
            cash=0,
            holdings=(holding,),
            allocation_by_holding={"ZZZZ": 100.0},
            allocation_by_asset_class={"Crypto": 100.0},
            largest_positions=(holding,),
            concentration_metrics={},
        )
        conc = analyze_real_portfolio_concentration(snap, security_metadata={"ZZZZ": {}})
        self.assertTrue(
            any(o.code == "unknown_security_type" for o in conc.observations)
            or conc.concentration_status == "unknown_metadata"
        )

    def test_missing_price_partial_concentration(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BAD", 2, 10.0)]
        snap = _snap(txns, {"VOO": 450.0})
        conc = analyze_real_portfolio_concentration(snap)
        self.assertEqual(conc.concentration_status, "partial_data")
        self.assertIn("missing_prices", conc.data_quality_flags)

    def test_negative_cash_flag_propagates_to_performance(self) -> None:
        txns = [_buy("VOO", 10, 400.0)]
        snap = _snap(txns, {"VOO": 450.0})
        perf = analyze_real_portfolio_performance(snap)
        self.assertIn("negative_cash_balance", perf.data_quality_flags)


if __name__ == "__main__":
    unittest.main()
