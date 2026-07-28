"""Shared behavioral-finance / risk-reduction copy (wording frozen)."""

from __future__ import annotations

BEGINNER_RISK_REDUCTION_HEADLINE = "**Ideas to reduce risk (tradeoffs, not advice):**"

BEGINNER_RISK_REDUCTION_BULLETS: tuple[str, ...] = (
    "- **Add bonds or balanced funds** to cushion stock drops.",
    "- **Trim your largest position** if one fund dominates the portfolio.",
    "- **Reduce tech/growth overlap** if QQQ/VGT-style funds stack together.",
    "- **Rebalance toward targets** instead of letting winners run unchecked.",
)

ADVANCED_RISK_REDUCTION_HEADLINE = "**Risk-reduction levers:**"

ADVANCED_RISK_REDUCTION_BULLETS: tuple[str, ...] = (
    "- Increase defensive allocation (IGSB/BND-style) to lower portfolio beta.",
    "- Cut top-weight concentration and correlated growth ETFs.",
    "- Tighten rebalance bands to prevent drift into higher-volatility weights.",
)


def format_beginner_concentration_lever(ticker: str, weight_pct: float) -> str:
    return f"- Start with **{ticker}** (**{weight_pct:.1f}%**) — largest concentration lever."


def format_advanced_volatility_lever(volatility: str) -> str:
    return (
        f"- Current historical vol **{volatility}** — simulate impact of +10% bond sleeve in full AMI analysis."
    )


def build_beginner_risk_reduction_lines(
    *,
    top_ticker: str | None = None,
    top_pct: float | None = None,
) -> list[str]:
    lines = [BEGINNER_RISK_REDUCTION_HEADLINE, *BEGINNER_RISK_REDUCTION_BULLETS]
    if top_ticker and top_pct is not None and top_pct >= 25:
        lines.append(format_beginner_concentration_lever(top_ticker, top_pct))
    return lines


def build_advanced_risk_reduction_lines(*, volatility: str = "") -> list[str]:
    lines = [ADVANCED_RISK_REDUCTION_HEADLINE, *ADVANCED_RISK_REDUCTION_BULLETS]
    vol = str(volatility or "").strip()
    if vol:
        lines.append(format_advanced_volatility_lever(vol))
    return lines
