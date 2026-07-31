"""Regression tests for active Applied Investment Insight selection and restore."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from applied_math_return_insight import (
    ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY,
    SESSION_PENDING_KEY,
    commit_applied_investment_insight_after_render,
    hydrate_applied_math_insight_for_session,
    load_latest_applied_math_insight_for_app,
    render_suite_applied_math_insight_for_page,
    resolve_active_applied_investment_insight_id,
)
from investment_persistent_state import apply_investment_disk_state, build_investment_disk_state


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

    def columns(self, spec: Any) -> list[Any]:
        n = max(int(spec), 1)
        from unittest.mock import MagicMock

        return [MagicMock() for _ in range(n)]

    def link_button(self, *args: Any, **kwargs: Any) -> None:
        return None

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def info(self, *args: Any, **kwargs: Any) -> None:
        return None


def _insight(iid: str, *, conclusion: str, revision: int = 1, updated_at: str = "") -> dict[str, Any]:
    return {
        "insight_id": iid,
        "source_app": "investment",
        "source_page": "Portfolio Inputs",
        "question": "Is my portfolio investment reasonable?",
        "conclusion": conclusion,
        "analyst_sections": {"insights_layout": "decision_support", "direct_answer": conclusion},
        "insight_revision": revision,
        "updated_at": updated_at or f"2026-07-30T12:00:{revision:02d}Z",
        "canonical_instant": True,
    }


class TestInvestmentInsightActiveSelection(unittest.TestCase):
    def test_commit_sets_active_pointer_and_clears_render_flags(self) -> None:
        st = _FakeSt()
        st.session_state["_suite_inv_persistence_bootstrapped"] = True
        st.session_state["_ami_render_requested"] = True
        st.session_state["_ami_insight_render_success"] = True
        blob = _insight("insight-b", conclusion="Structured B")
        st.session_state[SESSION_PENDING_KEY] = dict(blob)

        stored: list[dict[str, Any]] = []

        def _store(data: dict[str, Any], **kwargs: Any) -> str:
            stored.append(dict(data))
            return str(data.get("insight_id") or "")

        with patch("applied_math_return_insight.store_applied_math_insight", side_effect=_store), patch(
            "investment_persistent_state.autosave_investment_state"
        ):
            result = commit_applied_investment_insight_after_render(st, blob)

        self.assertTrue(result["ok"])
        self.assertEqual(resolve_active_applied_investment_insight_id(st.session_state), "insight-b")
        self.assertEqual(st.session_state[ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY], "insight-b")
        self.assertIsNone(st.session_state.get("_ami_render_requested"))
        self.assertIsNone(st.session_state.get("_ami_insight_render_success"))
        self.assertEqual(st.session_state[SESSION_PENDING_KEY]["insight_id"], "insight-b")
        self.assertTrue(stored)

    def test_navigation_persistence_prefers_b_over_a(self) -> None:
        import applied_math_return_insight as ami

        st = _FakeSt()
        st.session_state["_suite_inv_persistence_bootstrapped"] = True
        st.session_state[ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY] = "insight-a"
        st.session_state[SESSION_PENDING_KEY] = _insight("insight-b", conclusion="New B", revision=3)

        def _load(iid: str, *, source_app: str = "") -> dict[str, Any]:
            if iid == "insight-a":
                return _insight("insight-a", conclusion="Old A", revision=1)
            if iid == "insight-b":
                return _insight("insight-b", conclusion="New B", revision=3)
            return {}

        with patch.object(ami, "load_applied_math_insight", side_effect=_load), patch.object(
            ami, "sync_dismissed_insights_from_cloud"
        ), patch.object(ami, "load_latest_applied_math_insight_for_app", return_value={}):
            commit_applied_investment_insight_after_render(st, st.session_state[SESSION_PENDING_KEY])
            st.session_state["investment_active_tab"] = "How Much Should I Invest?"
            hydrate_applied_math_insight_for_session(st, "investment")

        self.assertEqual(
            st.session_state[SESSION_PENDING_KEY]["insight_id"],
            "insight-b",
        )
        self.assertIn("New B", st.session_state[SESSION_PENDING_KEY]["conclusion"])

    def test_refresh_rehydrate_restores_active_b(self) -> None:
        st = _FakeSt()
        st.session_state.update(
            {
                "_suite_inv_persistence_bootstrapped": True,
                ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY: "insight-b",
                SESSION_PENDING_KEY: _insight("insight-b", conclusion="New B", revision=2),
                "investment_active_tab": "Portfolio Inputs",
            }
        )
        disk = build_investment_disk_state(st)

        st2 = _FakeSt()
        st2.session_state["_suite_inv_persistence_bootstrapped"] = True
        apply_investment_disk_state(st2, disk)

        import applied_math_return_insight as ami

        with patch.object(ami, "sync_dismissed_insights_from_cloud"), patch.object(
            ami, "load_applied_math_insight",
            return_value=_insight("insight-b", conclusion="New B", revision=2),
        ), patch.object(ami, "load_latest_applied_math_insight_for_app", return_value={}):
            hydrate_applied_math_insight_for_session(st2, "investment")

        self.assertEqual(resolve_active_applied_investment_insight_id(st2.session_state), "insight-b")
        self.assertEqual(st2.session_state[SESSION_PENDING_KEY]["insight_id"], "insight-b")

    def test_commit_failure_keeps_pending_and_does_not_switch_active(self) -> None:
        st = _FakeSt()
        st.session_state[ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY] = "insight-a"
        pending = _insight("insight-b", conclusion="New B")
        st.session_state[SESSION_PENDING_KEY] = pending
        st.session_state["_ami_render_requested"] = True

        with patch(
            "applied_math_return_insight.store_applied_math_insight",
            return_value="",
        ):
            result = commit_applied_investment_insight_after_render(st, pending)

        self.assertFalse(result["ok"])
        self.assertEqual(st.session_state[ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY], "insight-a")
        self.assertEqual(st.session_state[SESSION_PENDING_KEY]["insight_id"], "insight-b")
        self.assertTrue(st.session_state.get("_ami_render_requested"))
        status = st.session_state.get("_ami_insight_submit_status") or {}
        self.assertEqual(str(status.get("state")), "error")

    def test_newest_insight_precedence_over_legacy(self) -> None:
        rows = [
            {
                "item_key": "insight-a",
                "payload": _insight("insight-a", conclusion="Old A", revision=1, updated_at="2026-01-01T00:00:00Z"),
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "item_key": "insight-b",
                "payload": _insight("insight-b", conclusion="New B", revision=5, updated_at="2026-07-30T00:00:00Z"),
                "updated_at": "2026-07-30T00:00:00Z",
            },
        ]

        with patch("suite_account.load_saved_items", return_value=rows), patch(
            "applied_math_return_insight._insight_from_persisted_full_session",
            return_value={},
        ):
            latest = load_latest_applied_math_insight_for_app("investment")

        self.assertEqual(latest.get("insight_id"), "insight-b")
        self.assertIn("New B", str(latest.get("conclusion")))

    def test_render_commit_then_return_to_source_tab(self) -> None:
        import applied_math_return_insight as ami

        st = _FakeSt()
        st.session_state["_suite_inv_persistence_bootstrapped"] = True
        st.session_state[ACTIVE_APPLIED_INVESTMENT_INSIGHT_ID_KEY] = "insight-a"
        insight_b = _insight("insight-b", conclusion="Structured B", revision=2)
        st.session_state[SESSION_PENDING_KEY] = dict(insight_b)
        st.session_state["_ami_last_submit_source_page"] = "Portfolio Inputs"

        with patch.object(ami, "store_applied_math_insight", return_value="insight-b"), patch(
            "investment_persistent_state.autosave_investment_state"
        ), patch.object(ami, "sync_dismissed_insights_from_cloud"), patch.object(
            ami, "load_latest_applied_math_insight_for_app", return_value={}
        ), patch.object(
            ami, "render_applied_math_insight_panel", return_value=True
        ):
            rendered = render_suite_applied_math_insight_for_page(
                st,
                source_app="investment",
                source_page="Portfolio Inputs",
            )
            self.assertTrue(rendered)
            st.session_state["investment_active_tab"] = "How Much Should I Invest?"
            hydrate_applied_math_insight_for_session(st, "investment")
            st.session_state["investment_active_tab"] = "Portfolio Inputs"
            from applied_math_return_insight import investment_insight_main_render_needed

            self.assertTrue(investment_insight_main_render_needed(st.session_state))
            rendered_again = render_suite_applied_math_insight_for_page(
                st,
                source_app="investment",
                source_page="Portfolio Inputs",
            )

        self.assertTrue(rendered_again)
        self.assertEqual(st.session_state[SESSION_PENDING_KEY]["insight_id"], "insight-b")


if __name__ == "__main__":
    unittest.main()
