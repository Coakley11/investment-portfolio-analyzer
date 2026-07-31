"""Tests for AMI decision-support modules."""

from __future__ import annotations

import unittest

import portfolio_core as core

from applied_math_context import build_investment_applied_math_context
from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR, MODULE_CASH_RESERVE
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.decision_support.presentation import render_user_analyst_sections, user_visible_markdown
from investment_ami_answer_format import render_investment_page_insight_markdown
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_context import detect_investment_send_intent, intent_supported


class DecisionSupportPipelineTests(unittest.TestCase):
    _CTX = {
        "plan_total_cash": 120_000,
        "plan_emergency": 30_000,
        "plan_near_term": 10_000,
        "plan_debt": 5_000,
        "plan_expenses": 8_000,
        "plan_monthly": 2_000,
        "plan_monthly_provided": True,
        "plan_horizon": 20,
        "plan_risk": "moderate",
        "investment_plan_generated": True,
        "monthly_expenses": 5_000,
    }

    def test_allocation_monthly_question_applies_rules(self) -> None:
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            dict(self._CTX),
            question="How much should I invest this month?",
        )
        self.assertIn("alloc_monthly_contribution", response.applied_rule_ids)
        self.assertTrue(response.assessment)
        self.assertTrue(response.facts)

    def test_cash_emergency_fund_question(self) -> None:
        response = run_decision_support_module(
            MODULE_CASH_RESERVE,
            dict(self._CTX),
            question="Is my emergency fund large enough?",
        )
        self.assertIn("cash_emergency_fund_size", response.applied_rule_ids)
        self.assertTrue(any("emergency" in o.lower() for o in response.observations))

    def test_intent_detection_and_instant_engine(self) -> None:
        q = "Should I pay off debt before investing?"
        intent = detect_investment_send_intent(q, "Investment Planning")
        self.assertEqual(intent, "allocation_advisor")
        self.assertTrue(intent_supported(intent))
        result = run_instant_engine(intent, self._CTX, beginner=True, question=q)
        self.assertNotIn("###", result.short_answer)
        self.assertEqual(result.computed.get("decision_support_version"), "ds-v1")
        sections = result.analyst_sections or {}
        self.assertEqual(sections.get("insights_layout"), "decision_support")

    def test_cash_intent_job_loss(self) -> None:
        intent = detect_investment_send_intent("What if I lost my job?", "")
        self.assertEqual(intent, "cash_reserve_advisor")
        result = run_instant_engine(intent, self._CTX, beginner=False, question="What if I lost my job?")
        self.assertIn("Pause or reduce", result.short_answer)

    def test_expense_shift_question_compares_levels(self) -> None:
        q = "My monthly expenses increased from $5,000 to $7,000. How should that affect my investing?"
        response = run_decision_support_module(MODULE_CASH_RESERVE, dict(self._CTX), question=q)
        joined = " ".join([response.assessment] + response.observations)
        self.assertIn("5,000", joined)
        self.assertIn("7,000", joined)
        self.assertIn("30,000", joined)
        self.assertIn("42,000", joined)

    def test_portfolio_questions_not_captured_by_decision_support(self) -> None:
        self.assertEqual(
            detect_investment_send_intent("Is my portfolio too concentrated?", ""),
            "portfolio_concentration",
        )
        self.assertEqual(
            detect_investment_send_intent("What should I change in my portfolio?", ""),
            "allocation_recommendation",
        )

    def test_missing_income_not_invented_in_facts(self) -> None:
        ctx = {k: v for k, v in self._CTX.items() if k != "monthly_expenses"}
        ctx.pop("monthly_income", None)
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            ctx,
            question="How much should I invest this month?",
        )
        facts_joined = " ".join(response.facts).lower()
        self.assertNotIn("monthly income:", facts_joined)
        self.assertTrue(response.information_needed)

    def test_user_visible_output_has_no_internal_tokens(self) -> None:
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            dict(self._CTX),
            question="Am I investing enough?",
        )
        visible = user_visible_markdown(response).lower()
        self.assertNotIn("placeholder", visible)
        self.assertNotIn("framework ds-v1", visible)
        self.assertNotIn("ds-v1", visible)

    def test_single_confidence_in_rendered_sections(self) -> None:
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            dict(self._CTX),
            question="Am I investing enough?",
        )
        sections = render_user_analyst_sections(response)
        body = render_investment_page_insight_markdown(sections, beginner=False)
        self.assertEqual(body.count("**Confidence**"), 1)
        self.assertIn("**Assessment**", body)
        self.assertNotIn("Conclusion:", body)

    def test_explicit_zero_monthly_contribution(self) -> None:
        ctx = dict(self._CTX)
        ctx["plan_monthly"] = 0
        ctx["plan_monthly_provided"] = True
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            ctx,
            question="Am I investing enough?",
        )
        self.assertIn("$0", response.assessment)
        facts = " ".join(response.facts)
        self.assertIn("$0", facts)

    def test_investing_enough_starts_with_direct_assessment(self) -> None:
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            dict(self._CTX),
            question="Am I investing enough?",
        )
        self.assertTrue(
            response.assessment.lower().startswith("ami cannot")
            or "monthly investment" in response.assessment.lower()
        )

    def test_plan_session_reaches_snapshot_via_applied_math_context(self) -> None:
        plan = core.InvestmentPlanResult(
            total_available=120_000,
            suggested_emergency_reserve=30_000,
            short_term_cash_amount=10_000,
            debt_reserve=5_000,
            amount_potentially_investable=67_000,
            long_term_suggested=56_950,
            short_term_investable=10_050,
            monthly_contribution=0,
            summary_lines=[],
            educational_notes=[],
            money_needed_1_2_years=10_000,
            planned_large_expenses=8_000,
        )
        session = {
            "investment_active_tab": "Portfolio Inputs",
            "plan_total_cash": 120_000,
            "plan_emergency": 30_000,
            "plan_near_term": 10_000,
            "plan_debt": 5_000,
            "plan_expenses": 8_000,
            "plan_monthly": 0,
            "plan_monthly_provided": True,
            "plan_horizon": 20,
            "plan_risk": "moderate",
            "investment_plan_generated": True,
            "investment_plan": plan,
        }
        ctx = build_investment_applied_math_context("Portfolio Inputs", session)
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            ctx,
            question="Am I investing enough?",
        )
        facts = " ".join(response.facts)
        self.assertIn("120,000", facts)
        self.assertIn("30,000", facts)
        self.assertIn("67,000", facts)
        self.assertNotIn("Limited plan data", response.assessment)

    def test_invested_amount_question_routing_and_rule(self) -> None:
        q = (
            "Given my total net worth and financial situation, "
            "is the amount I currently have invested appropriate?"
        )
        self.assertEqual(detect_investment_send_intent(q, ""), "allocation_advisor")
        ctx = dict(self._CTX)
        ctx["sidebar_portfolio_value"] = 100_000
        ctx["investment_plan_generated"] = True
        plan = core.InvestmentPlanResult(
            total_available=120_000,
            suggested_emergency_reserve=30_000,
            short_term_cash_amount=10_000,
            debt_reserve=5_000,
            amount_potentially_investable=67_000,
            long_term_suggested=58_451,
            short_term_investable=8_549,
            monthly_contribution=2_000,
            summary_lines=[],
            educational_notes=[],
        )
        ctx["investment_plan"] = plan
        response = run_decision_support_module(MODULE_ALLOCATION_ADVISOR, ctx, question=q)
        self.assertIn("alloc_invested_amount", response.applied_rule_ids)
        self.assertNotIn("alloc_monthly_contribution", response.applied_rule_ids)
        self.assertIn("approximately", response.assessment.lower())
        self.assertIn("not direct substitutes", response.assessment.lower())
        self.assertNotIn("vs plan context", response.assessment.lower())
        self.assertNotIn("contribution assessment", response.assessment.lower())
        visible = user_visible_markdown(response).lower()
        self.assertNotIn("framework ds-v1", visible)
        self.assertNotIn("placeholder", visible)
        self.assertIn("58,451", response.assessment)
        obs = " ".join(response.observations)
        self.assertIn("100,000", obs)
        self.assertIn("Suggested long-term deployment", obs)

    def test_invested_amount_rendered_sections(self) -> None:
        q = "Am I underinvested given my plan?"
        ctx = {**self._CTX, "sidebar_portfolio_value": 30_000, "investment_plan_generated": True}
        result = run_instant_engine("allocation_advisor", ctx, beginner=False, question=q)
        sections = result.analyst_sections or {}
        body = render_investment_page_insight_markdown(sections)
        self.assertIn("**Assessment**", body)
        self.assertNotIn("Conclusion:", body)
        self.assertNotIn("### Investment Allocation Advisor", body)

    def test_legacy_conclusion_detected(self) -> None:
        from applied_math_return_insight import _is_legacy_decision_support_conclusion, _resolve_insight_analyst_sections

        legacy = "### Investment Allocation Advisor\n\nFramework `ds-v1`"
        self.assertTrue(_is_legacy_decision_support_conclusion(legacy))
        _sections, is_ds, stale = _resolve_insight_analyst_sections(
            {"conclusion": legacy, "problem_type": "allocation_advisor"}
        )
        self.assertTrue(is_ds)
        self.assertTrue(stale)


if __name__ == "__main__":
    unittest.main()
