"""Import smoke tests for allocation dollar helper (Streamlit Cloud hotfix)."""


def test_streamlit_app_imports_ui_helpers_holding_dollar():
    from components.ui_helpers import format_money_cents, holding_dollar_from_weight

    assert holding_dollar_from_weight(43_881, 60) == 26_328.60
    assert format_money_cents(26_328.60) == "$26,328.60"


def test_investment_planning_reexports_holding_dollar():
    from components.investment_planning import holding_dollar_from_weight

    assert holding_dollar_from_weight(100_000, 25) == 25_000.0
