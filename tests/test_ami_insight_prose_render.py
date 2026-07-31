"""Regression: decision-support AMI sections render as Markdown prose, not LaTeX."""

from __future__ import annotations

import unittest

from investment_ami_answer_format import (
    escape_streamlit_markdown_prose,
    insight_section_render_mode,
    render_investment_page_insight_markdown,
)


class TestAmiInsightProseRender(unittest.TestCase):
    _PROSE_SAMPLE = (
        "Current portfolio value: **$100,000**. "
        "**Suggested long-term deployment** from available cash: **$58,451**. "
        "Potentially investable after reserves: **$68,766**. "
        "These are not direct substitutes — hyphenated words and full sentences stay intact."
    )

    def test_portfolio_analyst_view_classified_as_prose(self) -> None:
        sections = {
            "insights_layout": "decision_support",
            "portfolio_analyst_view": self._PROSE_SAMPLE,
        }
        self.assertEqual(
            insight_section_render_mode("portfolio_analyst_view", sections),
            "prose",
        )

    def test_escape_dollar_amounts_for_streamlit_markdown(self) -> None:
        escaped = escape_streamlit_markdown_prose(self._PROSE_SAMPLE)
        self.assertIn("\\$100,000", escaped)
        self.assertIn("\\$58,451", escaped)
        self.assertIn("**Suggested long-term deployment**", escaped)
        self.assertNotIn("$100,000", escaped.replace("\\$100,000", ""))

    def test_decision_support_page_markdown_escapes_currency(self) -> None:
        sections = {
            "insights_layout": "decision_support",
            "direct_answer": "Portfolio approximately **$100,000**.",
            "portfolio_analyst_view": self._PROSE_SAMPLE,
        }
        body = render_investment_page_insight_markdown(sections, beginner=False)
        self.assertIn("**What AMI Observes**", body)
        self.assertIn("\\$100,000", body)
        self.assertIn("\\$58,451", body)
        self.assertIn("**Suggested long-term deployment**", body)


if __name__ == "__main__":
    unittest.main()
