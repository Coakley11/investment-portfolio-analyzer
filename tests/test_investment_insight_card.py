"""Tests for Investment AMI insight card scoping and labels."""

from __future__ import annotations

import unittest
from typing import Any

from applied_math_return_insight import (
    INVESTMENT_INSIGHT_PANEL_TITLE,
    SESSION_PENDING_KEY,
    _insight_panel_title,
    _investment_tabs_match,
    hydrate_applied_math_insight_for_session,
    insight_page_scope_decision,
    should_render_insight_on_page,
)
from suite_analytical_question import (
    INVESTMENT_AMI_STARTER_QUESTIONS,
    investment_ami_default_question,
    source_question_card_title,
)


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()
        self.query_params: dict[str, str] = {}


class TestInvestmentInsightCard(unittest.TestCase):
    def test_investment_tab_aliases_match(self) -> None:
        self.assertTrue(_investment_tabs_match("⑤ Portfolio Health", "Portfolio Health"))
        self.assertFalse(_investment_tabs_match("Overview", "Portfolio Health"))

    def test_strict_page_scope_hides_on_wrong_tab(self) -> None:
        insight = {
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "Test conclusion",
        }
        decision = insight_page_scope_decision("investment", "Portfolio Analytics", insight)
        self.assertFalse(decision["should_render_insight_on_page"])
        self.assertEqual(decision["render_skip_reason"], "source_tab_mismatch")
        self.assertFalse(should_render_insight_on_page("investment", "Portfolio Analytics", insight))

    def test_renders_on_source_tab(self) -> None:
        insight = {
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "Test conclusion",
        }
        self.assertTrue(should_render_insight_on_page("investment", "⑤ Portfolio Health", insight))

    def test_investment_panel_title(self) -> None:
        self.assertEqual(
            _insight_panel_title("investment", {"source_app": "investment"}),
            INVESTMENT_INSIGHT_PANEL_TITLE,
        )
        self.assertEqual(_insight_panel_title("baseball"), "Applied Math Insight")

    def test_investment_starter_questions(self) -> None:
        q = investment_ami_default_question("Portfolio Health")
        self.assertIn(q, INVESTMENT_AMI_STARTER_QUESTIONS)
        self.assertNotIn("meaningful", q.lower())
        self.assertIn(
            source_question_card_title("investment"),
            "Applied Investment Insight question from Investment",
        )

    def test_hydrate_from_cloud(self) -> None:
        st = _FakeSt()
        cloud_insight = {
            "insight_id": "abc123",
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "Cloud insight",
            "question": "Q?",
        }

        def _fake_load(app: str, *, exclude_ids=None):
            self.assertEqual(app, "investment")
            return dict(cloud_insight)

        import applied_math_return_insight as ami

        original = ami.load_latest_applied_math_insight_for_app
        ami.load_latest_applied_math_insight_for_app = _fake_load  # type: ignore[assignment]
        try:
            ok = hydrate_applied_math_insight_for_session(st, "investment")
        finally:
            ami.load_latest_applied_math_insight_for_app = original  # type: ignore[assignment]

        self.assertTrue(ok)
        self.assertEqual(st.session_state[SESSION_PENDING_KEY]["conclusion"], "Cloud insight")
        self.assertEqual(st.session_state["insight_source_tab"], "Portfolio Health")
        self.assertEqual(st.session_state["_ami_insight_hydrate_source"], "cloud_saved_items")


if __name__ == "__main__":
    unittest.main()
