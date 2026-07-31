"""Monthly Contribution Advisor — routing and structured reasoning tests."""

from __future__ import annotations

import unittest

from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR
from investment_ami.decision_support.monthly_contribution_advisor import analyze_monthly_contribution
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.presentation import (
    build_suggested_next_steps,
    render_user_analyst_sections,
)
from investment_ami.decision_support.question_topics import is_monthly_contribution_question
from investment_ami.decision_support.snapshot import build_financial_snapshot
from investment_ami_answer_format import render_investment_page_insight_markdown
from investment_ami_context import detect_investment_send_intent


def _base_ctx(**overrides: object) -> dict:
    ctx = {
        "plan_total_cash": 120_000,
        "plan_emergency": 30_000,
        "plan_near_term": 10_000,
        "plan_debt": 5_000,
        "plan_horizon": 20,
        "plan_risk": "moderate",
        "investment_plan_generated": True,
        "sidebar_portfolio_value": 80_000,
        "monthly_income": 10_000,
        "monthly_expenses": 5_000,
        "plan_monthly": 2_000,
        "plan_monthly_provided": True,
        "job_stability": "Stable",
    }
    ctx.update(overrides)
    return ctx


class TestMonthlyContributionRouting(unittest.TestCase):
    def test_exact_question_routes_to_allocation_advisor(self) -> None:
        q = "How much should I contribute each month to my investments?"
        self.assertTrue(is_monthly_contribution_question(q))
        self.assertEqual(detect_investment_send_intent(q, ""), "allocation_advisor")

    def test_paraphrases(self) -> None:
        for q in (
            "What monthly contribution should I make?",
            "Am I investing enough each month?",
            "Should I invest more every month?",
            "How much should I invest each month based on my financial situation?",
        ):
            with self.subTest(q=q):
                self.assertTrue(is_monthly_contribution_question(q))


