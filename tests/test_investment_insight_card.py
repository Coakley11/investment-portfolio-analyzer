"""Tests for Investment AMI insight card scoping and labels."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

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
from investment_ami_context import INVESTMENT_INSIGHT_QUESTION_CARD_TITLE


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

    def container(self, **kwargs: Any):  # noqa: ANN003
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield self

        return _cm()

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        return None

    def caption(self, *args: Any, **kwargs: Any) -> None:
        return None

    def columns(self, spec: Any) -> list:
        n = max(int(spec), 1)
        return [MagicMock() for _ in range(n)]

    def link_button(self, *args: Any, **kwargs: Any) -> None:
        return None

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False


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
        self.assertEqual(
            source_question_card_title("investment"),
            INVESTMENT_INSIGHT_QUESTION_CARD_TITLE,
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

    def test_post_submit_rerun_gate_ignores_stale_inline_success(self) -> None:
        from applied_math_return_insight import investment_insight_main_render_needed

        ss: dict[str, Any] = {
            SESSION_PENDING_KEY: {
                "source_app": "investment",
                "source_page": "Overview",
                "conclusion": "Instant answer.",
                "question": "What happens if rates rise?",
            },
            "_ami_submit_render_insight_this_run": True,
            "_ami_insight_render_success": True,
            "_ami_last_submit_source_page": "Overview",
        }
        self.assertTrue(investment_insight_main_render_needed(ss))
        self.assertNotIn("_ami_submit_render_insight_this_run", ss)
        self.assertIsNone(ss.get("_ami_insight_render_success"))

    def test_post_submit_rerun_renders_card_on_overview(self) -> None:
        from applied_math_return_insight import (
            investment_insight_main_render_needed,
            render_suite_applied_math_insight_for_page,
        )

        st = _FakeSt()
        st.session_state.update(
            {
                SESSION_PENDING_KEY: {
                    "source_app": "investment",
                    "source_page": "Overview",
                    "conclusion": "Top holding is 45% of the portfolio.",
                    "question": "Is my portfolio too concentrated?",
                    "problem_type": "portfolio_concentration",
                },
                "_ami_submit_render_insight_this_run": True,
                "_ami_insight_render_success": True,
                "_ami_last_submit_source_page": "Overview",
            }
        )

        self.assertTrue(investment_insight_main_render_needed(st.session_state))

        import applied_math_return_insight as ami

        with unittest.mock.patch.object(ami, "load_latest_applied_math_insight_for_app", return_value=None), unittest.mock.patch.object(
            ami, "sync_dismissed_insights_from_cloud"
        ):
            rendered = render_suite_applied_math_insight_for_page(
                st,
                source_app="investment",
                source_page="Overview",
            )
        self.assertTrue(rendered)
        self.assertTrue(st.session_state.get("_ami_insight_render_success"))
        self.assertIsNone(st.session_state.get("_ami_insight_render_skipped_reason"))

    def test_hydrate_submit_rerun_skips_cloud_when_pending_missing(self) -> None:
        import applied_math_return_insight as ami

        st = _FakeSt()
        st.session_state["_ami_submit_render_insight_this_run"] = True
        with patch.object(ami, "load_latest_applied_math_insight_for_app") as mock_load, patch.object(
            ami, "sync_dismissed_insights_from_cloud"
        ):
            ok = hydrate_applied_math_insight_for_session(st, "investment")
        self.assertTrue(ok)
        self.assertEqual(st.session_state.get("_ami_insight_hydrate_source"), "submit_staged_missing_pending")
        mock_load.assert_not_called()

    def test_slider_widget_rerun_opens_default_gate_via_prepare(self) -> None:
        from applied_math_return_insight import (
            investment_insight_main_render_needed,
            prepare_insight_card_widget_rerun,
        )

        st = _FakeSt()
        st.session_state.update(
            {
                SESSION_PENDING_KEY: {
                    "source_app": "investment",
                    "source_page": "Forward Macro Analysis",
                    "conclusion": "Falling Rates scenario.",
                    "question": "Rate cut impact?",
                    "problem_type": "macro_rates",
                },
                "_ami_insight_render_success": True,
            }
        )
        self.assertFalse(investment_insight_main_render_needed(st.session_state))
        st.session_state["_ami_insight_render_success"] = True
        self.assertTrue(prepare_insight_card_widget_rerun(st))
        self.assertTrue(investment_insight_main_render_needed(st.session_state))

    def test_prepare_lifecycle_logs_cleared_stale_success(self) -> None:
        from applied_math_return_insight import (
            AMI_INSIGHT_LIFECYCLE_LOG_KEY,
            prepare_insight_card_widget_rerun,
        )

        st = _FakeSt()
        st.session_state.update(
            {
                SESSION_PENDING_KEY: {
                    "insight_id": "id1",
                    "conclusion": "Answer.",
                    "question": "Q?",
                },
                "_ami_insight_render_success": True,
            }
        )
        prepare_insight_card_widget_rerun(st)
        buf = st.session_state.get(AMI_INSIGHT_LIFECYCLE_LOG_KEY) or []
        outcomes = [e.get("outcome") for e in buf if e.get("step") == "prepare_insight_card_widget_rerun"]
        self.assertEqual(outcomes, ["entered", "cleared_stale_success"])
        cleared = buf[-1]
        self.assertTrue(cleared.get("pending_valid"))
        self.assertTrue(cleared.get("pending_present"))
        self.assertFalse(cleared.get("dismissed"))
        self.assertTrue(cleared.get("render_success_before"))
        self.assertIsNone(cleared.get("render_success_after"))

    def test_prepare_lifecycle_logs_skipped_invalid_pending(self) -> None:
        from applied_math_return_insight import (
            AMI_INSIGHT_LIFECYCLE_LOG_KEY,
            prepare_insight_card_widget_rerun,
        )
        import applied_math_return_insight as ami

        st = _FakeSt()
        st.session_state.update(
            {
                SESSION_PENDING_KEY: {
                    "insight_id": "gone",
                    "conclusion": "Answer.",
                    "question": "Q?",
                },
                "_ami_insight_render_success": True,
            }
        )
        with patch.object(ami, "_insight_is_dismissed", return_value=True):
            prepare_insight_card_widget_rerun(st)
        buf = st.session_state.get(AMI_INSIGHT_LIFECYCLE_LOG_KEY) or []
        outcomes = [e.get("outcome") for e in buf if e.get("step") == "prepare_insight_card_widget_rerun"]
        self.assertEqual(outcomes, ["entered", "skipped_invalid_pending"])
        skip = buf[-1]
        self.assertTrue(skip.get("pending_present"))
        self.assertFalse(skip.get("pending_valid"))
        self.assertTrue(skip.get("dismissed"))
        self.assertTrue(skip.get("render_success_before"))
        self.assertTrue(skip.get("render_success_after"))


if __name__ == "__main__":
    unittest.main()
