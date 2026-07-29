"""Structural + rubric helpers for B1 portfolio critique / IC memo benchmark."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

B1_QUESTION = "Critique my portfolio as an institutional portfolio manager."
B1_BENCHMARK_ID = "B1"

# Analyst dimensions (1–5 human scores); structural proxies support live A/B comparison.
CRITIQUE_DIMENSIONS: tuple[str, ...] = (
    "depth_of_reasoning",
    "portfolio_personalization",
    "macro_analysis",
    "scenario_analysis",
    "recommendation_quality",
    "originality",
    "institutional_tone",
    "evidence_grounding",
    "actionability",
    "overall_usefulness",
)

_SCENARIO_KEYWORDS: tuple[str, ...] = (
    "recession",
    "inflation",
    "rising rates",
    "falling rates",
    "stagflation",
    "credit crisis",
    "energy shock",
    "geopolitical",
    "global conflict",
    "ai productivity",
    "productivity boom",
)

_REASONING_MARKERS: tuple[str, ...] = (
    "because",
    "therefore",
    "trade-off",
    "trade off",
    "however",
    "uncertain",
    "uncertainty",
    "would change my view",
    "on the other hand",
)


@dataclass
class B1StructuralMetrics:
    """Automated signals (0–1 scale per metric); not a substitute for human 1–5 scores."""

    answer_chars: int = 0
    section_headings: int = 0
    holding_symbols_mentioned: int = 0
    scenario_topics_covered: int = 0
    reasoning_marker_count: int = 0
    citation_count: int = 0
    has_executive_summary: bool = False
    has_investment_thesis: bool = False
    has_priority_recommendations: bool = False
    mock_or_error: bool = False
    structural_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _count_sections(md: str) -> int:
    return len(re.findall(r"^##\s+", md, flags=re.MULTILINE))


def compute_b1_structural_metrics(
    *,
    answer_markdown: str,
    parsed_response: dict[str, Any] | None,
    holdings: dict[str, Any] | None,
    synthesis_error: str = "",
) -> B1StructuralMetrics:
    md = str(answer_markdown or "").strip()
    parsed = dict(parsed_response or {})
    metrics = B1StructuralMetrics(answer_chars=len(md))

    low = md.lower()
    if "mock analytical synthesis" in low or "could not run" in low or "empty answer" in low:
        metrics.mock_or_error = True
        metrics.notes.append("Response is mock, error, or placeholder — human critique scores require live synthesis.")
    if synthesis_error:
        metrics.mock_or_error = True
        metrics.notes.append(synthesis_error[:200])

    metrics.section_headings = _count_sections(md)
    metrics.has_executive_summary = "## executive summary" in low or "## Executive Summary" in md
    thesis = str(parsed.get("investment_thesis") or "").strip()
    metrics.has_investment_thesis = bool(thesis) or "## investment thesis" in low
    pri = parsed.get("priority_recommendations")
    metrics.has_priority_recommendations = isinstance(pri, dict) and any(str(v).strip() for v in pri.values())

    cites = parsed.get("citations")
    metrics.citation_count = len(cites) if isinstance(cites, list) else len(re.findall(r"\[[\w.]+\]", md))

    weights = holdings or {}
    for sym in weights:
        if re.search(rf"\b{re.escape(str(sym))}\b", md, flags=re.IGNORECASE):
            metrics.holding_symbols_mentioned += 1

    for kw in _SCENARIO_KEYWORDS:
        if kw in low:
            metrics.scenario_topics_covered += 1

    metrics.reasoning_marker_count = sum(low.count(m) for m in _REASONING_MARKERS)

    # Weighted structural score (guardrail for iteration A/B on live runs)
    parts = [
        min(metrics.answer_chars / 4500, 1.0) * 0.15,
        min(metrics.section_headings / 10, 1.0) * 0.1,
        min(metrics.holding_symbols_mentioned / max(len(weights), 1), 1.0) * 0.15,
        min(metrics.scenario_topics_covered / 6, 1.0) * 0.15,
        min(metrics.reasoning_marker_count / 12, 1.0) * 0.15,
        min(metrics.citation_count / 5, 1.0) * 0.1,
        (0.05 if metrics.has_executive_summary else 0.0),
        (0.1 if metrics.has_investment_thesis else 0.0),
        (0.05 if metrics.has_priority_recommendations else 0.0),
    ]
    metrics.structural_score = round(sum(parts), 3)
    if metrics.mock_or_error:
        metrics.structural_score = round(metrics.structural_score * 0.35, 3)
    return metrics


def empty_human_scorecard() -> dict[str, int | str]:
    return {d: "" for d in CRITIQUE_DIMENSIONS}
