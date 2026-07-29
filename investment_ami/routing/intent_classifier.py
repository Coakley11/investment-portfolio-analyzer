"""Intent-first routing signals — reasoning/judgment vs quantitative calculation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

IntentPrimary = Literal["reasoning_judgment", "quantitative_metric", "hybrid"]

CLASSIFIER_VERSION = "intent-v1"

# (substring in normalized question, weight)
REASONING_SIGNALS: tuple[tuple[str, float], ...] = (
    ("why ", 2.0),
    ("why would", 2.0),
    ("explain ", 2.0),
    ("explain why", 2.5),
    ("compare ", 2.0),
    ("contrast ", 2.0),
    ("versus ", 1.5),
    (" vs ", 1.5),
    ("trade-off", 2.0),
    ("trade off", 2.0),
    ("tradeoffs", 2.0),
    ("priorit", 2.0),
    ("rank ", 1.5),
    ("ranking", 1.5),
    ("critique", 3.0),
    ("investment committee", 3.0),
    ("institutional", 2.0),
    ("professional insight", 2.5),
    ("recommend", 1.5),
    ("recommendation", 1.5),
    ("should i ", 1.0),
    ("would you ", 1.5),
    ("judgment", 2.0),
    ("judgement", 2.0),
    ("analyze how", 2.5),
    ("analysis of", 2.0),
    ("primary drivers", 2.5),
    ("each environment", 2.0),
    ("historical", 2.0),
    ("would have performed", 3.0),
    ("would have done", 2.5),
    ("scenario analysis", 2.5),
    ("stress test", 2.0),
    ("devil", 2.0),
    ("argue against", 3.0),
    ("bear case", 2.0),
    ("bull case", 2.0),
    ("strategy", 1.5),
    ("allocate philosoph", 2.0),
    ("missing from", 1.5),
    ("what am i wrong", 2.5),
    ("what am i missing", 2.5),
    ("improve my portfolio", 2.0),
    ("how would you improve", 2.5),
)

QUANTITATIVE_SIGNALS: tuple[tuple[str, float], ...] = (
    ("what percentage", 3.0),
    ("what percent", 3.0),
    ("how much of my portfolio", 2.5),
    ("calculate", 3.0),
    ("computation", 3.0),
    ("compute ", 3.0),
    ("dividend yield", 3.0),
    ("sharpe ratio", 3.0),
    ("expected volatility", 3.0),
    ("portfolio volatility", 3.0),
    ("max drawdown", 3.0),
    ("largest holding", 3.0),
    ("biggest holding", 3.0),
    ("top holding", 3.0),
    ("overlap between", 2.5),
    ("etf overlap", 2.5),
    ("monte carlo", 3.0),
    ("simulation", 2.0),
    ("tax lot", 2.5),
    ("cost basis", 2.5),
    ("rebalance drift", 2.5),
    ("slider", 2.0),
    ("rate shock", 2.5),
    ("basis point", 2.0),
)


@dataclass(frozen=True)
class IntentClassification:
    """Explainable intent snapshot used before engine selection."""

    classifier_version: str
    primary: IntentPrimary
    reasoning_score: float
    quantitative_score: float
    legacy_intent_hint: str
    reasoning_signals: tuple[str, ...] = ()
    quantitative_signals: tuple[str, ...] = ()
    suggested_question_tag: str = ""
    prefer_synthesis: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _suggest_tag(q: str, reasoning_signals: tuple[str, ...]) -> str:
    if any("critique" in s or "committee" in s for s in reasoning_signals):
        return "critique"
    if "rank" in q or "priorit" in q or "five biggest risk" in q:
        return "ranked_risks"
    if "argue against" in q or "devil" in q or "bear case" in q:
        return "devils_advocate"
    if "compare" in q or " versus" in q or " vs " in q:
        if "endowment" in q:
            return "peer_compare"
        return "open_ended"
    if any(
        t in q
        for t in (
            "2008",
            "financial crisis",
            "covid",
            "would have performed",
            "historical",
            "each environment",
            "primary drivers",
        )
    ):
        return "historical_scenario"
    if "ray dalio" in q or "all weather" in q or "boglehead" in q:
        return "philosophy_lens"
    if "explain" in q or "why " in q:
        return "open_ended"
    if "scenario" in q or "stress" in q:
        return "open_ended"
    return "open_ended"


def classify_routing_intent(
    question: str,
    *,
    q_normalized: str,
    legacy_intent_hint: str = "",
    has_portfolio_context: bool = False,
) -> IntentClassification:
    """Score reasoning vs quantitative intent from the question (not legacy alone)."""
    q = str(q_normalized or "").strip()
    reasoning = 0.0
    quantitative = 0.0
    r_hits: list[str] = []
    q_hits: list[str] = []

    for phrase, weight in REASONING_SIGNALS:
        if phrase in q:
            reasoning += weight
            r_hits.append(phrase)

    for phrase, weight in QUANTITATIVE_SIGNALS:
        if phrase in q:
            quantitative += weight
            q_hits.append(phrase)

    # Open-ended prose favors synthesis when portfolio context exists
    if has_portfolio_context and len(q.split()) >= 14:
        reasoning += 1.0
        r_hits.append("long_form_with_portfolio_context")

    if re.search(r"\bwhy\b", q):
        reasoning += 1.5
        r_hits.append("why_question")

    if quantitative >= 4.0 and reasoning < 2.0:
        primary: IntentPrimary = "quantitative_metric"
        rationale = "Strong quantitative signals; prefer deterministic engines."
        prefer = False
    elif reasoning >= 2.0 or (reasoning >= 1.5 and reasoning > quantitative + 1.0):
        primary = "reasoning_judgment"
        rationale = "Reasoning/judgment signals dominate; prefer analytical synthesis."
        prefer = True
    else:
        primary = "hybrid"
        rationale = "Mixed signals; defer to structured router rules."
        prefer = reasoning >= quantitative and reasoning >= 1.5

    # Legacy hint is evidence, not the decision — boost quant only for clearly calc intents
    legacy = str(legacy_intent_hint or "").strip()
    calc_legacy = frozenset(
        {
            "portfolio_concentration",
            "etf_overlap",
            "sector_exposure",
            "valuation",
            "rebalance_allocation",
        }
    )
    if legacy in calc_legacy and reasoning < 2.5:
        prefer = False
        if quantitative >= 1.0 or legacy in calc_legacy:
            primary = "quantitative_metric" if quantitative >= 2.0 else "hybrid"
        rationale += f" Structured calc legacy `{legacy}`; defer to deterministic engine."

    if legacy in ("macro_inflation", "macro_rates", "macro_recession") and reasoning >= 2.0:
        prefer = True
        rationale += " Macro legacy overridden by reasoning/historical framing."

    tag = _suggest_tag(q, tuple(r_hits))

    return IntentClassification(
        classifier_version=CLASSIFIER_VERSION,
        primary=primary,
        reasoning_score=round(reasoning, 2),
        quantitative_score=round(quantitative, 2),
        legacy_intent_hint=legacy,
        reasoning_signals=tuple(r_hits[:12]),
        quantitative_signals=tuple(q_hits[:12]),
        suggested_question_tag=tag,
        prefer_synthesis=prefer,
        rationale=rationale.strip(),
    )
