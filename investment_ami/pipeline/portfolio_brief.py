"""Attach portfolio analysis brief to instant AMI pipeline."""

from __future__ import annotations

import json
from typing import Any

from investment_ami.engines.support.portfolio_analysis_brief import (
    PortfolioAnalysisBrief,
    build_portfolio_analysis_brief,
)


def attach_portfolio_analysis_brief(
    result: Any,
    context: dict[str, Any] | None,
    *,
    question: str = "",
) -> PortfolioAnalysisBrief:
    """Build brief, merge into solver ``computed``, return brief for diagnostics."""
    brief = build_portfolio_analysis_brief(context, question=question)
    computed = dict(getattr(result, "computed", None) or {})
    computed["portfolio_analysis_brief_version"] = brief.brief_version
    computed["portfolio_analysis_brief"] = brief.to_dict()
    try:
        result.computed = computed
    except AttributeError:
        pass
    return brief


def portfolio_brief_diagnostics_summary(brief: PortfolioAnalysisBrief) -> dict[str, Any]:
    """Compact summary for submit trace (full brief stored separately)."""
    return {
        "brief_version": brief.brief_version,
        "fact_count": len(brief.facts),
        "limitation_count": len(brief.limitations),
        "assembly_trace": list(brief.assembly_trace),
        "limitations": list(brief.limitations),
    }


def portfolio_brief_json_for_dev_panel(brief: PortfolioAnalysisBrief, *, indent: int = 2) -> str:
    return json.dumps(brief.to_dict(), indent=indent, default=str)
