"""End-to-end AMI decision-support submit → session → render (Streamlit staging path)."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from applied_math_return_insight import (
    SESSION_PENDING_KEY,
    _resolve_insight_analyst_sections,
    hydrate_applied_math_insight_for_session,
    insight_has_displayable_content,
    insight_page_scope_decision,
    investment_insight_main_render_needed,
    render_applied_math_insight_panel,
    render_ami_insight_submit_feedback,
    render_suite_applied_math_insight_for_page,
)
from suite_analytical_question import (
    _stage_investment_instant_insight,
    build_question_payload,
    build_submit_context,
)

QUESTIONS = (
    "Is the amount I currently have invested appropriate?",
    "Am I holding too much cash?",
    "Is my emergency fund large enough?",
)


class _FakeSessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()
        self.container = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
        self.markdown = MagicMock()
        self.info = MagicMock()
        self.success = MagicMock()
        self.warning = MagicMock()
        self.error = MagicMock()
        self.caption = MagicMock()
        self.columns = MagicMock(return_value=[MagicMock(), MagicMock()])
        self.button = MagicMock(return_value=False)
        self.link_button = MagicMock()


class TestDecisionSupportSubmitE2E(unittest.TestCase):
    def _base_session(self) -> _FakeSessionState:
        from components.investment_planning import PLAN_MONTHLY_PROVIDED_KEY

        ss = _FakeSessionState(
            investment_active_tab="Portfolio Inputs",
            plan_total_cash=120_000,
            plan_emergency=25_000,
            plan_near_term=5_000,
            plan_debt=0,
            plan_expenses=0,
            investment_plan_generated=True,
            sidebar_portfolio_value=80_000,
        )
        ss[PLAN_MONTHLY_PROVIDED_KEY] = False
        return ss

    def test_three_questions_stage_select_and_survive_rerun(self) -> None:
        from components.investment_planning import PLAN_MONTHLY_PROVIDED_KEY

        import applied_math_return_insight as ami

        for question in QUESTIONS:
            with self.subTest(question=question):
                st = _FakeSt()
                ss = self._base_session()
                ss[PLAN_MONTHLY_PROVIDED_KEY] = False
                st.session_state = ss
                page = "Portfolio Inputs"
                ctx = build_submit_context("investment", page, ss)
                pre = build_question_payload(
                    source_app="investment",
                    source_page=page,
                    question=question,
                    context=ctx,
                )
                with patch.object(ami, "store_applied_math_insight", return_value={"ok": True}):
                    ok = _stage_investment_instant_insight(
                        st,
                        ss,
                        question=question,
                        source_app="investment",
                        source_page=page,
                        submit_ctx=ctx,
                        submit_source_state={},
                        pre_payload=pre,
                    )
                self.assertTrue(ok, ss.get("_ami_investment_submit_diagnostics"))
                pending = ss.get(SESSION_PENDING_KEY)
                self.assertIsInstance(pending, dict)
                self.assertTrue(insight_has_displayable_content(pending))
                self.assertTrue(str(pending.get("insight_id") or "").strip())
                self.assertEqual(str(pending.get("source_page") or ""), page)
                scope = insight_page_scope_decision("investment", page, pending)
                self.assertTrue(scope.get("should_render_insight_on_page"), scope)

                ss["_ami_submit_render_insight_this_run"] = True
                with patch.object(ami, "load_latest_applied_math_insight_for_app", return_value=None), patch.object(
                    ami, "sync_dismissed_insights_from_cloud"
                ):
                    hydrate_applied_math_insight_for_session(st, "investment")
                self.assertTrue(investment_insight_main_render_needed(ss))
                with patch.object(ami, "insight_exists_in_cloud", return_value=False):
                    rendered = render_suite_applied_math_insight_for_page(
                        st, source_app="investment", source_page=page
                    )
                self.assertTrue(rendered, ss.get("_ami_insight_render_skipped_reason"))
                panel = render_applied_math_insight_panel(st, source_app="investment", insight=pending)
                self.assertTrue(panel)
                sections, is_ds, legacy_stale = _resolve_insight_analyst_sections(pending)
                self.assertFalse(legacy_stale, pending.get("conclusion"))
                self.assertTrue(is_ds, sections)
                self.assertIsInstance(sections, dict)
                self.assertEqual(str((sections or {}).get("insights_layout") or ""), "decision_support")

    def test_submit_success_and_processing_status_messages(self) -> None:
        import applied_math_return_insight as ami

        st = _FakeSt()
        ss = self._base_session()
        st.session_state = ss
        ss["_ami_insight_submit_status"] = {"state": "processing"}
        render_ami_insight_submit_feedback(st, insight_rendered=False)
        st.info.assert_called()

        ss["_ami_insight_submit_status"] = {"state": "success"}
        render_ami_insight_submit_feedback(st, insight_rendered=True)
        st.success.assert_called()
        st.warning.assert_not_called()

        st.warning.reset_mock()
        ss["_ami_insight_submit_status"] = {"state": "success"}
        render_ami_insight_submit_feedback(st, insight_rendered=False)
        st.warning.assert_called()

    def test_pending_insight_survives_disk_roundtrip(self) -> None:
        import applied_math_return_insight as ami

        from investment_persistent_state import apply_investment_disk_state, build_investment_disk_state

        st = _FakeSt()
        ss = self._base_session()
        st.session_state = ss
        page = "Portfolio Inputs"
        q = QUESTIONS[0]
        ctx = build_submit_context("investment", page, ss)
        pre = build_question_payload(
            source_app="investment", source_page=page, question=q, context=ctx
        )
        with patch.object(ami, "store_applied_math_insight", return_value={"ok": True}):
            self.assertTrue(
                _stage_investment_instant_insight(
                    st,
                    ss,
                    question=q,
                    source_app="investment",
                    source_page=page,
                    submit_ctx=ctx,
                    submit_source_state={},
                    pre_payload=pre,
                )
            )
        disk = build_investment_disk_state(st)
        st2 = _FakeSt()
        apply_investment_disk_state(st2, disk)
        pending = st2.session_state.get(SESSION_PENDING_KEY)
        self.assertIsInstance(pending, dict)
        self.assertTrue(insight_has_displayable_content(pending))
        self.assertEqual(str(pending.get("question") or ""), q)

    def test_stage_failure_surfaces_error_status(self) -> None:
        st = _FakeSt()
        ss = _FakeSessionState(investment_active_tab="Portfolio Inputs")
        st.session_state = ss
        with patch("investment_ami_instant_solver.solve_instant_investment_insight", return_value=None):
            ok = _stage_investment_instant_insight(
                st,
                ss,
                question="Am I holding too much cash?",
                source_app="investment",
                source_page="Portfolio Inputs",
                submit_ctx={},
                submit_source_state={},
                pre_payload={},
            )
        self.assertFalse(ok)
        self.assertNotIn(SESSION_PENDING_KEY, ss)


if __name__ == "__main__":
    unittest.main()