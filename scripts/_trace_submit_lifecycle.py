"""Trace initial AMI submit → main card render (steps 1–7). Run: python scripts/_trace_submit_lifecycle.py"""
from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import patch

ROOT = __file__.replace("\\", "/").rsplit("/scripts/", 1)[0]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT.replace("/", "\\") if sys.platform == "win32" else ROOT)


def _step(steps: list[dict[str, Any]], name: str, **kw: Any) -> None:
    steps.append({"step": name, **kw})


def trace_submit_lifecycle(
    *,
    question: str = "What happens if the Federal Reserve cuts interest rates?",
    active_tab: str = "Forward Macro Analysis",
) -> list[dict[str, Any]]:
    from applied_math_return_insight import (
        AMI_INSIGHT_LIFECYCLE_LOG_KEY,
        SESSION_PENDING_KEY,
        hydrate_applied_math_insight_for_session,
        investment_insight_main_render_needed,
        render_suite_applied_math_insight_for_page,
    )
    from suite_analytical_question import _stage_investment_instant_insight, build_question_payload
    from tests.test_investment_macro_rate_submit_sync import _FakeSt, _SUBMIT_CTX

    steps: list[dict[str, Any]] = []
    st = _FakeSt()
    ss = st.session_state
    submit_ctx = {**_SUBMIT_CTX, "page": active_tab}
    submit_ctx["scenario_params"] = dict(ss.get("_ami_scenario_params") or {"rate_shock_pp": -2.0})
    pre = build_question_payload(
        source_app="investment",
        source_page=active_tab,
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
            source_page=active_tab,
            submit_ctx=submit_ctx,
            submit_source_state={"source_page": active_tab},
            pre_payload=pre,
            action_url_pre="https://example.test/ami",
        )
    pending = ss.get(SESSION_PENDING_KEY)
    _step(
        steps,
        "1_solver_stage",
        ok=ok,
        pending_present=isinstance(pending, dict),
        has_conclusion=bool(isinstance(pending, dict) and pending.get("conclusion")),
        insight_id=(pending or {}).get("insight_id") if isinstance(pending, dict) else None,
    )
    if not ok or not isinstance(pending, dict) or not pending.get("conclusion"):
        _step(steps, "FAIL", at="1_solver_stage")
        return steps

    _step(steps, "2_session_pending_key", pending_keys=sorted(pending.keys())[:12])

    ss["investment_active_tab"] = active_tab
    with patch.object(ami, "sync_dismissed_insights_from_cloud"), patch.object(
        ami, "load_latest_applied_math_insight_for_app", return_value=None
    ):
        hydrate_ok = hydrate_applied_math_insight_for_session(st, "investment")
    pending_after_hydrate = ss.get(SESSION_PENDING_KEY)
    _step(
        steps,
        "3_hydrate",
        hydrate_ok=hydrate_ok,
        hydrate_source=ss.get("_ami_insight_hydrate_source"),
        pending_still_present=isinstance(pending_after_hydrate, dict),
        same_id=(
            isinstance(pending_after_hydrate, dict)
            and pending_after_hydrate.get("insight_id") == pending.get("insight_id")
        ),
    )

    gate = investment_insight_main_render_needed(ss)
    _step(
        steps,
        "4_gate",
        investment_insight_main_render_needed=gate,
        force_flag=ss.get("_ami_force_insight_render"),
        render_success_before_render=ss.get("_ami_insight_render_success"),
    )
    if not gate:
        _step(steps, "FAIL", at="4_gate")
        return steps

    with patch.object(ami, "sync_dismissed_insights_from_cloud"), patch.object(
        ami, "load_latest_applied_math_insight_for_app", return_value=None
    ):
        rendered = render_suite_applied_math_insight_for_page(
            st,
            source_app="investment",
            source_page=active_tab,
        )
    _step(
        steps,
        "5_render_suite",
        called=True,
        rendered=rendered,
        skip_reason=ss.get("_ami_insight_render_skipped_reason"),
    )
    _step(
        steps,
        "6_render_success_flag",
        _ami_insight_render_success=ss.get("_ami_insight_render_success"),
        matches_rendered=ss.get("_ami_insight_render_success") == rendered,
    )
    tail = ss.get(AMI_INSIGHT_LIFECYCLE_LOG_KEY) or []
    _step(steps, "7_lifecycle_tail", entries=tail[-8:])
    if not rendered:
        _step(steps, "FAIL", at="5_render_suite")
    return steps


if __name__ == "__main__":
    out = trace_submit_lifecycle()
    print(json.dumps(out, indent=2, default=str))
