"""Shared presentation helpers for instant engines."""

from __future__ import annotations


def default_educational_risk_notes(beginner: bool) -> str:
    if beginner:
        return (
            "This is educational analysis based on your entered weights — not personal financial advice. "
            "Past performance and simple concentration checks do not predict future results."
        )
    return (
        "Educational portfolio analysis only; not investment advice. "
        "Metrics are snapshot-based from session weights and historical health metrics where available."
    )
