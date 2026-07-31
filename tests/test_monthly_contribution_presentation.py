"""Presentation regressions for Monthly Contribution Advisor rendered insight cards."""

from __future__ import annotations

import unittest

from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.presentation import render_user_analyst_sections
from investment_ami_answer_format import render_investment_page_insight_markdown
from investment_ami_context import normalize_insight_question_text


def _ctx(**overrides: object) -> dict:
    base = {
        "plan_total_cash": 120_000,
        "plan_emergency": 30_000,
        "plan_near_term": 10_000,
        "plan_debt": 5_000,
        "plan_horizon": 20,
        "plan_risk": "moderate",
        "investment_plan_generated": True,
        "sidebar_portfolio_value": 80_000,
        "monthly_income": 4_100,
        "monthly_expenses": 2_800,
        "plan_monthly": 500,
        "plan_monthly_provided": True,
        "job_stability": "Stable",
    }
    base.update(overrides)
    return base


class TestMonthlyContributionPresentation(unittest.TestCase):
    def test_normalize_insight_question_strips_duplicate_prefix(self) -> None:
        raw = "Question: Question: Should I increase my monthly investment contribution?"
        self.assertEqual(
            normalize_insight_question_text(raw),
            "Should I increase my monthly investment contribution?",
        )

    def test_e2e_render_no_duplicate_context_or_bad_confidence_grammar(self) -> None:
        q = "How much should I contribute each month to my investments?"
        response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, _ctx(), question=q)
        sections = render_user_analyst_sections(response)
        body = render_investment_page_insight_markdown(sections)
        lower = body.lower()
        self.assertNotIn("additional context", lower)
        self.assertIn("employer match and retirement goals are included", lower)
        self.assertNotIn("employer match, retirement goals are included", lower)
        self.assertEqual(lower.count("uses about"), 1)
        self.assertIn("suggested monthly contribution", lower)

    def test_increase_question_render_uses_single_surplus_explanation(self) -> None:
        q = "Should I increase my monthly investment contribution?"
        response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, _ctx(), question=q)
        body = render_investment_page_insight_markdown(render_user_analyst_sections(response))
        lower = body.lower()
        self.assertNotIn("additional context", lower)
        self.assertEqual(lower.count("uses about"), 1)


if __name__ == "__main__":
    unittest.main()
