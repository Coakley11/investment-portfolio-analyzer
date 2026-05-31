"""Plain-English translations for technical portfolio terms."""

from __future__ import annotations

# Order matters — longer phrases first when applying replacements.
BEGINNER_PHRASE_MAP: list[tuple[str, str]] = [
    (
        "Portfolio volatility is elevated",
        "Your portfolio may move up and down more than a beginner investor might expect",
    ),
    (
        "Drawdown risk is high",
        "This portfolio has had large drops in the past, so you should be prepared for possible losses before recovery",
    ),
    (
        "Concentration risk is elevated",
        "Too much money may be in one area, so one bad move could hurt the whole portfolio",
    ),
    (
        "concentration risk",
        "having too much in one investment",
    ),
    (
        "Sharpe ratio",
        "risk/reward score",
    ),
    (
        "Sortino ratio",
        "downside risk score",
    ),
    (
        "Max drawdown",
        "worst historical drop",
    ),
    (
        "volatility",
        "how much your portfolio tends to move up and down",
    ),
    (
        "drawdown",
        "a drop from a previous high",
    ),
    (
        "beta",
        "how much you move compared to the broad market",
    ),
    (
        "macro regime",
        "the broad economic environment",
    ),
    (
        "efficient frontier",
        "best risk vs. return mixes the model can find",
    ),
]


def translate_for_beginner(text: str) -> str:
    """Return a beginner-friendly version of technical commentary."""
    out = text
    for technical, plain in BEGINNER_PHRASE_MAP:
        if technical in out:
            out = out.replace(technical, plain)
    return out
