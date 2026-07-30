"""Tests for AMI decision-support modules."""

from __future__ import annotations

import unittest

from investment_ami.decision_support.modules import MODULE_ALLOCATION_ADVISOR, MODULE_CASH_RESERVE
from investment_ami.decision_support.pipeline import run_decision_support_module
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_context import detect_investment_send_intent, intent_supported


class DecisionSupportPipelineTests(unittest.TestCase):
    _CTX = {
        "plan_total_cash": 120_000,
        "plan_emergency": 30_000,
        "plan_near_term": 10_000,
        "plan_monthly": 2_000,
        "monthly_expenses": 5_000,
        "plan_horizon": 20,
        "plan_risk": "moderate",
    }

    def test_allocation_monthly_question_applies_rules(self) -> None:
        response = run_decision_support_module(
            MODULE_ALLOCATION_ADVISOR,
            dict(self._CTX),
            question="How much should I invest this month?",
        )
        self.assertIn("alloc_monthly_contribution", response.applied_rule_ids)
        self.assertIn("alloc_baseline_context", response.applied_rule_ids)
        self.assertTrue(response.suggested_actions)
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
        self.assertIn("Investment Allocation Advisor", result.short_answer)
        self.assertEqual(result.computed.get("decision_support_version"), "ds-v1")

    def test_cash_intent_job_loss(self) -> None:
        intent = detect_investment_send_intent("What if I lost my job?", "")
        self.assertEqual(intent, "cash_reserve_advisor")
        result = run_instant_engine(intent, self._CTX, beginner=False, question="What if I lost my job?")
        self.assertIn("Cash Reserve", result.short_answer)
        self.assertIn("Pause or reduce", result.short_answer)

    def test_expense_shift_question_compares_levels(self) -> None:
        q = "My monthly expenses increased from $5,000 to $7,000. How should that affect my investing?"
        response = run_decision_support_module(MODULE_CASH_RESERVE, dict(self._CTX), question=q)
        joined = " ".join(response.observations)
        self.assertIn("5,000", joined)
        self.assertIn("7,000", joined)
        self.assertIn("30,000", joined)  # 6 * 5000
        self.assertIn("42,000", joined)  # 6 * 7000

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
        self.assertNotIn("monthly income", facts_joined)
        self.assertTrue(any("income" in x.lower() for x in response.limitations))


if __name__ == "__main__":
    unittest.main()
