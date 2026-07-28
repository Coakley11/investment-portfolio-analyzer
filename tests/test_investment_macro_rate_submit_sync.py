"""Integration: macro rate submit → session params → post-submit rerun render stay in sync."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from applied_math_return_insight import (
    SESSION_PENDING_KEY,
    hydrate_applied_math_insight_for_session,
    investment_insight_main_render_needed,
    render_suite_applied_math_insight_for_page,
)
from investment_ami_sliders import build_scenario_params_from_sliders, slider_specs_for
from suite_analytical_question import _stage_investment_instant_insight, build_question_payload


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

    def container(self, **kwargs: Any):
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

    def slider(self, *args: Any, **kwargs: Any) -> float:
        if "value" in kwargs:
            return float(kwargs["value"])
        if len(args) >= 4:
            return float(args[3])
        return 0.0

    def select_slider(self, *args: Any, **kwargs: Any) -> str:
        if "value" in kwargs:
            return str(kwargs["value"])
        opts = kwargs.get("options") or (args[1] if len(args) > 1 else [])
        return str(opts[0]) if opts else ""


_SUBMIT_CTX = {
    "experience_mode": "Advanced Mode",
    "page": "Macro Outlook",
    "current_weights": {"VTI": "55%", "BND": "45%"},
    "holdings": ["VTI", "BND"],
}


class TestMacroRateSubmitRerunSync(unittest.TestCase):
    def _run_flow(self, question: str) -> tuple[_FakeSt, dict[str, Any]]:
        st = _FakeSt()
        ss = st.session_state
        ss["_ami_scenario_params"] = {"rate_rise_pct": 2.0, "rate_shock": "Rising"}
        submit_ctx = {
            **_SUBMIT_CTX,
            "scenario_params": dict(ss["_ami_scenario_params"]),
        }
        pre_payload = build_question_payload(
            source_app="investment",
            source_page="Macro Outlook",
            question=question,
            context=submit_ctx,
        )
        import applied_math_return_insight as ami

        with patch.object(ami, "store_applied_math_insight"), patch.object(
            ami, "sync_dismissed_insights_from_cloud"
        ), patch.object(ami, "load_latest_applied_math_insight_for_app", return_value=None):
            ok = _stage_investment_instant_insight(
                st,
                ss,
                question=question,
                source_app="investment",
                source_page="Macro Outlook",
                submit_ctx=submit_ctx,
                submit_source_state={"source_page": "Macro Outlook"},
                pre_payload=pre_payload,
                action_url_pre="https://example.test/ami",
            )
        self.assertTrue(ok, ss.get("_ami_investment_submit_diagnostics"))

        ss["investment_active_tab"] = "Macro Outlook"
        hydrate_applied_math_insight_for_session(st, "investment")
        from applied_math_return_insight import clear_stale_insight_render_success_when_pending

        clear_stale_insight_render_success_when_pending(st)
        self.assertTrue(investment_insight_main_render_needed(ss))

        with patch.object(ami, "load_latest_applied_math_insight_for_app", return_value=None), patch.object(
            ami, "sync_dismissed_insights_from_cloud"
        ):
            rendered = render_suite_applied_math_insight_for_page(
                st,
                source_app="investment",
                source_page="Macro Outlook",
            )
        self.assertTrue(rendered)
        pending = ss.get(SESSION_PENDING_KEY) or {}
        return st, pending

    def _slider_init_pp(self, st: _FakeSt, pending: dict[str, Any]) -> float:
        specs = slider_specs_for("macro_rates", pending)
        params = dict(st.session_state.get("_ami_scenario_params") or {})
        values = {s.key: params.get(s.key, s.default) for s in specs}
        merged = build_scenario_params_from_sliders(specs, values, problem_type="macro_rates")
        return float(merged["rate_shock_pp"])

    def _sections(self, pending: dict[str, Any]) -> dict[str, Any]:
        sec = pending.get("analyst_sections")
        if isinstance(sec, dict):
            return sec
        kn = pending.get("key_numbers")
        if isinstance(kn, dict) and isinstance(kn.get("analyst_sections"), dict):
            return dict(kn["analyst_sections"])
        return {}

    def test_fed_rate_cuts_submit_rerun_sync(self) -> None:
        q = "What happens if the Federal Reserve cuts interest rates?"
        st, pending = self._run_flow(q)
        ss = st.session_state
        self.assertEqual(ss["_ami_scenario_params"].get("rate_shock_pp"), -2.0)
        self.assertEqual(ss["_ami_scenario_params"].get("rate_shock"), "Falling")
        self.assertEqual(self._slider_init_pp(st, pending), -2.0)

        sections = self._sections(pending)
        kv = str(sections.get("key_variables") or "")
        self.assertIn("-2.0%", kv)
        direct = str(sections.get("direct_answer") or pending.get("conclusion") or "")
        self.assertIn("Falling Rates", direct)
        actions = str(sections.get("recommended_actions") or "")
        self.assertTrue("cash" in actions.lower() or "duration" in actions.lower())

    def test_fed_rate_hikes_submit_rerun_sync(self) -> None:
        q = "What happens if the Federal Reserve hikes interest rates by 2%?"
        st, pending = self._run_flow(q)
        ss = st.session_state
        self.assertEqual(ss["_ami_scenario_params"].get("rate_shock_pp"), 2.0)
        self.assertEqual(ss["_ami_scenario_params"].get("rate_shock"), "Rising")
        self.assertEqual(self._slider_init_pp(st, pending), 2.0)

        sections = self._sections(pending)
        kv = str(sections.get("key_variables") or "")
        self.assertIn("+2.0%", kv)
        direct = str(sections.get("direct_answer") or pending.get("conclusion") or "")
        self.assertIn("Rising Rates", direct)


if __name__ == "__main__":
    unittest.main()
