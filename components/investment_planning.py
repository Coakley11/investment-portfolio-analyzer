"""How much should I invest? — educational cash planning."""

from __future__ import annotations

from typing import Any

import streamlit as st

import portfolio_core as core
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode

DISCLAIMER = f"Educational estimate only. {APP_DISCLAIMER}"

# Dict keys from older callers / fallbacks mapped to InvestmentPlanResult fields.
_PLAN_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "total_available": ("total_available", "total_cash"),
    "suggested_emergency_reserve": (
        "suggested_emergency_reserve",
        "emergency_reserve",
        "emergency_fund",
    ),
    "short_term_cash_amount": ("short_term_cash_amount", "short_term_reserve"),
    "debt_reserve": ("debt_reserve", "debt_obligations"),
    "amount_potentially_investable": (
        "amount_potentially_investable",
        "available_to_invest",
    ),
    "long_term_suggested": ("long_term_suggested", "suggested_long_term_amount"),
    "short_term_investable": ("short_term_investable", "suggested_safer_amount"),
    "monthly_contribution": ("monthly_contribution",),
    "summary_lines": ("summary_lines", "summary", "rationale"),
    "educational_notes": ("educational_notes", "explanation", "notes"),
}


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _plan_field(raw: Any, field: str, default: float | list[str]) -> Any:
    """Read a plan field from a dataclass, dict, or object with alternate key names."""
    if isinstance(raw, dict):
        for key in _PLAN_FIELD_ALIASES.get(field, (field,)):
            if key in raw and raw[key] is not None:
                return raw[key]
        return default
    for key in _PLAN_FIELD_ALIASES.get(field, (field,)):
        if hasattr(raw, key):
            val = getattr(raw, key)
            if val is not None:
                return val
    return default


def _normalize_investment_plan(raw: Any) -> core.InvestmentPlanResult:
    """Coerce plan output to InvestmentPlanResult with safe defaults for missing keys."""
    if isinstance(raw, core.InvestmentPlanResult):
        return raw

    summary = _plan_field(raw, "summary_lines", [])
    notes = _plan_field(raw, "educational_notes", [])
    if isinstance(summary, str):
        summary = [summary]
    if isinstance(notes, str):
        notes = [notes]

    total = float(_plan_field(raw, "total_available", 0.0))
    emergency = float(_plan_field(raw, "suggested_emergency_reserve", 0.0))
    short_term = float(_plan_field(raw, "short_term_cash_amount", 0.0))
    debt = float(_plan_field(raw, "debt_reserve", 0.0))
    investable = float(_plan_field(raw, "amount_potentially_investable", max(0.0, total - emergency - short_term - debt)))
    long_term = float(_plan_field(raw, "long_term_suggested", investable))
    short_inv = float(_plan_field(raw, "short_term_investable", max(0.0, investable - long_term)))
    monthly = float(_plan_field(raw, "monthly_contribution", 0.0))

    if not summary:
        summary = [
            f"Total available: {_money(total)}",
            f"Suggested emergency reserve: {_money(emergency)}",
            f"Short-term needs: {_money(short_term)}",
            f"Amount potentially available to invest: {_money(investable)}",
            f"Model suggests for long-term investing: {_money(long_term)}",
        ]
    if not notes:
        notes = ["Educational estimate only — not financial advice."]

    return core.InvestmentPlanResult(
        total_available=total,
        suggested_emergency_reserve=emergency,
        short_term_cash_amount=short_term,
        debt_reserve=debt,
        amount_potentially_investable=investable,
        long_term_suggested=long_term,
        short_term_investable=short_inv,
        monthly_contribution=monthly,
        summary_lines=list(summary),
        educational_notes=list(notes),
    )


