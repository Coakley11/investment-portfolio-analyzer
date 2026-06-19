"""Investment AMI UX fixes: mode-aware dedupe, dismiss, immediate render flags."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from applied_math_return_insight import (
    SESSION_DISMISSED_KEY,
    SESSION_PENDING_KEY,
    _pending_insight_valid,
    dismiss_applied_math_insight,
    hydrate_applied_math_insight_for_session,
    render_suite_applied_math_insight_for_page,
)
from suite_analytical_question import question_dedupe_fingerprint, question_id


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
        self.container = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
        self.markdown = MagicMock()
        self.caption = MagicMock()
        self.columns = MagicMock(return_value=[MagicMock(), MagicMock()])
        self.button = MagicMock(return_value=False)
        self.link_button = MagicMock()


class TestInvestmentAmiUx(unittest.TestCase):
    def test_experience_mode_changes_question_id(self) -> None:
        adv = question_id(
            "Is my portfolio too concentrated?",
            source_app="investment",
            source_page="Portfolio Health",
            context={"holdings": "voo,bnd", "health_score": 72, "experience_mode": "Advanced Mode"},
        )
        beg = question_id(
            "Is my portfolio too concentrated?",
            source_app="investment",
            source_page="Portfolio Health",
            context={"holdings": "voo,bnd", "health_score": 72, "experience_mode": "Beginner Mode"},
        )
        self.assertNotEqual(adv, beg)

    def test_same_mode_same_question_id(self) -> None:
        ctx = {"experience_mode": "Advanced Mode", "holdings": "voo"}
        a = question_dedupe_fingerprint(
            "Should I rebalance?",
            source_app="investment",
            source_page="Portfolio Health",
            context=ctx,
        )
        b = question_dedupe_fingerprint(
            "Should I rebalance?",
            source_app="investment",
            source_page="Portfolio Health",
            context=ctx,
        )
        self.assertEqual(a, b)

    def test_dismiss_hides_pending_insight(self) -> None:
        st = _FakeSt()
        st.session_state[SESSION_PENDING_KEY] = {
            "insight_id": "inv-dismiss-1",
            "source_app": "investment",
            "conclusion": "Top weight VOO 40%.",
        }
        with patch("applied_math_return_insight.persist_insight_dismissal_to_cloud"), patch(
            "investment_persistent_state.autosave_investment_state"
        ):
            dismiss_applied_math_insight(st, app_key="investment")
        self.assertNotIn(SESSION_PENDING_KEY, st.session_state)
        self.assertIn("inv-dismiss-1", st.session_state.get(SESSION_DISMISSED_KEY, []))
        self.assertEqual(_pending_insight_valid(st), {})

    def test_hydrate_submit_staged_skips_cloud(self) -> None:
        st = _FakeSt()
        st.session_state[SESSION_PENDING_KEY] = {
            "insight_id": "inv-stage-1",
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "conclusion": "Staged answer.",
        }
        st.session_state["_ami_submit_render_insight_this_run"] = True

        with patch("applied_math_return_insight.load_latest_applied_math_insight_for_app") as mock_load:
            ok = hydrate_applied_math_insight_for_session(st, "investment")
        self.assertTrue(ok)
        self.assertEqual(st.session_state.get("_ami_insight_hydrate_source"), "submit_staged")
        mock_load.assert_not_called()

    def test_force_render_on_submit_page(self) -> None:
        st = _FakeSt()
        insight = {
            "insight_id": "inv-render-1",
            "source_app": "investment",
            "source_page": "Portfolio Analytics",
            "conclusion": "Tech exposure is elevated.",
            "question": "Am I too exposed to tech?",
        }
        st.session_state[SESSION_PENDING_KEY] = insight
        st.session_state["_ami_submit_render_insight_this_run"] = True
        st.session_state["_ami_last_submit_source_page"] = "Portfolio Analytics"

        with patch(
            "applied_math_return_insight.render_applied_math_insight_panel",
            return_value=True,
        ) as mock_panel:
            ok = render_suite_applied_math_insight_for_page(
                st,
                source_app="investment",
                source_page="④ Analyze Portfolio",
            )
        self.assertTrue(ok)
        mock_panel.assert_called_once()
        self.assertTrue(st.session_state.get("_ami_insight_render_success"))

    def test_resolve_canonical_prefers_pending_over_cloud(self) -> None:
        from applied_math_return_insight import resolve_canonical_instant_insight

        st = _FakeSt()
        st.query_params = {"suite_ami_insight": "abc123"}
        st.session_state[SESSION_PENDING_KEY] = {
            "insight_id": "abc123",
            "conclusion": "Updated scenario",
            "analyst_sections": {"proposed_portfolio": "- **VTI** 35.0%"},
            "scenario_params": {"allocation_overrides": {"VTI": 35.0}},
        }
        stale = {
            "insight_id": "abc123",
            "conclusion": "Original saved insight",
            "analyst_sections": {"current_portfolio": "- **VTI** 40.0%"},
        }
        with patch("applied_math_return_insight.load_applied_math_insight", return_value=stale):
            resolved = resolve_canonical_instant_insight(st, {}, source_app="investment")
        self.assertEqual(resolved.get("conclusion"), "Updated scenario")
        self.assertIn("proposed_portfolio", resolved.get("analyst_sections") or {})
        self.assertEqual(
            st.session_state.get("_ami_scenario_params", {}).get("allocation_overrides", {}).get("VTI"),
            35.0,
        )


if __name__ == "__main__":
    unittest.main()
