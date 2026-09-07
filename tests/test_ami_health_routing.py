"""AMI routing: Health/Sharpe questions must not divert to VTI valuation."""

from __future__ import annotations

import unittest

from investment_ami.integration.instant_solver_facade import solve_instant_insight
from investment_ami.routing.mode_router import route_investment_response_mode
from investment_ami_context import detect_investment_send_intent, is_portfolio_health_question
from investment_ami_valuation import resolve_valuation_target


_SHADOW_CTX = {
    "page": "Portfolio Health",
    "health_score": 81,
    "health_score_label": "Mostly On Plan",
    "health_status_message": (
        "Core Portfolio Health is mostly on plan (81/100) based on objective fit, "
        "construction, risk appropriateness, and policy-relative delivery."
    ),
    "sharpe_ratio": "0.28",
    "objective": "balanced growth",
    "current_weights": {"VTI": "40.0%", "VXUS": "20.0%", "BND": "30.0%", "VNQ": "10.0%"},
    "holdings": ["VTI", "VXUS", "BND", "VNQ"],
}


class TestAmiHealthVsValuationRouting(unittest.TestCase):
    def test_a_how_healthy_routes_health_not_valuation(self) -> None:
        q = "How healthy is my current portfolio?"
        self.assertEqual(detect_investment_send_intent(q, ""), "portfolio_health")
        mode = route_investment_response_mode(q, _SHADOW_CTX)
        self.assertEqual(mode.deterministic_intent, "portfolio_health")
        self.assertNotEqual(mode.deterministic_intent, "valuation")
        route, result = solve_instant_insight(q, _SHADOW_CTX)
        self.assertIsNotNone(route)
        assert result is not None
        text = (result.short_answer or "") + str(result.analyst_sections or {})
        self.assertIn("Mostly On Plan", text)
        self.assertNotIn("moderately rich", text.lower())
        self.assertNotIn("P/E 24", text)
        self.assertNotIn("earnings yield", text.lower())

    def test_b_sharpe_diagnostic_not_core_trigger(self) -> None:
        q = "My Sharpe is 0.28. Is that a problem?"
        self.assertTrue(is_portfolio_health_question(q))
        self.assertEqual(detect_investment_send_intent(q, ""), "portfolio_health")
        _route, result = solve_instant_insight(q, _SHADOW_CTX)
        text = (result.short_answer or "") + str(result.analyst_sections or {})
        self.assertIn("diagnostic", text.lower())
        self.assertIn("not", text.lower())
        self.assertIn("core health", text.lower())
        self.assertNotIn("moderately rich", text.lower())
        self.assertNotIn("P/E 24", text)

    def test_c_main_issue_objective_alignment(self) -> None:
        q = "What is the main issue with my portfolio?"
        self.assertEqual(detect_investment_send_intent(q, ""), "portfolio_health")
        _route, result = solve_instant_insight(q, _SHADOW_CTX)
        text = (result.short_answer or "").lower()
        self.assertTrue(
            "objective" in text or "t-bill" in text or "guided" in text,
            msg=text,
        )
        self.assertNotIn("p/e", text)

    def test_d_multi_intent_health_sharpe_no_vti_pe(self) -> None:
        q = (
            "How healthy is my current portfolio, what is the main issue with it, and "
            "should I change anything because my Sharpe ratio is only about 0.28?"
        )
        # Root bug: "pe ratio" must not match inside "sharpe ratio"
        self.assertNotEqual(detect_investment_send_intent(q, ""), "valuation")
        self.assertEqual(detect_investment_send_intent(q, ""), "portfolio_health")
        mode = route_investment_response_mode(q, _SHADOW_CTX)
        self.assertEqual(mode.effective_intent_id, "portfolio_health")
        _route, result = solve_instant_insight(q, _SHADOW_CTX)
        text = (result.short_answer or "") + str(result.analyst_sections or {})
        self.assertIn("Mostly On Plan", text)
        self.assertIn("0.28", text)
        self.assertIn("diagnostic", text.lower())
        self.assertIn("Guided", text)
        self.assertNotIn("P/E 24", text)
        self.assertNotIn("moderately rich", text.lower())
        self.assertNotIn("dollar-cost average", text.lower())
        self.assertEqual(result.computed.get("ami_engine_id"), "portfolio_health")

    def test_e_vti_expensive_still_valuation(self) -> None:
        q = "Is VTI expensive at a P/E of 24?"
        self.assertEqual(detect_investment_send_intent(q, ""), "valuation")
        mode = route_investment_response_mode(q, _SHADOW_CTX)
        self.assertEqual(mode.deterministic_intent, "valuation")

    def test_f_add_vti_valuation_appropriate(self) -> None:
        q = "Should I add more VTI given its valuation?"
        self.assertEqual(detect_investment_send_intent(q, ""), "valuation")

    def test_g_vti_weight_alone_does_not_force_valuation(self) -> None:
        q = "How is my portfolio doing overall?"
        self.assertNotEqual(detect_investment_send_intent(q, "Portfolio Health"), "valuation")
        self.assertIsNone(resolve_valuation_target(q, _SHADOW_CTX))

    def test_h_health_aware_insight_stale_on_objective_change(self) -> None:
        from applied_math_context import investment_ami_insight_staleness_reasons

        insight = {
            "source_app": "investment",
            "source_state": {
                "entity_params": {"objective": "balanced growth", "holdings_fingerprint": "fp1"},
                "filter_params": {},
            },
            "computed": {"ami_engine_id": "portfolio_health"},
        }
        session = {
            "health_objective": "capital preservation",
            "holdings_df": None,
        }
        reasons = investment_ami_insight_staleness_reasons(session, insight)
        self.assertTrue(any("objective" in r for r in reasons))

    def test_pure_sharpe_lookup_stays_metric_path(self) -> None:
        q = "What is my Sharpe ratio?"
        self.assertFalse(is_portfolio_health_question(q))
        # Not valuation (pe-ratio false positive fixed)
        self.assertNotEqual(detect_investment_send_intent(q, ""), "valuation")


if __name__ == "__main__":
    unittest.main()
