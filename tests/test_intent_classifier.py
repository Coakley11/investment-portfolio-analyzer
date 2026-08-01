"""Intent classifier unit tests."""

from __future__ import annotations

import unittest

from investment_ami.routing.intent_classifier import classify_routing_intent
from investment_ami.routing.mode_router import route_investment_response_mode

_CTX = {"page": "Overview", "current_weights": {"VOO": "55%", "BND": "45%"}}


class TestIntentClassifier(unittest.TestCase):
    def test_historical_multi_crisis_prefers_synthesis(self) -> None:
        q = (
            "Analyze how my portfolio would likely have performed during the 2008 Financial Crisis, "
            "the COVID-19 crash of 2020, and the inflationary period of 2022."
        )
        mode = route_investment_response_mode(q, _CTX)
        self.assertEqual(mode.response_mode, "analytical_synthesis")
        self.assertTrue(mode.intent_classification.get("prefer_synthesis"))

    def test_sector_percentage_stays_deterministic(self) -> None:
        q = "What percentage of my portfolio is technology?"
        mode = route_investment_response_mode(q, _CTX)
        self.assertEqual(mode.response_mode, "deterministic")
        self.assertEqual(mode.deterministic_intent, "sector_exposure")

    def test_why_question_prefers_synthesis(self) -> None:
        q = "Why would a recession affect global equity markets differently than bonds?"
        intent = classify_routing_intent(
            q,
            q_normalized=q.lower(),
            legacy_intent_hint="macro_recession",
            has_portfolio_context=True,
        )
        self.assertTrue(intent.prefer_synthesis)
        mode = route_investment_response_mode(q, _CTX)
        self.assertEqual(mode.response_mode, "analytical_synthesis")

    def test_intent_snapshot_on_decision(self) -> None:
        q = "Critique my portfolio as an institutional portfolio manager."
        mode = route_investment_response_mode(q, _CTX)
        self.assertIn("primary", mode.intent_classification)
        self.assertIn("reasoning_score", mode.intent_classification)


if __name__ == "__main__":
    unittest.main()
