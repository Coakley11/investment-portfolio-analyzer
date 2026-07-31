"""Canonical planning-page portfolio value (How Much → Apply to sidebar).

Separate from holdings market value, plan total cash, and AMI snapshots.
AMI and decision-support read these helpers; they must not mutate session except
explicit apply/reconcile entry points.
"""

from __future__ import annotations

from typing import Any

APPLIED_PLAN_PORTFOLIO_VALUE_KEY = "applied_plan_portfolio_value"
LEGACY_APPLIED_PLAN_KEY = "investment_plan_applied_portfolio_value"
APPLIED_PLAN_SOURCE_KEY = "investment_plan_applied_source"

# Keys restored from AMI source_state / disk must not clobber an explicit plan apply.
PORTFOLIO_VALUE_RESTORE_PROTECTED_KEYS: frozenset[str] = frozenset(
    {
        APPLIED_PLAN_PORTFOLIO_VALUE_KEY,
        LEGACY_APPLIED_PLAN_KEY,
        APPLIED_PLAN_SOURCE_KEY,
        "sidebar_portfolio_value",
        "pending_sidebar_portfolio_value",
        "_suite_inv_portfolio_value_user_set",
    }
)


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


def effective_planning_portfolio_value_for_ami(session_state: dict[str, Any] | Any) -> float | None:
    """Read-only precedence for AMI Facts Used and submit context."""
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
    sidebar = session_state.get("sidebar_portfolio_value")
    if sidebar is not None and sidebar != "":
        try:
            return float(sidebar)
        except (TypeError, ValueError):
            return None
    return None


def reconcile_sidebar_to_applied_plan_portfolio_value(session_state: dict[str, Any] | Any) -> bool:
    """
    When user applied a plan amount, keep sidebar widget value aligned.

    Returns True when sidebar was updated.
    """
    if not has_explicit_applied_plan_portfolio_value(session_state):
        return False
    applied = get_applied_plan_portfolio_value(session_state)
    if applied is None:
        return False
    current = session_state.get("sidebar_portfolio_value")
    try:
        cur_int = int(round(float(current))) if current is not None else None
    except (TypeError, ValueError):
        cur_int = None
    if cur_int == applied:
        return False
    session_state["sidebar_portfolio_value"] = applied
    session_state.pop("_suite_inv_portfolio_value_user_set", None)
    return True


def prepare_session_for_investment_ami_submit(session_state: dict[str, Any] | Any) -> None:
    """Apply pending sidebar updates, then enforce explicit plan apply before AMI ROUTE."""
    try:
        from components.ui_helpers import apply_pending_sidebar_portfolio_value

        apply_pending_sidebar_portfolio_value(respect_user_edit=False)
    except ImportError:
        pass
    reconcile_sidebar_to_applied_plan_portfolio_value(session_state)


def should_block_portfolio_value_restore(session_state: dict[str, Any] | Any, key: str) -> bool:
    if key not in PORTFOLIO_VALUE_RESTORE_PROTECTED_KEYS:
        return False
    return has_explicit_applied_plan_portfolio_value(session_state)
