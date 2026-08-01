"""Single-priority Real Portfolio Advisor presentation and refresh rules."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import portfolio_engine as pe

from investment_ami.decision_support.real_portfolio_concentration import analyze_real_portfolio_concentration
from investment_ami.decision_support.real_portfolio_drift import analyze_real_portfolio_drift
from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot, RealPortfolioSnapshot
from investment_ami.decision_support.real_portfolio_performance import analyze_real_portfolio_performance
from investment_ami.decision_support.real_portfolio_presentation import build_real_portfolio_presentation
from investment_ami.decision_support.real_portfolio_recommendation_rules import (
    build_real_portfolio_recommendations,
    STALE_QUOTE_AGE_SECONDS,
)
from investment_ami.decision_support.real_portfolio_single_priority import (
    market_data_needs_refresh,
    select_highest_priority_recommendation,
)
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot
from investment_ami_answer_format import render_investment_page_insight_markdown


def _deposit(amount: float) -> dict:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date="2024-01-01",
        ticker="",
        quantity=amount,
        execution_price=1.0,
    ).to_record()


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


def _snap(txns: list, prices: dict[str, float], **extra: object):
    ss = {"portfolio_transactions": txns, **extra}
    result = build_real_portfolio_snapshot(ss, prices=prices)
    assert result.ok and result.snapshot is not None
    return result.snapshot


class TestSinglePriorityPresentation(unittest.TestCase):
    _ONE_THING = (
        "If you could change only one thing about my portfolio, what would it be and why?"
    )

    def test_reserve_shortfall_is_single_primary(self) -> None:
        snap = _snap(
            [_deposit(16_500.0)],
            {},
            plan_emergency=7_654.0,
            plan_near_term=12_345.0,
            health_objective="balanced growth",
        )
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, health_objective="balanced growth")
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        primary = select_highest_priority_recommendation(recs, snap)
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertEqual(primary.code, "preserve_liquidity")
        shortfall = float(primary.evidence.get("protected_shortfall") or 0)
        self.assertGreater(shortfall, 0)
        pres = build_real_portfolio_presentation(
            question=self._ONE_THING,
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertIn("Highest-Priority Change", render_investment_page_insight_markdown(
            {
                "insights_layout": "real_portfolio_advisor",
                "ami_module_name": "Real Portfolio Advisor",
                "direct_answer": pres.assessment,
                "highest_priority_change": pres.highest_priority_change,
            }
        ))
        self.assertIn("If I could change only one thing", pres.highest_priority_change)
        self.assertIn(f"{shortfall:,.0f}".replace(",", ""), pres.highest_priority_change.replace(",", ""))
        self.assertIn("19999", pres.highest_priority_change.replace(",", ""))
        self.assertTrue(
            "Later steps" in pres.suggestions
            or "No other changes are co-primary" in pres.suggestions
        )
        self.assertNotIn("Refresh market prices", pres.suggestions)
        self.assertNotIn("you should sell", pres.highest_priority_change.lower())
        self.assertNotIn("sell vti", pres.highest_priority_change.lower())

    def test_one_primary_not_many_equal_bullets(self) -> None:
        snap = _snap(
            [_deposit(16_500.0)],
            {},
            plan_emergency=7_654.0,
            plan_near_term=12_345.0,
        )
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(snap, health_objective="balanced growth")
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        pres = build_real_portfolio_presentation(
            question=self._ONE_THING,
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertTrue(pres.highest_priority_change.strip())
        self.assertNotRegex(
            pres.suggestions,
            r"^\-\s*Your current portfolio cash is about",
        )

    def test_cached_fresh_no_refresh_advice(self) -> None:
        holding = RealHoldingSnapshot(
            ticker="VTI",
            name="VTI",
            shares=10,
            average_cost=200,
            total_cost_basis=2000,
            current_price=250,
            current_value=2500,
            gain_loss_dollars=500,
            gain_loss_pct=25,
            current_weight=100,
            target_weight=None,
            asset_class="ETFs",
            price_source="cache",
            price_as_of=datetime.now(timezone.utc),
        )
        snap = RealPortfolioSnapshot(
            as_of=datetime.now(timezone.utc),
            market_data_status="cached",
            market_data_age_seconds=30,
            data_source="real_portfolio_engine",
            total_market_value=2500,
            total_cost_basis=2000,
            total_gain_loss_dollars=500,
            total_gain_loss_pct=25,
            priced_holdings_gain_loss_pct=25,
            cash=0,
            holdings=(holding,),
            allocation_by_holding={"VTI": 100.0},
            allocation_by_asset_class={"ETFs": 100.0},
            largest_positions=(holding,),
            concentration_metrics={},
            data_quality_flags=("missing_prices",),
        )
        self.assertFalse(market_data_needs_refresh(snap))
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
        )
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        codes = {r.code for r in recs.recommendations}
        self.assertNotIn("refresh_market_data", codes)
        pres = build_real_portfolio_presentation(
            question="How is my portfolio doing?",
            snapshot=snap,
            performance=perf,
            concentration=conc,
            drift=drift,
            recommendations=recs,
        )
        self.assertNotIn("Refresh market prices", pres.suggestions)

    def test_stale_cached_still_refresh(self) -> None:
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
            market_data_age_seconds=STALE_QUOTE_AGE_SECONDS + 100,
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
        self.assertTrue(market_data_needs_refresh(snap))
        _, _, _, recs = (
            analyze_real_portfolio_performance(snap),
            analyze_real_portfolio_concentration(snap),
            analyze_real_portfolio_drift(
                snap,
                user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
            ),
            None,
        )
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
        )
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        self.assertIn("refresh_market_data", {r.code for r in recs.recommendations})

    def test_partial_prices_still_refresh(self) -> None:
        snap = _snap(
            [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BAD", 2, 10.0)],
            {"VOO": 450.0},
        )
        self.assertTrue(market_data_needs_refresh(snap))
        perf = analyze_real_portfolio_performance(snap)
        conc = analyze_real_portfolio_concentration(snap)
        drift = analyze_real_portfolio_drift(
            snap,
            user_asset_class_targets={"Equity": 60.0, "Bonds": 30.0, "Cash_and_TBills": 10.0},
        )
        recs = build_real_portfolio_recommendations(snap, perf, conc, drift)
        self.assertIn("refresh_market_data", {r.code for r in recs.recommendations})


if __name__ == "__main__":
    unittest.main()
