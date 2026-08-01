"""Phase D — Real Portfolio Advisor routing and presentation."""

from __future__ import annotations

import copy
import json
import unittest

import portfolio_engine as pe

from investment_ami.decision_support.modules import MODULE_REAL_PORTFOLIO
from investment_ami.decision_support.question_topics import (
    is_cash_reserve_question,
    is_invested_amount_question,
    is_monthly_contribution_question,
    is_real_portfolio_question,
)
from investment_ami.decision_support.real_portfolio_advisor import run_real_portfolio_advisor
from investment_ami.routing.mode_router import route_investment_response_mode
from investment_ami_answer_format import render_investment_page_insight_markdown
from investment_ami_context import detect_investment_send_intent
from investment_ami.integration.instant_solver_facade import solve_instant_insight

_PORTFOLIO_CTX = {
    "page": "Real Portfolio",
    "current_weights": {"VOO": 60.0},
}

_PLAN = {
    "plan_monthly": 500,
    "plan_monthly_provided": True,
    "health_objective": "balanced growth",
}


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


def _ledger_ctx(*extra: object) -> dict:
    txns = [_deposit(20_000.0), _buy("VOO", 10, 400.0), _buy("BND", 10, 80.0, asset_type="bond")]
    base = {
        **_PORTFOLIO_CTX,
        **_PLAN,
        "portfolio_transactions": txns,
        "_real_portfolio_prices": {"VOO": 450.0, "BND": 82.0},
    }
    base.update(extra)
    return base


class TestRealPortfolioRouting(unittest.TestCase):
    def test_how_is_portfolio_doing(self) -> None:
        q = "How is my portfolio doing right now?"
        self.assertTrue(is_real_portfolio_question(q))
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.response_mode, "deterministic")
        self.assertEqual(mode.deterministic_intent, MODULE_REAL_PORTFOLIO)

    def test_actual_portfolio_performing(self) -> None:
        q = "How is my actual portfolio performing?"
        self.assertEqual(detect_investment_send_intent(q, ""), MODULE_REAL_PORTFOLIO)

    def test_contributors_question(self) -> None:
        q = "Which holdings are helping or hurting my portfolio?"
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.deterministic_intent, MODULE_REAL_PORTFOLIO)

    def test_rebalance_question(self) -> None:
        q = "Should I rebalance my portfolio?"
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.deterministic_intent, MODULE_REAL_PORTFOLIO)

    def test_contribution_placement(self) -> None:
        q = "Where should my next contribution go based on my current holdings?"
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.deterministic_intent, MODULE_REAL_PORTFOLIO)

    def test_monthly_still_allocation_advisor(self) -> None:
        q = "How much should I contribute each month?"
        self.assertTrue(is_monthly_contribution_question(q))
        mode = route_investment_response_mode(q, {**_PORTFOLIO_CTX, **_PLAN})
        self.assertEqual(mode.deterministic_intent, "allocation_advisor")

    def test_invested_amount_still_allocation(self) -> None:
        q = "How much should I invest given my financial situation?"
        self.assertTrue(is_invested_amount_question(q))
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.deterministic_intent, "allocation_advisor")

    def test_cash_reserve(self) -> None:
        q = "How much cash should I keep in reserve?"
        self.assertTrue(is_cash_reserve_question(q))
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.deterministic_intent, "cash_reserve_advisor")

    def test_recession_markets_stays_synthesis(self) -> None:
        q = "What might a recession do to markets?"
        mode = route_investment_response_mode(q, _PORTFOLIO_CTX)
        self.assertEqual(mode.response_mode, "analytical_synthesis")

    def test_portfolio_recommend_beats_synthesis_when_real_intent(self) -> None:
        q = "What changes should I consider for my actual portfolio?"
        mode = route_investment_response_mode(q, {**_PORTFOLIO_CTX, "current_weights": {"VOO": 80}})
        self.assertEqual(mode.response_mode, "deterministic")
        self.assertEqual(mode.deterministic_intent, MODULE_REAL_PORTFOLIO)


