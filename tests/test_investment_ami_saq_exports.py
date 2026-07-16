"""Regression: Investment AMI SAQ helpers survive suite sync."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestInvestmentAmiSaqExports(unittest.TestCase):
    def test_required_exports_present(self) -> None:
        from suite_analytical_question import (
            ensure_investment_source_state_portfolio_payload,
            peek_investment_portfolio_entity_params,
            sync_analytical_question_instant_insight,
        )

        self.assertTrue(callable(peek_investment_portfolio_entity_params))
        self.assertTrue(callable(sync_analytical_question_instant_insight))
        self.assertTrue(callable(ensure_investment_source_state_portfolio_payload))

    def test_peek_returns_dict(self) -> None:
        from suite_analytical_question import peek_investment_portfolio_entity_params

        with patch(
            "suite_analytical_question.load_cloud_full_session",
            create=True,
            side_effect=ImportError,
        ):
            out = peek_investment_portfolio_entity_params()
        self.assertIsInstance(out, dict)

    def test_sync_instant_insight_no_payload_returns_false(self) -> None:
        from suite_analytical_question import sync_analytical_question_instant_insight

        with patch(
            "suite_analytical_question.load_analytical_question_payload",
            return_value={},
        ):
            self.assertFalse(
                sync_analytical_question_instant_insight("qid", {"summary": "x"})
            )

    def test_ensure_portfolio_payload_passthrough_non_investment(self) -> None:
        from suite_analytical_question import ensure_investment_source_state_portfolio_payload

        state = {"source_app": "nba", "entity_params": {"x": 1}}
        out = ensure_investment_source_state_portfolio_payload(state)
        self.assertEqual(out.get("source_app"), "nba")


if __name__ == "__main__":
    unittest.main()
