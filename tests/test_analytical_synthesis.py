"""Phase 4 analytical synthesis tests (mock LLM — no API key)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from investment_ami.integration.instant_solver_facade import solve_instant_insight
from investment_ami.pipeline.analytical_synthesis import synthesize_with_diagnostics
from investment_ami.routing.mode_router import route_investment_response_mode

_CTX = {
    "page": "Portfolio Health",
    "current_weights": {"VOO": 55.0, "BND": 45.0},
    "asset_class_breakdown": {"Equity": 55.0, "Bond": 45.0},
    "volatility": "10%",
    "health_score": 75,
}


class TestAnalyticalSynthesis(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(
            os.environ,
            {
                "INVESTMENT_AMI_ANALYTICAL_SYNTHESIS": "1",
                "INVESTMENT_AMI_SYNTHESIS_MOCK": "1",
            },
            clear=False,
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()

    def test_mock_synthesis_produces_answer_and_diagnostics(self) -> None:
        q = "Critique my portfolio as an institutional portfolio manager."
        mode = route_investment_response_mode(q, _CTX)
        _route, result, diag = synthesize_with_diagnostics(q, _CTX, mode)
        self.assertTrue(diag.synthesis_enabled)
        self.assertIn("Mock analytical synthesis", result.short_answer)
        self.assertTrue(diag.system_prompt)
        self.assertTrue(diag.user_prompt)
        self.assertTrue(diag.structured_inputs.get("brief"))
        self.assertIn("brief_ms", diag.timing_ms)
        computed = dict(getattr(result, "computed", None) or {})
        self.assertIn("analytical_synthesis_diagnostics", computed)

    def test_facade_analytical_path_uses_synthesis_when_flagged(self) -> None:
        q = "Argue against my portfolio."
        solved = solve_instant_insight(q, _CTX)
        self.assertIsNotNone(solved)
        assert solved is not None
        _route, result = solved
        self.assertIn("Mock analytical synthesis", result.short_answer)
        self.assertEqual(
            (getattr(result, "computed", None) or {}).get("ami_pipeline_step"),
            "analytical_synthesis",
        )

    def test_grounding_validation_flags_bad_fact_id(self) -> None:
        from investment_ami.pipeline.synthesis_validation import validate_synthesis_grounding

        parsed = {
            "answer_markdown": "Weight is [not.a.real.fact].",
            "citations": [{"fact_id": "fake.fact", "excerpt": "x"}],
        }
        out = validate_synthesis_grounding(
            parsed,
            valid_fact_ids={"holdings.largest_weight_pct"},
            answer_markdown=parsed["answer_markdown"],
        )
        self.assertFalse(out.ok)
        self.assertTrue(out.invalid_fact_ids)


if __name__ == "__main__":
    unittest.main()
