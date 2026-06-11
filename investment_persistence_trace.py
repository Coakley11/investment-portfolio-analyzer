"""Developer-mode persistence trace for Investment (``?dev=1`` or Developer sidebar)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

INVESTMENT_PERSIST_DEPLOY_VERSION = "investment-persistence-trace-pr1-v1"
TRACE_KEY = "_investment_persist_trace"
APP_ID = "investment"
PR1_DIAG_CHECKBOX_KEY = "investment_pr1_diagnostics_enabled"

DEPLOY_TRACE_LABELS: tuple[str, ...] = (
    "deploy_version",
    "git_commit",
    "git_branch",
    "app_marker",
    "APP_ID",
    "cloud_configured",
    "persistence_module_loaded",
)

TAB_TRACE_LABELS: tuple[str, ...] = (
    "investment_active_tab",
    "health_active_tab",
    "_suite_investment_page",
    "final_investment_tab",
    "active_tab_source",
    "tab_widget_value",
    "tab_restore_source",
)

WORKSPACE_RESTORE_TRACE_LABELS: tuple[str, ...] = (
    "restore_attempted",
    "restore_decision",
    "cloud_fetch_tab",
    "restored_tab",
    "final_tab",
    "page_overwrite_source",
    "cloud_updated_at",
    "local_updated_at",
)

GLOBAL_SETTINGS_TRACE_LABELS: tuple[str, ...] = (
    "experience",
    "_suite_persisted_experience",
    "sidebar_portfolio_value",
    "analysis_start",
    "analysis_end",
    "risk_free_pct",
    "portfolio_preset",
)

PORTFOLIO_TRACE_LABELS: tuple[str, ...] = (
    "holdings_fingerprint",
    "holdings_row_count",
    "preset_applied",
    "selected_portfolio",
    "health_objective",
    "health_summary_exists",
    "health_result_exists",
    "workflow_state_exists",
)

FILTER_TRACE_LABELS: tuple[str, ...] = (
    "overview_subtab",
    "mc_assumption_mode",
    "health_run_optimizer",
    "health_bond_min",
    "frontier_points",
    "macro_scenario_id",
    "macro_scenario_mode",
    "health_rate_env",
    "health_inflation",
    "health_recession",
    "health_valuation",
    "health_regime",
)

AMI_RETURN_TRACE_LABELS: tuple[str, ...] = (
    "ami_return_detected",
    "source_app_normalized",
    "current_investment_tab",
    "final_investment_tab",
    "return_context_keys",
    "apply_source_state_attempted",
    "apply_source_state_success",
)

SAVE_TRACE_LABELS: tuple[str, ...] = (
    "autosave_ran",
    "save_reason",
    "cloud_payload_source",
    "cloud_write_ok",
    "cloud_write_error",
    "last_save_cloud",
    "saved_tab",
    "saved_experience",
    "saved_portfolio_value",
    "saved_holdings_fingerprint",
)

TEST_A_TRACE_LABELS: tuple[str, ...] = (
    "device_id",
    "trace_captured_at",
    "cloud_updated_at",
    "local_updated_at",
    "investment_active_tab",
    "health_active_tab",
    "cloud_fetch_tab",
    "restored_tab",
    "final_investment_tab",
    "active_tab_source",
    "tab_restore_source",
    "restore_decision",
    "page_overwrite_source",
)

TEST_B_TRACE_LABELS: tuple[str, ...] = (
    "device_id",
    "trace_captured_at",
    "cloud_updated_at",
    "local_updated_at",
    "experience",
    "_suite_persisted_experience",
    "sidebar_portfolio_value",
    "analysis_start",
    "analysis_end",
    "risk_free_pct",
    "portfolio_preset",
)

TEST_C_TRACE_LABELS: tuple[str, ...] = (
    "device_id",
    "trace_captured_at",
    "cloud_updated_at",
    "local_updated_at",
    "final_investment_tab",
    "overview_subtab",
    "mc_assumption_mode",
    "health_run_optimizer",
    "health_bond_min",
    "frontier_points",
    "macro_scenario_id",
    "macro_scenario_mode",
    "health_rate_env",
    "health_inflation",
    "health_recession",
    "health_valuation",
    "health_regime",
)

TEST_D_TRACE_LABELS: tuple[str, ...] = (
    "device_id",
    "trace_captured_at",
    "cloud_updated_at",
    "local_updated_at",
    "holdings_fingerprint",
    "holdings_row_count",
    "preset_applied",
    "selected_portfolio",
    "health_objective",
    "health_summary_exists",
    "health_result_exists",
    "workflow_state_exists",
    "restore_decision",
    "page_overwrite_source",
)

TEST_E_TRACE_LABELS: tuple[str, ...] = AMI_RETURN_TRACE_LABELS + (
    "cloud_fetch_tab",
    "restored_tab",
    "page_overwrite_source",
    "holdings_fingerprint",
)


def _raw_dev_query_param(st: Any) -> str:
    try:
        raw = st.query_params.get("dev")
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        return str(raw or "")
    except Exception:
        return ""


def init_developer_mode_from_query(st: Any) -> None:
    """Enable diagnostics when ``?dev=1`` is present (one-step trace panel access)."""
    try:
        st.session_state["_pr1_init_developer_mode_ran"] = True
        raw = _raw_dev_query_param(st)
        st.session_state["_pr1_dev_query_raw"] = raw
        if str(raw).strip().lower() in {"1", "true", "yes", "on"}:
            st.session_state["investment_show_dev_diagnostics"] = True
            st.session_state["_pr1_dev_query_matched"] = True
        else:
            st.session_state["_pr1_dev_query_matched"] = False
    except Exception as exc:
        st.session_state["_pr1_init_developer_mode_error"] = str(exc)


def pr1_baseline_trace_active(*, persistence_ok: bool | None = None) -> bool:
    """PR1 baseline: show trace when persistence loaded and deploy marker matches (no ``?dev=1``)."""
    return bool(persistence_ok) and INVESTMENT_PERSIST_DEPLOY_VERSION == "investment-persistence-trace-pr1-v1"


def investment_trace_enabled(st: Any, *, persistence_ok: bool | None = None) -> bool:
    """True when PR1 baseline, sidebar checkbox, or developer diagnostics are active."""
    if pr1_baseline_trace_active(persistence_ok=persistence_ok):
        return True
    if st.session_state.get(PR1_DIAG_CHECKBOX_KEY):
        return True
    if st.session_state.get("investment_show_dev_diagnostics"):
        return True
    try:
        from investment_workflow import developer_diagnostics_enabled

        return bool(developer_diagnostics_enabled(st))
    except ImportError:
        return False


def render_investment_diagnostics_controls(st: Any, *, persistence_ok: bool | None = None) -> None:
    """Always-visible PR1 checkbox (Streamlit Cloud may not pass ``?dev=1`` to query_params)."""
    if not persistence_ok:
        return
    st.sidebar.checkbox(
        "Enable Investment diagnostics",
        key=PR1_DIAG_CHECKBOX_KEY,
        help=(
            "Show Investment persistence trace and Test A–E copy blocks. "
            "Also auto-enabled during PR1 baseline when persistence is loaded."
        ),
    )


def get_trace(st: Any) -> dict[str, Any]:
    raw = st.session_state.get(TRACE_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def update_trace(st: Any, **fields: Any) -> None:
    trace = get_trace(st)
    trace.update(fields)
    trace.setdefault("deploy_version", INVESTMENT_PERSIST_DEPLOY_VERSION)
    try:
        trace.setdefault("git_commit", _git_head_short())
        trace.setdefault("git_branch", _git_branch())
    except Exception:
        pass
    st.session_state[TRACE_KEY] = trace


def _git_head_short() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _trace_display(val: Any) -> str:
    if val is None:
        return "(not set)"
    if isinstance(val, bool):
        return str(val)
    text = str(val).strip()
    if not text:
        return "(empty)"
    return text


def _cloud_tab_from_state(state: dict[str, Any]) -> str:
    if not isinstance(state, dict):
        return ""
    return str(
        state.get("investment_active_tab")
        or state.get("health_active_tab")
        or state.get("active_page")
        or ""
    ).strip()


def _device_id(st: Any) -> str:
    try:
        from suite_user import get_external_user_id

        return str(get_external_user_id() or "unknown")
    except Exception:
        return "unknown"


def _holdings_fingerprint_and_count(st: Any) -> tuple[str | None, int | None]:
    ss = st.session_state
    fp: str | None = None
    count: int | None = None
    try:
        import pandas as pd

        from components.beginner_navigation import _holdings_fingerprint

        df = ss.get("holdings_df")
        if isinstance(df, pd.DataFrame):
            count = int(len(df))
            if not df.empty:
                fp = str(_holdings_fingerprint(df))
    except Exception:
        pass
    if not fp:
        fp = str(ss.get("holdings_fingerprint") or "").strip() or None
    return fp, count


def _cloud_configured(st: Any) -> bool | None:
    ss = st.session_state
    probe = ss.get("_suite_inv_debug_cloud_probe")
    if isinstance(probe, dict) and "cloud_enabled" in probe:
        return bool(probe.get("cloud_enabled"))
    try:
        from suite_storage_config import cloud_storage_enabled

        return bool(cloud_storage_enabled())
    except Exception:
        return None


def _persistence_module_loaded(st: Any) -> bool:
    import_err = st.session_state.get("_suite_persist_import_error")
    return import_err is None


def snapshot_deploy_info(st: Any, *, persistence_ok: bool | None = None) -> dict[str, Any]:
    fields = {
        "deploy_version": INVESTMENT_PERSIST_DEPLOY_VERSION,
        "git_commit": _git_head_short(),
        "git_branch": _git_branch(),
        "app_marker": INVESTMENT_PERSIST_DEPLOY_VERSION,
        "APP_ID": APP_ID,
        "cloud_configured": _cloud_configured(st),
        "persistence_module_loaded": persistence_ok if persistence_ok is not None else _persistence_module_loaded(st),
    }
    update_trace(st, **fields)
    return fields


def snapshot_tab_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    trace = get_trace(st)
    final_tab = str(ss.get("investment_active_tab") or "").strip() or None
    fields = {
        "investment_active_tab": ss.get("investment_active_tab"),
        "health_active_tab": ss.get("health_active_tab"),
        "_suite_investment_page": ss.get("_suite_investment_page") or trace.get("_suite_investment_page"),
        "final_investment_tab": final_tab,
        "active_tab_source": ss.get("active_tab_source")
        or ss.get("active_page_source")
        or trace.get("active_tab_source"),
        "tab_widget_value": ss.get("investment_active_tab"),
        "tab_restore_source": trace.get("tab_restore_source")
        or ss.get("_suite_persist_last_restore_source"),
    }
    update_trace(st, **fields)
    return fields


def snapshot_workspace_restore_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    trace = get_trace(st)

    cloud_fetch = str(
        trace.get("cloud_fetch_tab")
        or ss.get("_suite_cloud_fetch_active_page")
        or ""
    ).strip()
    cloud_updated = (
        trace.get("cloud_updated_at")
        or ss.get("_suite_cloud_fetch_updated_at")
        or ss.get("_suite_persist_debug_cloud_ts")
    )
    local_updated = (
        trace.get("local_updated_at")
        or ss.get("_suite_persist_debug_disk_ts")
        or ss.get("_suite_persist_last_save_at")
        or ss.get("_suite_persist_last_restore_at")
    )
    restore_decision = (
        trace.get("restore_decision")
        or ss.get("_suite_restore_decision")
        or ss.get("_suite_persist_debug_pick_source")
    )
    restored_tab = trace.get("restored_tab") or trace.get("restored_investment_tab")
    final_tab = str(ss.get("investment_active_tab") or "").strip() or None

    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        if cloud_ts and not cloud_updated:
            cloud_updated = cloud_ts
        if isinstance(cloud_state, dict) and cloud_state:
            probed_tab = _cloud_tab_from_state(cloud_state)
            if probed_tab:
                cloud_fetch = cloud_fetch or probed_tab
    except Exception:
        pass

    fields = {
        "restore_attempted": trace.get("restore_attempted")
        if trace.get("restore_attempted") is not None
        else bool(
            ss.get("_suite_cloud_fetch_attempted")
            or ss.get("_suite_inv_debug_restore_ran") is not None
            or ss.get("_suite_disk_state_restored::investment")
        ),
        "restore_decision": restore_decision,
        "cloud_fetch_tab": cloud_fetch or None,
        "restored_tab": restored_tab,
        "final_tab": final_tab,
        "page_overwrite_source": ss.get("_suite_page_overwrite_source") or trace.get("page_overwrite_source"),
        "cloud_updated_at": cloud_updated,
        "local_updated_at": local_updated,
    }
    update_trace(st, **fields)
    return fields


def snapshot_global_settings_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    start = ss.get("analysis_start_date")
    end = ss.get("analysis_end_date")
    fields = {
        "experience": ss.get("experience"),
        "_suite_persisted_experience": ss.get("_suite_persisted_experience"),
        "sidebar_portfolio_value": ss.get("sidebar_portfolio_value"),
        "analysis_start": start.isoformat() if hasattr(start, "isoformat") else start,
        "analysis_end": end.isoformat() if hasattr(end, "isoformat") else end,
        "risk_free_pct": ss.get("risk_free_pct"),
        "portfolio_preset": ss.get("portfolio_preset"),
    }
    update_trace(st, **fields)
    return fields


def snapshot_portfolio_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    fp, count = _holdings_fingerprint_and_count(st)
    workflow_exists = False
    try:
        from investment_workflow import WORKFLOW_STATE_BLOB_KEY

        blob = ss.get(WORKFLOW_STATE_BLOB_KEY)
        workflow_exists = isinstance(blob, dict) and bool(blob)
    except ImportError:
        blob = ss.get("workflow_state")
        workflow_exists = isinstance(blob, dict) and bool(blob)

    fields = {
        "holdings_fingerprint": fp,
        "holdings_row_count": count,
        "preset_applied": ss.get("preset_applied"),
        "selected_portfolio": ss.get("portfolio_preset") or ss.get("preset_applied"),
        "health_objective": ss.get("health_objective"),
        "health_summary_exists": isinstance(ss.get("health_summary"), dict),
        "health_result_exists": ss.get("health_result") is not None,
        "workflow_state_exists": workflow_exists,
    }
    update_trace(st, **fields)
    return fields


def snapshot_filter_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    fields = {
        "overview_subtab": ss.get("overview_subtab"),
        "mc_assumption_mode": ss.get("mc_assumption_mode"),
        "health_run_optimizer": ss.get("health_run_optimizer"),
        "health_bond_min": ss.get("health_bond_min"),
        "frontier_points": ss.get("frontier_points"),
        "macro_scenario_id": ss.get("macro_scenario_id"),
        "macro_scenario_mode": ss.get("macro_scenario_mode"),
        "health_rate_env": ss.get("health_rate_env"),
        "health_inflation": ss.get("health_inflation"),
        "health_recession": ss.get("health_recession"),
        "health_valuation": ss.get("health_valuation"),
        "health_regime": ss.get("health_regime"),
    }
    update_trace(st, **fields)
    return fields


def snapshot_ami_return_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    trace = get_trace(st)
    return_ctx = ss.get("_ami_return_context")
    ctx_keys: list[str] = []
    if isinstance(return_ctx, dict):
        ctx_keys = sorted(str(k) for k in return_ctx.keys())
    ami_detected = bool(
        ss.get("ami_return_detected")
        or ss.get("insight_return_detected")
        or trace.get("ami_return_detected")
    )
    try:
        from applied_math_return_insight import ami_return_navigation_active

        if ami_return_navigation_active(st, APP_ID):
            ami_detected = True
    except Exception:
        pass

    fields = {
        "ami_return_detected": ami_detected,
        "source_app_normalized": ss.get("source_app_normalized")
        or (return_ctx or {}).get("source_app")
        if isinstance(return_ctx, dict)
        else ss.get("source_app_normalized"),
        "current_investment_tab": trace.get("current_investment_tab") or ss.get("investment_active_tab"),
        "final_investment_tab": ss.get("investment_active_tab"),
        "return_context_keys": ctx_keys or None,
        "apply_source_state_attempted": trace.get("apply_source_state_attempted"),
        "apply_source_state_success": trace.get("apply_source_state_success"),
    }
    update_trace(st, **fields)
    return fields


def snapshot_save_trace(st: Any) -> dict[str, Any]:
    ss = st.session_state
    trace = get_trace(st)
    last_event = ss.get("_suite_inv_debug_last_autosave_event")
    if not isinstance(last_event, dict):
        last_event = {}

    fields = {
        "autosave_ran": trace.get("autosave_ran")
        if trace.get("autosave_ran") is not None
        else bool(last_event),
        "save_reason": trace.get("save_reason") or last_event.get("trigger"),
        "cloud_payload_source": trace.get("cloud_payload_source")
        or ss.get("_suite_autosave_payload_source")
        or "full_session",
        "cloud_write_ok": trace.get("cloud_write_ok")
        if trace.get("cloud_write_ok") is not None
        else last_event.get("saved_cloud"),
        "cloud_write_error": trace.get("cloud_write_error") or last_event.get("cloud_save_error"),
        "last_save_cloud": trace.get("last_save_cloud")
        or ss.get("_suite_persist_last_save_at")
        or last_event.get("cloud_readback_ts"),
        "saved_tab": trace.get("saved_tab") or last_event.get("blob_tab"),
        "saved_experience": trace.get("saved_experience") or last_event.get("blob_experience"),
        "saved_portfolio_value": trace.get("saved_portfolio_value") or last_event.get("blob_portfolio_value"),
        "saved_holdings_fingerprint": trace.get("saved_holdings_fingerprint")
        or last_event.get("blob_holdings_fingerprint"),
    }
    update_trace(st, **fields)
    return fields


def record_restore_trace(st: Any) -> None:
    """Record restore snapshot after ``restore_investment_disk_state_once`` (read-only)."""
    ss = st.session_state
    restored_tab = None
    restored_source = ss.get("_suite_persist_last_restore_source")
    try:
        from suite_cloud_state import load_cloud_full_session

        cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        cloud_tab = _cloud_tab_from_state(cloud_state) if isinstance(cloud_state, dict) else ""
        if isinstance(cloud_state, dict):
            restored_tab = (
                cloud_state.get("investment_active_tab")
                or cloud_state.get("health_active_tab")
                or restored_tab
            )
    except Exception:
        cloud_tab = ""
        cloud_ts = None
        cloud_state = None

    pick_source = ss.get("_suite_persist_debug_pick_source")
    if pick_source == "cloud" and isinstance(cloud_state, dict):
        restored_tab = restored_tab or cloud_state.get("investment_active_tab")
    elif pick_source == "disk":
        try:
            from suite_user_persistence import load_user_state

            disk_state, _ = load_user_state(APP_ID)
            if isinstance(disk_state, dict):
                restored_tab = disk_state.get("investment_active_tab") or disk_state.get("health_active_tab")
        except Exception:
            pass

    update_trace(
        st,
        restore_attempted=True,
        restore_decision=ss.get("_suite_restore_decision") or pick_source,
        cloud_fetch_tab=cloud_tab or ss.get("_suite_cloud_fetch_active_page"),
        restored_tab=restored_tab,
        restored_investment_tab=restored_tab,
        tab_restore_source=restored_source,
        cloud_updated_at=cloud_ts or ss.get("_suite_persist_debug_cloud_ts"),
        local_updated_at=ss.get("_suite_persist_debug_disk_ts"),
        page_overwrite_source=ss.get("_suite_page_overwrite_source"),
        _suite_investment_page=ss.get("_suite_investment_page"),
    )


def record_save_trace(
    st: Any,
    *,
    event: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    """Record autosave snapshot (read-only; does not affect save path)."""
    ss = st.session_state
    evt = event if isinstance(event, dict) else ss.get("_suite_inv_debug_last_autosave_event")
    if not isinstance(evt, dict):
        evt = {}
    blob_tab = None
    blob_fp = None
    blob_pv = None
    blob = state if isinstance(state, dict) else None
    if blob:
        blob_tab = blob.get("investment_active_tab")
        blob_fp = blob.get("holdings_fingerprint")
        blob_pv = blob.get("sidebar_portfolio_value")
        evt = {**evt, "blob_tab": blob_tab, "blob_holdings_fingerprint": blob_fp, "blob_portfolio_value": blob_pv}

    update_trace(
        st,
        autosave_ran=True,
        save_reason=evt.get("trigger"),
        cloud_payload_source="full_session",
        cloud_write_ok=evt.get("saved_cloud"),
        cloud_write_error=evt.get("cloud_save_error"),
        last_save_cloud=evt.get("cloud_readback_ts") or ss.get("_suite_persist_last_save_at"),
        saved_tab=blob_tab or evt.get("blob_tab"),
        saved_experience=evt.get("blob_experience"),
        saved_portfolio_value=blob_pv or evt.get("blob_portfolio_value"),
        saved_holdings_fingerprint=blob_fp or evt.get("blob_holdings_fingerprint"),
    )


def record_ami_apply_trace(
    st: Any,
    *,
    source_state: dict[str, Any] | None,
    success: bool | None = None,
    error: str | None = None,
) -> None:
    """Record AMI return apply attempt for Test E (does not change AMI behavior)."""
    ss = st.session_state
    tab_before = ss.get("investment_active_tab")
    ctx_keys: list[str] | None = None
    if isinstance(source_state, dict):
        ctx_keys = sorted(str(k) for k in source_state.keys())
    update_trace(
        st,
        ami_return_detected=True,
        apply_source_state_attempted=True,
        apply_source_state_success=success if success is not None else error is None,
        apply_source_state_error=error,
        current_investment_tab=tab_before,
        return_context_keys=ctx_keys,
        source_app_normalized=source_state.get("source_app") if isinstance(source_state, dict) else None,
    )


def snapshot_full_trace(st: Any, *, persistence_ok: bool | None = None) -> dict[str, Any]:
    """Refresh all trace sections for sidebar render."""
    st.session_state["_pr1_snapshot_full_trace_ran"] = True
    snapshot_deploy_info(st, persistence_ok=persistence_ok)
    snapshot_tab_trace(st)
    snapshot_workspace_restore_trace(st)
    snapshot_global_settings_trace(st)
    snapshot_portfolio_trace(st)
    snapshot_filter_trace(st)
    snapshot_ami_return_trace(st)
    snapshot_save_trace(st)
    return get_trace(st)


def _trace_captured_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _base_compare_rows(st: Any, trace: dict[str, Any]) -> dict[str, Any]:
    ss = st.session_state
    return {
        "device_id": _device_id(st),
        "trace_captured_at": _trace_captured_at(),
        "cloud_updated_at": trace.get("cloud_updated_at")
        or ss.get("_suite_cloud_fetch_updated_at")
        or ss.get("_suite_persist_debug_cloud_ts"),
        "local_updated_at": trace.get("local_updated_at")
        or ss.get("_suite_persist_debug_disk_ts")
        or ss.get("_suite_persist_last_save_at"),
    }


def collect_test_a_trace_rows(st: Any, trace: dict[str, Any]) -> dict[str, Any]:
    rows = _base_compare_rows(st, trace)
    rows.update(
        {
            "investment_active_tab": trace.get("investment_active_tab") or st.session_state.get("investment_active_tab"),
            "health_active_tab": trace.get("health_active_tab") or st.session_state.get("health_active_tab"),
            "cloud_fetch_tab": trace.get("cloud_fetch_tab"),
            "restored_tab": trace.get("restored_tab"),
            "final_investment_tab": trace.get("final_investment_tab")
            or st.session_state.get("investment_active_tab"),
            "active_tab_source": trace.get("active_tab_source"),
            "tab_restore_source": trace.get("tab_restore_source"),
            "restore_decision": trace.get("restore_decision"),
            "page_overwrite_source": trace.get("page_overwrite_source"),
        }
    )
    return rows


def collect_test_b_trace_rows(st: Any, trace: dict[str, Any]) -> dict[str, Any]:
    rows = _base_compare_rows(st, trace)
    rows.update(
        {
            "experience": trace.get("experience") or st.session_state.get("experience"),
            "_suite_persisted_experience": trace.get("_suite_persisted_experience")
            or st.session_state.get("_suite_persisted_experience"),
            "sidebar_portfolio_value": trace.get("sidebar_portfolio_value")
            or st.session_state.get("sidebar_portfolio_value"),
            "analysis_start": trace.get("analysis_start"),
            "analysis_end": trace.get("analysis_end"),
            "risk_free_pct": trace.get("risk_free_pct") or st.session_state.get("risk_free_pct"),
            "portfolio_preset": trace.get("portfolio_preset") or st.session_state.get("portfolio_preset"),
        }
    )
    return rows


def collect_test_c_trace_rows(st: Any, trace: dict[str, Any]) -> dict[str, Any]:
    rows = _base_compare_rows(st, trace)
    for label in FILTER_TRACE_LABELS:
        if label == "final_investment_tab":
            continue
        rows[label] = trace.get(label) if label in trace else st.session_state.get(label)
    rows["final_investment_tab"] = trace.get("final_investment_tab") or st.session_state.get(
        "investment_active_tab"
    )
    return rows


def collect_test_d_trace_rows(st: Any, trace: dict[str, Any]) -> dict[str, Any]:
    rows = _base_compare_rows(st, trace)
    for label in PORTFOLIO_TRACE_LABELS:
        rows[label] = trace.get(label)
    rows["restore_decision"] = trace.get("restore_decision")
    rows["page_overwrite_source"] = trace.get("page_overwrite_source")
    return rows


def collect_test_e_trace_rows(st: Any, trace: dict[str, Any]) -> dict[str, Any]:
    rows = {label: trace.get(label) for label in AMI_RETURN_TRACE_LABELS}
    rows["cloud_fetch_tab"] = trace.get("cloud_fetch_tab")
    rows["restored_tab"] = trace.get("restored_tab")
    rows["page_overwrite_source"] = trace.get("page_overwrite_source")
    rows["holdings_fingerprint"] = trace.get("holdings_fingerprint")
    return rows


def format_test_compare_trace(title: str, labels: tuple[str, ...], rows: dict[str, Any]) -> str:
    lines = [title, ""]
    for label in labels:
        val = rows.get(label)
        if val is None or val == "":
            lines.append(f"{label}: (empty)")
        else:
            lines.append(f"{label}: {val}")
    return "\n".join(lines)


def format_test_a_compare_trace(rows: dict[str, Any]) -> str:
    return format_test_compare_trace("# Test A — page/tab sync", TEST_A_TRACE_LABELS, rows)


def format_test_b_compare_trace(rows: dict[str, Any]) -> str:
    return format_test_compare_trace("# Test B — global settings sync", TEST_B_TRACE_LABELS, rows)


def format_test_c_compare_trace(rows: dict[str, Any]) -> str:
    return format_test_compare_trace("# Test C — page filters sync", TEST_C_TRACE_LABELS, rows)


def format_test_d_compare_trace(rows: dict[str, Any]) -> str:
    return format_test_compare_trace("# Test D — portfolio/analysis restore", TEST_D_TRACE_LABELS, rows)


def format_test_e_compare_trace(rows: dict[str, Any]) -> str:
    return format_test_compare_trace("# Test E — AMI return", TEST_E_TRACE_LABELS, rows)


def _render_trace_section(st: Any, title: str, labels: tuple[str, ...], rows: dict[str, Any]) -> None:
    st.markdown(f"**{title}**")
    for label in labels:
        st.text(f"{label}: {_trace_display(rows.get(label))}")


def render_pr1_verification_sidebar(st: Any, *, persistence_ok: bool | None = None) -> None:
    """Temporary PR1 deploy/gate diagnostics — always visible until baseline traces captured."""
    ss = st.session_state
    dev_raw = _raw_dev_query_param(st)
    dev_access = None
    dev_diag = None
    trace_enabled = None
    try:
        from investment_workflow import developer_access_available, developer_diagnostics_enabled

        dev_access = bool(developer_access_available(st))
        dev_diag = bool(developer_diagnostics_enabled(st))
    except Exception as exc:
        dev_access = f"import error: {exc}"
        dev_diag = f"import error: {exc}"
    try:
        trace_enabled = bool(investment_trace_enabled(st, persistence_ok=persistence_ok))
    except Exception as exc:
        trace_enabled = f"error: {exc}"
    pr1_baseline = pr1_baseline_trace_active(persistence_ok=persistence_ok)

    with st.sidebar.expander("PR1 deploy verification (temp)", expanded=True):
        st.caption(f"**Deploy marker:** `{INVESTMENT_PERSIST_DEPLOY_VERSION}`")
        try:
            st.caption(f"**Git:** `{_git_head_short()}` · `{_git_branch()}`")
        except Exception:
            st.caption("**Git:** unavailable")
        st.markdown("**Gate checks**")
        st.text(f"persistence_ok: {persistence_ok}")
        st.text(f"dev query raw: {dev_raw!r}")
        st.text(f"init_developer_mode_from_query ran: {ss.get('_pr1_init_developer_mode_ran', False)}")
        st.text(f"dev query matched at init: {ss.get('_pr1_dev_query_matched', False)}")
        st.text(f"investment_show_dev_diagnostics: {ss.get('investment_show_dev_diagnostics', False)}")
        st.text(f"pr1_baseline_trace_active: {pr1_baseline}")
        st.text(f"investment_pr1_diagnostics_enabled: {ss.get(PR1_DIAG_CHECKBOX_KEY, False)}")
        st.text(f"developer_access_available: {dev_access}")
        st.text(f"developer_diagnostics_enabled: {dev_diag}")
        st.text(f"investment_trace_enabled: {trace_enabled}")
        st.markdown("**Call flags**")
        st.text(f"render_persistence_trace_sidebar called: {ss.get('_pr1_trace_sidebar_called', False)}")
        st.text(f"snapshot_full_trace ran: {ss.get('_pr1_snapshot_full_trace_ran', False)}")
        init_err = ss.get("_pr1_init_developer_mode_error")
        if init_err:
            st.warning(f"init_developer_mode_from_query error: {init_err}")
        persist_import = ss.get("_suite_persist_import_error")
        if persist_import:
            st.warning(f"Persistence import error: {persist_import}")


def render_persistence_trace_sidebar(st: Any, *, persistence_ok: bool | None = None) -> None:
    st.session_state["_pr1_trace_sidebar_called"] = True
    if not investment_trace_enabled(st, persistence_ok=persistence_ok):
        st.session_state["_pr1_trace_sidebar_skipped"] = "investment_trace_enabled=False"
        return

    trace = snapshot_full_trace(st, persistence_ok=persistence_ok)

    with st.sidebar.expander("Investment persistence trace", expanded=False):
        st.caption(f"Deploy: {trace.get('deploy_version', INVESTMENT_PERSIST_DEPLOY_VERSION)}")
        st.caption(f"Commit: {trace.get('git_commit', 'unknown')} · Branch: {trace.get('git_branch', 'unknown')}")

        _render_trace_section(st, "1. Deploy / app info", DEPLOY_TRACE_LABELS, trace)
        _render_trace_section(st, "2. Tab/page trace", TAB_TRACE_LABELS, trace)
        _render_trace_section(st, "3. Workspace restore trace", WORKSPACE_RESTORE_TRACE_LABELS, trace)
        _render_trace_section(st, "4. Global settings trace", GLOBAL_SETTINGS_TRACE_LABELS, trace)
        _render_trace_section(st, "5. Portfolio trace", PORTFOLIO_TRACE_LABELS, trace)
        _render_trace_section(st, "6. Filter trace", FILTER_TRACE_LABELS, trace)
        _render_trace_section(st, "7. AMI return trace", AMI_RETURN_TRACE_LABELS, trace)
        _render_trace_section(st, "8. Save/autosave trace", SAVE_TRACE_LABELS, trace)

        st.markdown("**9. Manual test copy blocks**")
        st.caption(
            "Baseline manual tests (PR1 trace-only). "
            "1) Set non-default state on device A → wait ~10s → copy block. "
            "2) Hard-refresh device B → copy block → compare fields."
        )

        test_a = collect_test_a_trace_rows(st, trace)
        st.text_area(
            "Copy Test A — page/tab sync",
            value=format_test_a_compare_trace(test_a),
            height=220,
            label_visibility="collapsed",
        )
        test_b = collect_test_b_trace_rows(st, trace)
        st.text_area(
            "Copy Test B — global settings sync",
            value=format_test_b_compare_trace(test_b),
            height=200,
            label_visibility="collapsed",
        )
        test_c = collect_test_c_trace_rows(st, trace)
        st.text_area(
            "Copy Test C — page filters sync",
            value=format_test_c_compare_trace(test_c),
            height=260,
            label_visibility="collapsed",
        )
        test_d = collect_test_d_trace_rows(st, trace)
        st.text_area(
            "Copy Test D — portfolio/analysis restore",
            value=format_test_d_compare_trace(test_d),
            height=240,
            label_visibility="collapsed",
        )
        test_e = collect_test_e_trace_rows(st, trace)
        st.text_area(
            "Copy Test E — AMI return",
            value=format_test_e_compare_trace(test_e),
            height=200,
            label_visibility="collapsed",
        )
