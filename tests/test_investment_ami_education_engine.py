"""P2 — EducationEngine and shared education content."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.education import EducationEngine, get_education_engine
from investment_ami.engines.support.education_content import format_beginner_coach_snapshot
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import solve_instant_investment_insight
from investment_ami_phase2_solvers import coach_answer, education_answer


class TestEducationContent(unittest.TestCase):
    def test_beginner_snapshot_includes_core_concepts(self) -> None:
        text = format_beginner_coach_snapshot("Retirement")
        self.assertIn("Portfolio coaching snapshot", text)
        self.assertIn("Diversification", text)
        self.assertIn("Allocation", text)
        self.assertIn("Rebalancing", text)
        self.assertIn("Retirement", text)


class TestEducationEngine(unittest.TestCase):
    _CTX = {"experience_mode": "Beginner Mode", "objective": "Long-term growth"}

    def test_engine_metadata(self) -> None:
        result = get_education_engine().solve(
            InstantEngineRequest(
                context=self._CTX,
                beginner=True,
                question="What is diversification?",
            )
        )
        self.assertEqual(result.problem_type, "investment_coach")
        self.assertEqual(result.model_name, "Investment coach")
        self.assertEqual(result.confidence_pct, 74)
        self.assertEqual(result.computed.get("ami_engine_id"), "education")
        self.assertIn("Diversification", result.short_answer)

    def test_advanced_mode_framework(self) -> None:
        result = EducationEngine().solve(
            InstantEngineRequest(
                context={"objective": "Income", "experience_mode": "Advanced Mode"},
                beginner=False,
                question="Explain portfolio construction",
            )
        )
        self.assertIn("expected return vs volatility", result.short_answer)
        self.assertIn("Income", result.short_answer)

    def test_pipeline_matches_wrappers(self) -> None:
        ctx = dict(self._CTX)
        question = "What is diversification?"
        via_engine = run_instant_engine("education", ctx, beginner=True, question=question)
        via_education = education_answer(ctx, beginner=True, question=question)
        via_coach = coach_answer(ctx, beginner=True, question=question)
        via_alias = run_instant_engine("investment_coach", dict(self._CTX), beginner=True, question=question)
        self.assertEqual(via_engine.short_answer, via_education.short_answer)
        self.assertEqual(via_engine.short_answer, via_coach.short_answer)
        self.assertEqual(via_engine.short_answer, via_alias.short_answer)
        self.assertEqual(via_engine.confidence_pct, via_education.confidence_pct)

    def test_instant_solver_routes_coach_phrases(self) -> None:
        q = "Help me understand how investing works"
        self.assertEqual(detect_investment_send_intent(q, ""), "investment_coach")
        solved = solve_instant_investment_insight(q, self._CTX)
        self.assertIsNotNone(solved)
        route, result = solved
        self.assertEqual(route.problem_type, "investment_coach")
        self.assertIn("Portfolio coaching snapshot", result.short_answer)


if __name__ == "__main__":
    unittest.main()
