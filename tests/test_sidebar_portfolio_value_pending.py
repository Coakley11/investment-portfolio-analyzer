"""Pending sidebar portfolio value must not clobber manual user edits."""

from components.ui_helpers import (
    PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY,
    apply_pending_sidebar_portfolio_value,
)


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_pending_key_constant():
    assert PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY == "pending_sidebar_portfolio_value"


def test_apply_pending_respects_user_edit_flag():
    ss = _FakeSessionState(
        {
            "sidebar_portfolio_value": 250_000,
            PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY: 100_000,
            "_suite_inv_portfolio_value_user_set": True,
        }
    )
    import streamlit as st

    original = st.session_state
    st.session_state = ss
    try:
        apply_pending_sidebar_portfolio_value()
    finally:
        st.session_state = original
    assert ss["sidebar_portfolio_value"] == 250_000
    assert PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY not in ss


def test_apply_pending_sets_value_when_no_user_edit():
    ss = _FakeSessionState(
        {
            "sidebar_portfolio_value": 100_000,
            PENDING_SIDEBAR_PORTFOLIO_VALUE_KEY: 175_000,
        }
    )
    import streamlit as st

    original = st.session_state
    st.session_state = ss
    try:
        apply_pending_sidebar_portfolio_value()
    finally:
        st.session_state = original
    assert ss["sidebar_portfolio_value"] == 175_000
