"""Regression: scenario submit survives bad scenario_params and stages insight."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from suite_analytical_question import _stage_investment_instant_insight, build_question_payload


class TestScenarioSubmitRegression(unittest.TestCase):
    def test_stage_scenario_question_with_fair_value_param(self) -> None:
        st = MagicMock()
        ss: dict = {}
        st.session_state = ss
        submit_ctx = {
            "experience_mode": "Advanced Mode",
            "page": "Portfolio Health",
            "current_weights": {"SCHD": "20%", "VYM": "20%", "VNQ": "20%", "BND": "40%"},
            "scenario_params": {"tech_drawdown_pct": "Fair Value", "rate_shock": "Rising"},
        }
        pre_payload = build_question_payload(
            source_app="investment",
            source_page="Portfolio Health",
            question="What happens if tech falls 20%?",
            context=submit_ctx,
        )

        with patch("applied_math_return_insight.store_applied_math_insight"), patch(
            "applied_math_return_insight.stage_pending_insight",
            side_effect=lambda _st, insight, **kwargs: ss.update({"_ami_pending_insight": insight.to_dict()}),
        ):
            ok = _stage_investment_instant_insight(
                st,
                ss,
                question=pre_payload["question"],
                source_app="investment",
                source_page="Portfolio Health",
                submit_ctx=submit_ctx,
                submit_source_state={"source_page": "Portfolio Health"},
                pre_payload=pre_payload,
                action_url_pre="https://example.test/ami",
            )
        self.assertTrue(ok)
        diag = ss.get("_ami_investment_submit_diagnostics") or {}
        self.assertEqual(diag.get("detected_intent"), "scenario_stress")
        self.assertTrue(diag.get("instant_solved"))
        self.assertFalse(diag.get("solver_error"))
        pending = ss.get("_ami_pending_insight") or {}
        self.assertIn("20", str(pending.get("conclusion") or ""))


if __name__ == "__main__":
    unittest.main()
