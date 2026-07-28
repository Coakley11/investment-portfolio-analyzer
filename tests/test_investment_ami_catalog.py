"""P1 question catalog and routing tests."""

from __future__ import annotations

import unittest

import investment_ami_context as legacy
from investment_ami.catalog.registry import (
    all_question_definitions,
    get_question_definition,
    reset_question_catalog_for_tests,
)
from investment_ami.routing.router import route_instant_question


class TestInvestmentAmiCatalog(unittest.TestCase):
    def setUp(self) -> None:
        reset_question_catalog_for_tests()

    def test_every_legacy_intent_has_catalog_entry(self) -> None:
        for intent_id in legacy._INVESTMENT_SOLVER_INTENTS:  # noqa: SLF001
            defn = get_question_definition(intent_id)
            self.assertIsNotNone(defn, msg=intent_id)
            assert defn is not None
            self.assertEqual(defn.id, intent_id)

    def test_starter_questions_map_to_intents(self) -> None:
        catalog = {d.id: d for d in all_question_definitions()}
        for starter in legacy.INVESTMENT_AMI_STARTER_QUESTIONS:
            routed = route_instant_question(starter, {"page": "Portfolio Health"})
            self.assertIsNotNone(routed, msg=starter)
            assert routed is not None
            self.assertIn(starter, catalog[routed.intent_id].starter_questions)

    def test_router_matches_legacy_detect(self) -> None:
        q = "Should I own both VOO and QQQ?"
        legacy_intent = legacy.detect_investment_send_intent(q, "")
        routed = route_instant_question(q, {})
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed.intent_id, legacy_intent)


if __name__ == "__main__":
    unittest.main()
