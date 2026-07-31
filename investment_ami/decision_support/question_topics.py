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
    if "contribute" in q and "month" in q:
        return False
    if "monthly" in q and any(w in q for w in ("contribution", "contribute", "invest", "investing")):
        return False
    return False


def is_monthly_contribution_question(question: str) -> bool:
    q = str(question or "").strip().lower()
    if not q:
        return False
    if any(
        p in q
        for p in (
            "expenses increased",
            "expenses decreased",
            "expense increased",
            "expense decreased",
            "how should that affect my investing",
        )
    ):
        return False
    if is_invested_amount_question(q) and not any(
        w in q for w in ("each month", "every month", "monthly", "per month", "contribute", "contribution")
    ):
        return False
    monthly_cues = (
        "each month",
        "every month",
        "per month",
        "monthly contribution",
        "monthly investment",
        "contribute each month",
        "contribute every month",
        "how much should i contribute",
        "what monthly contribution",
        "monthly contribution goal",
        "invest enough each month",
        "investing enough each month",
        "invest more every month",
        "should i invest more every month",
    )
    if any(p in q for p in monthly_cues):
        return True
    if "contribute" in q and "month" in q:
        return True
    if "monthly" in q and any(w in q for w in ("contribution", "invest", "investing", "investment")):
        if "financial situation" in q or "each month" in q or "every month" in q:
            return True
        if "expense" not in q:
            return True
    if "investing enough" in q and "invested" not in q:
        return True
    return any(
        p in q
        for p in (
            "how much should i invest this month",
            "invest this month",
            "investing enough",
            "increase my monthly",
            "decrease my monthly",
            "should i increase my monthly",
            "should i decrease my monthly",
        )
    )
