"""Tests for ledger-backed RealPortfolioSnapshot (Phase A)."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import pandas as pd
import portfolio_core as core
import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_snapshot import (
    build_real_portfolio_snapshot,
    build_real_portfolio_snapshot_copy_safe,
)


def _buy(ticker: str, qty: float, price: float, *, day: str = "2024-01-15") -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        company_name=ticker,
        asset_type="etf",
    ).to_record()


def _deposit(amount: float, *, day: str = "2024-01-01") -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date=day,
        ticker="",
        quantity=amount,
        execution_price=1.0,
    ).to_record()


class TestRealPortfolioSnapshotLedger(unittest.TestCase):
    def test_ledger_only_marks_and_weights(self) -> None:
        txns = [
            _deposit(50_000.0),
            _buy("VOO", 10, 400.0),
            _buy("VOO", 5, 430.0),
            _buy("BND", 20, 80.0),
        ]
        prices = {"VOO": 450.0, "BND": 82.0}
        result = build_real_portfolio_snapshot(
            {"portfolio_transactions": txns},
            prices=prices,
        )
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        snap = result.snapshot
        self.assertEqual(snap.data_source, "real_portfolio_engine")
        voo = next(h for h in snap.holdings if h.ticker == "VOO")
        self.assertAlmostEqual(voo.shares, 15.0)
        self.assertAlmostEqual(voo.average_cost, (10 * 400 + 5 * 430) / 15, places=2)
        self.assertAlmostEqual(voo.current_value, 15 * 450.0)
        self.assertAlmostEqual(voo.gain_loss_dollars or 0, voo.current_value - voo.total_cost_basis, places=2)
        bnd = next(h for h in snap.holdings if h.ticker == "BND")
        self.assertAlmostEqual(bnd.current_value, 20 * 82.0)
        expected_total = 15 * 450.0 + 20 * 82.0 + snap.cash
        self.assertAlmostEqual(snap.total_market_value, expected_total, places=2)
        self.assertAlmostEqual(
            snap.total_cost_basis,
            voo.total_cost_basis + bnd.total_cost_basis,
            places=2,
        )
        self.assertAlmostEqual(sum(snap.allocation_by_holding.values()), 100.0, places=1)
        self.assertIn("$CASH", snap.allocation_by_holding)

    def test_cash_included(self) -> None:
        txns = [_deposit(5000.0), _buy("VTI", 10, 200.0)]
        prices = {"VTI": 210.0}
        result = build_real_portfolio_snapshot({"portfolio_transactions": txns}, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        snap = result.snapshot
        self.assertAlmostEqual(snap.cash, 5000.0 - 10 * 200.0, places=2)
        self.assertAlmostEqual(snap.total_market_value, 10 * 210.0 + snap.cash, places=2)


class TestRealPortfolioSnapshotFailures(unittest.TestCase):
    def test_no_real_ledger_despite_holdings_df(self) -> None:
        df = pd.DataFrame(core.DEFAULT_HOLDINGS)
        result = build_real_portfolio_snapshot(
            {
                "holdings_df": df,
                "sidebar_portfolio_value": 100_000,
                "portfolio_transactions": [],
            }
        )
        self.assertFalse(result.ok)
        assert result.failure is not None
        self.assertEqual(result.failure.code, "no_real_ledger")

    def test_missing_price_partial_snapshot(self) -> None:
        txns = [_buy("VOO", 5, 400.0), _buy("BADTK", 3, 10.0)]
        prices = {"VOO": 450.0}
        result = build_real_portfolio_snapshot({"portfolio_transactions": txns}, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        snap = result.snapshot
        bad = next(h for h in snap.holdings if h.ticker == "BADTK")
        self.assertIsNone(bad.current_price)
        self.assertIn("missing_price", bad.data_quality_flags)
        self.assertIsNone(bad.gain_loss_dollars)
        self.assertIn("missing_prices", snap.data_quality_flags)
        self.assertEqual(snap.market_data_status, "partial")
        self.assertIsNone(snap.total_gain_loss_pct)
        self.assertIsNotNone(snap.priced_holdings_gain_loss_pct)
        self.assertAlmostEqual(snap.known_marked_securities_value, 5 * 450.0, places=2)

    def test_no_sidebar_or_plan_value_fallback(self) -> None:
        txns = [_deposit(1000.0), _buy("SPY", 2, 500.0)]
        prices = {"SPY": 520.0}
        ledger_total = 2 * 520.0 + (1000.0 - 2 * 500.0)
        result = build_real_portfolio_snapshot(
            {
                "portfolio_transactions": txns,
                "sidebar_portfolio_value": 100_000,
                "applied_plan_portfolio_value": 58_451,
                "investment_plan_applied_portfolio_value": 58_451,
            },
            prices=prices,
        )
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        self.assertAlmostEqual(result.snapshot.total_market_value, ledger_total, places=2)
        self.assertNotAlmostEqual(result.snapshot.total_market_value, 100_000.0, places=0)
        self.assertNotAlmostEqual(result.snapshot.total_market_value, 58_451.0, places=0)


class TestRealPortfolioSnapshotIsolation(unittest.TestCase):
    def test_snapshot_module_does_not_import_demo_defaults(self) -> None:
        from pathlib import Path

        text = Path("investment_ami/decision_support/real_portfolio_snapshot.py").read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_HOLDINGS", text)
        self.assertNotIn("portfolio_demo", text)
        self.assertNotIn("PORTFOLIO_PRESETS", text)
        self.assertNotIn('.get("sidebar_portfolio_value")', text)

    @patch("portfolio_core.DEFAULT_HOLDINGS", [{"Ticker": "FAKE", "Weight (%)": 100.0}])
    def test_default_holdings_not_used_when_transactions_empty(self) -> None:
        result = build_real_portfolio_snapshot(
            {"holdings_df": pd.DataFrame([{"Ticker": "FAKE", "Weight (%)": 100.0}])},
            prices={"FAKE": 1.0},
        )
        self.assertFalse(result.ok)


class TestHoldingsDfMismatch(unittest.TestCase):
    def test_material_mismatch_warns(self) -> None:
        txns = [_buy("VOO", 10, 400.0)]
        prices = {"VOO": 450.0}
        df = pd.DataFrame([{"Ticker": "BND", "Weight (%)": 100.0, "Asset Type": "Bond"}])
        result = build_real_portfolio_snapshot(
            {"portfolio_transactions": txns, "holdings_df": df},
            prices=prices,
        )
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        self.assertIsNotNone(result.snapshot.holdings_df_mismatch_warning)

    def test_small_weight_diff_no_warning(self) -> None:
        txns = [_buy("VOO", 10, 400.0), _buy("BND", 10, 80.0)]
        prices = {"VOO": 450.0, "BND": 82.0}
        result = build_real_portfolio_snapshot({"portfolio_transactions": txns}, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        voo_w = result.snapshot.allocation_by_holding["VOO"]
        bnd_w = result.snapshot.allocation_by_holding["BND"]
        df = pd.DataFrame(
            [
                {"Ticker": "VOO", "Weight (%)": voo_w + 0.5, "Asset Type": "Equity"},
                {"Ticker": "BND", "Weight (%)": bnd_w - 0.5, "Asset Type": "Bond"},
            ]
        )
        result2 = build_real_portfolio_snapshot(
            {"portfolio_transactions": txns, "holdings_df": df},
            prices=prices,
        )
        assert result2.snapshot is not None
        self.assertIsNone(result2.snapshot.holdings_df_mismatch_warning)


class TestTargetWeightsNormalization(unittest.TestCase):
    """Regression: Health caches target_weights as '60.0%' strings — must not crash snapshot."""

    def _ledger_session(self, **extra):
        txns = [
            _deposit(20_000.0),
            _buy("VOO", 10, 400.0),
            _buy("QQQ", 5, 300.0),
            _buy("BND", 50, 80.0),
        ]
        prices = {"VOO": 420.0, "QQQ": 280.0, "BND": 78.0}
        ss = {"portfolio_transactions": txns, **extra}
        return ss, prices

    def test_live_health_percent_string_shape_does_not_crash(self) -> None:
        # Exact shape from applied_math_context.record_rebalance_from_health.
        ss, prices = self._ledger_session(
            target_weights={
                "VOO": "50.0%",
                "QQQ": "20.0%",
                "BND": "20.0%",
                "VXUS": "10.0%",
            },
            rebalance_drift={
                "VOO": "+2.0pp",
                "QQQ": "-7.0pp",
                "BND": "0.0pp",
                "VXUS": "+5.0pp",
            },
        )
        result = build_real_portfolio_snapshot(ss, prices=prices)
        self.assertTrue(result.ok, msg=str(getattr(result.failure, "message", None)))
        assert result.snapshot is not None
        # Health display strings are NOT promoted to authoritative real target.
        self.assertIsNone(result.snapshot.target_allocation)
        # Optional per-holding display may parse percent strings.
        voo = next(h for h in result.snapshot.holdings if h.ticker == "VOO")
        self.assertAlmostEqual(float(voo.target_weight or 0), 50.0, places=1)

    def test_plain_numeric_decimals(self) -> None:
        from investment_ami.decision_support.real_portfolio_snapshot import extract_numeric_weight_map

        self.assertEqual(
            extract_numeric_weight_map({"VOO": 0.5, "BND": 0.5}),
            {"VOO": 0.5, "BND": 0.5},
        )

    def test_numeric_percent_strings(self) -> None:
        from investment_ami.decision_support.real_portfolio_snapshot import (
            extract_numeric_weight_map,
            parse_weight_like_value,
        )

        self.assertEqual(parse_weight_like_value("60%"), 60.0)
        self.assertEqual(parse_weight_like_value("60.0%"), 60.0)
        self.assertEqual(parse_weight_like_value("60"), 60.0)
        self.assertEqual(
            extract_numeric_weight_map({"Equity": "60%", "Bonds": "40%"}),
            {"Equity": 60.0, "Bonds": 40.0},
        )

    def test_nested_mixed_metadata_skipped(self) -> None:
        from investment_ami.decision_support.real_portfolio_snapshot import extract_numeric_weight_map

        raw = {
            "VOO": "50.0%",
            "source": "health_rebalance",
            "label": "model",
            "meta": {"nested": True},
            "BND": {"weight": 20},
            "QQQ": None,
        }
        self.assertEqual(extract_numeric_weight_map(raw), {"VOO": 50.0})

    def test_malformed_values_skipped(self) -> None:
        from investment_ami.decision_support.real_portfolio_snapshot import parse_weight_like_value

        self.assertIsNone(parse_weight_like_value("+2.5pp"))
        self.assertIsNone(parse_weight_like_value("n/a"))
        self.assertIsNone(parse_weight_like_value(True))
        self.assertIsNone(parse_weight_like_value({"a": 1}))

    def test_missing_target_weights_ok(self) -> None:
        ss, prices = self._ledger_session()
        result = build_real_portfolio_snapshot(ss, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        self.assertIsNone(result.snapshot.target_allocation)

    def test_explicit_real_target_still_attached(self) -> None:
        ss, prices = self._ledger_session(
            target_weights={"VOO": "99.0%"},  # Health noise — ignored for target_allocation
            real_portfolio_target_allocation={"Equity": 60.0, "Bonds": 40.0},
        )
        result = build_real_portfolio_snapshot(ss, prices=prices)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        self.assertEqual(result.snapshot.target_allocation, {"Equity": 60.0, "Bonds": 40.0})

    def test_allocate_new_money_path_with_health_strings(self) -> None:
        from investment_ami.decision_support.contribution_advisor import (
            STATUS_TARGET_NOT_DEFINED,
            recommend_contribution_allocation,
        )

        ss, prices = self._ledger_session(
            target_weights={"VOO": "50.0%", "QQQ": "20.0%", "BND": "30.0%"},
            rebalance_drift={"VOO": "+1.0pp"},
        )
        built = build_real_portfolio_snapshot(ss, prices=prices)
        self.assertTrue(built.ok)
        # Without an explicit Contribution Advisor target source selection → clear block.
        blocked = recommend_contribution_allocation(
            snapshot=built.snapshot,
            contribution_amount=1000.0,
            target_source="user_explicit",
            explicit_holding_targets=None,
        )
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.status, STATUS_TARGET_NOT_DEFINED)
        # Recommended path still works after snapshot boots.
        ok = recommend_contribution_allocation(
            snapshot=built.snapshot,
            contribution_amount=1000.0,
            target_source="stated_objective_recommended",
            health_objective="balanced growth",
            include_cash=False,
        )
        self.assertTrue(ok.ok)


class TestSnapshotQuotePathAlignment(unittest.TestCase):
    def test_uses_dashboard_batch_quotes_not_avg_cost_fallback(self) -> None:
        """Snapshot must share get_latest_quotes with Dashboard and never avg-cost mark."""
        from unittest.mock import MagicMock, patch

        txns = [
            _deposit(10_000.0),
            _buy("VTI", 10, 200.0),
            _buy("BADTK", 5, 10.0),
        ]
        ss = {"portfolio_transactions": txns}
        provider = MagicMock()
        provider.get_latest_quotes.return_value = {
            "VTI": (210.0, "yfinance_batch_close"),
            "BADTK": (None, ""),
        }
        provider.get_spot_quote_freshness.side_effect = lambda sym: (
            (210.0, "yfinance_batch_close", 1_700_000_000.0) if sym == "VTI" else (None, "", None)
        )
        with patch(
            "investment_market_data.get_market_data_provider",
            return_value=provider,
        ):
            result = build_real_portfolio_snapshot(ss)
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        provider.get_latest_quotes.assert_called()
        vti = next(h for h in result.snapshot.holdings if h.ticker == "VTI")
        bad = next(h for h in result.snapshot.holdings if h.ticker == "BADTK")
        self.assertAlmostEqual(float(vti.current_price or 0), 210.0)
        self.assertIsNone(bad.current_price)
        self.assertIn("missing_price", bad.data_quality_flags)
        # Dashboard would avg-cost BADTK at $10; snapshot must not.
        self.assertNotAlmostEqual(bad.current_value, 5 * 10.0)
        from investment_ami.decision_support.real_portfolio_snapshot import unpriced_holding_tickers

        self.assertEqual(unpriced_holding_tickers(result.snapshot), ("BADTK",))

    def test_skip_spot_cash_ticker_flagged_not_fabricated(self) -> None:
        txns = [
            _deposit(5_000.0),
            pe.PortfolioTransaction(
                id=pe._new_id(),
                action="buy",
                date="2024-01-15",
                ticker="CASH",
                quantity=100.0,
                execution_price=1.0,
                company_name="Cash",
                asset_type="cash",
            ).to_record(),
        ]
        result = build_real_portfolio_snapshot({"portfolio_transactions": txns}, prices={})
        self.assertTrue(result.ok)
        assert result.snapshot is not None
        cash_pos = next(h for h in result.snapshot.holdings if h.ticker == "CASH")
        self.assertIsNone(cash_pos.current_price)
        self.assertIn("missing_price", cash_pos.data_quality_flags)
        self.assertIn("non_market_quoted_instrument", cash_pos.data_quality_flags)


class TestRealPortfolioSnapshotNoMutation(unittest.TestCase):
    def test_build_does_not_mutate_session(self) -> None:
        txns = [_deposit(2000.0), _buy("VTI", 5, 100.0)]
        ss = {
            "portfolio_transactions": txns,
            "holdings_df": pd.DataFrame(core.DEFAULT_HOLDINGS),
            "sidebar_portfolio_value": 100_000,
            "applied_plan_portfolio_value": 58_451,
        }
        before = copy.deepcopy(ss)
        before_txn = copy.deepcopy(ss["portfolio_transactions"])
        result = build_real_portfolio_snapshot_copy_safe(ss, prices={"VTI": 105.0})
        self.assertTrue(result.ok)
        self.assertEqual(ss["portfolio_transactions"], before_txn)
        self.assertEqual(ss["sidebar_portfolio_value"], before["sidebar_portfolio_value"])
        pd.testing.assert_frame_equal(ss["holdings_df"], before["holdings_df"])


if __name__ == "__main__":
    unittest.main()
