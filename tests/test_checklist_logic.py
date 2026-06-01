"""Checklist completion rules (no Streamlit runtime)."""

from components.beginner_navigation import _holdings_fingerprint

import pandas as pd
import portfolio_core as core


def test_holdings_fingerprint_detects_custom_portfolio():
    default = pd.DataFrame(core.DEFAULT_HOLDINGS)
    custom = default.copy()
    custom.loc[0, "Weight (%)"] = 50.0
    assert _holdings_fingerprint(default) == _holdings_fingerprint(default)
    assert _holdings_fingerprint(custom) != _holdings_fingerprint(default)


def test_preset_differs_from_default():
    aggressive = pd.DataFrame(core.PORTFOLIO_PRESETS["Aggressive"])
    default = pd.DataFrame(core.DEFAULT_HOLDINGS)
    assert _holdings_fingerprint(aggressive) != _holdings_fingerprint(default)
