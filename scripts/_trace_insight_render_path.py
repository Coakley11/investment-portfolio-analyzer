"""Trace Investment insight render path (post-submit rerun simulation). No app code changes."""
from __future__ import annotations

import copy
import sys
from typing import Any
from unittest.mock import MagicMock

ROOT = __file__.replace("\\", "/").rsplit("/scripts/", 1)[0]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT.replace("/", "\\") if sys.platform == "win32" else ROOT)


def _log(steps: list[dict[str, Any]], step: str, **details: Any) -> None:
    steps.append({"step": step, **details})


def simulate_post_submit_rerun(
    *,
    active_tab: str,
    sidebar_tab_at_submit: str | None = None,
    beginner_label: bool = False,
) -> list[dict[str, Any]]:
    from applied_math_return_insight import (
        SESSION_PENDING_KEY,
        hydrate_applied_math_insight_for_session,
        investment_insight_main_render_needed,
        render_suite_applied_math_insight_for_page,
    )
    from suite_analytical_question import (
        _stage_investment_instant_insight,
        build_applied_math_resume_url,
        build_question_payload,
        render_suite_applied_math_insight,
    )

    steps: list[dict[str, Any]] = []
    st = MagicMock()
    ss: dict[str, Any] = {}
    st.session_state = ss
    st.columns = lambda n: [MagicMock() for _ in range(max(int(n), 1))]

    submit_page = sidebar_tab_at_submit or active_tab
    ctx = {
        "page": submit_page,
        "experience_mode": "Beginner Mode" if beginner_label else "Advanced Mode",
        "current_weights": {"VOO": "50%", "BND": "50%"},
    }
    pre = build_question_payload(
        source_app="investment",
        source_page=submit_page,
        question="What happens if rates rise?",
        context=ctx,
    )
    url = build_applied_math_resume_url(pre)

    ok = _stage_investment_instant_insight(
        st,
        ss,
        question=pre["question"],
        source_app="investment",
        source_page=submit_page,
        submit_ctx=ctx,
        submit_source_state={},
        pre_payload=pre,
        action_url_pre=url,
    )
    _log(steps, "after_stage", ok=ok, pending=bool(ss.get(SESSION_PENDING_KEY)))

    ss["investment_active_tab"] = active_tab

    pending_before_gate = copy.deepcopy(ss.get(SESSION_PENDING_KEY))
    _log(
        steps,
        "before_gate",
        pending_exists=bool(
            isinstance(pending_before_gate, dict)
            and (pending_before_gate.get("conclusion") or pending_before_gate.get("question"))
        ),
        submit_flag=ss.get("_ami_submit_render_insight_this_run"),
        render_success=ss.get("_ami_insight_render_success"),
    )

    try:
        hydrate_applied_math_insight_for_session(st, "investment")
        _log(steps, "after_app_hydrate", pending=bool(ss.get(SESSION_PENDING_KEY)))
    except Exception as exc:
        _log(steps, "after_app_hydrate", error=f"{type(exc).__name__}: {exc}")

    gate = investment_insight_main_render_needed(ss)
    _log(
        steps,
        "investment_insight_main_render_needed",
        returned=gate,
        pending_after=bool(ss.get(SESSION_PENDING_KEY)),
        force_flag=ss.get("_ami_force_insight_render"),
        submit_flag_after=ss.get("_ami_submit_render_insight_this_run"),
    )

    pending_before_render = ss.get(SESSION_PENDING_KEY)
    _log(
        steps,
        "before_render_suite_applied_math_insight",
        pending_exists=bool(
            isinstance(pending_before_render, dict)
            and (pending_before_render.get("conclusion") or pending_before_render.get("question"))
        ),
        will_call=gate,
    )

    if not gate:
        return steps

    suite_ok = None
    for_page_ok = None
    panel_ok = None

    import applied_math_return_insight as ami

    orig_for_page = ami.render_suite_applied_math_insight_for_page
    orig_panel = ami.render_applied_math_insight_panel

    def _wrap_for_page(st_arg, **kwargs):
        nonlocal for_page_ok
        _log(steps, "render_suite_applied_math_insight_for_page", entered=True, source_page=kwargs.get("source_page"))
        try:
            for_page_ok = orig_for_page(st_arg, **kwargs)
        except Exception as exc:
            for_page_ok = False
            _log(steps, "render_suite_applied_math_insight_for_page", exception=f"{type(exc).__name__}: {exc}")
            raise
        _log(
            steps,
            "render_suite_applied_math_insight_for_page",
            returned=for_page_ok,
            skip=ss.get("_ami_insight_render_skipped_reason"),
            success=ss.get("_ami_insight_render_success"),
        )
        return for_page_ok

    def _wrap_panel(st_arg, **kwargs):
        nonlocal panel_ok
        _log(steps, "render_applied_math_insight_panel", entered=True)
        try:
            panel_ok = orig_panel(st_arg, **kwargs)
        except Exception as exc:
            panel_ok = False
            _log(steps, "render_applied_math_insight_panel", exception=f"{type(exc).__name__}: {exc}")
            raise
        _log(steps, "render_applied_math_insight_panel", returned=panel_ok)
        return panel_ok

    ami.render_suite_applied_math_insight_for_page = _wrap_for_page  # type: ignore[assignment]
    ami.render_applied_math_insight_panel = _wrap_panel  # type: ignore[assignment]
    try:
        with __import__("unittest.mock").mock.patch.object(ami, "load_latest_applied_math_insight_for_app", return_value=None), __import__(
            "unittest.mock"
        ).mock.patch.object(ami, "sync_dismissed_insights_from_cloud"):
            suite_ok = render_suite_applied_math_insight(
                st,
                source_app="investment",
                source_page=active_tab,
            )
    except Exception as exc:
        suite_ok = False
        _log(steps, "render_suite_applied_math_insight", exception=f"{type(exc).__name__}: {exc}")
    finally:
        ami.render_suite_applied_math_insight_for_page = orig_for_page  # type: ignore[assignment]
        ami.render_applied_math_insight_panel = orig_panel  # type: ignore[assignment]

    _log(steps, "render_suite_applied_math_insight", returned=suite_ok)
    return steps


