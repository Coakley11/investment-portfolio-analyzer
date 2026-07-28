"""Compare submit vs slider widget rerun lifecycle (steps through gate)."""
from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import patch

ROOT = __file__.replace("\\", "/").rsplit("/scripts/", 1)[0]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT.replace("/", "\\") if sys.platform == "win32" else ROOT)


def _log(steps: list[dict[str, Any]], name: str, **kw: Any) -> None:
    steps.append({"step": name, **kw})


def _run_post_stage_pipeline(st, ss, active_tab: str, *, label: str) -> dict[str, Any]:
    from applied_math_return_insight import (
        SESSION_PENDING_KEY,
        hydrate_applied_math_insight_for_session,
        investment_insight_main_render_needed,
        prepare_insight_card_widget_rerun,
    )

    import applied_math_return_insight as ami

    ss["investment_active_tab"] = active_tab
    out: dict[str, Any] = {"flow": label}
    with patch.object(ami, "sync_dismissed_insights_from_cloud"), patch.object(
        ami, "load_latest_applied_math_insight_for_app", return_value=None
    ):
        hydrate_applied_math_insight_for_session(st, "investment")
    out["after_hydrate_pending"] = bool(ss.get(SESSION_PENDING_KEY))
    out["render_success_after_hydrate"] = ss.get("_ami_insight_render_success")
    prepare_insight_card_widget_rerun(st)
    out["prepare_widget_rerun"] = True
    out["render_success_after_prepare"] = ss.get("_ami_insight_render_success")
    gate = investment_insight_main_render_needed(ss)
    out["gate"] = gate
    out["render_success_after_gate"] = ss.get("_ami_insight_render_success")
    return out


def compare_submit_vs_slider_rerun() -> list[dict[str, Any]]:
    from applied_math_return_insight import SESSION_PENDING_KEY
    from suite_analytical_question import _stage_investment_instant_insight, build_question_payload
    from tests.test_investment_macro_rate_submit_sync import _FakeSt, _SUBMIT_CTX

    steps: list[dict[str, Any]] = []
    question = "What happens if the Federal Reserve cuts interest rates?"
    tab = "Forward Macro Analysis"
    st = _FakeSt()
    ss = st.session_state
    ctx = {**_SUBMIT_CTX, "page": tab}
    pre = build_question_payload(source_app="investment", source_page=tab, question=question, context=ctx)

    import applied_math_return_insight as ami

    with patch.object(ami, "store_applied_math_insight"), patch.object(
        ami, "sync_dismissed_insights_from_cloud"
    ), patch.object(ami, "load_latest_applied_math_insight_for_app", return_value=None):
        ok = _stage_investment_instant_insight(
            st,
            ss,
            question=question,
            source_app="investment",
            source_page=tab,
            submit_ctx=ctx,
            submit_source_state={"source_page": tab},
            pre_payload=pre,
            action_url_pre="https://example.test/ami",
        )
    _log(steps, "submit_stage", ok=ok, pending=bool(ss.get(SESSION_PENDING_KEY)))

    submit_path = _run_post_stage_pipeline(st, ss, tab, label="initial_submit_rerun")
    _log(steps, "submit_pipeline", **submit_path)

    ss["_ami_insight_render_success"] = True
    ss["_ami_submit_render_insight_this_run"] = False
    slider_path = _run_post_stage_pipeline(st, ss, tab, label="slider_widget_rerun")
    _log(steps, "slider_pipeline", **slider_path)

    if not slider_path.get("gate"):
        _log(steps, "DIVERGENCE", first_failure="slider gate False while pending exists")
    return steps


if __name__ == "__main__":
    print(json.dumps(compare_submit_vs_slider_rerun(), indent=2, default=str))
