"""Structured Investment AMI analyst answer sections (Phase 2)."""

from __future__ import annotations

from typing import Any

SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "Portfolio Analyst View"),
    ("key_variables", "Key Variables"),
    ("tradeoffs", "Tradeoffs"),
    ("what_if_scenarios", "What-If Scenarios"),
    ("recommended_actions", "Recommended Actions"),
    ("risk_notes", "Risk Notes"),
)

_BEGINNER_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "What This Means"),
    ("key_variables", "Key Numbers"),
    ("tradeoffs", "Tradeoffs"),
    ("recommended_actions", "What You Could Do"),
    ("risk_notes", "Important Notes"),
)

ALLOCATION_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "Portfolio Analyst View"),
    ("current_strengths", "Current Strengths"),
    ("current_weaknesses", "Current Weaknesses"),
    ("potential_increases", "Potential Increases"),
    ("potential_reductions", "Potential Reductions"),
    ("tradeoffs", "Tradeoffs"),
    ("what_if_scenarios", "What-If Scenarios"),
    ("recommended_actions", "Recommended Actions"),
    ("risk_notes", "Risk Notes"),
)

_BEGINNER_ALLOCATION_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "What This Means"),
    ("current_strengths", "What's Working"),
    ("current_weaknesses", "What to Watch"),
    ("potential_increases", "Consider Adding"),
    ("potential_reductions", "Consider Trimming"),
    ("tradeoffs", "Tradeoffs"),
    ("recommended_actions", "What You Could Do"),
    ("risk_notes", "Important Notes"),
)

AMI_DEEP_DIVE_EXTRA_SECTIONS: tuple[tuple[str, str], ...] = (
    ("current_portfolio", "Current Portfolio"),
    ("proposed_portfolio", "Proposed Portfolio"),
    ("portfolio_comparison", "Before vs After"),
    ("rebalance_candidates", "Rebalance Candidates"),
    ("calculation_chains", "Calculation Chains"),
    ("methodology", "Methodology"),
    ("assumptions", "Assumptions"),
)

AMI_ALLOCATION_DEEP_DIVE_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("portfolio_analyst_view", "Portfolio Analyst View"),
    ("current_portfolio", "Current Portfolio"),
    ("proposed_portfolio", "Proposed Portfolio"),
    ("portfolio_comparison", "Before vs After"),
    ("net_allocation_changes", "Net Allocation Changes"),
    ("current_strengths", "Current Strengths"),
    ("current_weaknesses", "Current Weaknesses"),
    ("potential_increases", "Potential Increases"),
    ("potential_reductions", "Potential Reductions"),
    ("rebalance_candidates", "Rebalance Candidates"),
    ("tradeoffs", "Tradeoffs"),
    ("what_if_scenarios", "What-If Scenarios"),
    ("recommended_actions", "Recommended Actions"),
    ("calculation_chains", "Calculation Chains"),
    ("methodology", "Methodology"),
    ("assumptions", "Assumptions"),
    ("risk_notes", "Risk Notes"),
)


def build_analyst_sections(
    *,
    direct_answer: str,
    portfolio_analyst_view: str = "",
    key_variables: str = "",
    tradeoffs: str = "",
    what_if_scenarios: str = "",
    recommended_actions: str = "",
    risk_notes: str = "",
    beginner: bool = False,
) -> dict[str, str]:
    """Build non-empty analyst sections dict."""
    raw = {
        "direct_answer": str(direct_answer or "").strip(),
        "portfolio_analyst_view": str(portfolio_analyst_view or "").strip(),
        "key_variables": str(key_variables or "").strip(),
        "tradeoffs": str(tradeoffs or "").strip(),
        "what_if_scenarios": str(what_if_scenarios or "").strip(),
        "recommended_actions": str(recommended_actions or "").strip(),
        "risk_notes": str(risk_notes or "").strip(),
    }
    if beginner:
        raw.pop("what_if_scenarios", None)
    return {k: v for k, v in raw.items() if v}


