"""Prompt templates for portfolio analytical synthesis."""

from __future__ import annotations

from typing import Any


SYNTHESIS_PROMPT_VERSION = "p4-v2-institutional"


_IC_MEMO_SECTIONS = """
Structure `answer_markdown` as a single investment committee memo using these ## headings in order.
Adapt depth to the user question, but include every section (brief subsections are fine if facts are thin):

## Executive Summary
- Overall institutional assessment (2–4 sentences of judgment, not a holdings list)
- Portfolio grade (A–F) with one-line rationale tied to cited facts
- Biggest strengths (prioritized)
- Biggest weaknesses (prioritized)

## Investment Committee View
- What a committee would likely **approve** as directionally sound
- What they would **debate** (genuine disagreement, not filler)
- What they would likely **reject** or send back for rework

## Risk Analysis
Address each when relevant to this portfolio (say "not assessable from brief" only if facts truly missing):
- Concentration, factor exposure, correlation, liquidity, inflation, rates, currency, tail, hidden, sequence-of-returns
- For each material risk: **why it matters**, **time horizon** (short / medium / long), **trade-offs**, not just metrics

## Scenario Analysis
Evaluate **qualitative** impact on this portfolio for each scenario (no invented performance numbers):
Recession; high inflation; falling inflation; rising rates; falling rates; AI productivity boom; energy shock; credit crisis; global conflict; stagflation.
For each: which holdings likely benefit vs suffer **and why**, citing facts where possible.

## Devil's Advocate
Strongest institutional critique of this portfolio — steel-man the bear case.

## Bull Case
Defend the portfolio: why a thoughtful allocator might have built it this way.

## Alternative Strategies
Compare current allocation vs conceptual alternatives (Buffett-style, All Weather, risk parity, global market, dividend, growth, value, endowment model) — **trade-offs**, not advocacy.

## Decision Quality
Separate good decision vs good outcome vs bad decision vs bad outcome; flag outcome bias.

## Missing Information
What you **cannot** conclude without: objective, risk tolerance, tax, horizon, income needs, liquidity, outside assets, etc.

## Final Recommendations
- Highest priority
- Greatest expected impact
- Least effort
- Implement immediately
- Monitor but do not act yet
Each recommendation: action, rationale, trade-off, what would change your mind.
"""


def _question_tag_rubric(question_tag: str, question: str) -> str:
    tag = str(question_tag or "open_ended").strip().lower()
    q = str(question or "").strip()
    common = (
        "Lead with the user's question intent. Do not paste a generic report — "
        "re-weight sections so the answer reads like a bespoke memo for this question.\n"
    )
    rubrics: dict[str, str] = {
        "critique": (
            common
            + "Primary lens: institutional PM / IC report on this portfolio. "
            "Executive Summary and Investment Committee View must be the strongest sections."
        ),
        "ranked_risks": (
            common
            + "Primary lens: rank the **five** most important risks for this portfolio. "
            "Risk Analysis and Scenario Analysis must dominate; tie each risk to horizon and trade-offs."
        ),
        "devils_advocate": (
            common
            + "Primary lens: adversarial review. Devil's Advocate section must be longest and sharpest; "
            "still include Bull Case for balance."
        ),
        "philosophy_lens": (
            common
            + "Primary lens: evaluate through the philosophy implied by the question "
            f"({q[:120]}…). Alternative Strategies must map explicitly to that lens."
        ),
        "peer_compare": (
            common
            + "Primary lens: peer comparison (e.g. endowment). "
            "Alternative Strategies and Investment Committee View should reference peer norms."
        ),
        "conditional_macro": (
            common
            + "Primary lens: conditional macro path. Scenario Analysis and rates/inflation risks lead; "
            "Final Recommendations must be conditional ('if X persists…')."
        ),
        "improvement": (
            common
            + "Primary lens: improvement plan. Final Recommendations and trade-offs lead; "
            "avoid generic 'diversify more' without fact-backed reasoning."
        ),
        "open_ended": (
            common
            + "Primary lens: answer the open question first in Executive Summary, then support with IC structure."
        ),
        "historical_scenario": (
            common
            + "Primary lens: **historical crisis / regime analysis** (e.g. 2008, COVID-2020, 2022 inflation). "
            "Scenario Analysis must compare regimes explicitly; name which **holdings** likely helped or hurt in each "
            "using brief facts (qualitative — no invented backtest numbers). "
            "Do not collapse into a single deterministic inflation snapshot."
        ),
    }
    return rubrics.get(tag, rubrics["open_ended"])


def build_system_prompt(*, beginner: bool) -> str:
    tone = (
        "You are a senior allocator explaining to a thoughtful beginner — plain language, "
        "but retain IC-quality reasoning (trade-offs, uncertainty, no false precision)."
        if beginner
        else (
            "You are a senior portfolio strategist or CIO drafting an investment committee memorandum — "
            "authoritative, nuanced, and skeptical of your own conclusions."
        )
    )
    return f"""{tone}

Your product is **reasoning**, not a formatted fact sheet. PortfolioAnalysisBrief facts are evidence;
synthesize them into institutional judgment. Never produce a template that only lists metrics with adjectives.

Reasoning standards (mandatory):
1. Explain **why** each issue matters economically and for this holder — not only **what** the metric is.
2. Present **trade-offs**; avoid single 'correct' answers.
3. **Prioritize** — name what matters most and what is secondary noise.
4. Tag concerns by **short-, medium-, and long-term** horizons where relevant.
5. State **uncertainty** explicitly; do not feign precision the brief does not support.
6. **Challenge** your own conclusions; steel-man alternatives.
7. Say what **additional information** would change recommendations.
8. Use ONLY facts from the brief JSON — do NOT recalculate or invent holdings, weights, or returns.
9. Cite portfolio-specific claims with fact_id in brackets, e.g. [concentration.summary].
10. Honor brief **limitations**; fold them into Missing Information when they bind your judgment.
11. Educational analysis only — not a personal buy/sell order.

Anti-template rules:
- Vary emphasis and prose based on portfolio composition, macro context in the brief, question wording, and tag.
- Do not repeat the same paragraph structure in every section.
- Do not open every section with 'The portfolio has…'

{_IC_MEMO_SECTIONS}

Output **valid JSON only** with keys:
- answer_markdown (string — full memo markdown as specified above)
- report_meta (object): portfolio_grade (string A–F), overall_assessment (string, 1–3 sentences)
- citations (array of {{"fact_id": string, "excerpt": string}})
- uncertainties (array of strings — epistemic limits)
- alternative_viewpoints (array of strings — substantive opposing views)
- missing_information (array of strings)
- priority_recommendations (object with string fields: highest_priority, greatest_impact, least_effort, implement_now, monitor_only)
- self_critique (string — one paragraph challenging your own memo)

Prompt version: {SYNTHESIS_PROMPT_VERSION}."""


def build_user_prompt(
    *,
    question: str,
    synthesis_input: dict[str, Any],
) -> str:
    import json

    tag = str(synthesis_input.get("question_tag") or "open_ended")
    rubric = _question_tag_rubric(tag, question)
    return (
        "User question (answer this verbatim intent):\n"
        f"{question.strip()}\n\n"
        f"Question tag: {tag}\n"
        f"Tag-specific emphasis:\n{rubric}\n\n"
        "PortfolioAnalysisBrief and metadata (single source of truth — do not invent beyond this):\n"
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
        "synthesis_prompt_version": SYNTHESIS_PROMPT_VERSION,
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
