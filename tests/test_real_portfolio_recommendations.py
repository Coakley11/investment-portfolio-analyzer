"""Phase C — drift and recommendation rules on real portfolio analyses."""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_concentration import analyze_real_portfolio_concentration
from investment_ami.decision_support.real_portfolio_drift import (
    DRIFT_IMMATERIAL_PP,
    analyze_real_portfolio_drift,
)
from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot, RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import analyze_real_portfolio_performance
from investment_ami.decision_support.real_portfolio_recommendation_rules import build_real_portfolio_recommendations
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


def _snap(txns: list, prices: dict[str, float], **session_extra: object):
    ss = {"portfolio_transactions": txns, **session_extra}
    result = build_real_portfolio_snapshot(ss, prices=prices)
    assert result.ok and result.snapshot is not None
    return result.snapshot


def _pipeline(snap, **drift_kw):
    perf = analyze_real_portfolio_performance(snap)
    conc = analyze_real_portfolio_concentration(snap)
    drift = analyze_real_portfolio_drift(snap, **drift_kw)
    recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
    return perf, conc, drift, recs


class TestRealPortfolioDrift(unittest.TestCase):
    def test_immaterial_drift_no_rebalance(self) -> None:
        txns = [_deposit(5_000.0), _buy("VOO", 10, 400.0), _buy("BND", 5, 80.0)]
        snap = _snap(txns, {"VOO": 400.0, "BND": 80.0})
        targets = {
            "ETFs": round(snap.allocation_by_asset_class.get("ETFs", 0.0), 1),
            "Bonds": round(snap.allocation_by_asset_class.get("Bonds", 0.0), 1),
            "Cash": round(snap.allocation_by_asset_class.get("Cash", 0.0) or snap.allocation_by_holding.get("$CASH", 0.0), 1),
            "Stocks": 0.0,
            "Other": 0.0,
        }
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        self.assertFalse(drift.rebalance_triggered)
        self.assertIn(drift.drift_status, ("aligned", "immaterial_drift"))

    def test_material_overweight_triggers_rebalance(self) -> None:
        txns = [_deposit(2_000.0), _buy("VOO", 20, 400.0)]
        snap = _snap(txns, {"VOO": 450.0})
        targets = {"Equity": 40.0, "Bonds": 40.0, "Cash_and_TBills": 20.0}
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        self.assertTrue(drift.rebalance_triggered)
        self.assertIsNotNone(drift.largest_overweight)

    def test_material_underweight_for_contributions(self) -> None:
        txns = [_deposit(40_000.0), _buy("BND", 50, 80.0), _buy("VOO", 5, 400.0)]
        snap = _snap(txns, {"VOO": 400.0, "BND": 80.0})
        targets = {"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0}
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        self.assertIsNotNone(drift.largest_underweight)
        self.assertLess(drift.largest_underweight.drift_percentage_points, -DRIFT_IMMATERIAL_PP)

    def test_combined_modest_drifts_can_trigger(self) -> None:
        snap = _snap(
            [_deposit(10_000.0), _buy("VOO", 8, 400.0), _buy("BND", 8, 80.0)],
            {"VOO": 420.0, "BND": 78.0},
        )
        targets = {"Stocks": 0.0, "ETFs": 50.0, "Cash": 10.0, "Bonds": 40.0}
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        modest = [o for o in drift.observations if o.severity == "modest"]
        if len(modest) >= 2:
            self.assertTrue(drift.rebalance_triggered or drift.drift_status == "modest_drift")

    def test_invalid_target_no_rebalance(self) -> None:
        snap = _snap([_deposit(10_000.0), _buy("VOO", 5, 400.0)], {"VOO": 400.0})
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets={"Equity": 50.0})
        self.assertFalse(drift.rebalance_triggered)
        self.assertEqual(drift.target_quality, "invalid")

    def test_explicit_user_target_beats_inferred(self) -> None:
        snap = _snap([_deposit(10_000.0), _buy("VOO", 10, 400.0)], {"VOO": 400.0})
        user = {"Equity": 55.0, "Bonds": 35.0, "Cash_and_TBills": 10.0}
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets=user,
            health_objective="aggressive growth",
        )
        self.assertEqual(drift.target_source, "user_defined_target")
        self.assertEqual(drift.target_allocation["Equity"], 55.0)


