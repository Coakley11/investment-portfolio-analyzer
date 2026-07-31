"""Classify decision-support question topics for routing and rule matching."""

from __future__ import annotations

INVESTED_AMOUNT_PHRASES: tuple[str, ...] = (
    "invested appropriate",
    "amount invested",
    "amount i have invested",
    "amount i currently have invested",
    "currently have invested",
    "underinvested",
    "overinvested",
    "holding too much cash",
    "too much cash relative",
    "should more of my",
    "available assets be invested",
    "net worth",
    "invested amount",
    "appropriate for my situation",
    "appropriate for my",
    "is my current invested",
    "how much should be invested",
    "invested vs",
    "portfolio investment reasonable",
    "investment reasonable",
    "reasonable given my financial",
    "financial situation",
    "investing a reasonable amount",
    "reasonable amount",
    "investment level make sense",
    "current investment level",
    "portfolio too large",
    "portfolio too small",
    "too large or too small",
    "make sense for my situation",
    "does my current investment",
    "is my portfolio investment",
    "investment appropriate",
    "invested level",
)


def is_invested_amount_question(question: str) -> bool:
    q = str(question or "").strip().lower()
    if not q:
        return False
    if any(p in q for p in INVESTED_AMOUNT_PHRASES):
        return True
    if "invested" in q and any(w in q for w in ("appropriate", "enough", "too little", "too much", "reasonable")):
        return True
    if "portfolio" in q and "invest" in q and any(
        w in q for w in ("reasonable", "appropriate", "too much", "too little", "make sense", "large", "small")
    ):
        return True
    if "investment" in q and any(w in q for w in ("reasonable", "appropriate", "make sense")):
        if any(w in q for w in ("amount", "level", "portfolio", "situation", "financial")):
            return True
    return False


def is_monthly_contribution_question(question: str) -> bool:
    q = str(question or "").strip().lower()
    if is_invested_amount_question(q):
        return False
    return any(
        p in q
        for p in (
            "how much should i invest this month",
            "invest this month",
            "investing enough",
            "increase my monthly",
            "decrease my monthly",
            "monthly contribution",
            "should i increase my monthly",
            "should i decrease my monthly",
        )
    )
