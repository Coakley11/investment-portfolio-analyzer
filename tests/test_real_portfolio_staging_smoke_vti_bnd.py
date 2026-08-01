"""
Staging smoke — VTI/BND/cash ledger (matches manual Real Portfolio staging targets).

Mark prices implied from expected market values:
  VTI 25 sh @ 368.21 → ~$9,205.25
  BND 30 sh @ 72.23 → ~$2,166.90
  Cash ~$16,500 → total ~$27,872.15
"""

from __future__ import annotations

import json
import unittest

import portfolio_engine as pe

from investment_ami.decision_support.modules import MODULE_REAL_PORTFOLIO
from investment_ami.decision_support.question_topics import is_monthly_contribution_question
from investment_ami.decision_support.real_portfolio_advisor import run_real_portfolio_advisor
from investment_ami.decision_support.real_portfolio_performance import METRIC_LABEL_UNREALIZED
from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot
from investment_ami.routing.mode_router import route_investment_response_mode
from investment_ami_answer_format import render_investment_page_insight_markdown

_STAGING_PRICES = {"VTI": 368.21, "BND": 72.23}

# deposit 27,220 − VTI 8,500 − BND 2,220 = 16,500 cash
_STAGING_TXNS = [
    pe.PortfolioTransaction(
        id="staging-dep",
        action="cash_deposit",
        date="2025-01-01",
        ticker="",
        quantity=27_220.0,
        execution_price=1.0,
    ).to_record(),
    pe.PortfolioTransaction(
        id="staging-vti",
        action="buy",
        date="2025-01-02",
        ticker="VTI",
        quantity=25.0,
        execution_price=340.0,
        asset_type="etf",
        company_name="Vanguard Total Stock Market ETF",
    ).to_record(),
    pe.PortfolioTransaction(
        id="staging-bnd",
        action="buy",
        date="2025-01-03",
        ticker="BND",
        quantity=30.0,
        execution_price=74.0,
        asset_type="bond",
        company_name="Vanguard Total Bond Market ETF",
    ).to_record(),
]

_CTX = {
    "page": "Real Portfolio",
    "holdings_df": [{"Ticker": "VTI", "Weight (%)": 40.0}],
    "sidebar_portfolio_value": 100_000,
    "portfolio_transactions": _STAGING_TXNS,
    "_real_portfolio_prices": _STAGING_PRICES,
    "health_objective": "balanced growth",
    "plan_monthly": 500,
    "plan_monthly_provided": True,
}

_QUESTIONS_REAL = (
    "How is my portfolio doing right now?",
    "Which holdings are helping or hurting my portfolio?",
    "Is my portfolio too concentrated?",
    "Should I rebalance my portfolio?",
    "Where should my next contribution go based on my current holdings?",
    "What changes, if any, should I consider for my portfolio?",
)

_QUESTION_MONTHLY = "How much should I contribute each month?"


def _approx(actual: float, expected: float, *, tol: float = 1.0) -> bool:
    return abs(actual - expected) <= tol


class TestStagingLedgerMetrics(unittest.TestCase):
    def test_real_portfolio_tab_numbers(self) -> None:
        txns = pe.transactions_from_records(_STAGING_TXNS)
        positions, cash = pe.build_positions(txns, prices=_STAGING_PRICES)
        vti = next(p for p in positions if p.ticker == "VTI")
        bnd = next(p for p in positions if p.ticker == "BND")
        self.assertAlmostEqual(vti.shares_owned, 25.0, places=2)
        self.assertAlmostEqual(bnd.shares_owned, 30.0, places=2)
        self.assertTrue(_approx(cash, 16_500.0, tol=0.05))
        self.assertTrue(_approx(vti.market_value, 9_205.25, tol=0.05))
        self.assertTrue(_approx(bnd.market_value, 2_166.90, tol=0.05))
        summary = pe.compute_portfolio_summary(txns, prices=_STAGING_PRICES)
        self.assertTrue(_approx(summary.total_portfolio_value, 27_872.15, tol=0.10))
        self.assertTrue(_approx(summary.allocation_by_bucket["Bonds"], 7.8, tol=0.3))
        self.assertAlmostEqual(summary.allocation_by_bucket["Other"], 0.0, places=1)

    def test_snapshot_ignores_holdings_df_for_value(self) -> None:
        build = build_real_portfolio_snapshot(_CTX, prices=_STAGING_PRICES)
        self.assertTrue(build.ok)
        assert build.snapshot is not None
        snap = build.snapshot
        self.assertTrue(_approx(snap.total_market_value, 27_872.15, tol=0.15))
        self.assertNotAlmostEqual(snap.total_market_value, 100_000.0, delta=1000.0)
        self.assertEqual(
            next(h for h in snap.holdings if h.ticker == "BND").asset_class,
            "Bonds",
        )


