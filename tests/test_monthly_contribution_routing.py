"""Routing precedence for Monthly Contribution Advisor vs analytical synthesis."""

from __future__ import annotations

import unittest

from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.presentation import render_user_analyst_sections
from investment_ami.decision_support.question_topics import is_monthly_contribution_question
from investment_ami_answer_format import render_investment_page_insight_markdown
from investment_ami.routing.mode_router import route_investment_response_mode
from investment_ami_context import detect_investment_send_intent

_PORTFOLIO_CTX = {
    "page": "Portfolio Health",
    "current_weights": {"VOO": 60.0, "BND": 40.0},
    "asset_class_breakdown": {"Equity": 60.0, "Bond": 40.0},
    "health_score": 72.0,
    "volatility": "12.5%",
    "expected_return": "8.1%",
    "sharpe_ratio": "0.65",
}

_PLAN_CTX = {
    "plan_total_cash": 120_000,
    "plan_emergency": 30_000,
    "plan_horizon": 22,
    "plan_risk": "moderate",
    "investment_plan_generated": True,
    "sidebar_portfolio_value": 58_451,
    "monthly_income": 4_100,
    "monthly_expenses": 2_800,
    "plan_monthly": 500,
    "plan_monthly_provided": True,
    "job_stability": "Stable",
}

_LEGACY_RENDERER_MARKERS = (
    "investment committee",
    "chief investment officer",
    " cio ",
    "risk officer",
    "executive summary",
    "**direct answer**",
)

_MONTHLY_QUESTIONS = (
    "Based on my income, expenses, and current portfolio, what monthly contribution do you recommend?",
    "What monthly contribution do you recommend?",
    "Based on my financial information, how much should I invest each month?",
    "Given my income and expenses, what should my monthly investment be?",
    "What recurring monthly investment would you recommend?",
    "What monthly investing amount makes sense for me?",
    "Based on my finances, how much should I contribute every month?",
    "How much should I contribute each month to my investments?",
    "Should I increase my monthly investment contribution?",
)


class TestMonthlyContributionRoutingPrecedence(unittest.TestCase):
    def test_income_expenses_portfolio_recommend_phrase_is_monthly_contribution(self) -> None:
        q = "Based on my income, expenses, and current portfolio, what monthly contribution do you recommend?"
        self.assertTrue(is_monthly_contribution_question(q))
        self.assertEqual(detect_investment_send_intent(q, ""), "allocation_advisor")

    def test_mode_router_prefers_decision_support_over_synthesis(self) -> None:
        q = "Based on my income, expenses, and current portfolio, what monthly contribution do you recommend?"
        ctx = {**_PORTFOLIO_CTX, **_PLAN_CTX}
        mode = route_investment_response_mode(q, ctx)
        self.assertEqual(mode.response_mode, "deterministic", msg=mode.reasons)
        self.assertEqual(mode.deterministic_intent, "allocation_advisor")
        self.assertIn("decision_support_priority:allocation_advisor", mode.matched_rules)

    def test_monthly_contribution_paraphrases_render_structured_advisor(self) -> None:
        ctx = {**_PORTFOLIO_CTX, **_PLAN_CTX}
        for q in _MONTHLY_QUESTIONS:
            with self.subTest(q=q):
                self.assertTrue(is_monthly_contribution_question(q))
                mode = route_investment_response_mode(q, ctx)
                self.assertEqual(mode.response_mode, "deterministic", msg=(q, mode.reasons))
                self.assertEqual(mode.deterministic_intent, "allocation_advisor")
                response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, ctx, question=q)
                self.assertIn("alloc_monthly_contribution", response.applied_rule_ids)
                sections = render_user_analyst_sections(response)
                self.assertEqual(sections.get("insights_layout"), "decision_support")
                body = render_investment_page_insight_markdown(sections).lower()
                self.assertIn("suggested monthly contribution", body)
                for marker in _LEGACY_RENDERER_MARKERS:
                    self.assertNotIn(marker, body, msg=f"{q!r} matched legacy marker {marker!r}")


if __name__ == "__main__":
    unittest.main()
