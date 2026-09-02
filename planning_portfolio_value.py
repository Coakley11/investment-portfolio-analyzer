"""Canonical planning-page portfolio value (How Much → Apply to sidebar).

Separate from holdings market value, plan total cash, and AMI snapshots.
"""

from __future__ import annotations

from typing import Any

APPLIED_PLAN_PORTFOLIO_VALUE_KEY = "applied_plan_portfolio_value"
LEGACY_APPLIED_PLAN_KEY = "investment_plan_applied_portfolio_value"
APPLIED_PLAN_SOURCE_KEY = "investment_plan_applied_source"
SIDEBAR_PORTFOLIO_VALUE_KEY = "sidebar_portfolio_value"
SIDEBAR_PORTFOLIO_WIDGET_INSTANTIATED_KEY = "_sidebar_portfolio_value_widget_instantiated"

PORTFOLIO_VALUE_RESTORE_PROTECTED_KEYS: frozenset[str] = frozenset(
    {
        APPLIED_PLAN_PORTFOLIO_VALUE_KEY,
        LEGACY_APPLIED_PLAN_KEY,
        APPLIED_PLAN_SOURCE_KEY,
        SIDEBAR_PORTFOLIO_VALUE_KEY,
        "pending_sidebar_portfolio_value",
        "_suite_inv_portfolio_value_user_set",
    }
)

DEFAULT_SIDEBAR_PORTFOLIO_VALUE = 100_000


def sidebar_portfolio_widget_instantiated(session_state: dict[str, Any] | Any) -> bool:
    return bool(session_state.get(SIDEBAR_PORTFOLIO_WIDGET_INSTANTIATED_KEY))


def mark_sidebar_portfolio_widget_instantiated(session_state: dict[str, Any] | Any) -> None:
    session_state[SIDEBAR_PORTFOLIO_WIDGET_INSTANTIATED_KEY] = True


def reset_sidebar_portfolio_widget_gate_for_run(session_state: dict[str, Any] | Any) -> None:
    """
    Clear the per-run widget gate at the start of each Streamlit script run.

    The gate exists so we never mutate ``sidebar_portfolio_value`` after
    ``st.number_input`` is drawn *in the same run*. It must not survive across
    reruns — otherwise pending/applied plan values never reach the sidebar and
    allocation dollars keep using a stale portfolio value.
    """
    session_state.pop(SIDEBAR_PORTFOLIO_WIDGET_INSTANTIATED_KEY, None)


def get_applied_plan_portfolio_value(session_state: dict[str, Any] | Any) -> int | None:
    for key in (APPLIED_PLAN_PORTFOLIO_VALUE_KEY, LEGACY_APPLIED_PLAN_KEY):
        val = session_state.get(key)
        if val is not None and val != "":
            try:
                return int(round(float(val)))
            except (TypeError, ValueError):
                continue
    return None


def has_explicit_applied_plan_portfolio_value(session_state: dict[str, Any] | Any) -> bool:
    applied = get_applied_plan_portfolio_value(session_state)
    if applied is None:
        return False
    return bool(str(session_state.get(APPLIED_PLAN_SOURCE_KEY) or "").strip())


def set_applied_plan_portfolio_value(
    session_state: dict[str, Any] | Any,
    amount: int | float,
    *,
    source: str,
) -> int:
    rounded = int(round(float(amount)))
    session_state[APPLIED_PLAN_PORTFOLIO_VALUE_KEY] = rounded
    session_state[LEGACY_APPLIED_PLAN_KEY] = rounded
    session_state[APPLIED_PLAN_SOURCE_KEY] = str(source or "").strip()
    return rounded


def resolve_persisted_sidebar_portfolio_value(session_state: dict[str, Any] | Any) -> int | None:
    """Value written to disk/cloud for sidebar_portfolio_value (canonical wins)."""
    if has_explicit_applied_plan_portfolio_value(session_state):
        return get_applied_plan_portfolio_value(session_state)
    val = session_state.get(SIDEBAR_PORTFOLIO_VALUE_KEY)
    if val is not None and val != "":
        try:
            return int(round(float(val)))
        except (TypeError, ValueError):
            return None
    return None


