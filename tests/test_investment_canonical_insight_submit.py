"""Investment submit stores canonical instant insight."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from suite_analytical_question import (
    _stage_investment_instant_insight,
    build_question_payload,
    metrics_for_applied_math_resume,
)


class TestInvestmentCanonicalSubmit(unittest.TestCase):
    def test_metrics_include_ami_insight(self) -> None:
        payload = build_question_payload(
            source_app="investment",
            source_page="Portfolio Health",
            question="Is my portfolio too concentrated?",
            context={"experience_mode": "Advanced Mode"},
        )
        payload["instant_insight"] = {"insight_id": "inv-1", "conclusion": "Concentrated.", "canonical_instant": True}
        metrics = metrics_for_applied_math_resume(payload)
        self.assertEqual(metrics.get("ami_insight"), "inv-1")

    def test_stage_investment_instant_insight_stores_canonical(self) -> None:
        st = MagicMock()
        ss: dict = {}
        st.session_state = ss
        pre_payload = build_question_payload(
            source_app="investment",
            source_page="Portfolio Health",
            question="Is my portfolio too concentrated?",
            context={
                "experience_mode": "Advanced Mode",
                "current_weights": {"VOO": "50%", "BND": "50%"},
            },
        )

        def _stage(_st, _insight, **kwargs):
            ss["_ami_pending_insight"] = {"insight_id": "inv-1", "conclusion": "Top weight VOO 50%."}

        with patch("applied_math_return_insight.store_applied_math_insight") as mock_store, patch(
            "applied_math_return_insight.stage_pending_insight",
            side_effect=_stage,
        ), patch(
            "applied_math_return_insight.build_return_insight_payload",
            return_value=MagicMock(
                to_dict=lambda: {
                    "insight_id": "inv-1",
                    "conclusion": "Top weight VOO 50%.",
                    "question_id": pre_payload["question_id"],
                }
            ),
        ):
            ok = _stage_investment_instant_insight(
                st,
                ss,
                question=pre_payload["question"],
                source_app="investment",
                source_page="Portfolio Health",
                submit_ctx=dict(pre_payload["context"]),
                submit_source_state={"source_page": "Portfolio Health"},
                pre_payload=pre_payload,
                action_url_pre="https://example.test/ami",
            )
        self.assertTrue(ok)
        mock_store.assert_called_once()
        store_blob = mock_store.call_args.args[0]
        self.assertTrue(store_blob.get("canonical_instant"))
        self.assertEqual(ss.get("_ami_investment_instant_canonical", {}).get("insight_id"), "inv-1")

    def test_investment_sidebar_submit_stages_before_command_center_send(self) -> None:
        from suite_analytical_question import render_analyze_with_applied_math_sidebar

        st = MagicMock()
        ss: dict = {}
        st.session_state = ss
        st.sidebar.button.return_value = True
        st.sidebar.text_area.return_value = "What happens if rates rise?"

        with patch(
            "investment_ami_submit_runtime.queue_investment_ami_submit",
        ) as queue_mock, patch.object(st, "rerun") as rerun_mock:
            render_analyze_with_applied_math_sidebar(
                st,
                source_app="investment",
                source_page="Portfolio Health",
                session_state=ss,
            )

        queue_mock.assert_called_once()
        rerun_mock.assert_called_once()
        self.assertEqual(queue_mock.call_args.kwargs.get("question"), "What happens if rates rise?")


if __name__ == "__main__":
    unittest.main()
