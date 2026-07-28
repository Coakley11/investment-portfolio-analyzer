"""P2 — BehavioralFinanceEngine (risk_reduction intent)."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.behavioral_finance import BehavioralFinanceEngine, get_behavioral_finance_engine
from investment_ami.engines.support.behavioral_finance_content import build_beginner_risk_reduction_lines
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_phase2_solvers import behavioral_finance_answer, risk_reduction_answer


class TestBehavioralFinanceContent(unittest.TestCase):
    def test_beginner_adds_concentration_lever_at_threshold(self) -> None:
        lines = build_beginner_risk_reduction_lines(top_ticker="VOO", top_pct=30.0)
        self.assertTrue(any("VOO" in line and "30.0%" in line for line in lines))

    def test_beginner_skips_lever_below_threshold(self) -> None:
        lines = build_beginner_risk_reduction_lines(top_ticker="BND", top_pct=20.0)
        self.assertFalse(any("BND" in line for line in lines))


class TestBehavioralFinanceEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"VOO": "40%", "QQQ": "35%", "BND": "25%"},
        "volatility": "14.2%",
    }

    def test_engine_metadata(self) -> None:
        result = get_behavioral_finance_engine().solve(
            InstantEngineRequest(context=self._CTX, beginner=False, question="What should I change if I want less risk?")
        )
        self.assertEqual(result.problem_type, "risk_reduction")
        self.assertEqual(result.model_name, "Investment risk coach")
        self.assertEqual(result.confidence_pct, 79)
        self.assertEqual(result.computed.get("ami_engine_id"), "behavioral_finance")
        self.assertIn("14.2", result.short_answer)

    def test_beginner_with_concentration(self) -> None:
        result = BehavioralFinanceEngine().solve(
            InstantEngineRequest(
                context={"current_weights": {"VOO": "40%", "BND": "20%"}, "experience_mode": "Beginner Mode"},
                beginner=True,
                question="What should I change if I want less risk?",
            )
        )
        self.assertIn("tradeoffs, not advice", result.short_answer)
        self.assertIn("VOO", result.short_answer)

    def test_pipeline_matches_wrappers(self) -> None:
        ctx = dict(self._CTX)
        question = "What should I change if I want less risk?"
        via_engine = run_instant_engine("behavioral_finance", ctx, beginner=False, question=question)
        via_behavioral = behavioral_finance_answer(ctx, beginner=False, question=question)
        via_risk = risk_reduction_answer(ctx, beginner=False, question=question)
        via_alias = run_instant_engine("risk_reduction", dict(self._CTX), beginner=False, question=question)
        self.assertEqual(via_engine.short_answer, via_behavioral.short_answer)
        self.assertEqual(via_engine.short_answer, via_risk.short_answer)
        self.assertEqual(via_engine.short_answer, via_alias.short_answer)

    def test_instant_solver_end_to_end(self) -> None:
        q = "What should I change if I want less risk?"
        self.assertEqual(detect_investment_send_intent(q, ""), "risk_reduction")
        solved = solve_instant_investment_insight(q, self._CTX)
        self.assertIsNotNone(solved)
        route, result = solved
        self.assertEqual(route.problem_type, "risk_reduction")
        self.assertIn("Risk-reduction levers", result.short_answer)


if __name__ == "__main__":
    unittest.main()