def effective_planning_portfolio_value_for_ami(session_state: dict[str, Any] | Any) -> float | None:
    """Read-only: AMI ROUTE/SOLVE/Facts Used — never mutates session."""
    applied = get_applied_plan_portfolio_value(session_state)
    if applied is not None and has_explicit_applied_plan_portfolio_value(session_state):
        return float(applied)
    try:
        from components.ui_helpers import PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY

        pending = session_state.get(PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY)
        if pending is not None:
            return float(pending)
    except ImportError:
        pass
    sidebar = session_state.get(SIDEBAR_PORTFOLIO_VALUE_KEY)
    if sidebar is not None and sidebar != "":
        try:
            return float(sidebar)
        except (TypeError, ValueError):
            return None
    return None


def _set_sidebar_portfolio_value_if_allowed(session_state: dict[str, Any] | Any, value: int) -> bool:
    if sidebar_portfolio_widget_instantiated(session_state):
        return False
    session_state[SIDEBAR_PORTFOLIO_VALUE_KEY] = int(value)
    return True


def initialize_sidebar_portfolio_value_before_widget(session_state: dict[str, Any] | Any) -> None:
    """
    Run once per run before ``st.number_input(key=\"sidebar_portfolio_value\")``.

    Order: pending deferred apply → canonical applied → existing sidebar → default.
    """
    if sidebar_portfolio_widget_instantiated(session_state):
        return

    try:
        from components.ui_helpers import PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY

        pending_key = PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY
    except ImportError:
        pending_key = "pending_sidebar_portfolio_value"

    if pending_key in session_state:
        if session_state.get("_suite_inv_portfolio_value_user_set"):
            session_state.pop(pending_key, None)
        else:
            pending_val = int(round(float(session_state.pop(pending_key))))
            session_state[SIDEBAR_PORTFOLIO_VALUE_KEY] = pending_val
            return

    if has_explicit_applied_plan_portfolio_value(session_state):
        applied = get_applied_plan_portfolio_value(session_state)
        if applied is not None:
            session_state[SIDEBAR_PORTFOLIO_VALUE_KEY] = applied
            session_state.pop("_suite_inv_portfolio_value_user_set", None)
            return

    if SIDEBAR_PORTFOLIO_VALUE_KEY not in session_state:
        session_state[SIDEBAR_PORTFOLIO_VALUE_KEY] = DEFAULT_SIDEBAR_PORTFOLIO_VALUE


def sync_portfolio_value_after_persistence_restore(
    session_state: dict[str, Any] | Any,
    *,
    restore_source: str = "",
) -> None:
    """After disk/cloud hydrate: align sidebar with canonical applied (pre-widget only)."""
    session_state["_portfolio_value_restore_source"] = str(restore_source or "").strip()
    if sidebar_portfolio_widget_instantiated(session_state):
        return
    if has_explicit_applied_plan_portfolio_value(session_state):
        applied = get_applied_plan_portfolio_value(session_state)
        if applied is not None:
            session_state[SIDEBAR_PORTFOLIO_VALUE_KEY] = applied
            session_state.pop("_suite_inv_portfolio_value_user_set", None)


def apply_applied_plan_from_persist_blob(session_state: dict[str, Any] | Any, blob: dict[str, Any] | None) -> None:
    """Merge plan persist sub-blob into session (canonical applied + mirrors)."""
    if not isinstance(blob, dict):
        return
    for key in (
        APPLIED_PLAN_PORTFOLIO_VALUE_KEY,
        LEGACY_APPLIED_PLAN_KEY,
        APPLIED_PLAN_SOURCE_KEY,
    ):
        if key in blob and blob.get(key) is not None and blob.get(key) != "":
            session_state[key] = blob[key]
    applied = blob.get(APPLIED_PLAN_PORTFOLIO_VALUE_KEY)
    if applied is None:
        applied = blob.get(LEGACY_APPLIED_PLAN_KEY)
    if applied is not None and blob.get(APPLIED_PLAN_SOURCE_KEY):
        set_applied_plan_portfolio_value(
            session_state,
            applied,
            source=str(blob.get(APPLIED_PLAN_SOURCE_KEY) or "restore"),
        )


def should_block_portfolio_value_restore(session_state: dict[str, Any] | Any, key: str) -> bool:
    if key not in PORTFOLIO_VALUE_RESTORE_PROTECTED_KEYS:
        return False
    return has_explicit_applied_plan_portfolio_value(session_state)
