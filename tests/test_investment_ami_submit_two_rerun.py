"""Two-rerun Investment AMI submit: queue → main process → hydrate → render."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from applied_math_return_insight import (
    SESSION_PENDING_KEY,
    hydrate_applied_math_insight_for_session,
    investment_insight_main_render_needed,
    render_suite_applied_math_insight_for_page,
)
from investment_ami_submit_runtime import (
    SUBMIT_QUEUE_KEY,
    queue_investment_ami_submit,
    process_investment_ami_submit_queue,
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
        self.session_state = _FakeSessionState(investment_active_tab="Portfolio Inputs")
        self.markdown = MagicMock()
        self.info = MagicMock()
        self.error = MagicMock()
        self.success = MagicMock()
        self.warning = MagicMock()
        self.caption = MagicMock()
        self.columns = MagicMock(return_value=[MagicMock(), MagicMock()])
        self.button = MagicMock(return_value=False)
        self.link_button = MagicMock()


class TestInvestmentAmiSubmitTwoRerun(unittest.TestCase):
    def test_queue_then_main_process_stages_render_request(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        question = "Is the amount I currently have invested appropriate?"

        queue_investment_ami_submit(
            ss,
            question=question,
            source_page="Portfolio Inputs",
            page_suffix="Portfolio_Inputs",
            send_gen=0,
        )
        self.assertEqual(ss["_ami_insight_submit_status"]["state"], "processing")
        self.assertIn(SUBMIT_QUEUE_KEY, ss)

        def _fake_exec(_st_obj, session, **_kw):
            session.update(
                {
                    "_ami_pending_insight": {
                        "insight_id": "inv-test-1",
                        "question": question,
                        "conclusion": "Your invested amount fits the plan.",
                        "source_page": "Portfolio Inputs",
                        "analyst_sections": {"insights_layout": "decision_support"},
                    },
                    "_ami_investment_instant_canonical": {"insight_id": "inv-test-1"},
                    "_ami_submit_render_insight_this_run": True,
                    "_ami_force_insight_render": True,
                }
            )
            return True, ""

        with patch(
            "suite_analytical_question.execute_investment_ami_submit_pipeline",
            side_effect=_fake_exec,
        ):
            handled = process_investment_ami_submit_queue(st)

        self.assertTrue(handled)
        self.assertEqual(ss["_ami_insight_submit_status"]["state"], "success")
        self.assertNotIn(SUBMIT_QUEUE_KEY, ss)
        self.assertTrue(ss.get("_ami_render_requested"))

    def test_hydrate_between_submit_and_render_keeps_pending(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss["_ami_render_requested"] = True
        ss["_ami_pending_insight"] = {
            "insight_id": "inv-hydrate-1",
            "question": "Am I holding too much cash?",
            "conclusion": "Cash buffer looks adequate.",
            "source_page": "Portfolio Inputs",
        }
        ss["_ami_insight_submit_status"] = {"state": "success", "insight_id": "inv-hydrate-1"}

        with patch(
            "applied_math_return_insight.load_latest_applied_math_insight_for_app",
            return_value={
                "insight_id": "old-cloud-id",
                "conclusion": "Old legacy insight.",
                "source_page": "Portfolio Health",
            },
        ):
            hydrate_applied_math_insight_for_session(st, "investment")

        self.assertEqual(str(ss["_ami_pending_insight"].get("insight_id")), "inv-hydrate-1")
        self.assertTrue(investment_insight_main_render_needed(ss))

        with patch("applied_math_return_insight.render_applied_math_insight_panel", return_value=True):
            rendered = render_suite_applied_math_insight_for_page(
                st, source_app="investment", source_page="Portfolio Inputs"
            )
        self.assertTrue(rendered)
        self.assertFalse(ss.get("_ami_render_requested"))


if __name__ == "__main__":
    unittest.main()