class TestRealPortfolioRecommendations(unittest.TestCase):
    def test_immaterial_no_rebalance_rec(self) -> None:
        snap = _snap(
            [_deposit(5_000.0), _buy("VOO", 10, 400.0), _buy("BND", 5, 80.0)],
            {"VOO": 400.0, "BND": 80.0},
        )
        targets = {
            "ETFs": round(snap.allocation_by_asset_class.get("ETFs", 0.0), 1),
            "Bonds": round(snap.allocation_by_asset_class.get("Bonds", 0.0), 1),
            "Cash": round(snap.allocation_by_asset_class.get("Cash", 0.0) or snap.allocation_by_holding.get("$CASH", 0.0), 1),
            "Stocks": 0.0,
            "Other": 0.0,
        }
        _, _, drift, recs = _pipeline(snap, user_asset_class_targets=targets)
        self.assertFalse(drift.rebalance_triggered)
        codes = {r.code for r in recs.recommendations}
        self.assertNotIn("rebalance_with_new_money", codes)

    def test_material_overweight_review(self) -> None:
        snap = _snap([_deposit(1_000.0), _buy("VOO", 15, 400.0)], {"VOO": 450.0})
        targets = {"Equity": 35.0, "Bonds": 45.0, "Cash_and_TBills": 20.0}
        _, _, _, recs = _pipeline(snap, user_asset_class_targets=targets)
        codes = {r.code for r in recs.recommendations}
        self.assertIn("review_asset_class_overweight", codes)

    def test_underweight_direct_contributions(self) -> None:
        snap = _snap(
            [_deposit(30_000.0), _buy("BND", 40, 80.0), _buy("VOO", 3, 400.0)],
            {"VOO": 400.0, "BND": 80.0},
        )
        targets = {"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0}
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        recs = build_real_portfolio_recommendations(
            snap, perf, conc, drift, ask_contribution_placement=True
        )
        codes = {r.code for r in recs.recommendations}
        self.assertIn("direct_new_contributions_underweight", codes)
        self.assertIsNotNone(recs.contribution_placement)
        self.assertNotIn("ticker", str(recs.contribution_placement))

    def test_broad_etf_overweight_not_single_stock(self) -> None:
        snap = _snap([_deposit(500.0), _buy("VOO", 20, 400.0)], {"VOO": 450.0})
        targets = {"Equity": 50.0, "Bonds": 30.0, "Cash_and_TBills": 20.0}
        _, conc, drift, recs = _pipeline(snap, user_asset_class_targets=targets)
        self.assertTrue(drift.rebalance_triggered)
        review = [r for r in recs.recommendations if r.code == "review_asset_class_overweight"]
        self.assertTrue(review)
        self.assertEqual(review[0].rationale_code, "broad_etf_asset_class_overweight")

    def test_individual_stock_review(self) -> None:
        snap = _snap(
            [_deposit(20_000.0), _buy("AAPL", 100, 150.0, asset_type="stock")],
            {"AAPL": 200.0},
        )
        _, _, _, recs = _pipeline(snap, health_objective="balanced growth")
        codes = {r.code for r in recs.recommendations}
        self.assertIn("review_material_single_security", codes)

    def test_narrow_etf_thematic_review(self) -> None:
        snap = _snap([_deposit(5_000.0), _buy("QQQ", 30, 300.0)], {"QQQ": 350.0})
        _, _, _, recs = _pipeline(snap)
        codes = {r.code for r in recs.recommendations}
        self.assertIn("review_thematic_etf_concentration", codes)

    def test_missing_prices_refresh_first(self) -> None:
        snap = _snap(
            [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BAD", 2, 10.0)],
            {"VOO": 450.0},
        )
        _, _, _, recs = _pipeline(snap, user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0})
        self.assertEqual(recs.recommendations[0].action_type, "refresh_market_data")
        self.assertNotIn("rebalance_with_new_money", {r.code for r in recs.recommendations})

    def test_stale_quotes_reduce_confidence(self) -> None:
        holding = RealHoldingSnapshot(
            ticker="VOO",
            name="VOO",
            shares=10,
            average_cost=400,
            total_cost_basis=4000,
            current_price=400,
            current_value=4000,
            gain_loss_dollars=0,
            gain_loss_pct=0,
            current_weight=100,
            target_weight=None,
            asset_class="ETFs",
            price_source="cache",
            price_as_of=datetime.now(timezone.utc),
        )
        snap = RealPortfolioSnapshot(
            as_of=datetime.now(timezone.utc),
            market_data_status="cached",
            market_data_age_seconds=500,
            data_source="real_portfolio_engine",
            total_market_value=4000,
            total_cost_basis=4000,
            total_gain_loss_dollars=0,
            total_gain_loss_pct=0,
            priced_holdings_gain_loss_pct=0,
            cash=0,
            holdings=(holding,),
            allocation_by_holding={"VOO": 100.0},
            allocation_by_asset_class={"ETFs": 100.0},
            largest_positions=(holding,),
            concentration_metrics={},
        )
        _, _, _, recs = _pipeline(
            snap,
            user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
        )
        self.assertIn("refresh_market_data", {r.code for r in recs.recommendations})
        self.assertIn(recs.confidence_level, ("low", "medium"))

    def test_missing_cost_basis_recommendation(self) -> None:
        holding = RealHoldingSnapshot(
            ticker="VOO",
            name="VOO",
            shares=10,
            average_cost=0,
            total_cost_basis=0,
            current_price=400,
            current_value=4000,
            gain_loss_dollars=None,
            gain_loss_pct=None,
            current_weight=100,
            target_weight=None,
            asset_class="ETFs",
            price_source="test",
            price_as_of=datetime.now(timezone.utc),
        )
        snap = RealPortfolioSnapshot(
            as_of=datetime.now(timezone.utc),
            market_data_status="fresh",
            market_data_age_seconds=0,
            data_source="real_portfolio_engine",
            total_market_value=4000,
            total_cost_basis=0,
            total_gain_loss_dollars=None,
            total_gain_loss_pct=None,
            priced_holdings_gain_loss_pct=None,
            cash=0,
            holdings=(holding,),
            allocation_by_holding={"VOO": 100.0},
            allocation_by_asset_class={"ETFs": 100.0},
            largest_positions=(holding,),
            concentration_metrics={},
        )
        _, _, _, recs = _pipeline(snap)
        self.assertIn("add_missing_cost_basis", {r.code for r in recs.recommendations})

    def test_negative_cash_review(self) -> None:
        snap = _snap([_buy("VOO", 10, 400.0)], {"VOO": 450.0})
        _, _, _, recs = _pipeline(snap)
        self.assertIn("review_negative_cash", {r.code for r in recs.recommendations})

    def test_near_term_preserves_liquidity(self) -> None:
        snap = _snap(
            [_deposit(50_000.0), _buy("VOO", 10, 400.0), _buy("BND", 10, 80.0)],
            {"VOO": 400.0, "BND": 80.0},
            plan_near_term=40_000.0,
            plan_emergency=5_000.0,
        )
        targets = {"Equity": 40.0, "Bonds": 40.0, "Cash_and_TBills": 20.0}
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        recs = build_real_portfolio_recommendations(
            snap, perf, conc, drift, ask_contribution_placement=True
        )
        codes = [r.code for r in recs.recommendations]
        self.assertIn("preserve_liquidity", codes)
        if "direct_new_contributions_underweight" in codes:
            self.assertGreater(codes.index("preserve_liquidity"), codes.index("preserve_liquidity"))

    def test_no_contribution_no_dollar_invention(self) -> None:
        snap = _snap([_deposit(20_000.0), _buy("BND", 20, 80.0)], {"BND": 80.0})
        targets = {"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0}
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, user_asset_class_targets=targets)
        recs = build_real_portfolio_recommendations(
            snap, perf, conc, drift, ask_contribution_placement=True
        )
        self.assertIn("monthly_contribution_capacity", recs.information_needed)
        for r in recs.recommendations:
            self.assertNotIn("buy", r.title.lower())
            self.assertNotIn("sell", r.title.lower())

    def test_no_urgent_change_when_aligned(self) -> None:
        snap = _snap(
            [_deposit(5_000.0), _buy("VOO", 10, 400.0), _buy("BND", 5, 80.0)],
            {"VOO": 400.0, "BND": 80.0},
        )
        targets = {
            "ETFs": round(snap.allocation_by_asset_class.get("ETFs", 0.0), 1),
            "Bonds": round(snap.allocation_by_asset_class.get("Bonds", 0.0), 1),
            "Cash": round(snap.allocation_by_asset_class.get("Cash", 0.0) or snap.allocation_by_holding.get("$CASH", 0.0), 1),
            "Stocks": 0.0,
            "Other": 0.0,
        }
        _, _, _, recs = _pipeline(snap, user_asset_class_targets=targets)
        codes = {r.code for r in recs.recommendations}
        self.assertIn("no_urgent_change", codes)

    def test_tax_caution_on_sale_path(self) -> None:
        snap = _snap([_deposit(500.0), _buy("BND", 20, 80.0)], {"BND": 90.0})
        targets = {"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0}
        _, _, _, recs = _pipeline(snap, user_asset_class_targets=targets)
        self.assertTrue(
            any("tax" in t.lower() for t in recs.tradeoffs)
            or any("seek_tax_guidance_before_sale" in r.caution_flags for r in recs.recommendations)
        )

    def test_no_mutation(self) -> None:
        snap = _snap([_deposit(10_000.0), _buy("VOO", 5, 400.0)], {"VOO": 450.0})
        before = copy.deepcopy(snap)
        _pipeline(snap, user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0})
        self.assertEqual(snap.total_market_value, before.total_market_value)

    def test_deterministic_ordering(self) -> None:
        snap = _snap([_deposit(10_000.0), _buy("VOO", 10, 400.0)], {"VOO": 450.0})
        kw = {"user_asset_class_targets": {"Equity": 50.0, "Bonds": 40.0, "Cash_and_TBills": 10.0}}
        a = _pipeline(snap, **kw)[3].recommendations
        b = _pipeline(snap, **kw)[3].recommendations
        self.assertEqual([r.code for r in a], [r.code for r in b])

    def test_rules_do_not_read_model_portfolio(self) -> None:
        from pathlib import Path

        text = Path("investment_ami/decision_support/real_portfolio_recommendation_rules.py").read_text(
            encoding="utf-8"
        )
        for token in ("sidebar_portfolio_value", "DEFAULT_HOLDINGS", "build_real_portfolio_snapshot"):
            self.assertNotIn(token, text)
        for line in text.splitlines():
            if "holdings_df_mismatch_warning" in line:
                continue
            self.assertNotIn("holdings_df", line)

    def test_define_target_when_unavailable(self) -> None:
        snap = _snap([_deposit(10_000.0), _buy("VOO", 5, 400.0)], {"VOO": 400.0})
        _, _, drift, recs = _pipeline(snap)
        self.assertEqual(drift.target_source, "unavailable")
        self.assertIn("define_target_allocation", {r.code for r in recs.recommendations})


if __name__ == "__main__":
    unittest.main()
