"""Contribution Advisor — new-money-only engine + real-portfolio gates."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import portfolio_core as core
import portfolio_engine as pe

from investment_ami.decision_support.contribution_allocation_engine import (
    DOLLAR_SUM_TOLERANCE,
    allocate_contribution_new_money_only,
)
from investment_ami.decision_support.contribution_advisor import (
    STATUS_MISSING_PRICES,
    STATUS_NO_REAL_PORTFOLIO,
    STATUS_STALE_PRICES,
    STATUS_TARGET_NOT_DEFINED,
    recommend_contribution_allocation,
    recommend_contribution_allocation_from_session,
)
from investment_ami.decision_support.real_portfolio_models import (
    RealHoldingSnapshot,
    RealPortfolioSnapshot,
)
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot


def _buy(ticker: str, qty: float, price: float, *, day: str = "2024-01-15", asset: str = "etf") -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        company_name=ticker,
        asset_type=asset,
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


def _holding(
    ticker: str,
    value: float,
    weight: float,
    *,
    asset_class: str = "ETFs",
    price: float | None = 100.0,
    flags: tuple[str, ...] = (),
) -> RealHoldingSnapshot:
    shares = (value / price) if price else 0.0
    return RealHoldingSnapshot(
        ticker=ticker,
        name=ticker,
        shares=shares,
        average_cost=float(price or 0.0),
        total_cost_basis=value,
        current_price=price,
        current_value=value,
        gain_loss_dollars=0.0 if price is not None else None,
        gain_loss_pct=0.0 if price is not None else None,
        current_weight=weight,
        target_weight=None,
        asset_class=asset_class,
        price_source="test",
        price_as_of=datetime.now(timezone.utc) if price is not None else None,
        data_quality_flags=flags,
    )


def _snapshot_from_values(
    values: dict[str, float],
    *,
    classes: dict[str, str] | None = None,
    cash: float = 0.0,
    health_objective: str = "balanced growth",
    market_data_status: str = "fresh",
    market_data_age_seconds: int | None = 10,
    unpriced: int = 0,
    flags: tuple[str, ...] = (),
) -> RealPortfolioSnapshot:
    classes = classes or {}
    total = sum(values.values()) + cash
    holdings = []
    for t, v in values.items():
        w = (v / total * 100.0) if total else 0.0
        holdings.append(
            _holding(
                t,
                v,
                w,
                asset_class=classes.get(t, "ETFs"),
                price=100.0,
            )
        )
    return RealPortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        market_data_status=market_data_status,  # type: ignore[arg-type]
        market_data_age_seconds=market_data_age_seconds,
        data_source="real_portfolio_engine",
        total_market_value=total,
        total_cost_basis=sum(values.values()),
        total_gain_loss_dollars=0.0,
        total_gain_loss_pct=0.0,
        priced_holdings_gain_loss_pct=0.0,
        cash=cash,
        holdings=tuple(holdings),
        allocation_by_holding={**{k: (v / total * 100 if total else 0) for k, v in values.items()}, **({"$CASH": cash / total * 100} if cash and total else {})},
        allocation_by_asset_class={},
        largest_positions=tuple(holdings[:3]),
        concentration_metrics={},
        health_objective=health_objective,
        data_quality_flags=flags,
        known_marked_securities_value=sum(values.values()),
        unpriced_holdings_count=unpriced,
    )


class TestContributionEngineCases(unittest.TestCase):
    def test_a_underweight_asset_gets_most_new_money(self) -> None:
        # VOO overweight, QQQ underweight vs 50/50.
        values = {"VOO": 7000.0, "QQQ": 3000.0}
        targets = {"VOO": 0.50, "QQQ": 0.50}
        result = allocate_contribution_new_money_only(
            current_values=values, target_weights=targets, contribution=1000.0
        )
        self.assertTrue(result.ok)
        by = {r.ticker: r for r in result.rows}
        self.assertGreater(by["QQQ"].recommended_add, by["VOO"].recommended_add)
        self.assertGreater(by["QQQ"].recommended_add, 700.0)
        self.assertAlmostEqual(by["QQQ"].projected_value, 3000.0 + by["QQQ"].recommended_add, places=4)
        self.assertAlmostEqual(sum(r.recommended_add for r in result.rows), 1000.0, delta=DOLLAR_SUM_TOLERANCE)

    def test_b_already_balanced_follows_target_weights(self) -> None:
        values = {"VOO": 5000.0, "BND": 5000.0}
        targets = {"VOO": 0.50, "BND": 0.50}
        result = allocate_contribution_new_money_only(
            current_values=values, target_weights=targets, contribution=1000.0
        )
        self.assertTrue(result.ok)
        by = {r.ticker: r for r in result.rows}
        self.assertAlmostEqual(by["VOO"].recommended_add, 500.0, delta=1.0)
        self.assertAlmostEqual(by["BND"].recommended_add, 500.0, delta=1.0)
        self.assertIn("close to the selected target", result.explanation.lower())

    def test_c_overweight_receives_zero_while_underweights_absorb(self) -> None:
        # Example-shaped portfolio from the roadmap (scaled dollars).
        values = {"VOO": 5200.0, "QQQ": 1300.0, "BND": 2000.0, "VXUS": 1500.0}
        targets = {"VOO": 0.50, "QQQ": 0.20, "BND": 0.20, "VXUS": 0.10}
        # C within underweight capacity so overweight names stay at $0.
        result = allocate_contribution_new_money_only(
            current_values=values, target_weights=targets, contribution=800.0
        )
        self.assertTrue(result.ok)
        by = {r.ticker: r for r in result.rows}
        self.assertAlmostEqual(by["VOO"].recommended_add, 0.0, delta=0.02)
        self.assertAlmostEqual(by["VXUS"].recommended_add, 0.0, delta=0.02)
        self.assertGreater(by["QQQ"].recommended_add, 0.0)
        self.assertAlmostEqual(by["QQQ"].recommended_add, 800.0, delta=0.02)
        for r in result.rows:
            self.assertGreaterEqual(r.recommended_add, -1e-9)

    def test_d_contribution_too_small_leaves_remaining_drift(self) -> None:
        values = {"VOO": 8000.0, "QQQ": 2000.0}
        targets = {"VOO": 0.50, "QQQ": 0.50}
        result = allocate_contribution_new_money_only(
            current_values=values, target_weights=targets, contribution=200.0
        )
        self.assertTrue(result.ok)
        self.assertGreater(result.aggregate_drift_after, 0.05)
        self.assertLess(result.aggregate_drift_after, result.aggregate_drift_before)
        by = {r.ticker: r for r in result.rows}
        self.assertAlmostEqual(by["VOO"].recommended_add, 0.0, delta=0.02)
        self.assertAlmostEqual(by["QQQ"].recommended_add, 200.0, delta=0.02)

    def test_e_large_contribution_fills_then_prorata(self) -> None:
        values = {"VOO": 7000.0, "QQQ": 3000.0}
        targets = {"VOO": 0.50, "QQQ": 0.50}
        result = allocate_contribution_new_money_only(
            current_values=values, target_weights=targets, contribution=10_000.0
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.meta.get("filled_then_prorata"))
        by = {r.ticker: r for r in result.rows}
        # Phase-1 fills QQQ underweight; remainder is pro-rata (VOO may get remainder only).
        self.assertGreater(by["QQQ"].recommended_add, by["VOO"].recommended_add)
        self.assertGreater(by["VOO"].recommended_add, 0.0)
        self.assertLess(result.aggregate_drift_after, result.aggregate_drift_before)
        # Without sales, exact 50/50 may be unreachable; QQQ should move closer to target.
        self.assertLess(abs(by["QQQ"].remaining_drift), abs(by["QQQ"].drift))

    def test_f_market_values_change_changes_recommendation(self) -> None:
        targets = {"VOO": 0.50, "QQQ": 0.50}
        m1 = allocate_contribution_new_money_only(
            current_values={"VOO": 6000.0, "QQQ": 4000.0},
            target_weights=targets,
            contribution=1000.0,
        )
        m2 = allocate_contribution_new_money_only(
            current_values={"VOO": 4500.0, "QQQ": 5500.0},  # QQQ now overweight
            target_weights=targets,
            contribution=1000.0,
        )
        a1 = {r.ticker: r.recommended_add for r in m1.rows}
        a2 = {r.ticker: r.recommended_add for r in m2.rows}
        self.assertGreater(a1["QQQ"], a1["VOO"])
        self.assertGreater(a2["VOO"], a2["QQQ"])

    def test_k_math_invariants(self) -> None:
        values = {"VOO": 5200.0, "QQQ": 1300.0, "BND": 2000.0, "VXUS": 1500.0}
        targets = {"VOO": 50, "QQQ": 20, "BND": 20, "VXUS": 10}  # percent form
        c = 1234.56
        result = allocate_contribution_new_money_only(
            current_values=values, target_weights=targets, contribution=c
        )
        self.assertTrue(result.ok)
        adds = [r.recommended_add for r in result.rows]
        self.assertAlmostEqual(sum(adds), c, delta=DOLLAR_SUM_TOLERANCE)
        self.assertTrue(all(a >= -1e-9 for a in adds))
        for r in result.rows:
            self.assertAlmostEqual(r.projected_value, r.current_value + r.recommended_add, places=4)
        self.assertAlmostEqual(sum(r.projected_weight for r in result.rows), 1.0, delta=1e-6)
        self.assertAlmostEqual(
            result.portfolio_value_after,
            result.portfolio_value_before + c,
            places=4,
        )


class TestContributionAdvisorGates(unittest.TestCase):
    def test_h_no_real_portfolio_ignores_default_holdings(self) -> None:
        result = recommend_contribution_allocation_from_session(
            {
                "holdings_df": __import__("pandas").DataFrame(core.DEFAULT_HOLDINGS),
                "portfolio_transactions": [],
                "sidebar_portfolio_value": 100_000,
            },
            contribution_amount=1000.0,
            target_source="current_mix",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, STATUS_NO_REAL_PORTFOLIO)
        self.assertIn("demo or default", result.explanation.lower())

    def test_j_target_not_defined_for_user_explicit(self) -> None:
        snap = _snapshot_from_values({"VOO": 5000.0, "BND": 5000.0})
        result = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=1000.0,
            target_source="user_explicit",
            explicit_holding_targets=None,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, STATUS_TARGET_NOT_DEFINED)

    def test_i_missing_prices_block(self) -> None:
        snap = _snapshot_from_values(
            {"VOO": 5000.0},
            market_data_status="partial",
            unpriced=1,
            flags=("missing_prices",),
        )
        # Attach an unpriced holding so the warning can name it.
        from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot
        from datetime import datetime, timezone

        unpriced = RealHoldingSnapshot(
            ticker="BADTK",
            name="BADTK",
            shares=10.0,
            average_cost=10.0,
            total_cost_basis=100.0,
            current_price=None,
            current_value=0.0,
            gain_loss_dollars=None,
            gain_loss_pct=None,
            current_weight=0.0,
            target_weight=None,
            asset_class="ETFs",
            price_source="",
            price_as_of=None,
            data_quality_flags=("missing_price",),
        )
        snap = RealPortfolioSnapshot(
            as_of=snap.as_of,
            market_data_status="partial",
            market_data_age_seconds=10,
            data_source="real_portfolio_engine",
            total_market_value=snap.total_market_value,
            total_cost_basis=snap.total_cost_basis,
            total_gain_loss_dollars=None,
            total_gain_loss_pct=None,
            priced_holdings_gain_loss_pct=None,
            cash=0.0,
            holdings=snap.holdings + (unpriced,),
            allocation_by_holding=snap.allocation_by_holding,
            allocation_by_asset_class={},
            largest_positions=snap.largest_positions,
            concentration_metrics={},
            health_objective="balanced growth",
            data_quality_flags=("missing_prices",),
            known_marked_securities_value=5000.0,
            unpriced_holdings_count=1,
        )
        result = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=500.0,
            target_source="current_mix",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, STATUS_MISSING_PRICES)
        self.assertTrue(any("BADTK" in w for w in result.warnings))

    def test_i_stale_prices_block(self) -> None:
        snap = _snapshot_from_values(
            {"VOO": 5000.0, "BND": 5000.0},
            market_data_status="cached",
            market_data_age_seconds=500,
        )
        result = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=500.0,
            target_source="current_mix",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, STATUS_STALE_PRICES)

    def test_stated_objective_recommended_is_labeled(self) -> None:
        snap = _snapshot_from_values(
            {"VTI": 7000.0, "BND": 3000.0},
            classes={"VTI": "ETFs", "BND": "Bonds"},
            health_objective="balanced growth",
            cash=0.0,
        )
        # Exclude cash so sleeve math is on securities only.
        result = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=1000.0,
            target_source="stated_objective_recommended",
            include_cash=False,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.target_source, "stated_objective_recommended")
        self.assertTrue(any("not a user-saved" in a.lower() for a in result.assumptions))

    def test_user_explicit_targets_work(self) -> None:
        snap = _snapshot_from_values({"VOO": 7000.0, "QQQ": 3000.0}, cash=0.0)
        result = recommend_contribution_allocation(
            snapshot=snap,
            contribution_amount=1000.0,
            target_source="user_explicit",
            explicit_holding_targets={"VOO": 50, "QQQ": 50},
            include_cash=False,
        )
        self.assertTrue(result.ok)
        by = {r.ticker: r for r in result.rows}
        self.assertGreater(by["QQQ"].recommended_add, by["VOO"].recommended_add)


class TestDepositAccounting(unittest.TestCase):
    def test_g_deposit_is_not_investment_profit(self) -> None:
        """$1,000 deposit raises assets/contributed capital, not gain/loss profit."""
        txns = [
            _deposit(5_000.0, day="2024-01-01"),
            _buy("VTI", 20, 200.0, day="2024-01-02"),  # cost 4000; cash left 1000
        ]
        # Mark up: 20 * 215 = 4300 → market gain $300 on securities.
        prices = {"VTI": 215.0}
        before = pe.compute_portfolio_summary(
            pe.transactions_from_records(txns), prices=prices
        )
        cash_before = pe.compute_cash_ledger_summary(pe.transactions_from_records(txns))
        gain_before = before.total_gain_loss_dollar

        txns2 = txns + [_deposit(1_000.0, day="2024-06-01")]
        after = pe.compute_portfolio_summary(
            pe.transactions_from_records(txns2), prices=prices
        )
        cash_after = pe.compute_cash_ledger_summary(pe.transactions_from_records(txns2))

        self.assertAlmostEqual(cash_after.total_deposits - cash_before.total_deposits, 1000.0, places=2)
        self.assertAlmostEqual(after.total_portfolio_value - before.total_portfolio_value, 1000.0, places=2)
        # Unrealized gain unchanged by the deposit (same marks / cost basis).
        self.assertAlmostEqual(after.total_gain_loss_dollar, gain_before, places=2)
        self.assertAlmostEqual(gain_before, 300.0, places=2)

    def test_snapshot_path_for_advisor_uses_ledger(self) -> None:
        txns = [
            _deposit(20_000.0),
            _buy("VOO", 10, 400.0),
            _buy("QQQ", 5, 300.0),
            _buy("BND", 50, 80.0),
        ]
        prices = {"VOO": 420.0, "QQQ": 280.0, "BND": 78.0}
        built = build_real_portfolio_snapshot({"portfolio_transactions": txns}, prices=prices)
        self.assertTrue(built.ok)
        assert built.snapshot is not None
        result = recommend_contribution_allocation(
            snapshot=built.snapshot,
            contribution_amount=1000.0,
            target_source="user_explicit",
            explicit_holding_targets={"VOO": 40, "QQQ": 30, "BND": 20, "$CASH": 10},
            include_cash=True,
        )
        self.assertTrue(result.ok)
        self.assertAlmostEqual(sum(r.recommended_add for r in result.rows), 1000.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