class TestStagingAmiSmoke(unittest.TestCase):
    def _run(self, question: str) -> tuple[dict, str]:
        _resp, payload = run_real_portfolio_advisor(_CTX, question=question)
        md = render_investment_page_insight_markdown(payload["analyst_sections"])
        return payload, md.lower()

    def test_routing_matrix(self) -> None:
        for q in _QUESTIONS_REAL:
            mode = route_investment_response_mode(q, _CTX)
            self.assertEqual(
                mode.deterministic_intent,
                MODULE_REAL_PORTFOLIO,
                msg=q,
            )
        self.assertTrue(is_monthly_contribution_question(_QUESTION_MONTHLY))
        mode7 = route_investment_response_mode(_QUESTION_MONTHLY, _CTX)
        self.assertEqual(mode7.deterministic_intent, "allocation_advisor")

    def test_q1_portfolio_snapshot_and_terminology(self) -> None:
        payload, md = self._run(_QUESTIONS_REAL[0])
        self.assertIn(METRIC_LABEL_UNREALIZED.lower()[:15], md)
        self.assertNotIn("today's return", md)
        self.assertNotIn("investment committee", md)
        self.assertNotIn("executive summary", md)
        self.assertEqual(payload["computed"].get("ami_engine_id"), "real_portfolio_advisor")
        self.assertIn("27,872", md)
        self.assertNotIn("DEFAULT_HOLDINGS", json.dumps(payload))

    def test_q2_contributors_vti_positive_bnd_negative(self) -> None:
        _, md = self._run(_QUESTIONS_REAL[1])
        self.assertIn("vti", md)
        self.assertIn("bnd", md)
        # Performance block lists dollar unrealized contributors.
        self.assertIn("unrealized gain", md)
        self.assertIn("unrealized loss", md)

    def test_q3_concentration_vti_not_single_stock(self) -> None:
        _, md = self._run(_QUESTIONS_REAL[2])
        self.assertIn("broad-market etf", md)
        self.assertNotIn("you should sell", md)

    def test_q4_rebalance_not_one_day_return(self) -> None:
        _, md = self._run(_QUESTIONS_REAL[3])
        self.assertNotIn("today's return", md)
        self.assertNotIn("you should sell", md)

    def test_q5_contribution_placement(self) -> None:
        payload, md = self._run(_QUESTIONS_REAL[4])
        self.assertEqual(payload["computed"]["ami_engine_id"], MODULE_REAL_PORTFOLIO)
        self.assertIn("bonds", md)

    def test_q6_changes_consideration(self) -> None:
        payload, _ = self._run(_QUESTIONS_REAL[5])
        self.assertEqual(payload["computed"]["insights_layout"], "real_portfolio_advisor")

    def test_transaction_display_signs(self) -> None:
        txns = pe.transactions_from_records(_STAGING_TXNS)
        df = pe.transactions_display_dataframe(txns)
        vti_row = df[df["Ticker"] == "VTI"].iloc[0]
        self.assertTrue(str(vti_row["Total"]).startswith("↓ −"))
        dep_row = df[df["Action"].str.contains("Deposit", case=False)].iloc[0]
        self.assertTrue(str(dep_row["Amount"]).startswith("↑ +"))


if __name__ == "__main__":
    unittest.main()
