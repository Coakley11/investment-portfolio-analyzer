"""Prompt templates for portfolio analytical synthesis."""

from __future__ import annotations

from typing import Any


SYNTHESIS_PROMPT_VERSION = "p4-v1"


def build_system_prompt(*, beginner: bool) -> str:
    tone = (
        "Use plain language suitable for a beginner investor, but keep institutional rigor."
        if beginner
        else "Write in the tone of an institutional portfolio manager or investment committee memo."
    )
    return f"""You are an experienced investment analyst. {tone}

Rules (strict):
1. Answer the user's question directly — structure the response for that question, not a generic template.
2. Use ONLY facts from the provided PortfolioAnalysisBrief JSON (facts, sections, limitations).
3. Do NOT recalculate portfolio mathematics or invent holdings, weights, or metrics.
4. When stating a number or portfolio-specific claim, cite the fact_id in brackets, e.g. [holdings.largest_weight_pct].
5. Discuss trade-offs, uncertainty, and alternative viewpoints when appropriate.
6. Explicitly acknowledge relevant items from "limitations" when they affect your reasoning.
7. Avoid generic advice that could apply to any portfolio without citing this portfolio's facts.
8. This is educational analysis, not a personal recommendation to buy or sell.

Output valid JSON only with keys:
- answer_markdown (string, markdown)
- citations (array of {{"fact_id": string, "excerpt": string}})
- uncertainties (array of strings)
- alternative_viewpoints (array of strings)

Prompt version: {SYNTHESIS_PROMPT_VERSION}."""


def build_user_prompt(
    *,
    question: str,
    synthesis_input: dict[str, Any],
) -> str:
    import json

    return (
        "User question (answer this verbatim intent):\n"
        f"{question.strip()}\n\n"
        "PortfolioAnalysisBrief and metadata (single source of truth):\n"
        f"{json.dumps(synthesis_input, indent=2, default=str)}"
    )


def build_synthesis_input(
    *,
    question: str,
    brief_dict: dict[str, Any],
    question_tag: str,
    experience_mode: str,
    source_page: str,
    routing_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Structured payload sent to the model (also used in dev diagnostics)."""
    return {
        "question": question,
        "question_tag": question_tag,
        "experience_mode": experience_mode,
        "source_page": source_page,
        "routing": dict(routing_metadata or {}),
        "brief": {
            "brief_version": brief_dict.get("brief_version"),
            "brief_schema_version": brief_dict.get("brief_schema_version"),
            "limitations": brief_dict.get("limitations") or [],
            "facts": brief_dict.get("facts") or {},
            "fact_index": brief_dict.get("fact_index") or {},
            "sections": brief_dict.get("sections") or {},
            "data_quality": (brief_dict.get("facts") or {}).get("data_quality.completeness"),
        },
    }
