"""Response-mode routing: deterministic engines vs analytical synthesis (P4 pipeline)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

ResponseMode = Literal["deterministic", "analytical_synthesis"]

MODE_ROUTER_VERSION = "p4-phase1-v2"


@dataclass(frozen=True)
class ModeRoutingDecision:
    """Why a question was routed to deterministic solvers or analytical synthesis."""

    response_mode: ResponseMode
    question_tag: str
    deterministic_intent: str
    legacy_intent_hint: str
    matched_rules: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    router_version: str = MODE_ROUTER_VERSION

    @property
    def effective_intent_id(self) -> str:
        if self.response_mode == "analytical_synthesis":
            return "analytical_synthesis"
        return self.deterministic_intent


def mode_routing_diagnostics_dict(decision: ModeRoutingDecision) -> dict[str, Any]:
    """JSON-friendly routing trace for submit diagnostics and dev panels."""
    return {
        "router_version": decision.router_version,
        "response_mode": decision.response_mode,
        "question_tag": decision.question_tag,
        "effective_intent_id": decision.effective_intent_id,
        "deterministic_intent": decision.deterministic_intent,
        "legacy_intent_hint": decision.legacy_intent_hint,
        "matched_rules": list(decision.matched_rules),
        "reasons": list(decision.reasons),
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _has_portfolio_context(ctx: dict[str, Any] | None) -> bool:
    c = dict(ctx or {})
    weights = c.get("current_weights")
    if isinstance(weights, dict) and any(str(k).strip() for k in weights):
        return True
    holdings = c.get("holdings")
    if isinstance(holdings, list) and any(str(h).strip() for h in holdings):
        return True
    return False


def _match_analytical_tag(q: str) -> tuple[str, str] | None:
    """Return (question_tag, rule_id) when the prompt needs tailored analysis."""
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "critique",
            (
                "critique my portfolio",
                "critique this portfolio",
                "as an institutional portfolio manager",
                "institutional portfolio manager",
                "investment committee",
                " as a cio",
                "chief investment officer",
            ),
        ),
        (
            "ranked_risks",
            (
                "five biggest risk",
                "five largest risk",
                "top five risk",
                "5 biggest risk",
                "biggest risks facing",
                "largest risks facing",
            ),
        ),
        (
            "devils_advocate",
            (
                "argue against",
                "devil's advocate",
                "devils advocate",
                "make the case against",
                "bear case against",
            ),
        ),
        (
            "peer_compare",
            (
                "compare my portfolio",
                "compare this portfolio",
                "university endowment",
                "endowment portfolio",
                "typical endowment",
            ),
        ),
        (
            "goal_horizon",
            (
                "for retirement",
                "managing this portfolio for retirement",
                "over the next 10 years",
                "next ten years",
                "next 10 years",
            ),
        ),
        (
            "philosophy_lens",
            (
                "ray dalio",
                "all-weather",
                "all weather portfolio",
                "boglehead",
                "bogle head",
                "value investing philosophy",
                "think of this portfolio",
                "think of my portfolio",
            ),
        ),
        (
            "improvement",
            (
                "how would you improve",
                "improve this portfolio",
                "improve my portfolio",
            ),
        ),
        (
            "epistemic",
            (
                "what am i wrong about",
                "what am i missing",
                "hidden risk",
            ),
        ),
    )
    for tag, phrases in rules:
        if any(p in q for p in phrases):
            return tag, f"analytical_phrase:{tag}"
    if re.search(r"\btop\s+\d+\s+risk", q):
        return "ranked_risks", "analytical_phrase:ranked_risks_regex"
    return None


def _portfolio_change_framing(q: str) -> bool:
    return any(
        p in q
        for p in (
            "how should",
            "what should i change",
            "what would you change",
            "how would you change",
            "what changes",
            "what changes would you",
            "changes would you make",
            "should my portfolio",
            "adjust my portfolio",
            "change my portfolio",
            "reposition",
            "recommend",
            "would you make",
        )
    )


def _match_deterministic_objective(q: str) -> tuple[str, str] | None:
    """
    Objective portfolio metric questions — always deterministic even when phrasing is open-ended.
    Returns (intent_id, rule_id).
    """
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "sector_exposure",
            (
                "percentage of my portfolio is technology",
                "percentage of my portfolio is tech",
                "percent of my portfolio is technology",
                "percent of my portfolio is tech",
                "how much of my portfolio is tech",
                "how much of my portfolio is technology",
                "current sector allocation",
                "sector allocation",
                "what is my sector",
            ),
        ),
        (
            "portfolio_concentration",
            (
                "largest holding",
                "biggest holding",
                "top holding",
                "largest position",
                "biggest position",
            ),
        ),
        (
            "portfolio_risk",
            (
                "expected volatility",
                "portfolio volatility",
                "what is my volatility",
                "sharpe ratio",
                "max drawdown",
            ),
        ),
    )
    for intent, phrases in rules:
        if any(p in q for p in phrases):
            return intent, f"deterministic_objective:{intent}"
    if re.search(r"what\s+percentage\s+of\s+my\s+portfolio", q) and any(
        t in q for t in ("tech", "technology", "sector", "equity", "bond", "fixed")
    ):
        return "sector_exposure", "deterministic_objective:sector_exposure_regex"
    return None


def _conditional_macro_analytical(q: str) -> tuple[str, str] | None:
    try:
        from investment_ami_context import _is_inflation_question, _is_recession_question  # noqa: SLF001
    except ImportError:
        return None
    if _is_inflation_question(q) and _portfolio_change_framing(q):
        return "conditional_macro", "analytical:conditional_inflation"
    if _is_inflation_question(q) and any(
        p in q for p in ("elevated for", "remains elevated", "stay elevated", "stays high")
    ) and any(p in q for p in ("change", "make", "adjust", "recommend")):
        return "conditional_macro", "analytical:conditional_inflation_elevated"
    if _is_recession_question(q) and _portfolio_change_framing(q):
        return "conditional_macro", "analytical:conditional_recession"
    return None


def _is_explicit_portfolio_risk(q: str, source_page: str) -> bool:
    explicit = (
        "biggest risk",
        "biggest portfolio risk",
        "main risk",
        "too risky",
        "portfolio risk",
    )
    if any(p in q for p in explicit):
        if any(p in q for p in ("five biggest", "five largest", "top five", "top 5")):
            return False
        return True
    page = str(source_page or "").strip().lower()
    if "health" in page and re.search(r"\brisk\b", q):
        if any(p in q for p in ("five", "top ", "largest", "biggest risks")):
            return False
        return True
    return False


def _is_definitional_coach(q: str) -> bool:
    if not any(
        p in q
        for p in (
            "what is",
            "what does",
            "what are",
            "explain",
            "teach me",
            "help me understand",
        )
    ):
        return False
    analytical_markers = (
        "my portfolio",
        "this portfolio",
        "institutional",
        "critique",
        "argue",
        "endowment",
        "retirement",
        "improve",
    )
    if any(m in q for m in analytical_markers):
        return False
    return True


def _is_open_ended_allocation(q: str) -> bool:
    if _match_analytical_tag(q):
        return True
    return any(
        p in q
        for p in (
            "over the next",
            "10 years",
            "ten years",
            "retirement",
            "institutional",
            "endowment",
        )
    )


def _strong_deterministic_legacy_intent(legacy: str, q: str, source_page: str) -> bool:
    """Legacy intent from phrase lists (not the portfolio_risk default fallback)."""
    if not legacy or legacy == "portfolio_risk":
        return _is_explicit_portfolio_risk(q, source_page)
    if legacy == "investment_coach":
        return _is_definitional_coach(q)
    if legacy == "allocation_recommendation":
        return not _is_open_ended_allocation(q)
    return True


def route_investment_response_mode(
    question: str,
    context: dict[str, Any] | None = None,
) -> ModeRoutingDecision:
    """
    Classify instant AMI questions into deterministic calculation vs analytical synthesis.

    Phase 1: analytical mode avoids generic ``portfolio_risk`` / ``investment_coach`` templates.
    """
    q = _normalize(question)
    ctx = dict(context or {})
    page = str(ctx.get("page") or ctx.get("source_page") or "").strip()

    try:
        from investment_ami_context import detect_investment_send_intent
    except ImportError:
        legacy = ""
    else:
        legacy = detect_investment_send_intent(question, page)

    matched: list[str] = []
    reasons: list[str] = []

    tag_match = _match_analytical_tag(q)
    if tag_match:
        tag, rule = tag_match
        matched.append(rule)
        reasons.append(f"Matched analytical phrase tag `{tag}`.")
        return ModeRoutingDecision(
            response_mode="analytical_synthesis",
            question_tag=tag,
            deterministic_intent=legacy or "portfolio_risk",
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
        )

    cond = _conditional_macro_analytical(q)
    if cond:
        tag, rule = cond
        matched.append(rule)
        reasons.append("Conditional macro/portfolio-change question → analytical synthesis.")
        return ModeRoutingDecision(
            response_mode="analytical_synthesis",
            question_tag=tag,
            deterministic_intent=legacy or "macro_inflation",
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
        )

    objective = _match_deterministic_objective(q)
    if objective:
        intent, rule = objective
        matched.append(rule)
        reasons.append(f"Objective portfolio metric question → deterministic `{intent}`.")
        return ModeRoutingDecision(
            response_mode="deterministic",
            question_tag="",
            deterministic_intent=intent,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
        )

    if legacy and _strong_deterministic_legacy_intent(legacy, q, page):
        matched.append(f"deterministic_legacy:{legacy}")
        reasons.append(f"Legacy intent `{legacy}` is a strong deterministic match.")
        return ModeRoutingDecision(
            response_mode="deterministic",
            question_tag="",
            deterministic_intent=legacy,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
        )

    if legacy == "investment_coach" and not _is_definitional_coach(q):
        matched.append("escalate:misclassified_coach")
        reasons.append("Question matched coach phrases but is not definitional → analytical.")
        return ModeRoutingDecision(
            response_mode="analytical_synthesis",
            question_tag="open_ended",
            deterministic_intent=legacy,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
        )

    if legacy == "allocation_recommendation" and _is_open_ended_allocation(q):
        matched.append("escalate:open_ended_allocation")
        reasons.append("Open-ended improvement/allocation question → analytical.")
        return ModeRoutingDecision(
            response_mode="analytical_synthesis",
            question_tag="improvement",
            deterministic_intent=legacy,
            legacy_intent_hint=legacy,
            matched_rules=tuple(matched),
            reasons=tuple(reasons),
        )

    if legacy == "portfolio_risk" or not legacy:
        if _is_explicit_portfolio_risk(q, page):
            matched.append("explicit_portfolio_risk")
            reasons.append("Explicit portfolio risk metric question → deterministic.")
            return ModeRoutingDecision(
                response_mode="deterministic",
                question_tag="",
                deterministic_intent="portfolio_risk",
                legacy_intent_hint=legacy or "portfolio_risk",
                matched_rules=tuple(matched),
                reasons=tuple(reasons),
            )
        if _has_portfolio_context(ctx):
            matched.append("default:open_ended_with_portfolio")
            reasons.append(
                "Open-ended question with portfolio context; legacy would use generic "
                "`portfolio_risk` fallback → analytical synthesis."
            )
            return ModeRoutingDecision(
                response_mode="analytical_synthesis",
                question_tag="open_ended",
                deterministic_intent="portfolio_risk",
                legacy_intent_hint=legacy or "portfolio_risk",
                matched_rules=tuple(matched),
                reasons=tuple(reasons),
            )

    matched.append(f"deterministic_fallback:{legacy or 'portfolio_risk'}")
    reasons.append("No portfolio context; using deterministic fallback.")
    intent = legacy or "portfolio_risk"
    return ModeRoutingDecision(
        response_mode="deterministic",
        question_tag="",
        deterministic_intent=intent,
        legacy_intent_hint=legacy,
        matched_rules=tuple(matched),
        reasons=tuple(reasons),
    )
