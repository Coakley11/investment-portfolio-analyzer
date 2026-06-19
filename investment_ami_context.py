"""Investment AMI intent detection and submit context helpers."""

from __future__ import annotations

import re
from typing import Any

INVESTMENT_AMI_STARTER_QUESTIONS: tuple[str, ...] = (
    "Is my portfolio too concentrated?",
    "Should I rebalance?",
    "What is my biggest portfolio risk?",
    "Explain my allocation.",
    "Am I too exposed to tech?",
    "What should I change if I want less risk?",
    "Should I own both VOO and QQQ?",
    "Am I diversified enough?",
    "What happens if tech falls 20%?",
    "Is SCHD expensive?",
    "What growth rate is implied for VOO?",
)

_INVESTMENT_SOLVER_INTENTS = frozenset(
    {
        "portfolio_concentration",
        "rebalance_allocation",
        "portfolio_risk",
        "sector_exposure",
        "risk_reduction",
        "investment_coach",
        "etf_overlap",
        "diversification",
        "scenario_stress",
        "valuation",
        "macro_rates",
        "macro_recession",
        "macro_inflation",
        "allocation_recommendation",
    }
)

_CONCENTRATION_PHRASES = (
    "too concentrated",
    "concentrated",
    "concentration",
    "overweight",
    "too much in one",
)

_REBALANCE_PHRASES = (
    "explain my allocation",
    "explain allocation",
    "my allocation",
    "target weights",
    "drift",
)

_ALLOCATION_RECOMMENDATION_PHRASES = (
    "what should i change",
    "what should i do",
    "what would you change",
    "what should i rebalance",
    "which etf should i add",
    "which etf should i reduce",
    "should i add more",
    "add more of",
    "should i reduce",
    "reduce my",
    "is my allocation reasonable",
    "allocation reasonable",
    "how would you improve",
    "improve this portfolio",
    "improve my portfolio",
    "how should i improve",
)

_RISK_PHRASES = (
    "biggest risk",
    "biggest portfolio risk",
    "main risk",
    "too risky",
    "portfolio risk",
)

_TECH_EXPOSURE_PHRASES = (
    "exposed to tech",
    "tech exposure",
    "too much tech",
    "technology exposure",
    "overweight tech",
)

_RISK_REDUCTION_PHRASES = (
    "less risk",
    "lower risk",
    "reduce risk",
    "more conservative",
    "safer portfolio",
)

_COACH_PHRASES = (
    "what is",
    "what does",
    "explain",
    "teach me",
    "help me understand",
)

_OVERLAP_PHRASES = (
    "overlap",
    "duplicate exposure",
    "duplicating exposure",
    "own both",
    "too similar",
    "same holdings",
)

_DIVERSIFICATION_PHRASES = (
    "diversified enough",
    "diversification",
    "diversified",
    "asset class",
    "asset classes",
    "missing asset",
    "how balanced",
)

_RATE_RISE_PHRASES = (
    "interest rate",
    "interest rates",
    "rates rise",
    "rates rising",
    "rate rise",
    "rate shock",
    "rising rates",
    "fed hike",
    "fed rate",
    "higher rates",
    "rates go up",
    "rates increase",
)

_VALUATION_PHRASES = (
    "expensive",
    "overvalued",
    "undervalued",
    "cheap",
    "fairly valued",
    "fair value",
    "p/e",
    "pe ratio",
    "price to earnings",
    " valuation",
    "implied growth",
    "growth rate is implied",
    "growth rate implied",
    "assumptions matter",
    "what assumptions",
    "too rich",
)

_SCENARIO_PHRASES = (
    "what happens if",
    "what if",
    "falls 20",
    "fall 20",
    "drawdown",
    "stress test",
    "stress testing",
)

_RECESSION_PHRASES = (
    "recession",
    "economic downturn",
    "economic slowdown",
    "bear market recession",
)

_INFLATION_PHRASES = (
    "inflation",
    "purchasing power",
    "real return",
    "cpi",
    "cost of living",
)


def investment_ami_default_question(source_page: str) -> str:
    page = str(source_page or "").strip().lower()
    if "health" in page or "portfolio" in page:
        return INVESTMENT_AMI_STARTER_QUESTIONS[0]
    return INVESTMENT_AMI_STARTER_QUESTIONS[2]


def is_beginner_experience(ctx: dict[str, Any]) -> bool:
    exp = str(ctx.get("experience_mode") or ctx.get("experience") or "").strip().lower()
    return "beginner" in exp


def detect_investment_send_intent(question: str, source_page: str = "") -> str:
    q = _normalize_question(question)
    if not q:
        return ""

    if any(p in q for p in _TECH_EXPOSURE_PHRASES) or (
        "tech" in q and any(w in q for w in ("exposed", "exposure", "overweight", "too much"))
    ):
        return "sector_exposure"
    if any(p in q for p in _OVERLAP_PHRASES) or (
        "both" in q and any(t in q for t in ("voo", "qqq", "vti", "spy", "ivv"))
    ):
        return "etf_overlap"
    if any(p in q for p in _VALUATION_PHRASES) and not any(p in q for p in _SCENARIO_PHRASES):
        return "valuation"
    if _is_rate_rise_question(q):
        return "macro_rates"
    if _is_inflation_question(q):
        return "macro_inflation"
    if _is_recession_question(q):
        return "macro_recession"
    if any(p in q for p in _SCENARIO_PHRASES):
        return "scenario_stress"
    if any(p in q for p in _DIVERSIFICATION_PHRASES):
        return "diversification"
    if any(p in q for p in _RISK_REDUCTION_PHRASES):
        return "risk_reduction"
    if _is_allocation_recommendation_question(q):
        return "allocation_recommendation"
    if any(p in q for p in _CONCENTRATION_PHRASES):
        return "portfolio_concentration"
    if any(p in q for p in ("rebalance", "rebalancing")) and any(
        w in q for w in ("should", "need", "when", "have to")
    ):
        return "allocation_recommendation"
    if any(p in q for p in _REBALANCE_PHRASES):
        return "rebalance_allocation"
    if any(p in q for p in _RISK_PHRASES):
        return "portfolio_risk"
    if any(p in q for p in _COACH_PHRASES):
        return "investment_coach"

    page = str(source_page or "").strip().lower()
    if "health" in page and "risk" in q:
        return "portfolio_risk"
    if "portfolio" in page and "allocation" in q:
        return "rebalance_allocation"
    return "portfolio_risk"


def intent_supported(intent: str) -> bool:
    return str(intent or "").strip() in _INVESTMENT_SOLVER_INTENTS


def _normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _is_rate_rise_question(q: str) -> bool:
    if any(p in q for p in _RATE_RISE_PHRASES):
        return True
    if "rate" in q and any(w in q for w in ("rise", "rising", "increase", "hike", "higher", "go up")):
        return True
    if re.search(r"duration", q) and any(w in q for w in ("rate", "bond", "rise", "rising")):
        return True
    return False


def _is_recession_question(q: str) -> bool:
    if not any(p in q for p in _RECESSION_PHRASES):
        return False
    if _is_inflation_question(q):
        return False
    if _is_rate_rise_question(q):
        return False
    return True


def _is_inflation_question(q: str) -> bool:
    return any(p in q for p in _INFLATION_PHRASES)


def _is_allocation_recommendation_question(q: str) -> bool:
    if any(p in q for p in _ALLOCATION_RECOMMENDATION_PHRASES):
        return True
    if "rebalance" in q and "explain" not in q and any(w in q for w in ("should", "need", "what", "how")):
        return True
    return False
