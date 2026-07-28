"""Canonical AMI URL hydrate for suite Streamlit entry apps."""

from __future__ import annotations

from typing import Any


def _qp_get(st: Any, name: str) -> str:
    try:
        raw = st.query_params.get(name)
    except Exception:
        return ""
    if raw is None:
        return ""
    if isinstance(raw, list):
        return str(raw[0] or "").strip()
    return str(raw).strip()


def _apply_applied_intelligence_page_hydrate(st: Any, page: str) -> None:
    lesson = _qp_get(st, "suite_lesson")
    if lesson:
        st.session_state["_suite_ai_lesson"] = lesson
    if page:
        st.session_state["_suite_ai_page"] = page
    try:
        from suite_analytical_question import hydrate_applied_intelligence_session

        hydrate_applied_intelligence_session(st)
    except Exception:
        q = _qp_get(st, "suite_ai_question")
        if q:
            st.session_state["_suite_ai_question"] = q
            st.session_state["ps_library_problem"] = q
        ctx_raw = _qp_get(st, "suite_ai_context")
        if ctx_raw:
            st.session_state["_suite_ai_context"] = ctx_raw
        for qp, key in (
            ("suite_ai_source_app", "_suite_ai_source_app"),
            ("suite_ai_source_page", "_suite_ai_source_page"),
            ("suite_ai_area", "_suite_ai_area"),
            ("suite_ai_question_id", "_suite_ai_question_id"),
        ):
            val = _qp_get(st, qp)
            if val:
                st.session_state[key] = val


def hydrate_applied_intelligence_from_url(st: Any, app_key: str = "investment") -> bool:
    """
    Hydrate AMI / analytical-question state from URL query params on app startup.

    Implemented here (not only re-exported from ``suite_resume_launch``) so entry
    apps stay bootable if an older ``suite_resume_launch.py`` is cached on deploy.
    """
    key = str(app_key or "investment").strip()
    if key == "math":
        key = "applied_intelligence"

    if key == "applied_intelligence":
        page = _qp_get(st, "suite_page")
        _apply_applied_intelligence_page_hydrate(st, page)
        try:
            from applied_math_return_insight import apply_ami_insight_from_query

            return bool(apply_ami_insight_from_query(st, "applied_intelligence"))
        except ImportError:
            return bool(_qp_get(st, "suite_ami_insight"))

    if key == "investment":
        try:
            from applied_math_return_insight import (
                hydrate_investment_ami_return_state,
                insight_return_query_id,
            )

            if insight_return_query_id(st) or _qp_get(st, "suite_ai_question_id"):
                return hydrate_investment_ami_return_state(st, "investment")
        except ImportError:
            pass
        try:
            from applied_math_return_insight import apply_ami_insight_from_query

            return bool(apply_ami_insight_from_query(st, "investment"))
        except ImportError:
            return False

    try:
        from applied_math_return_insight import apply_ami_insight_from_query

        return bool(apply_ami_insight_from_query(st, key))
    except ImportError:
        return False


def probe_suite_resume_launch_compat() -> dict[str, Any]:
    """Record which ``suite_resume_launch`` module Python loads and whether it re-exports hydrate."""
    probe: dict[str, Any] = {
        "canonical_hydrate_module": __file__,
        "canonical_hydrate_callable": callable(hydrate_applied_intelligence_from_url),
    }
    try:
        import suite_resume_launch as srl

        probe["suite_resume_launch_file"] = getattr(srl, "__file__", None)
        fn = getattr(srl, "hydrate_applied_intelligence_from_url", None)
        probe["suite_resume_launch_has_hydrate"] = callable(fn)
        probe["suite_resume_launch_same_callable"] = fn is hydrate_applied_intelligence_from_url
        probe["suite_resume_launch_public"] = sorted(
            name
            for name in dir(srl)
            if not name.startswith("_") and callable(getattr(srl, name, None))
        )
    except Exception as exc:
        probe["suite_resume_launch_import_error"] = repr(exc)
    return probe
