"""Pending sidebar portfolio value helpers (no Streamlit runtime)."""

from components.ui_helpers import PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY


def test_pending_key_constant():
    assert PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY == "pending_sidebar_portfolio_value"