class TestMonthlyContributionReasoning(unittest.TestCase):
    def test_complete_financial_information(self) -> None:
        q = "How much should I contribute each month to my investments?"
        response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, _base_ctx(), question=q)
        self.assertIn("alloc_monthly_contribution", response.applied_rule_ids)
        self.assertIn("Suggested monthly contribution", response.monthly_contribution_recommendation)
        self.assertNotIn("reviewed your saved plan inputs", response.assessment.lower())
        obs = " ".join(response.observations).lower()
        self.assertNotIn("no additional observations", obs)
        sections = render_user_analyst_sections(response)
        body = render_investment_page_insight_markdown(sections)
        self.assertIn("Suggested Monthly Contribution", body)
        self.assertIn("Facts Used", body)

    def test_missing_income(self) -> None:
        ctx = _base_ctx(monthly_income=None)
        snap = build_financial_snapshot(ctx, question="How much should I contribute each month?")
        advice = analyze_monthly_contribution(snap, question="How much should I contribute each month?")
        self.assertFalse(advice.precise_recommendation)
        self.assertIn("cannot yet recommend", advice.assessment.lower())

    def test_missing_expenses(self) -> None:
        ctx = _base_ctx(monthly_expenses=None)
        snap = build_financial_snapshot(ctx, question="How much should I contribute each month?")
        advice = analyze_monthly_contribution(snap, question="How much should I contribute each month?")
        self.assertFalse(advice.precise_recommendation)

    def test_missing_current_contribution(self) -> None:
        ctx = _base_ctx(plan_monthly_provided=False)
        snap = build_financial_snapshot(ctx, question="How much should I contribute each month?")
        advice = analyze_monthly_contribution(snap, question="How much should I contribute each month?")
        self.assertTrue(advice.precise_recommendation)
        self.assertTrue(any("unknown" in o.lower() for o in advice.observations))

    def test_high_surplus(self) -> None:
        ctx = _base_ctx(monthly_income=12_000, monthly_expenses=4_000, plan_monthly=500, plan_monthly_provided=True)
        snap = build_financial_snapshot(ctx, question="Should I increase my monthly investment?")
        advice = analyze_monthly_contribution(snap, question="Should I increase my monthly investment?")
        self.assertIsNotNone(advice.recommended_amount)
        assert advice.recommended_amount is not None
        self.assertGreater(advice.recommended_amount, 500)

    def test_low_surplus(self) -> None:
        ctx = _base_ctx(monthly_income=6_000, monthly_expenses=5_800, plan_monthly=2_000, plan_monthly_provided=True)
        snap = build_financial_snapshot(ctx, question="Am I contributing enough every month?")
        advice = analyze_monthly_contribution(snap, question="Am I contributing enough every month?")
        self.assertIsNotNone(advice.recommended_amount)
        assert advice.recommended_amount is not None
        self.assertLess(advice.recommended_amount, 2_000)

    def test_no_contribution_currently(self) -> None:
        ctx = _base_ctx(plan_monthly=0, plan_monthly_provided=True)
        snap = build_financial_snapshot(ctx, question="How much should I contribute each month?")
        advice = analyze_monthly_contribution(snap, question="How much should I contribute each month?")
        self.assertTrue(advice.precise_recommendation)
        assert advice.recommended_amount is not None
        self.assertGreater(advice.recommended_amount, 0)

    def test_confidence_notes_missing_cashflow(self) -> None:
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            _base_ctx(monthly_income=None, monthly_expenses=None),
            question="How much should I contribute each month to my investments?",
        )
        self.assertIn("low", response.confidence_note.lower())
        self.assertIn("exact", response.confidence_note.lower())

    def test_next_steps_skip_stale_income_prompt_when_cashflow_present(self) -> None:
        q = "How much should I contribute each month to my investments?"
        ctx = _base_ctx(monthly_income=4_100, monthly_expenses=2_800, plan_monthly=500)
        response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, ctx, question=q)
        snap = build_financial_snapshot(ctx, question=q)
        steps = build_suggested_next_steps(snap, list(response.findings), response.information_needed)
        self.assertNotIn("Enter **monthly income**", steps)
        self.assertIn("comfortable over several months", steps)
        sections = render_user_analyst_sections(response)
        body = render_investment_page_insight_markdown(sections)
        self.assertNotIn("Enter **monthly income** and **monthly essential expenses**", body)

    def test_no_remaining_gap_language_when_portfolio_matches_deployment_target(self) -> None:
        from dataclasses import replace

        ctx = _base_ctx(
            monthly_income=4_100,
            monthly_expenses=2_800,
            plan_monthly=500,
            plan_horizon=22,
            sidebar_portfolio_value=58_451,
        )
        snap = build_financial_snapshot(ctx, question="How much should I contribute each month?")
        snap = replace(snap, long_term_suggested=58_451.0, portfolio_value=58_451.0, horizon_years=22)
        advice = analyze_monthly_contribution(snap, question="How much should I contribute each month?")
        obs_text = " ".join(advice.observations).lower()
        self.assertNotIn("close any remaining gap", obs_text)
        self.assertNotIn("remaining gap", obs_text)
        self.assertIn("already matches", obs_text)

    def test_suggested_contribution_includes_surplus_breakdown_and_cushion(self) -> None:
        ctx = _base_ctx(monthly_income=4_100, monthly_expenses=2_800, plan_monthly=500)
        snap = build_financial_snapshot(ctx, question="How much should I contribute each month?")
        advice = analyze_monthly_contribution(snap, question="How much should I contribute each month?")
        section = advice.suggested_monthly_section.lower()
        self.assertIn("estimated monthly surplus", section)
        self.assertIn("remaining monthly cushion", section)
        self.assertIn("upper contribution guardrail", section)
        self.assertIn("ami recommends approximately", section)
        assert advice.surplus is not None
        assert advice.recommended_amount is not None
        cushion = max(0.0, advice.surplus - advice.recommended_amount)
        self.assertIn(f"${cushion:,.0f}", advice.suggested_monthly_section)

    def test_increase_contribution_paraphrase_matches_exact_recommendation(self) -> None:
        exact_q = "How much should I contribute each month to my investments?"
        paraphrase_q = "Should I increase my monthly investment contribution?"
        ctx = _base_ctx(monthly_income=4_100, monthly_expenses=2_800, plan_monthly=500, job_stability="Stable")
        self.assertTrue(is_monthly_contribution_question(paraphrase_q))
        self.assertEqual(detect_investment_send_intent(paraphrase_q, ""), "allocation_advisor")

        response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, ctx, question=paraphrase_q)
        self.assertIn("alloc_monthly_contribution", response.applied_rule_ids)

        snap = build_financial_snapshot(ctx, question=exact_q)
        advice_exact = analyze_monthly_contribution(snap, question=exact_q)
        advice_para = analyze_monthly_contribution(snap, question=paraphrase_q)
        self.assertEqual(advice_exact.recommended_amount, advice_para.recommended_amount)
        self.assertEqual(advice_para.recommended_amount, 700.0)
        self.assertIn("uses about **38%**", advice_para.assessment)
        self.assertIn("materially change", advice_para.assessment.lower())
        self.assertNotIn("well below surplus capacity", advice_para.assessment.lower())
        self.assertNotIn("job stability are included", response.confidence_note.lower())


if __name__ == "__main__":
    unittest.main()