def _fallback_investment_plan(
    *,
    total_available: float,
    emergency_fund_needed: float,
    money_needed_1_2_years: float,
    existing_debt_obligations: float,
    planned_large_expenses: float,
    horizon_years: int,
    risk_tolerance: str,
    monthly_contribution: float,
) -> core.InvestmentPlanResult:
    """Local fallback when portfolio_core.compute_investment_plan is unavailable."""
    emergency = max(0.0, emergency_fund_needed)
    short_term = max(0.0, money_needed_1_2_years + planned_large_expenses)
    debt = max(0.0, existing_debt_obligations)
    total = max(0.0, total_available)
    investable = max(0.0, total - emergency - short_term - debt)

    if horizon_years <= 2:
        long_pct = 0.30
    elif horizon_years <= 5:
        long_pct = 0.60
    else:
        long_pct = 0.85
    risk_adj = {"Low": -0.12, "Medium": 0.0, "High": 0.05}.get(risk_tolerance, 0.0)
    long_pct = min(0.92, max(0.20, long_pct + risk_adj))
    long_term = investable * long_pct
    short_inv = investable - long_term

    summary = [
        f"Total available: {_money(total)}",
        f"Suggested emergency reserve: {_money(emergency)}",
        f"Short-term needs (1–2 years + planned expenses): {_money(short_term)}",
        f"Debt / obligations set aside: {_money(debt)}",
        f"Amount potentially available to invest: {_money(investable)}",
        f"Model suggests for long-term investing: {_money(long_term)}",
        f"Model suggests for shorter-term / safer sleeve: {_money(short_inv)}",
    ]
    if monthly_contribution > 0:
        summary.append(f"Optional monthly contribution noted: {_money(monthly_contribution)}/month")

    return core.InvestmentPlanResult(
        total_available=total,
        suggested_emergency_reserve=emergency,
        short_term_cash_amount=short_term,
        debt_reserve=debt,
        amount_potentially_investable=investable,
        long_term_suggested=long_term,
        short_term_investable=short_inv,
        monthly_contribution=float(monthly_contribution),
        summary_lines=summary,
        educational_notes=[
            "Simplified on-page estimate (core planner unavailable).",
            "Consider keeping short-term needs in cash or T-bill style assets.",
            "Educational purposes only — not financial advice.",
        ],
    )


def _compute_investment_plan_safe(
    *,
    total_available: float,
    emergency_fund_needed: float,
    money_needed_1_2_years: float,
    existing_debt_obligations: float,
    planned_large_expenses: float,
    horizon_years: int,
    risk_tolerance: str,
    monthly_contribution: float,
) -> core.InvestmentPlanResult:
    """Call portfolio_core.compute_investment_plan with defensive fallbacks."""
    kwargs = {
        "total_available": total_available,
        "emergency_fund_needed": emergency_fund_needed,
        "money_needed_1_2_years": money_needed_1_2_years,
        "existing_debt_obligations": existing_debt_obligations,
        "planned_large_expenses": planned_large_expenses,
        "horizon_years": horizon_years,
        "risk_tolerance": risk_tolerance,
        "monthly_contribution": monthly_contribution,
    }
    compute_fn = getattr(core, "compute_investment_plan", None)
    if callable(compute_fn):
        try:
            return _normalize_investment_plan(compute_fn(**kwargs))
        except Exception as exc:
            st.warning(
                f"Could not run the full investment plan model ({exc}). "
                "Showing a simplified estimate instead."
            )
    else:
        st.warning(
            "Investment plan helper is missing from portfolio_core; "
            "showing a simplified on-page estimate."
        )
    return _fallback_investment_plan(**kwargs)


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

    plan = _compute_investment_plan_safe(
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

    summary_lines = _plan_field(plan, "summary_lines", [])
    educational_notes = _plan_field(plan, "educational_notes", [])
    long_term_suggested = float(_plan_field(plan, "long_term_suggested", 0.0))
    amount_investable = float(_plan_field(plan, "amount_potentially_investable", 0.0))

    st.markdown("##### Model summary")
    for line in summary_lines or []:
        st.markdown(f"- {line}")
    for note in educational_notes or []:
        st.caption(note)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Use long-term amount as portfolio value", use_container_width=True, key="apply_long_term"):
            st.session_state.sidebar_portfolio_value = int(long_term_suggested)
            st.success(f"Portfolio value set to {_money(long_term_suggested)} for analysis.")
            st.rerun()
    with b2:
        if st.button("Use full investable amount", use_container_width=True, key="apply_investable"):
            st.session_state.sidebar_portfolio_value = int(amount_investable)
            st.success(f"Portfolio value set to {_money(amount_investable)}.")
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
