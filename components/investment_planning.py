"""How much should I invest? — educational cash planning."""

from __future__ import annotations

import streamlit as st

import portfolio_core as core
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode

DISCLAIMER = f"Educational estimate only. {APP_DISCLAIMER}"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def render_how_much_to_invest(settings: dict) -> core.InvestmentPlanResult | None:
    """Beginner-friendly section: how much cash to keep vs. invest."""
    beginner = is_beginner_mode(settings)
    title = "How Much Should I Invest?"
    lead = (
        "Think through how much of your available money should stay in cash vs. go into investments."
        if beginner
        else "Educational cash-flow planning before setting portfolio value."
    )
    st.markdown(f"#### {title}")
    st.caption(lead)

    c1, c2 = st.columns(2)
    with c1:
        total_cash = st.number_input(
            "Total available cash / savings ($)",
            min_value=0,
            max_value=50_000_000,
            value=int(st.session_state.get("plan_total_cash", settings["initial_value"])),
            step=5_000,
            key="plan_total_cash",
        )
        emergency = st.number_input(
            "Emergency fund needed ($)",
            min_value=0,
            max_value=10_000_000,
            value=int(st.session_state.get("plan_emergency", 20_000)),
            step=1_000,
            key="plan_emergency",
        )
        near_term = st.number_input(
            "Money needed in the next 1–2 years ($)",
            min_value=0,
            max_value=10_000_000,
            value=int(st.session_state.get("plan_near_term", 0)),
            step=1_000,
            key="plan_near_term",
        )
    with c2:
        debt = st.number_input(
            "Existing debt or obligations ($)",
            min_value=0,
            max_value=10_000_000,
            value=int(st.session_state.get("plan_debt", 0)),
            step=1_000,
            key="plan_debt",
        )
        expenses = st.number_input(
            "Planned large expenses ($)",
            min_value=0,
            max_value=10_000_000,
            value=int(st.session_state.get("plan_expenses", 0)),
            step=1_000,
            key="plan_expenses",
        )
        monthly = st.number_input(
            "Monthly contribution (optional) ($)",
            min_value=0,
            max_value=500_000,
            value=int(st.session_state.get("plan_monthly", 0)),
            step=100,
            key="plan_monthly",
        )

    r1, r2 = st.columns(2)
    with r1:
        horizon = st.slider(
            "Investment time horizon (years)",
            1,
            40,
            int(st.session_state.get("plan_horizon", 15)),
            key="plan_horizon",
        )
    with r2:
        risk = st.selectbox(
            "Risk tolerance",
            ["Low", "Medium", "High"],
            index=1,
            key="plan_risk",
        )

    plan = core.compute_investment_plan(
        total_available=float(total_cash),
        emergency_fund_needed=float(emergency),
        money_needed_1_2_years=float(near_term),
        existing_debt_obligations=float(debt),
        planned_large_expenses=float(expenses),
        horizon_years=int(horizon),
        risk_tolerance=risk,
        monthly_contribution=float(monthly),
    )
    st.session_state.investment_plan = plan

    st.markdown("##### Model summary")
    for line in plan.summary_lines:
        st.markdown(f"- {line}")
    for note in plan.educational_notes:
        st.caption(note)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Use long-term amount as portfolio value", use_container_width=True, key="apply_long_term"):
            st.session_state.sidebar_portfolio_value = int(plan.long_term_suggested)
            st.success(f"Portfolio value set to {_money(plan.long_term_suggested)} for analysis.")
            st.rerun()
    with b2:
        if st.button("Use full investable amount", use_container_width=True, key="apply_investable"):
            st.session_state.sidebar_portfolio_value = int(plan.amount_potentially_investable)
            st.success(f"Portfolio value set to {_money(plan.amount_potentially_investable)}.")
            st.rerun()
    with b3:
        st.caption("Updates the sidebar **Portfolio value ($)** used for dollar amounts.")

    st.markdown("---")
    st.markdown("##### Compare investment amounts (same mix, educational)")
    st.caption("Shows how projected 1-year value might change if you invested different totals — not a forecast.")
    compare_amounts = st.multiselect(
        "Amounts to compare ($)",
        options=[25_000, 50_000, 100_000, 150_000, 200_000, 500_000],
        default=[50_000, 100_000, 200_000],
        key="plan_compare_amounts",
    )
    if compare_amounts and st.session_state.get("plan_compare_return") is not None:
        ann_ret = float(st.session_state["plan_compare_return"])
        rows = []
        for amt in compare_amounts:
            proj = amt * (1 + ann_ret)
            rows.append(
                {
                    "If you invest": _money(amt),
                    "Est. value in 1 year (model)": _money(proj),
                    "Est. change": _money(proj - amt),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.caption(DISCLAIMER)
    return plan
