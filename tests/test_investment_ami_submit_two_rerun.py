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

    def test_full_pipeline_with_investment_plan_result(self) -> None:
        import portfolio_core as core
        from components.investment_planning import PLAN_MONTHLY_PROVIDED_KEY
        from investment_persistent_state import apply_investment_disk_state, build_investment_disk_state
        from suite_analytical_question import execute_investment_ami_submit_pipeline

        st = _FakeSt()
        ss = st.session_state
        ss.update(
            {
                "plan_total_cash": 120_000,
                "plan_emergency": 25_000,
                "plan_near_term": 10_000,
                "plan_debt": 5_000,
                "plan_expenses": 8_000,
                "plan_horizon": 20,
                "plan_risk": "Medium",
                PLAN_MONTHLY_PROVIDED_KEY: False,
                "investment_plan_generated": True,
                "investment_plan": core.InvestmentPlanResult(
                    total_available=120_000,
                    suggested_emergency_reserve=25_000,
                    short_term_cash_amount=10_000,
                    debt_reserve=5_000,
                    amount_potentially_investable=80_000,
                    long_term_suggested=68_000,
                    short_term_investable=12_000,
                    monthly_contribution=0,
                    summary_lines=[],
                    educational_notes=[],
                ),
                "sidebar_portfolio_value": 75_000,
            }
        )
        question = "Is the amount I currently have invested appropriate?"

        with patch("applied_math_return_insight.store_applied_math_insight", return_value="inv-plan-1"), patch(
            "suite_analytical_question.submit_analytical_question",
            wraps=__import__("suite_analytical_question", fromlist=["submit_analytical_question"]).submit_analytical_question,
        ) as submit_mock, patch(
            "suite_analytical_question._upsert_applied_intelligence_resume",
        ):
            ok, err = execute_investment_ami_submit_pipeline(
                st,
                ss,
                question=question,
                source_page="Portfolio Inputs",
                page_suffix="Portfolio_Inputs",
                send_gen=0,
            )

        self.assertTrue(ok, err)
        self.assertIn(SESSION_PENDING_KEY, ss)
        self.assertTrue(ss.get("_ami_render_requested"))
        submit_mock.assert_called_once()
        metrics_ctx = submit_mock.call_args.kwargs.get("context") or {}
        self.assertIsInstance(metrics_ctx.get("investment_plan"), dict)
        log = ss.get("_ami_submit_pipeline_log") or []
        stages = [e.get("stage") for e in log if e.get("entered")]
        for stage in ("ROUTE", "SOLVE", "STAGE", "SAVE"):
            self.assertIn(stage, stages)

        disk = build_investment_disk_state(st)
        st2 = _FakeSt()
        apply_investment_disk_state(st2, disk)
        restored = st2.session_state.get(SESSION_PENDING_KEY)
        self.assertIsInstance(restored, dict)
        self.assertTrue(restored.get("conclusion") or restored.get("question"))

    def test_pipeline_exception_sets_error_not_processing(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        queue_investment_ami_submit(
            ss,
            question="Is the amount I currently have invested appropriate?",
            source_page="Portfolio Inputs",
            page_suffix="Portfolio_Inputs",
            send_gen=0,
        )
        with patch(
            "suite_analytical_question.execute_investment_ami_submit_pipeline",
            side_effect=RuntimeError("SAVE failed"),
        ):
            process_investment_ami_submit_queue(st)
        self.assertEqual(ss["_ami_insight_submit_status"]["state"], "error")
        self.assertNotEqual(ss["_ami_insight_submit_status"]["state"], "processing")

    def test_json_serialization_failure_sets_error_not_stuck(self) -> None:
        st = _FakeSt()
        ss = st.session_state
        ss.update(
            {
                "plan_total_cash": 120_000,
                "plan_emergency": 25_000,
                "plan_near_term": 10_000,
                "plan_debt": 5_000,
                "plan_expenses": 8_000,
                "plan_horizon": 20,
                "plan_risk": "Medium",
                "investment_plan_generated": True,
                "investment_plan": __import__("portfolio_core").InvestmentPlanResult(
                    total_available=120_000,
                    suggested_emergency_reserve=25_000,
                    short_term_cash_amount=10_000,
                    debt_reserve=5_000,
                    amount_potentially_investable=80_000,
                    long_term_suggested=68_000,
                    short_term_investable=12_000,
                    monthly_contribution=0,
                    summary_lines=[],
                    educational_notes=[],
                ),
                "sidebar_portfolio_value": 75_000,
            }
        )
        queue_investment_ami_submit(
            ss,
            question="Is the amount I currently have invested appropriate?",
            source_page="Portfolio Inputs",
            page_suffix="Portfolio_Inputs",
            send_gen=0,
        )
        with patch("applied_math_return_insight.store_applied_math_insight", return_value="inv-ser-1"), patch(
            "json_safe.ensure_json_safe",
            side_effect=TypeError("Object of type Bad is not JSON serializable"),
        ):
            process_investment_ami_submit_queue(st)
        self.assertEqual(ss["_ami_insight_submit_status"]["state"], "error")
        self.assertIn("TypeError", str(ss["_ami_insight_submit_status"].get("message") or ""))
        self.assertNotIn(SUBMIT_QUEUE_KEY, ss)


if __name__ == "__main__":
    unittest.main()
