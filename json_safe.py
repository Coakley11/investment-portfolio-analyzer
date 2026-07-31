"""Convert runtime objects to JSON-serializable plain data (no default=str)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
from decimal import Decimal
from typing import Any


def investment_plan_result_to_dict(result: Any) -> dict[str, Any]:
    """Stable AMI/persistence snapshot for InvestmentPlanResult."""
    import portfolio_core as core

    if isinstance(result, core.InvestmentPlanResult):
        raw = result.to_dict()
    elif isinstance(result, dict):
        raw = dict(result)
    else:
        return {}

    snapshot: dict[str, Any] = {
        "total_available": _scalar(raw.get("total_available")),
        "suggested_emergency_reserve": _scalar(
            raw.get("suggested_emergency_reserve", raw.get("emergency_reserve"))
        ),
        "short_term_cash_amount": _scalar(
            raw.get("short_term_cash_amount", raw.get("short_term_reserve"))
        ),
        "debt_reserve": _scalar(raw.get("debt_reserve")),
        "amount_potentially_investable": _scalar(
            raw.get("amount_potentially_investable", raw.get("available_to_invest"))
        ),
        "long_term_suggested": _scalar(
            raw.get("long_term_suggested", raw.get("suggested_long_term_amount"))
        ),
        "short_term_investable": _scalar(
            raw.get("short_term_investable", raw.get("suggested_safer_amount"))
        ),
        "monthly_contribution": _scalar(raw.get("monthly_contribution")),
        "money_needed_1_2_years": _scalar(raw.get("money_needed_1_2_years")),
        "planned_large_expenses": _scalar(raw.get("planned_large_expenses")),
        "long_term_allocation_pct": _scalar(raw.get("long_term_allocation_pct")),
        "safer_sleeve_allocation_pct": _scalar(raw.get("safer_sleeve_allocation_pct")),
        "summary_lines": _string_list(raw.get("summary_lines")),
        "educational_notes": _string_list(
            raw.get("educational_notes", raw.get("rationale"))
        ),
    }
    return {k: v for k, v in snapshot.items() if v is not None}


def _scalar(val: Any) -> float | int | str | bool | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    try:
        import numpy as np

        if isinstance(val, np.generic):
            return val.item()
    except ImportError:
        pass
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return str(val)


def _string_list(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val if str(x).strip()]
    return [str(val)]


def ensure_json_safe(value: Any) -> Any:
    """Recursively normalize to JSON-safe primitives and containers."""
    import portfolio_core as core

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
    except ImportError:
        pass
    if isinstance(value, core.InvestmentPlanResult):
        return investment_plan_result_to_dict(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return ensure_json_safe(dataclasses.asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return ensure_json_safe(model_dump(mode="json"))
        except TypeError:
            return ensure_json_safe(model_dump())
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict) and type(value).__name__ == "InvestmentPlanResult":
        return investment_plan_result_to_dict(value)
    if isinstance(value, dict):
        return {str(k): ensure_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [ensure_json_safe(v) for v in value]
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            return ensure_json_safe(value.to_dict(orient="records"))
        if isinstance(value, pd.Series):
            return ensure_json_safe(value.to_dict())
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_safe_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Sanitize AMI question context before json.dumps or cloud storage."""
    if not isinstance(context, dict):
        return {}
    return {str(k): ensure_json_safe(v) for k, v in context.items()}
