"""JSON-safe serialization for InvestmentPlanResult and AMI context."""

from __future__ import annotations

import json
import unittest

import portfolio_core as core
from applied_math_context import build_investment_applied_math_context
from json_safe import ensure_json_safe, investment_plan_result_to_dict, json_safe_context
from suite_analytical_question import build_question_payload, metrics_for_applied_math_resume


def _sample_plan() -> core.InvestmentPlanResult:
    return core.InvestmentPlanResult(
        total_available=120_000,
        suggested_emergency_reserve=25_000,
        short_term_cash_amount=10_000,
        debt_reserve=5_000,
        amount_potentially_investable=80_000,
        long_term_suggested=68_000,
        short_term_investable=12_000,
        monthly_contribution=500,
        summary_lines=["Line one"],
        educational_notes=["Note one"],
        money_needed_1_2_years=10_000,
        planned_large_expenses=8_000,
        long_term_allocation_pct=0.85,
        safer_sleeve_allocation_pct=0.15,
    )


class TestJsonSafeInvestmentPlan(unittest.TestCase):
    def test_investment_plan_result_to_dict_is_json_serializable(self) -> None:
        plan = _sample_plan()
        data = investment_plan_result_to_dict(plan)
        json.dumps(data)
        self.assertEqual(data["amount_potentially_investable"], 80_000)
        self.assertIsInstance(data["summary_lines"], list)

    def test_build_context_never_embeds_raw_dataclass(self) -> None:
        session = {
            "investment_active_tab": "Portfolio Inputs",
            "plan_total_cash": 120_000,
            "investment_plan_generated": True,
            "investment_plan": _sample_plan(),
        }
        ctx = build_investment_applied_math_context("Portfolio Inputs", session)
        self.assertIsInstance(ctx["investment_plan"], dict)
        json.dumps(ctx["investment_plan"])

    def test_metrics_for_applied_math_resume_save_stage(self) -> None:
        session = {
            "investment_active_tab": "Portfolio Inputs",
            "plan_total_cash": 120_000,
            "investment_plan_generated": True,
            "investment_plan": _sample_plan(),
        }
        ctx = build_investment_applied_math_context("Portfolio Inputs", session)
        payload = build_question_payload(
            source_app="investment",
            source_page="Portfolio Inputs",
            question="Is the amount I currently have invested appropriate?",
            context=ctx,
        )
        metrics = metrics_for_applied_math_resume(payload)
        json.loads(metrics["context_json"])
        self.assertIn("investment_plan", metrics["context"])

    def test_ensure_json_safe_rejects_unknown_objects(self) -> None:
        class _Bad:
            pass

        with self.assertRaises(TypeError):
            ensure_json_safe(_Bad())


if __name__ == "__main__":
    unittest.main()
