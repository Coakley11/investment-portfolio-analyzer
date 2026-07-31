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


_CASH_RESERVE_PHRASES: tuple[str, ...] = (
    "how much cash should i keep",
    "how much cash should i hold",
    "emergency fund",
    "cash reserve",
    "keep in cash",
    "hold in cash",
    "liquidity cushion",
)


def is_cash_reserve_question(question: str) -> bool:
    q = str(question or "").strip().lower()
    if not q:
        return False
    return any(p in q for p in _CASH_RESERVE_PHRASES)


_REAL_PORTFOLIO_PHRASES: tuple[str, ...] = (
    "how is my portfolio doing",
    "how is my actual portfolio",
    "how is my real portfolio",
    "actual portfolio performing",
    "real portfolio performing",
    "portfolio performing",
    "driving my portfolio gain",
    "driving my portfolio loss",
    "what is driving my portfolio",
    "what's driving my portfolio",
    "helping or hurting my portfolio",
    "helping or hurting",
    "hurting my portfolio",
    "too concentrated",
    "portfolio too concentrated",
    "should i rebalance my portfolio",
    "rebalance my portfolio",
    "drifted from my target",
    "drift from my target",
    "drifted from target",
    "changes should i consider for my portfolio",
    "changes should i consider for my actual portfolio",
    "consider for my actual portfolio",
    "consider for my portfolio",
    "review my current holdings",
    "analyze my real portfolio",
    "my real portfolio",
    "my actual portfolio",
    "next contribution go based on my current holdings",
    "next contribution go based on my holdings",
    "where should my next contribution go",
    "what should i do with my portfolio now",
)


def is_real_portfolio_question(question: str) -> bool:
    """Transaction-backed portfolio review — not monthly contribution or macro-only prompts."""
    q = str(question or "").strip().lower()
    if not q:
        return False
    if is_monthly_contribution_question(q):
        return False
    if is_invested_amount_question(q):
        return False
    if is_cash_reserve_question(q):
        return False
    analytical_markers = (
        "argue against",
        "critique",
        "investment committee",
        "devil",
        "would have performed",
        "would likely have",
        "primary drivers",
        "each environment",
        "analyze how",
        "why ",
        "why would",
        "improve my portfolio",
        "how would you improve",
        "institutional",
        "endowment",
        "financial crisis",
        "covid-19",
        "2008",
    )
    if any(m in q for m in analytical_markers):
        return False
    if any(
        p in q
        for p in (
            "how is the stock market",
            "how are markets doing",
            "stock market doing",
        )
    ):
        return False
    if "recession" in q and "portfolio" in q:
        if not any(
            m in q
            for m in (
                "my portfolio",
                "my holdings",
                "current holdings",
                "actual portfolio",
                "real portfolio",
                "rebalance",
                "concentrated",
                "doing",
                "performing",
            )
        ):
            return False
    if any(p in q for p in _REAL_PORTFOLIO_PHRASES):
        return True
    if "portfolio" in q and any(
        w in q
        for w in (
            "doing",
            "performing",
            "gains",
            "losses",
            "concentrated",
            "rebalance",
            "drift",
            "holdings",
            "contribution go",
        )
    ):
        if "market" in q and "my portfolio" not in q and "actual portfolio" not in q:
            return False
        return True
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
        return True
    if "investing enough" in q and "invested" not in q:
        return True
    monthly_recommendation_phrases = (
        "what monthly contribution do you recommend",
        "what monthly contribution would you recommend",
        "what monthly investing amount makes sense",
        "what recurring monthly investment would you recommend",
        "how much should i invest each month",
        "how much should i contribute every month",
        "what should my monthly investment be",
        "based on my finances",
        "based on my financial information",
        "given my income and expenses",
    )
    if any(p in q for p in monthly_recommendation_phrases):
        return True
    if "recommend" in q and "monthly" in q and any(
        w in q for w in ("contribution", "invest", "investing", "investment")
    ):
        return True
    if ("income" in q or "expenses" in q or "expense" in q) and "monthly" in q and any(
        w in q for w in ("contribution", "invest", "investing", "investment", "recommend")
    ):
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
