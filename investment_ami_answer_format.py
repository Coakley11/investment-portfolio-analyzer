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
    }
    if beginner:
        raw.pop("what_if_scenarios", None)
    return {k: v for k, v in raw.items() if v}


def _section_order_for(sections: dict[str, Any], *, beginner: bool) -> tuple[tuple[str, str], ...]:
    if "current_strengths" in sections or "potential_increases" in sections:
        return _BEGINNER_ALLOCATION_SECTION_ORDER if beginner else ALLOCATION_SECTION_ORDER
    return _BEGINNER_SECTION_ORDER if beginner else SECTION_ORDER


def render_analyst_sections_markdown(
    sections: dict[str, Any] | None,
    *,
    beginner: bool = False,
) -> str:
    """Render analyst sections as markdown for insight cards / AMI."""
    if not isinstance(sections, dict) or not sections:
        return ""
    order = _section_order_for(sections, beginner=beginner)
    parts: list[str] = []
    for key, label in order:
        body = str(sections.get(key) or "").strip()
        if body:
            parts.append(f"**{label}**\n\n{body}")
    return "\n\n".join(parts)


def direct_answer_from_sections(sections: dict[str, str]) -> str:
    return str(sections.get("direct_answer") or "").strip()
