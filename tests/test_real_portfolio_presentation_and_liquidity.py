"""Regression tests — Real Portfolio presentation, liquidity, and drift copy."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_cash_classification import classify_real_portfolio_cash
from investment_ami.decision_support.real_portfolio_concentration import analyze_real_portfolio_concentration
from investment_ami.decision_support.real_portfolio_drift import analyze_real_portfolio_drift
from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot, RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import (
    METRIC_LABEL_UNREALIZED,
    analyze_real_portfolio_performance,
)
from investment_ami.decision_support.real_portfolio_presentation import (
    build_real_portfolio_presentation,
)
from investment_ami.decision_support.real_portfolio_recommendation_rules import (
    build_real_portfolio_recommendations,
)
from investment_ami.decision_support.real_portfolio_recommendations import RealPortfolioRecommendationSet
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


def _empty_recs() -> RealPortfolioRecommendationSet:
    return RealPortfolioRecommendationSet(
        primary_action="no_urgent_change",
        recommendations=(),
        urgency="low",
        recommendation_status="hold",
        confidence_level="medium",
        confidence_score=55,
        supporting_facts=(),
        tradeoffs=(),
        information_needed=(),
    )


class TestPresentationAndLiquidity(unittest.TestCase):
    def test_unrealized_label_not_redundant_in_snapshot(self) -> None:
        snap = _snap(
            [_deposit(20_000.0), _buy("VTI", 10, 200.0)],
            {"VTI": 250.0},
        )
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap)
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        pres = build_real_portfolio_presentation(
            question="How is my portfolio doing?",
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertIn("Unrealized gain since purchase", pres.portfolio_snapshot)
        self.assertNotIn(f"({METRIC_LABEL_UNREALIZED})", pres.portfolio_snapshot)
        self.assertEqual(pres.metadata.get("metric_label"), METRIC_LABEL_UNREALIZED)

    def test_contributors_separate_blocks(self) -> None:
        holding_gain = RealHoldingSnapshot(
            ticker="VTI",
            name="VTI",
            shares=10,
            average_cost=200,
            total_cost_basis=2000,
            current_price=250,
            current_value=2500,
            gain_loss_dollars=500,
            gain_loss_pct=25,
            current_weight=50,
            target_weight=None,
            asset_class="ETFs",
            price_source="test",
            price_as_of=datetime.now(timezone.utc),
        )
        holding_loss = RealHoldingSnapshot(
            ticker="BND",
            name="BND",
            shares=10,
            average_cost=90,
            total_cost_basis=900,
            current_price=82,
            current_value=820,
            gain_loss_dollars=-80,
            gain_loss_pct=-8.9,
            current_weight=50,
            target_weight=None,
            asset_class="Bonds",
            price_source="test",
            price_as_of=datetime.now(timezone.utc),
        )
        snap = RealPortfolioSnapshot(
            as_of=datetime.now(timezone.utc),
            market_data_status="fresh",
            market_data_age_seconds=0,
            data_source="real_portfolio_engine",
            total_market_value=3320,
            total_cost_basis=2900,
            total_gain_loss_dollars=420,
            total_gain_loss_pct=14.5,
            priced_holdings_gain_loss_pct=14.5,
            cash=0,
            holdings=(holding_gain, holding_loss),
            allocation_by_holding={"VTI": 75.3, "BND": 24.7},
            allocation_by_asset_class={"ETFs": 75.3, "Bonds": 24.7},
            largest_positions=(holding_gain, holding_loss),
            concentration_metrics={},
        )
        perf = analyze_real_portfolio_performance(snap)
        block = build_real_portfolio_presentation(
            question="contributors",
            snapshot=snap,
            performance=perf,
            concentration=analyze_real_portfolio_concentration(snap),
            drift=analyze_real_portfolio_drift(snap),
            recommendations=_empty_recs(),
        ).performance_drivers
        self.assertIn("**Largest positive contributors:**", block)
        self.assertIn("**Largest negative contributors:**", block)
        pos_idx = block.index("**Largest positive contributors:**")
        neg_idx = block.index("**Largest negative contributors:**")
        between = block[pos_idx:neg_idx]
        self.assertIn("\n\n", block)
        self.assertNotIn("contributors:**\n**Largest negative", block)

    def test_reserve_shortfall_quantified_liquidity(self) -> None:
        snap = _snap(
            [_deposit(16_500.0)],
            {},
            plan_emergency=7_654.0,
            plan_near_term=12_345.0,
        )
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
        )
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        codes = {r.code for r in recs.recommendations}
        self.assertIn("preserve_liquidity", codes)
        self.assertNotIn("reduce_contribution_temporarily", codes)
        preserve = next(r for r in recs.recommendations if r.code == "preserve_liquidity")
        shortfall = float(preserve.evidence["protected_shortfall"])
        self.assertAlmostEqual(shortfall, 3_499.0, delta=50.0)
        pres = build_real_portfolio_presentation(
            question="liquidity",
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertIn("below the combined emergency and near-term reserve target", pres.suggestions)
        self.assertIn(f"{shortfall:,.0f}".replace(",", ""), pres.suggestions.replace(",", ""))

    def test_high_cash_weight_without_shortfall_no_pause(self) -> None:
        snap = _snap(
            [_deposit(50_000.0), _buy("VOO", 10, 400.0), _buy("BND", 10, 80.0)],
            {"VOO": 400.0, "BND": 80.0},
            plan_near_term=5_000.0,
            plan_emergency=5_000.0,
        )
        cc = classify_real_portfolio_cash(snap)
        self.assertGreater(cc.portfolio_cash_weight_pct, 15.0)
        self.assertEqual(cc.protected_shortfall, 0.0)
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets={"Equity": 40.0, "Bonds": 40.0, "Cash_and_TBills": 20.0},
        )
        recs = build_real_portfolio_recommendations(
            snap, perf, conc, drift, ask_contribution_placement=True
        )
        codes = {r.code for r in recs.recommendations}
        self.assertNotIn("preserve_liquidity", codes)
        self.assertNotIn("reduce_contribution_temporarily", codes)

    def test_cash_concepts_distinct(self) -> None:
        snap = _snap(
            [_deposit(16_500.0), _buy("VTI", 5, 200.0)],
            {"VTI": 250.0},
            plan_emergency=7_654.0,
            plan_near_term=12_345.0,
        )
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
        )
        cc = classify_real_portfolio_cash(snap, drift)
        self.assertAlmostEqual(cc.portfolio_cash, snap.cash, places=2)
        self.assertAlmostEqual(cc.protected_cash_target, 7_654.0 + 12_345.0, places=2)
        self.assertIsNotNone(cc.target_portfolio_cash_allocation_pct)
        self.assertAlmostEqual(cc.target_portfolio_cash_allocation_pct or 0, 10.0, places=1)

    def test_inferred_drift_conditional_guidance(self) -> None:
        snap = _snap(
            [_deposit(16_500.0), _buy("VTI", 5, 200.0), _buy("BND", 5, 80.0)],
            {"VTI": 250.0, "BND": 82.0},
            plan_emergency=7_654.0,
            plan_near_term=12_345.0,
            health_objective="balanced growth",
        )
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, health_objective="balanced growth")
        self.assertTrue(drift.rebalance_triggered or drift.drift_status.startswith("material"))
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        pres = build_real_portfolio_presentation(
            question="drift",
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        combined = (pres.assessment + pres.suggestions).lower()
        self.assertIn("investable", combined)
        self.assertIn("inferred", combined)
        self.assertNotIn("sell current holdings immediately", combined)

    def test_information_needed_protected_cash_question(self) -> None:
        snap = _snap([_deposit(16_500.0), _buy("VTI", 5, 200.0)], {"VTI": 250.0})
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, health_objective="balanced growth")
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        self.assertIn("protected_vs_investable_cash", recs.information_needed)
        pres = build_real_portfolio_presentation(
            question="cash",
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertIn("Which portion of the", pres.information_needed)
        self.assertIn("cash balance is reserved", pres.information_needed)

    def test_confidence_limited_inferred_and_unknown_cash(self) -> None:
        snap = _snap([_deposit(16_500.0), _buy("VTI", 5, 200.0)], {"VTI": 250.0})
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, health_objective="balanced growth")
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        pres = build_real_portfolio_presentation(
            question="confidence",
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertIn("Confidence is limited because", pres.confidence)
        self.assertIn("inferred", pres.confidence.lower())
        self.assertIn("protected cash from investable cash", pres.confidence.lower())


if __name__ == "__main__":
    unittest.main()
