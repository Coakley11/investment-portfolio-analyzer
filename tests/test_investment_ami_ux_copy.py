"""Investment AMI sidebar and insight panel use outcome-focused copy."""

from __future__ import annotations

import unittest

from investment_ami_context import (
    INVESTMENT_INSIGHT_PANEL_TITLE,
    INVESTMENT_INSIGHT_SIDEBAR_HEADING,
    INVESTMENT_INSIGHT_SUBMIT_LABEL,
    INVESTMENT_INSIGHT_FULL_ANALYSIS_BUTTON,
    investment_insight_duplicate_message,
    investment_insight_sent_message,
)
from suite_analytical_question import (
    _ami_sidebar_feedback_messages,
    analytical_question_continue_copy,
    build_question_payload,
)


class TestInvestmentAmiUxCopy(unittest.TestCase):
    def test_sidebar_labels_avoid_command_center(self) -> None:
        self.assertNotIn("Command Center", INVESTMENT_INSIGHT_SIDEBAR_HEADING)
        self.assertNotIn("Command Center", INVESTMENT_INSIGHT_SUBMIT_LABEL)
        self.assertEqual(INVESTMENT_INSIGHT_SUBMIT_LABEL, "Generate Investment Insight")

    def test_investment_feedback_messages(self) -> None:
        dup, ok = _ami_sidebar_feedback_messages("investment")
        self.assertNotIn("Command Center", dup)
        self.assertNotIn("Command Center", ok)
        self.assertEqual(dup, investment_insight_duplicate_message())
        self.assertEqual(ok, investment_insight_sent_message())

    def test_continue_copy_for_investment(self) -> None:
        payload = build_question_payload(
            source_app="investment",
            source_page="Portfolio Health",
            question="Am I too concentrated in tech?",
            context={},
        )
        _title, _subtitle, button = analytical_question_continue_copy(payload)
        self.assertEqual(button, "View Investment Insight →")
        self.assertNotIn("Command Center", button)

    def test_panel_and_full_analysis_labels(self) -> None:
        self.assertEqual(INVESTMENT_INSIGHT_PANEL_TITLE, "Investment Insight")
        self.assertEqual(INVESTMENT_INSIGHT_FULL_ANALYSIS_BUTTON, "View Investment Insight →")


if __name__ == "__main__":
    unittest.main()