def trace_for_page_decision(ss: dict, active_tab: str) -> dict[str, Any]:
    from applied_math_return_insight import (
        SESSION_PENDING_KEY,
        hydrate_applied_math_insight_for_session,
        insight_page_scope_decision,
    )

    st = MagicMock()
    st.session_state = ss
    hydrate_applied_math_insight_for_session(st, "investment")
    insight = ss.get(SESSION_PENDING_KEY)
    pending_exists = isinstance(insight, dict) and bool(insight.get("conclusion") or insight.get("question"))
    scope = (
        insight_page_scope_decision("investment", active_tab, insight)
        if pending_exists
        else {"should_render_insight_on_page": False, "render_skip_reason": "no_pending_insight"}
    )
    should_render = bool(scope.get("should_render_insight_on_page"))
    submit_page = str(ss.get("_ami_last_submit_source_page") or "")
    from applied_math_return_insight import _normalize_investment_tab

    sp = _normalize_investment_tab(submit_page)
    cur = _normalize_investment_tab(active_tab)
    force = bool(
        ss.get("_ami_force_insight_render")
        or ss.get("_ami_submit_render_insight_this_run")
        or (sp and cur and sp == cur and isinstance(insight, dict) and insight.get("conclusion"))
    )
    return {
        "pending_exists": pending_exists,
        "scope": scope,
        "should_render_initial": should_render,
        "force_render": force,
        "submit_page_norm": sp,
        "cur_page_norm": cur,
    }


def simulate_slider_widget_rerun(*, active_tab: str = "Macro Outlook") -> list[dict[str, Any]]:
    """After insight rendered once (success=True), user moves Rate shock slider → Streamlit reruns."""
    from applied_math_return_insight import (
        SESSION_PENDING_KEY,
        hydrate_applied_math_insight_for_session,
        investment_insight_main_render_needed,
    )

    steps: list[dict[str, Any]] = []
    st = MagicMock()
    ss: dict[str, Any] = {
        SESSION_PENDING_KEY: {
            "source_app": "investment",
            "source_page": active_tab,
            "conclusion": "Falling Rates scenario.",
            "question": "How would rate cuts affect my portfolio?",
            "problem_type": "macro_rates",
            "insight_id": "macro-test-1",
        },
        "_ami_insight_render_success": True,
        "investment_active_tab": active_tab,
        "_ami_scenario_params": {"rate_shock_pp": -2.0},
    }
    st.session_state = ss
    _log(steps, "slider_rerun_start", pending=True, render_success=True)

    hydrate_applied_math_insight_for_session(st, "investment")
    _log(steps, "after_hydrate", pending=bool(ss.get(SESSION_PENDING_KEY)))

    gate = investment_insight_main_render_needed(ss)
    _log(
        steps,
        "investment_insight_main_render_needed",
        returned=gate,
        pending_after=bool(ss.get(SESSION_PENDING_KEY)),
        render_success=ss.get("_ami_insight_render_success"),
    )
    if not gate:
        _log(steps, "FAIL", message="gate_false_insight_would_disappear")
    return steps


if __name__ == "__main__":
    import json

    for label, active, submit in (
        ("overview_match", "Overview", "Overview"),
        ("beginner_getting_started", "① Getting Started", "① Getting Started"),
        ("sidebar_main_mismatch", "Portfolio Health", "Overview"),
    ):
        print("=== SCENARIO", label, "===")
        steps = simulate_post_submit_rerun(active_tab=active, sidebar_tab_at_submit=submit)
        print(json.dumps(steps, indent=2, default=str))
        print()

    print("=== SCENARIO slider_widget_rerun (post-success) ===")
    print(json.dumps(simulate_slider_widget_rerun(), indent=2, default=str))
