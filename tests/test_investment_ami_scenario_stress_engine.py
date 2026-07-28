"""P2 — ScenarioStressEngine."""

from __future__ import annotations

import unittest

from investment_ami.engines.base import InstantEngineRequest
from investment_ami.engines.scenario_stress import ScenarioStressEngine, get_scenario_stress_engine
from investment_ami.engines.support.scenario_stress_data import (
    build_scenario_stress_snapshot,
    parse_scenario_drawdown_pct,
)
from investment_ami.pipeline.instant import run_instant_engine
from investment_ami_phase2_solvers import scenario_stress_answer


class TestScenarioStressSnapshot(unittest.TestCase):
    def test_parse_drawdown_from_question(self) -> None:
        self.assertEqual(
            parse_scenario_drawdown_pct({}, question="What happens if tech falls 20%?"),
            20.0,
        )

    def test_bad_param_falls_back_to_question(self) -> None:
        snap = build_scenario_stress_snapshot(
            {
                "scenario_params": {"tech_drawdown_pct": "Fair Value"},
                "current_weights": {"QQQ": "25%"},
            },
            question="What happens if tech falls 20%?",
        )
        self.assertEqual(snap.tech_drawdown_pct, 20.0)

    def test_rate_shock_from_macro_context(self) -> None:
        snap = build_scenario_stress_snapshot(
            {
                "current_weights": {"BND": "40%", "VOO": "60%"},
                "health_rate_env": "Rising Rates",
                "scenario_params": {"rate_shock": "Stable"},
            },
            question="What happens if tech falls 20%?",
        )
        self.assertEqual(snap.rate_shock, "Stable")


class TestScenarioStressEngine(unittest.TestCase):
    _CTX = {
        "experience_mode": "Advanced Mode",
        "current_weights": {"SCHD": "20%", "VYM": "20%", "VNQ": "20%", "BND": "40%"},
    }

    def test_engine_computed_fields(self) -> None:
        result = get_scenario_stress_engine().solve(
            InstantEngineRequest(
                context=self._CTX,
                beginner=False,
                question="What happens if tech falls 20%?",
            )
        )
        self.assertEqual(result.problem_type, "scenario_stress")
        self.assertEqual(result.computed.get("ami_engine_id"), "scenario_stress")
        self.assertEqual(result.computed.get("tech_drawdown_pct"), 20.0)
        self.assertIn("20", result.short_answer)

    def test_pipeline_matches_wrapper(self) -> None:
        ctx = dict(self._CTX)
        via_engine = run_instant_engine(
            "scenario_stress",
            ctx,
            beginner=False,
            question="What happens if tech falls 20%?",
        )
        via_wrapper = scenario_stress_answer(ctx, beginner=False, question="What happens if tech falls 20%?")
        self.assertEqual(via_engine.short_answer, via_wrapper.short_answer)
        self.assertEqual(
            via_engine.computed.get("illustrative_impact_pct"),
            via_wrapper.computed.get("illustrative_impact_pct"),
        )

    def test_confidence_when_no_tech_exposure(self) -> None:
        result = ScenarioStressEngine().solve(
            InstantEngineRequest(
                context={"current_weights": {"BND": "100%"}},
                beginner=True,
                question="What happens if tech falls 20%?",
            )
        )
        self.assertEqual(result.confidence_pct, 68)


if __name__ == "__main__":
    unittest.main()