def build_allocation_sections(
    *,
    direct_answer: str,
    portfolio_analyst_view: str = "",
    current_strengths: str = "",
    current_weaknesses: str = "",
    potential_increases: str = "",
    potential_reductions: str = "",
    tradeoffs: str = "",
    what_if_scenarios: str = "",
    recommended_actions: str = "",
    risk_notes: str = "",
    current_portfolio: str = "",
    proposed_portfolio: str = "",
    portfolio_comparison: str = "",
    net_allocation_changes: str = "",
    rebalance_candidates: str = "",
    calculation_chains: str = "",
    methodology: str = "",
    assumptions: str = "",
    beginner: bool = False,
) -> dict[str, str]:
    raw = {
        "direct_answer": str(direct_answer or "").strip(),
        "portfolio_analyst_view": str(portfolio_analyst_view or "").strip(),
        "current_strengths": str(current_strengths or "").strip(),
        "current_weaknesses": str(current_weaknesses or "").strip(),
        "potential_increases": str(potential_increases or "").strip(),
        "potential_reductions": str(potential_reductions or "").strip(),
        "tradeoffs": str(tradeoffs or "").strip(),
        "what_if_scenarios": str(what_if_scenarios or "").strip(),
        "recommended_actions": str(recommended_actions or "").strip(),
        "risk_notes": str(risk_notes or "").strip(),
        "current_portfolio": str(current_portfolio or "").strip(),
        "proposed_portfolio": str(proposed_portfolio or "").strip(),
        "portfolio_comparison": str(portfolio_comparison or "").strip(),
        "net_allocation_changes": str(net_allocation_changes or "").strip(),
        "rebalance_candidates": str(rebalance_candidates or "").strip(),
        "calculation_chains": str(calculation_chains or "").strip(),
        "methodology": str(methodology or "").strip(),
        "assumptions": str(assumptions or "").strip(),
    }
    if beginner:
        raw.pop("what_if_scenarios", None)
        raw.pop("calculation_chains", None)
        raw.pop("methodology", None)
    return {k: v for k, v in raw.items() if v}


def _section_order_for(
    sections: dict[str, Any],
    *,
    beginner: bool,
    mode: str = "deep_dive",
) -> tuple[tuple[str, str], ...]:
    is_allocation = "current_strengths" in sections or "potential_increases" in sections
    if mode == "deep_dive" and is_allocation and not beginner:
        return AMI_ALLOCATION_DEEP_DIVE_ORDER
    if is_allocation:
        return _BEGINNER_ALLOCATION_SECTION_ORDER if beginner else ALLOCATION_SECTION_ORDER
    return _BEGINNER_SECTION_ORDER if beginner else SECTION_ORDER


def render_analyst_sections_markdown(
    sections: dict[str, Any] | None,
    *,
    beginner: bool = False,
) -> str:
    """Render full analyst sections as markdown (AMI deep dive)."""
    return _render_sections_markdown(sections, beginner=beginner, mode="deep_dive")


INVESTMENT_PAGE_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("key_variables", "Key Variables"),
    ("recommended_actions", "Recommended Actions"),
)

_BEGINNER_INVESTMENT_PAGE_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("direct_answer", "Direct Answer"),
    ("key_variables", "Key Numbers"),
    ("recommended_actions", "What You Could Do"),
)


def render_investment_page_insight_markdown(
    sections: dict[str, Any] | None,
    *,
    beginner: bool = False,
    include_summary: bool = True,
) -> str:
    """Concise action-oriented insight card for the Investment app page."""
    if not isinstance(sections, dict) or not sections:
        return ""
    order = _BEGINNER_INVESTMENT_PAGE_SECTION_ORDER if beginner else INVESTMENT_PAGE_SECTION_ORDER
    parts: list[str] = []
    for key, label in order:
        body = str(sections.get(key) or "").strip()
        if body:
            parts.append(f"**{label}**\n\n{body}")
    if include_summary:
        summary = str(sections.get("portfolio_analyst_view") or "").strip()
        if summary and len(summary) <= 420:
            label = "What This Means" if beginner else "Summary"
            parts.insert(1, f"**{label}**\n\n{summary}")
    return "\n\n".join(parts)


def render_ami_deep_dive_markdown(
    sections: dict[str, Any] | None,
    *,
    beginner: bool = False,
) -> str:
    """Full analyst report for AMI deep-dive pages."""
    return _render_sections_markdown(sections, beginner=beginner, mode="deep_dive")


def _render_sections_markdown(
    sections: dict[str, Any] | None,
    *,
    beginner: bool = False,
    mode: str = "deep_dive",
) -> str:
    if not isinstance(sections, dict) or not sections:
        return ""
    if mode == "investment_page":
        return render_investment_page_insight_markdown(sections, beginner=beginner)
    order = _section_order_for(sections, beginner=beginner, mode=mode)
    parts: list[str] = []
    for key, label in order:
        body = str(sections.get(key) or "").strip()
        if body:
            parts.append(f"**{label}**\n\n{body}")
    return "\n\n".join(parts)


def direct_answer_from_sections(sections: dict[str, str]) -> str:
    return str(sections.get("direct_answer") or "").strip()
