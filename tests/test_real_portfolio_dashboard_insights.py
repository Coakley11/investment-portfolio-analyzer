"""Dashboard insights A/B/C — financial labels, $ drivers, strategy status thresholds."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_dashboard_insights import (
    STRATEGY_MILD_DRIFT_MAX_ABS_PP,
    STRATEGY_ON_TARGET_MAX_ABS_PP,
    analyze_strategy_status,
    best_and_worst_dollar_contributors,
    classify_strategy_status,
    financial_performance_from_engine,
    holding_performance_drivers,
)


def _pos(ticker: str, *, mv: float, cost: float, weight: float, gl: float | None = None) -> SimpleNamespace:
    shares = 10.0
    avg = cost / shares if shares else 0.0
    gain = (mv - cost) if gl is None else gl
    pct = (gain / cost * 100.0) if cost > 0 else 0.0
    return SimpleNamespace(
        ticker=ticker,
        market_value=mv,
        shares_owned=shares,
        average_cost_basis=avg,
        gain_loss_dollar=gain,
        gain_loss_pct=pct,
        weight_pct=weight,
    )


class TestStrategyStatusThresholds(unittest.TestCase):
    def test_boundaries_deterministic(self) -> None:
        self.assertEqual(STRATEGY_ON_TARGET_MAX_ABS_PP, 2.0)
        self.assertEqual(STRATEGY_MILD_DRIFT_MAX_ABS_PP, 5.0)
        # < 2 → On Target
        self.assertEqual(classify_strategy_status(0.0), "On Target")
        self.assertEqual(classify_strategy_status(1.999), "On Target")
        # 2 ≤ x < 5 → Mild
        self.assertEqual(classify_strategy_status(2.0), "Mild Drift")
        self.assertEqual(classify_strategy_status(4.999), "Mild Drift")
        # ≥ 5 → Significant
        self.assertEqual(classify_strategy_status(5.0), "Significant Drift")
        self.assertEqual(classify_strategy_status(12.0), "Significant Drift")
        # Absolute value
        self.assertEqual(classify_strategy_status(-2.0), "Mild Drift")
        self.assertEqual(classify_strategy_status(-5.0), "Significant Drift")

    def test_on_target_shadow_like(self) -> None:
        saved = {"VTI": 35.0, "VXUS": 25.0, "BND": 30.0, "VNQ": 10.0}
        live = {"VTI": 34.93, "VXUS": 25.12, "BND": 29.93, "VNQ": 10.01}
        result = analyze_strategy_status(live_weights_pct=live, saved_strategy_pct=saved)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "On Target")
        self.assertLess(result.max_abs_drift_pp, 2.0)
        # Saved target unchanged / authoritative copy
        self.assertEqual(result.saved_target_pct["VTI"], 35.0)
        self.assertEqual(saved["VTI"], 35.0)

    def test_mild_and_significant(self) -> None:
        saved = {"VTI": 50.0, "BND": 50.0}
        mild = analyze_strategy_status(
            live_weights_pct={"VTI": 53.0, "BND": 47.0},
            saved_strategy_pct=saved,
        )
        self.assertEqual(mild.status, "Mild Drift")
        self.assertAlmostEqual(mild.max_abs_drift_pp, 3.0, places=6)

        big = analyze_strategy_status(
            live_weights_pct={"VTI": 60.0, "BND": 40.0},
            saved_strategy_pct=saved,
        )
        self.assertEqual(big.status, "Significant Drift")
        self.assertAlmostEqual(big.max_abs_drift_pp, 10.0, places=6)

    def test_missing_strategy_does_not_invent_from_live(self) -> None:
        result = analyze_strategy_status(
            live_weights_pct={"VTI": 60.0, "BND": 40.0},
            saved_strategy_pct=None,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "No Strategy Target")
        self.assertEqual(result.saved_target_pct, {})

    def test_does_not_mutate_saved_strategy(self) -> None:
        saved = {"VTI": 35.0, "BND": 30.0, "VXUS": 25.0, "VNQ": 10.0}
        before = dict(saved)
        analyze_strategy_status(
            live_weights_pct={"VTI": 40.0, "BND": 25.0, "VXUS": 25.0, "VNQ": 10.0},
            saved_strategy_pct=saved,
        )
        self.assertEqual(saved, before)


class TestFinancialAndDrivers(unittest.TestCase):
    def test_financial_snapshot_labels_unrealized_not_nav_minus_contributions(self) -> None:
        # NAV 6000, contributions 5250, unrealized 50 — must not report 750 as "gain"
        snap = financial_performance_from_engine(
            total_portfolio_value=6000.0,
            securities_market_value=5950.0,
            cash_balance=50.0,
            net_external_contributions=5250.0,
            securities_cost_basis=5900.0,
            unrealized_gain_loss_dollar=50.0,
            num_holdings=4,
        )
        self.assertAlmostEqual(snap.unrealized_gain_loss_dollar, 50.0)
        self.assertAlmostEqual(snap.unrealized_gain_loss_pct, 50.0 / 5900.0 * 100.0, places=6)
        self.assertAlmostEqual(snap.net_external_contributions, 5250.0)
        self.assertNotAlmostEqual(snap.nav - snap.net_external_contributions, snap.unrealized_gain_loss_dollar)

    def test_deposit_does_not_create_unrealized_profit_in_engine(self) -> None:
        txns = [
            pe.PortfolioTransaction(
                id="d1",
                action="cash_deposit",
                date="2024-01-01",
                ticker="",
                quantity=5000.0,
                execution_price=1.0,
            ),
            pe.PortfolioTransaction(
                id="b1",
                action="buy",
                date="2024-01-02",
                ticker="VTI",
                quantity=20.0,
                execution_price=200.0,
                asset_type="etf",
            ),
        ]
        prices = {"VTI": 200.0}
        before = pe.compute_portfolio_summary(txns, prices=prices)
        cash_before = pe.compute_cash_ledger_summary(txns)
        txns2 = txns + [
            pe.PortfolioTransaction(
                id="d2",
                action="cash_deposit",
                date="2024-06-01",
                ticker="",
                quantity=1000.0,
                execution_price=1.0,
            )
        ]
        after = pe.compute_portfolio_summary(txns2, prices=prices)
        cash_after = pe.compute_cash_ledger_summary(txns2)
        self.assertAlmostEqual(after.total_gain_loss_dollar, before.total_gain_loss_dollar, places=2)
        self.assertAlmostEqual(cash_after.total_deposits - cash_before.total_deposits, 1000.0, places=2)

    def test_best_worst_use_dollar_not_percent(self) -> None:
        # High % small $ vs low % large $
        positions = [
            _pos("TINY", mv=110.0, cost=100.0, weight=2.0),  # +10 (+10%)
            _pos("BIG", mv=5500.0, cost=5000.0, weight=90.0),  # +500 (+10%)
            _pos("LOSER", mv=800.0, cost=1000.0, weight=8.0),  # -200 (-20%)
        ]
        # Adjust TINY to huge % small $
        positions[0] = _pos("TINY", mv=150.0, cost=100.0, weight=2.0)  # +50 (+50%)
        rows = holding_performance_drivers(positions)
        best, worst = best_and_worst_dollar_contributors(rows)
        assert best is not None and worst is not None
        self.assertEqual(best.ticker, "BIG")  # +500 beats +50
        self.assertEqual(worst.ticker, "LOSER")
        self.assertAlmostEqual(
            sum(r.contribution_to_aggregate_unrealized_dollar for r in rows),
            50.0 + 500.0 - 200.0,
            places=4,
        )

    def test_drivers_sum_matches_portfolio_unrealized(self) -> None:
        txns = [
            pe.PortfolioTransaction(
                id="d1", action="cash_deposit", date="2024-01-01", ticker="", quantity=10_000.0, execution_price=1.0
            ),
            pe.PortfolioTransaction(
                id="b1", action="buy", date="2024-01-02", ticker="VTI", quantity=35.0, execution_price=100.0, asset_type="etf"
            ),
            pe.PortfolioTransaction(
                id="b2", action="buy", date="2024-01-02", ticker="BND", quantity=30.0, execution_price=100.0, asset_type="etf"
            ),
            pe.PortfolioTransaction(
                id="b3", action="buy", date="2024-01-02", ticker="VXUS", quantity=25.0, execution_price=100.0, asset_type="etf"
            ),
            pe.PortfolioTransaction(
                id="b4", action="buy", date="2024-01-02", ticker="VNQ", quantity=10.0, execution_price=100.0, asset_type="etf"
            ),
        ]
        prices = {"VTI": 110.0, "BND": 95.0, "VXUS": 100.0, "VNQ": 90.0}
        summary = pe.compute_portfolio_summary(txns, prices=prices)
        positions, _ = pe.build_positions(txns, prices=prices)
        rows = holding_performance_drivers(positions)
        self.assertAlmostEqual(
            sum(r.contribution_to_aggregate_unrealized_dollar for r in rows),
            summary.total_gain_loss_dollar,
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
