"""Investment AMI sidebar submit queue — solve/stage on main run after ``st.rerun``."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

SUBMIT_QUEUE_KEY = "_ami_investment_submit_queue"
SUBMIT_STARTED_AT_KEY = "_ami_insight_submit_started_at"
RENDER_REQUESTED_KEY = "_ami_render_requested"
PENDING_INSIGHT_ID_KEY = "_ami_pending_insight_id"
SUBMIT_PIPELINE_LOG_KEY = "_ami_submit_pipeline_log"
SUBMIT_PROCESSING_TIMEOUT_SEC = 120.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _snapshot_flags(ss: dict[str, Any]) -> dict[str, Any]:
    pending = ss.get("_ami_pending_insight")
    status = ss.get("_ami_insight_submit_status")
    diag = ss.get("_ami_investment_submit_diagnostics") or {}
    return {
        "submit_status": status,
        "instant_solved": diag.get("instant_solved"),
        "insight_id": str(
            (pending or {}).get("insight_id")
            or (ss.get("_ami_investment_instant_canonical") or {}).get("insight_id")
            or ""
        )[:32],
        "pending_exists": isinstance(pending, dict),
        "pending_insight_id": ss.get(PENDING_INSIGHT_ID_KEY),
        "render_requested": ss.get(RENDER_REQUESTED_KEY),
        "render_success": ss.get("_ami_insight_render_success"),
    }


def _append_pipeline_log(ss: dict[str, Any], stage: str, *, entered: bool = True, exc: str = "", elapsed_ms: float | None = None) -> None:
    buf = ss.get(SUBMIT_PIPELINE_LOG_KEY)
    if not isinstance(buf, list):
        buf = []
    entry: dict[str, Any] = {
        "stage": stage,
        "entered": entered,
        "exited": not entered,
        "at": _utc_now_iso(),
        "flags": _snapshot_flags(ss),
    }
    if exc:
        entry["exception"] = exc
    if elapsed_ms is not None:
        entry["elapsed_ms"] = round(elapsed_ms, 1)
    buf.append(entry)
    ss[SUBMIT_PIPELINE_LOG_KEY] = buf[-40:]


def _log_stage(stage: str, ss: dict[str, Any], *, page: str = "", insight_id: str = "", extra: str = "") -> None:
    msg = f"AMI_{stage} insight_id={insight_id or '-'} page={page or '-'} {extra}".strip()
    log.info(msg)
    _append_pipeline_log(ss, stage, entered=True)


def _log_stage_exit(stage: str, ss: dict[str, Any], t0: float, *, exc: str = "") -> None:
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    log.info("AMI_%s_COMPLETE elapsed_ms=%.1f exception=%s", stage, elapsed_ms, exc or "-")
    _append_pipeline_log(ss, stage, entered=False, exc=exc, elapsed_ms=elapsed_ms)


def queue_investment_ami_submit(
    ss: dict[str, Any],
    *,
    question: str,
    source_page: str,
    page_suffix: str,
    send_gen: int,
) -> None:
    """Sidebar click: defer solve to main script (after sidebar ``st.rerun``)."""
    ss[SUBMIT_QUEUE_KEY] = {
        "question": str(question or "").strip(),
        "source_page": str(source_page or "").strip(),
        "page_suffix": page_suffix,
        "send_gen": send_gen,
        "queued_at": _utc_now_iso(),
    }
    ss[SUBMIT_STARTED_AT_KEY] = _utc_now_iso()
    ss["_ami_insight_submit_status"] = {
        "state": "processing",
        "started_at": ss[SUBMIT_STARTED_AT_KEY],
    }
    ss.pop("_ami_insight_render_success", None)
    _log_stage("SUBMIT_START", ss, page=source_page)


def submit_processing_timed_out(ss: dict[str, Any]) -> bool:
    status = ss.get("_ami_insight_submit_status")
    if not isinstance(status, dict) or str(status.get("state") or "").lower() != "processing":
        return False
    started = str(status.get("started_at") or ss.get(SUBMIT_STARTED_AT_KEY) or "").strip()
    if not started:
        return False
    try:
        dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        return age > SUBMIT_PROCESSING_TIMEOUT_SEC
    except ValueError:
        return False


def finalize_submit_status(ss: dict[str, Any], *, state: str, message: str = "", insight_id: str = "") -> None:
    payload: dict[str, Any] = {"state": state}
    if message:
        payload["message"] = message
    if insight_id:
        payload["insight_id"] = insight_id
    ss["_ami_insight_submit_status"] = payload
    if state != "processing":
        ss.pop(SUBMIT_QUEUE_KEY, None)


def process_investment_ami_submit_queue(st: Any) -> bool:
    """
    Main-area processor: ROUTE → SOLVE → STAGE → SAVE.

    Returns True when a queued submit was handled (success or failure).
    """
    ss = st.session_state
    queue = ss.get(SUBMIT_QUEUE_KEY)
    if not isinstance(queue, dict) or not str(queue.get("question") or "").strip():
        if submit_processing_timed_out(ss):
            finalize_submit_status(
                ss,
                state="error",
                message="AMI timed out while analyzing your question. Try again or check diagnostics.",
            )
            ss.pop(RENDER_REQUESTED_KEY, None)
            return True
        return False

    if submit_processing_timed_out(ss):
        finalize_submit_status(
            ss,
            state="error",
            message="AMI timed out while analyzing your question. Try again or check diagnostics.",
        )
        ss.pop(RENDER_REQUESTED_KEY, None)
        return True

    from suite_analytical_question import execute_investment_ami_submit_pipeline

    question = str(queue.get("question") or "").strip()
    source_page = str(queue.get("source_page") or "").strip()
    page_suffix = str(queue.get("page_suffix") or "")
    send_gen = int(queue.get("send_gen") or 0)

    try:
        from applied_math_context import (
            build_investment_applied_math_context,
            ensure_investment_source_state,
        )
    except ImportError:
        build_investment_applied_math_context = None  # type: ignore[misc, assignment]
        ensure_investment_source_state = None  # type: ignore[misc, assignment]

    def _ctx_builder() -> dict[str, Any] | None:
        if build_investment_applied_math_context is None:
            return None
        return build_investment_applied_math_context(source_page, ss)

    def _src_builder() -> dict[str, Any] | None:
        if ensure_investment_source_state is None:
            return None
        return ensure_investment_source_state(source_page, ss)

    t0 = time.perf_counter()
    _log_stage("SUBMIT", ss, page=source_page)
    try:
        ok, err = execute_investment_ami_submit_pipeline(
            st,
            ss,
            question=question,
            source_page=source_page,
            page_suffix=page_suffix,
            send_gen=send_gen,
            context_extra_builder=_ctx_builder,
            source_state_builder=_src_builder,
        )
    except Exception as exc:
        tb = traceback.format_exc()
        log.exception("Investment AMI submit pipeline failed")
        _log_stage_exit("SUBMIT", ss, t0, exc=f"{type(exc).__name__}: {exc}")
        finalize_submit_status(
            ss,
            state="error",
            message=f"AMI failed: {type(exc).__name__}: {exc}",
        )
        ss["_ami_submit_last_error_trace"] = tb
        ss.pop(RENDER_REQUESTED_KEY, None)
        return True

    _log_stage_exit("SUBMIT", ss, t0)
    if not ok:
        finalize_submit_status(
            ss,
            state="error",
            message=err or "AMI could not create an insight.",
        )
        ss.pop(RENDER_REQUESTED_KEY, None)
        return True

    iid = str((ss.get("_ami_investment_instant_canonical") or {}).get("insight_id") or "")
    finalize_submit_status(ss, state="success", insight_id=iid)
    ss[RENDER_REQUESTED_KEY] = True
    if iid:
        ss[PENDING_INSIGHT_ID_KEY] = iid
    _log_stage("COMPLETE", ss, page=source_page, insight_id=iid)
    return True


def protect_pending_insight_during_submit(ss: dict[str, Any]) -> bool:
    """True when cloud hydrate must not replace an in-flight or staged insight."""
    if ss.get(SUBMIT_QUEUE_KEY):
        return True
    if ss.get(RENDER_REQUESTED_KEY):
        return True
    status = ss.get("_ami_insight_submit_status")
    if isinstance(status, dict) and str(status.get("state") or "").lower() == "processing":
        return True
    return False