class TestRealPortfolioPresentation(unittest.TestCase):
    def _run(self, ctx: dict, question: str):
        ctx = dict(ctx)
        prices = ctx.pop("_real_portfolio_prices", None)
        if prices:
            from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot

            build = build_real_portfolio_snapshot(ctx, prices=prices)
            assert build.ok
        return run_real_portfolio_advisor(ctx, question=question)

    def test_no_ledger_guidance(self) -> None:
        _resp, payload = self._run(_PORTFOLIO_CTX, "How is my portfolio doing?")
        self.assertIn("no transaction-backed", payload["short_answer"].lower())
        self.assertTrue(payload["computed"]["real_portfolio"].get("no_ledger"))
        self.assertNotIn("DEFAULT_HOLDINGS", json.dumps(payload))

    def test_positive_portfolio_snapshot(self) -> None:
        _resp, payload = self._run(_ledger_ctx(), "How is my portfolio doing?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"])
        self.assertIn("Unrealized gain since purchase", md)
        self.assertNotIn("(cost basis)", md.lower())
        self.assertNotIn("today's return", md.lower())

    def test_no_committee_sections(self) -> None:
        _resp, payload = self._run(_ledger_ctx(), "How is my portfolio doing?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"]).lower()
        for bad in ("investment committee", "executive summary", "bull case", "bear case", "cio"):
            self.assertNotIn(bad, md)

    def test_other_not_called_bonds(self) -> None:
        ctx = _ledger_ctx()
        _resp, payload = self._run(ctx, "How is my portfolio doing?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"]).lower()
        self.assertIn("bonds", md)
        self.assertNotIn("other / uncategorized", md)
        self.assertNotIn("bond allocation is", md)

    def test_single_stock_review_not_sell(self) -> None:
        txns = [_deposit(30_000.0), _buy("AAPL", 100, 150.0, asset_type="stock")]
        ctx = {**_PORTFOLIO_CTX, "portfolio_transactions": txns, "_real_portfolio_prices": {"AAPL": 200.0}}
        _resp, payload = self._run(ctx, "Is my portfolio too concentrated?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"]).lower()
        self.assertIn("individual security", md)
        self.assertNotIn("sell aapl", md)
        self.assertNotIn("you should sell", md)

    def test_broad_etf_wording(self) -> None:
        txns = [_deposit(2_000.0), _buy("VOO", 20, 400.0)]
        ctx = {**_PORTFOLIO_CTX, "portfolio_transactions": txns, "_real_portfolio_prices": {"VOO": 450.0}}
        _resp, payload = self._run(ctx, "Is my portfolio too concentrated?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"]).lower()
        self.assertIn("broad-market etf", md)

    def test_partial_prices_warning(self) -> None:
        txns = [_deposit(10_000.0), _buy("VOO", 5, 400.0), _buy("BAD", 2, 10.0)]
        ctx = {**_PORTFOLIO_CTX, "portfolio_transactions": txns, "_real_portfolio_prices": {"VOO": 450.0}}
        _resp, payload = self._run(ctx, "How is my portfolio doing?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"]).lower()
        self.assertTrue(
            "missing" in md
            or "partial" in md
            or "refresh market" in md
            or "unpriced" in md
            or "bad" in md,
            msg="Expected partial-price handling or BAD holding in output",
        )

    def test_no_duplicate_question_label(self) -> None:
        _resp, payload = self._run(_ledger_ctx(), "How is my portfolio doing?")
        md = render_investment_page_insight_markdown(payload["analyst_sections"])
        self.assertNotIn("Question: Question:", md)
        self.assertNotIn("question: question:", md.lower())
        if "**Question**" in md:
            self.assertEqual(md.count("**Question**"), 1)

    def test_persist_roundtrip_sections(self) -> None:
        _resp, payload = self._run(_ledger_ctx(), "How is my portfolio doing?")
        blob = json.dumps(payload["analyst_sections"])
        restored = json.loads(blob)
        self.assertEqual(restored.get("insights_layout"), "real_portfolio_advisor")
        self.assertTrue(restored.get("direct_answer"))

    def test_no_mutation(self) -> None:
        ctx = _ledger_ctx()
        before = copy.deepcopy(ctx)
        self._run(ctx, "How is my portfolio doing?")
        self.assertEqual(ctx["portfolio_transactions"], before["portfolio_transactions"])

    def test_instant_solver_integration(self) -> None:
        ctx = _ledger_ctx()
        prices = ctx.pop("_real_portfolio_prices")
        from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot

        build_real_portfolio_snapshot(ctx, prices=prices)
        pair = solve_instant_insight("How is my actual portfolio performing?", ctx)
        self.assertIsNotNone(pair)
        _route, result = pair
        self.assertEqual(result.problem_type, MODULE_REAL_PORTFOLIO)
        self.assertEqual(result.computed.get("insights_layout"), "real_portfolio_advisor")


if __name__ == "__main__":
    unittest.main()
