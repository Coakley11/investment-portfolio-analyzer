"""How much should I invest? — educational cash planning."""

from __future__ import annotations

from typing import Any

import hashlib
import json

import numpy as np
import streamlit as st

import portfolio_core as core
from components.ui_helpers import (
    APP_DISCLAIMER,
    HOW_MUCH_PLAN_SCROLL_ANCHOR,
    format_money_cents,
    holding_dollar_from_weight,
    is_beginner_mode,
    render_how_much_plan_scroll_anchor,
    request_sidebar_portfolio_value,
)

DISCLAIMER = f"Educational estimate only. {APP_DISCLAIMER}"

# User-facing label for short_term_investable (internal field name unchanged).
CONSERVATIVE_ALLOCATION_LABEL = "Conservative / short-term reserve"
CONSERVATIVE_ALLOCATION_HELP = (
    "Cash the model suggests keeping in lower-risk or short-horizon holdings "
    "(not the same as your 1–2 year spending reserve above). "
    "Often held in bonds, T-bills, or cash-like assets until you deploy it."
)

CURRENT_MONTHLY_INVESTMENT_LABEL = "Current monthly investment (optional)"
CURRENT_MONTHLY_INVESTMENT_HELP = (
    "If you already invest money regularly each month, enter that current amount here. "
    "This is not the recommended amount. AMI can later compare your current contribution "
    "with a suggested contribution based on income, expenses, reserves, and goals. "
    "Leave blank if unknown, or enter $0 if you currently make no regular monthly investments."
)
PLAN_MONTHLY_PROVIDED_KEY = "plan_monthly_provided"
HOW_MUCH_PLAN_SCROLL_ANCHOR = "how-much-should-i-invest"
BEGINNER_PLAN_INPUT_TABS = (
    "💰 How Much to Invest",
    "💼 Dollar Amounts",
    "📘 Implementation Guide",
)
JOB_STABILITY_OPTIONS = ("", "Stable", "Moderate", "Uncertain")
PLAN_CASHFLOW_SESSION_KEYS = (
    "monthly_income",
    "monthly_expenses",
    "job_stability",
    "plan_employer_match",
    "plan_retirement_goal",
)
PLAN_COMPARE_AMOUNTS_KEY = "plan_compare_amounts_list"
INVESTMENT_PLAN_PERSIST_SCHEMA = "investment-plan-v1"
PLAN_RISK_OPTIONS = ("Low", "Medium", "High")
# Canonical session keys shared by beginner (`invest_plan_beginner_*`) and advanced widgets.
PLAN_CANONICAL_SCALAR_KEYS = (
    "plan_total_cash",
    "plan_emergency",
    "plan_near_term",
    "plan_debt",
    "plan_expenses",
    "plan_horizon",
)
INVESTMENT_PLAN_RESTORE_GEN_KEY = "_investment_plan_restore_gen"

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
    "money_needed_1_2_years": ("money_needed_1_2_years",),
    "planned_large_expenses": ("planned_large_expenses",),
    "long_term_allocation_pct": ("long_term_allocation_pct",),
    "safer_sleeve_allocation_pct": ("safer_sleeve_allocation_pct",),
}


def coerce_plan_integer(value: Any, fallback: int) -> int:
    """Safe int for plan widgets — cloud restore may leave None, '', or formatted strings."""
    fb = int(fallback)
    if value is None:
        return fb
    if isinstance(value, bool):
        return fb
    if isinstance(value, int):
        return max(0, int(value))
    if isinstance(value, float):
        if np.isnan(value):
            return fb
        return max(0, int(value))
    text = str(value).strip()
    if not text:
        return fb
    cleaned = text.replace(",", "").replace("$", "").strip()
    try:
        return max(0, int(float(cleaned)))
    except (TypeError, ValueError):
        return fb


def parse_current_monthly_investment_input(raw: Any) -> tuple[float | None, bool, str | None]:
    """
    Parse the optional current monthly investment field.

    Returns (amount, user_provided, error_message).
    Blank → (None, False, None). Valid ``0`` → (0.0, True, None).
    Invalid input → (None, False, error_message) — caller should keep prior session values.
    """
    text = str(raw or "").strip()
    if not text:
        return None, False, None
    cleaned = text.replace(",", "").replace("$", "").replace(" ", "")
    if not cleaned:
        return None, False, None
    try:
        amount = float(cleaned)
    except (TypeError, ValueError):
        return (
            None,
            False,
            "Enter a valid dollar amount, leave blank if unknown, or enter 0 if you invest nothing monthly.",
        )
    if amount < 0:
        return None, False, "Current monthly investment cannot be negative. Enter 0 or a positive amount."
    if amount > 500_000:
        return None, False, "Enter an amount up to $500,000/month, or leave blank if unknown."
    return amount, True, None


def format_current_monthly_investment_for_widget(session_state: Any) -> str:
    if not session_state.get(PLAN_MONTHLY_PROVIDED_KEY):
        return ""
    return str(int(coerce_plan_integer(session_state.get("plan_monthly"), 0)))


def current_monthly_investment_for_plan(session_state: Any) -> float | None:
    """Amount the user entered, or None if left blank (unknown)."""
    if not session_state.get(PLAN_MONTHLY_PROVIDED_KEY):
        return None
    return float(coerce_plan_integer(session_state.get("plan_monthly"), 0))


def _current_monthly_investment_summary_line(amount: float | None) -> str | None:
    if amount is None:
        return None
    if amount <= 0:
        return (
            "Current monthly investment noted: $0/month "
            "(no regular monthly investments entered; not a recommendation)"
        )
    return f"Current monthly investment noted: {_money(amount)}/month (not a recommendation)"


def _money(x: float) -> str:
    return f"${round(float(x)):,.0f}"


def _money_exact(x: float) -> str:
    return format_money_cents(float(x))


def normalize_compare_amounts(raw: list[Any] | None) -> list[float]:
    """Positive, deduplicated compare amounts (2 decimal precision)."""
    seen: set[float] = set()
    out: list[float] = []
    for item in raw or []:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            val = float(item)
        else:
            text = str(item or "").strip().replace(",", "").replace("$", "")
            if not text:
                continue
            try:
                val = float(text)
            except ValueError:
                continue
        if val <= 0 or np.isnan(val):
            continue
        key = round(val, 2)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return sorted(out)


def build_investable_waterfall_markdown(
    *,
    total: float,
    emergency: float,
    near_term: float,
    planned_expenses: float,
    debt: float,
    investable: float,
) -> str:
    """Show subtraction steps for maximum investable amount."""
    t = round(total)
    e = round(emergency)
    n = round(near_term)
    p = round(planned_expenses)
    d = round(debt)
    inv = round(investable)
    lines = [
        "**Available to invest (waterfall)**",
        "",
        f"- Total available cash: {_money(t)}",
        f"- Emergency fund reserved: − {_money(e)}",
        f"- Money needed in the next 1–2 years: − {_money(n)}",
        f"- Existing debt / obligations: − {_money(d)}",
        f"- Planned large expenses: − {_money(p)}",
        "",
        f"**Maximum potentially available to invest** = {_money(t)} − {_money(e)} − {_money(n)} − {_money(d)} − {_money(p)} = **{_money(inv)}**",
    ]
    return "\n".join(lines)


def build_sleeve_split_markdown(
    *,
    investable: float,
    long_term: float,
    safer: float,
    long_pct: float,
    safer_pct: float,
) -> str:
    inv = round(investable)
    lt = round(long_term)
    sf = round(safer)
    lp = long_pct * 100.0
    sp = safer_pct * 100.0
    return (
        f"**Sleeve split (applied to {_money(inv)} investable)**\n\n"
        f"- Long-term investment allocation: **{lp:.0f}%** → {_money(lt)} "
        f"(_{_money_exact(inv * long_pct)} before rounding_)\n"
        f"- {CONSERVATIVE_ALLOCATION_LABEL}: **{sp:.0f}%** → {_money(sf)} "
        f"(_remainder after long-term rounding; totals {_money(lt + sf)}_)"
    )


def build_allocation_assumptions_markdown(
    *,
    horizon_years: int,
    risk_tolerance: str,
    long_pct: float,
    safer_pct: float,
) -> str:
    lp = long_pct * 100.0
    sp = safer_pct * 100.0
    return (
        "**Recommendation assumptions**\n\n"
        f"- Investment horizon: **{int(horizon_years)} years**\n"
        f"- Risk tolerance: **{risk_tolerance}**\n"
        f"- Current allocation rule: **{lp:.0f}% long-term** / **{sp:.0f}% conservative** "
        f"(applied to the maximum investable amount only)"
    )


def _render_applied_portfolio_value_banner(*, key_prefix: str) -> None:
    """Persistent status for portfolio value driving allocation tables."""
    applied = st.session_state.get("investment_plan_applied_portfolio_value")
    source = str(st.session_state.get("investment_plan_applied_source") or "")
    if applied is None:
        sidebar_pv = st.session_state.get("sidebar_portfolio_value")
        if sidebar_pv is not None:
            st.caption(
                f"Portfolio value in the sidebar is **{_money(float(sidebar_pv))}**. "
                "Use **Step 4** below to apply a recommended amount from this plan."
            )
        return
    src_note = ""
    if source == "long_term":
        src_note = " (recommended long-term amount)"
    elif source == "max_investable":
        src_note = " (maximum investable amount)"
    st.markdown(
        f"""
<div style="background:rgba(46,204,113,0.12);border:1px solid rgba(46,204,113,0.45);
border-radius:8px;padding:0.75rem 1rem;margin:0.5rem 0 1rem 0;">
<strong>Current portfolio value:</strong> {_money(float(applied))} ✓{src_note}<br/>
<span style="font-size:0.85rem;color:#94a3b8;">This value drives <em>Dollar amounts (based on portfolio value)</em> below.</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _apply_plan_portfolio_value(amount: float, *, source: str) -> None:
    from planning_portfolio_value import set_applied_plan_portfolio_value

    set_applied_plan_portfolio_value(st.session_state, amount, source=source)
    request_sidebar_portfolio_value(amount, force=True, source=source)
    st.session_state.capital_deployed = True
    maybe_autosave_investment_plan(st, source="plan_apply_portfolio_value")
    try:
        from investment_persistent_state import notify_global_settings_change

        notify_global_settings_change(st, source="plan_apply_portfolio_value")
    except ImportError:
        pass


def _render_portfolio_value_buttons(
    *,
    key_prefix: str,
    amount_investable: float,
    long_term_suggested: float,
    beginner: bool,
) -> None:
    inv = round(amount_investable)
    lt = round(long_term_suggested)
    st.markdown("##### Step 4 — Apply to portfolio value")
    st.caption(
        "Choose which dollar total powers **Portfolio value** in the sidebar and the allocation table. "
        "This is **not** your total cash from Step 1."
    )
    st.markdown("**Recommended**")
    primary_label = f"Use Recommended Long-Term Amount ({_money(lt)}) as Portfolio Value"
    if st.button(
        primary_label,
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_apply_long_term_primary",
    ):
        _apply_plan_portfolio_value(lt, source="long_term")
        st.rerun()
    st.caption(
        "Best default for long-horizon portfolio analysis — uses the long-term portion from Step 3."
    )
    st.markdown("**Alternative**")
    secondary_label = f"Use Maximum Investable Amount ({_money(inv)}) as Portfolio Value"
    if st.button(
        secondary_label,
        use_container_width=True,
        key=f"{key_prefix}_apply_investable_secondary",
    ):
        _apply_plan_portfolio_value(inv, source="max_investable")
        st.rerun()
    st.caption(
        "Uses the full investable amount before the long-term / conservative split (Step 3)."
    )


def _render_compare_investment_amounts(
    *,
    key_prefix: str,
    plan: core.InvestmentPlanResult,
    beginner: bool,
) -> None:
    list_key = f"{key_prefix}_compare_amounts_list"
    seed_plan_compare_list_from_canonical(st.session_state, list_key=list_key)
    if list_key not in st.session_state or not isinstance(st.session_state.get(list_key), list):
        st.session_state[list_key] = []

    inv = round(float(plan.amount_potentially_investable))
    lt = round(float(plan.long_term_suggested))
    st.caption(
        "Optional: compare a few dollar amounts using a simple one-year model projection. "
        "Add amounts below; remove any you no longer need."
    )

    add_col, quick_col = st.columns([3, 2])
    with add_col:
        new_amt = st.number_input(
            "Amount to compare ($)",
            min_value=0,
            max_value=50_000_000,
            value=10_000,
            step=1_000,
            key=f"{key_prefix}_compare_new_amount",
            help="Enter a dollar amount, then click Add to comparison.",
        )
        if st.button("Add to comparison", type="primary", key=f"{key_prefix}_compare_add"):
            if new_amt <= 0:
                st.warning("Enter an amount greater than zero.")
            else:
                st.session_state[list_key] = normalize_compare_amounts(
                    list(st.session_state[list_key]) + [new_amt]
                )
                sync_plan_compare_amounts_to_canonical(st.session_state, list_key=list_key)
                maybe_autosave_investment_plan(st, source="plan_compare_add")
                st.rerun()
    with quick_col:
        st.markdown("**Quick add**")
        if st.button(f"Max investable ({_money(inv)})", key=f"{key_prefix}_compare_add_inv"):
            st.session_state[list_key] = normalize_compare_amounts(list(st.session_state[list_key]) + [inv])
            sync_plan_compare_amounts_to_canonical(st.session_state, list_key=list_key)
            maybe_autosave_investment_plan(st, source="plan_compare_quick")
            st.rerun()
        if st.button(f"Long-term rec. ({_money(lt)})", key=f"{key_prefix}_compare_add_lt"):
            st.session_state[list_key] = normalize_compare_amounts(list(st.session_state[list_key]) + [lt])
            sync_plan_compare_amounts_to_canonical(st.session_state, list_key=list_key)
            maybe_autosave_investment_plan(st, source="plan_compare_quick")
            st.rerun()

    amounts = normalize_compare_amounts(st.session_state.get(list_key))
    st.session_state[list_key] = amounts
    sync_plan_compare_amounts_to_canonical(st.session_state, list_key=list_key)

    if not amounts:
        st.info("No comparison amounts yet. Add one above or use a quick-add shortcut.")
        return

    st.markdown("**Your comparison amounts**")
    for idx, amt in enumerate(amounts):
        row_left, row_right = st.columns([5, 1])
        with row_left:
            st.markdown(f"- **{_money(amt)}**")
        with row_right:
            if st.button("Remove", key=f"{key_prefix}_compare_rm_{idx}", use_container_width=True):
                st.session_state[list_key] = [a for i, a in enumerate(amounts) if i != idx]
                sync_plan_compare_amounts_to_canonical(st.session_state, list_key=list_key)
                maybe_autosave_investment_plan(st, source="plan_compare_remove")
                st.rerun()

    if st.button("Clear all comparison amounts", key=f"{key_prefix}_compare_clear"):
        st.session_state[list_key] = []
        sync_plan_compare_amounts_to_canonical(st.session_state, list_key=list_key)
        maybe_autosave_investment_plan(st, source="plan_compare_clear")
        st.rerun()

    compare_amounts = normalize_compare_amounts(st.session_state.get(list_key))
    ann_ret = resolve_plan_compare_annual_return(st.session_state)
    if compare_amounts and ann_ret is not None:
        st.markdown("**Projected change in one year (model)**")
        rows = []
        for amt in compare_amounts:
            proj = amt * (1 + ann_ret)
            rows.append(
                {
                    "If you invest": _money(amt),
                    "Est. value in 1 year": _money(proj),
                    "Est. change": _money(proj - amt),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
    elif compare_amounts:
        st.caption("Run portfolio analysis to enable projected comparison rows.")


def _render_plan_results(
    plan: core.InvestmentPlanResult,
    *,
    key_prefix: str,
    beginner: bool,
    total_cash: float,
    emergency: float,
    horizon_years: int,
    risk_tolerance: str,
) -> None:
    long_term_suggested = float(_plan_field(plan, "long_term_suggested", 0.0))
    amount_investable = float(_plan_field(plan, "amount_potentially_investable", 0.0))
    safer = float(_plan_field(plan, "short_term_investable", 0.0))
    long_pct = float(_plan_field(plan, "long_term_allocation_pct", 0.0))
    safer_pct = float(_plan_field(plan, "safer_sleeve_allocation_pct", 0.0))
    if safer_pct <= 0 and long_pct > 0:
        safer_pct = 1.0 - long_pct
    near_term = float(_plan_field(plan, "money_needed_1_2_years", 0.0))
    planned_exp = float(_plan_field(plan, "planned_large_expenses", 0.0))
    debt = float(_plan_field(plan, "debt_reserve", 0.0))
    protected = float(emergency) + near_term + planned_exp + debt

    st.markdown("##### Your plan at a glance")
    st.caption(
        "Follow the steps: cash on hand → protected amounts → investable total → "
        "long-term vs conservative split → portfolio value for allocation tables."
    )
    _render_applied_portfolio_value_banner(key_prefix=key_prefix)

    st.markdown("##### Step 1 — Total cash and protected amounts")
    st.markdown(
        build_investable_waterfall_markdown(
            total=float(total_cash),
            emergency=float(emergency),
            near_term=near_term,
            planned_expenses=planned_exp,
            debt=debt,
            investable=amount_investable,
        )
    )

    st.markdown("##### Step 2 — Maximum investable amount")
    st.markdown(
        f"After reserves, **{_money(amount_investable)}** is the maximum that could be invested "
        f"while keeping **{_money(protected)}** protected (not double-counted in the split below)."
    )

    st.markdown("##### Step 3 — Recommended split of investable cash")
    if long_pct > 0:
        st.markdown(
            build_allocation_assumptions_markdown(
                horizon_years=horizon_years,
                risk_tolerance=risk_tolerance,
                long_pct=long_pct,
                safer_pct=safer_pct,
            )
        )
        st.markdown(
            build_sleeve_split_markdown(
                investable=amount_investable,
                long_term=long_term_suggested,
                safer=safer,
                long_pct=long_pct,
                safer_pct=safer_pct,
            )
        )
    st.markdown(
        f"**{CONSERVATIVE_ALLOCATION_LABEL}** — {CONSERVATIVE_ALLOCATION_HELP}"
    )

    st.markdown("##### Summary")
    st.markdown(
        "| Step | Concept | Amount |\n|------|--------|--------|\n"
        f"| 1 | Total available cash (not portfolio value) | **{_money(total_cash)}** |\n"
        f"| 1 | Protected cash & obligations | **{_money(protected)}** |\n"
        f"| 2 | Maximum potentially available to invest | **{_money(amount_investable)}** |\n"
        f"| 3 | Recommended long-term investment amount | **{_money(long_term_suggested)}** |\n"
        f"| 3 | Recommended {CONSERVATIVE_ALLOCATION_LABEL.lower()} | **{_money(safer)}** |"
    )

    if beginner:
        m1, m2, m3 = st.columns(3)
        m1.metric("Step 1: Total cash", _money(float(total_cash)))
        m2.metric("Step 2: Max investable", _money(amount_investable))
        m3.metric("Step 3: Long-term rec.", _money(long_term_suggested))

    notes = _plan_field(plan, "educational_notes", [])
    if notes:
        with st.expander("How the long-term / conservative split works", expanded=False):
            for note in notes:
                st.markdown(f"- {note}")

    _render_portfolio_value_buttons(
        key_prefix=key_prefix,
        amount_investable=amount_investable,
        long_term_suggested=long_term_suggested,
        beginner=beginner,
    )
    _render_applied_portfolio_value_banner(key_prefix=key_prefix)
    with st.expander("Compare investment amounts (optional)", expanded=not beginner):
        _render_compare_investment_amounts(key_prefix=key_prefix, plan=plan, beginner=beginner)


def plan_integer_from_session(key: str, fallback: int) -> int:
    """Read a plan scalar from session state; invalid stored values fall back."""
    if key not in st.session_state:
        return coerce_plan_integer(fallback, fallback)
    return coerce_plan_integer(st.session_state.get(key), fallback)


def sanitize_plan_session_integers(session_state: Any, defaults: dict[str, Any] | None = None) -> None:
    """Normalize persisted plan_* keys so widgets never see None or junk."""
    keys = (
        "plan_total_cash",
        "plan_emergency",
        "plan_near_term",
        "plan_debt",
        "plan_expenses",
        "plan_monthly",
        "plan_horizon",
    )
    for key in keys:
        fb = defaults.get(key) if defaults else None
        if fb is None:
            fb = 0 if key != "plan_emergency" else 20_000
            if key == "plan_horizon":
                fb = 15
        if key not in session_state:
            continue
        session_state[key] = coerce_plan_integer(session_state.get(key), int(fb))
    if "plan_risk" in session_state:
        rv = str(session_state.get("plan_risk") or "Medium").strip()
        if rv not in PLAN_RISK_OPTIONS:
            rv = "Medium"
        session_state["plan_risk"] = rv


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
        money_needed_1_2_years=float(_plan_field(raw, "money_needed_1_2_years", 0.0)),
        planned_large_expenses=float(_plan_field(raw, "planned_large_expenses", 0.0)),
        long_term_allocation_pct=float(_plan_field(raw, "long_term_allocation_pct", 0.0)),
        safer_sleeve_allocation_pct=float(_plan_field(raw, "safer_sleeve_allocation_pct", 0.0)),
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
    monthly_contribution: float | None,
) -> core.InvestmentPlanResult:
    """Local fallback when portfolio_core.compute_investment_plan is unavailable."""
    emergency = max(0.0, emergency_fund_needed)
    near_term = max(0.0, money_needed_1_2_years)
    planned_exp = max(0.0, planned_large_expenses)
    short_term = near_term + planned_exp
    debt = max(0.0, existing_debt_obligations)
    total = max(0.0, total_available)
    investable = max(0.0, total - emergency - short_term - debt)

    long_pct_fn = getattr(core, "investment_plan_long_term_pct", None)
    if callable(long_pct_fn):
        long_pct = float(long_pct_fn(horizon_years=int(horizon_years), risk_tolerance=str(risk_tolerance)))
    else:
        long_pct = 0.85
    safer_pct = 1.0 - long_pct
    long_term = round(investable * long_pct)
    short_inv = max(0.0, round(investable) - long_term)

    summary = [
        f"Maximum potentially available to invest: {_money(investable)}",
        f"Long-term sleeve ({long_pct * 100:.0f}%): {_money(long_term)}",
        f"Safer sleeve ({safer_pct * 100:.0f}%): {_money(short_inv)}",
    ]
    line = _current_monthly_investment_summary_line(monthly_contribution)
    if line:
        summary.append(line)

    stored_monthly = float(monthly_contribution) if monthly_contribution is not None else 0.0

    return core.InvestmentPlanResult(
        total_available=total,
        suggested_emergency_reserve=emergency,
        short_term_cash_amount=short_term,
        debt_reserve=debt,
        amount_potentially_investable=investable,
        long_term_suggested=float(long_term),
        short_term_investable=float(short_inv),
        monthly_contribution=stored_monthly,
        summary_lines=summary,
        educational_notes=[
            "Simplified on-page estimate (core planner unavailable).",
            "Educational purposes only — not financial advice.",
        ],
        money_needed_1_2_years=near_term,
        planned_large_expenses=planned_exp,
        long_term_allocation_pct=long_pct,
        safer_sleeve_allocation_pct=safer_pct,
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
    monthly_contribution: float | None,
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
        "current_monthly_investment": monthly_contribution,
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


def resolve_plan_compare_annual_return(session_state: Any) -> float | None:
    """
    Derived comparison metric — recomputed when portfolio analytics run.

    Not persisted; hydrated sessions clear stale values until analytics refresh.
    """
    raw = session_state.get("plan_compare_return")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def bump_investment_plan_restore_generation(session_state: Any) -> int:
    gen = int(session_state.get(INVESTMENT_PLAN_RESTORE_GEN_KEY) or 0) + 1
    session_state[INVESTMENT_PLAN_RESTORE_GEN_KEY] = gen
    return gen


def seed_plan_widget_keys_from_canonical(session_state: Any, *, key_prefix: str) -> None:
    """
    Copy canonical plan session keys into Streamlit widget keys for this mode prefix.

    Beginner and advanced UIs use different widget keys but one persistent model.
    """
    restore_gen = session_state.get(INVESTMENT_PLAN_RESTORE_GEN_KEY)
    seeded_gen = session_state.get(f"{key_prefix}_plan_widgets_seeded_gen")
    if restore_gen is not None and seeded_gen == restore_gen:
        return
    if restore_gen is None and session_state.get(f"{key_prefix}_plan_widgets_seeded"):
        return

    for field in PLAN_CANONICAL_SCALAR_KEYS:
        if field not in session_state:
            continue
        wkey = f"{key_prefix}_{field}"
        session_state[wkey] = coerce_plan_integer(session_state.get(field), 0)

    risk = str(session_state.get("plan_risk") or "Medium").strip()
    if risk not in PLAN_RISK_OPTIONS:
        risk = "Medium"
    session_state[f"{key_prefix}_plan_risk"] = risk
    session_state[f"{key_prefix}_plan_monthly_text"] = format_current_monthly_investment_for_widget(
        session_state
    )
    seed_plan_compare_list_from_canonical(session_state, list_key=f"{key_prefix}_compare_amounts_list")

    session_state[f"{key_prefix}_plan_widgets_seeded"] = True
    if restore_gen is not None:
        session_state[f"{key_prefix}_plan_widgets_seeded_gen"] = restore_gen


def _plan_risk_index(session_state: Any) -> int:
    val = str(session_state.get("plan_risk") or "Medium").strip()
    if val not in PLAN_RISK_OPTIONS:
        val = "Medium"
    return PLAN_RISK_OPTIONS.index(val)


def sync_plan_compare_amounts_to_canonical(session_state: Any, *, list_key: str) -> None:
    """Keep a prefix-independent compare list for durable persistence."""
    amounts = normalize_compare_amounts(session_state.get(list_key))
    session_state[list_key] = amounts
    session_state[PLAN_COMPARE_AMOUNTS_KEY] = list(amounts)


def seed_plan_compare_list_from_canonical(session_state: Any, *, list_key: str) -> None:
    if list_key in session_state and session_state.get(list_key):
        sync_plan_compare_amounts_to_canonical(session_state, list_key=list_key)
        return
    canon = normalize_compare_amounts(session_state.get(PLAN_COMPARE_AMOUNTS_KEY))
    if canon:
        session_state[list_key] = list(canon)
        session_state[PLAN_COMPARE_AMOUNTS_KEY] = list(canon)


def investment_plan_persist_fingerprint(session_state: Any) -> str:
    """Stable hash of plan inputs + outputs for change-detection autosave."""
    plan = session_state.get("investment_plan")
    plan_dict: dict[str, Any] = {}
    if plan is not None:
        to_dict = getattr(plan, "to_dict", None)
        if callable(to_dict):
            plan_dict = dict(to_dict())
        elif isinstance(plan, dict):
            plan_dict = dict(plan)
    blob = {
        "schema": INVESTMENT_PLAN_PERSIST_SCHEMA,
        "plan_total_cash": session_state.get("plan_total_cash"),
        "plan_emergency": session_state.get("plan_emergency"),
        "plan_near_term": session_state.get("plan_near_term"),
        "plan_debt": session_state.get("plan_debt"),
        "plan_expenses": session_state.get("plan_expenses"),
        "plan_monthly": session_state.get("plan_monthly"),
        "plan_monthly_provided": session_state.get(PLAN_MONTHLY_PROVIDED_KEY),
        "plan_horizon": session_state.get("plan_horizon"),
        "plan_risk": session_state.get("plan_risk"),
        "investment_plan_generated": session_state.get("investment_plan_generated"),
        "investment_plan": plan_dict,
        "plan_compare_amounts_list": normalize_compare_amounts(session_state.get(PLAN_COMPARE_AMOUNTS_KEY)),
        "investment_plan_applied_portfolio_value": session_state.get("investment_plan_applied_portfolio_value"),
        "applied_plan_portfolio_value": session_state.get("applied_plan_portfolio_value"),
        "investment_plan_applied_source": session_state.get("investment_plan_applied_source"),
    }
    for key in PLAN_CASHFLOW_SESSION_KEYS:
        blob[key] = session_state.get(key)
    raw = json.dumps(blob, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def capture_investment_plan_persist_blob(session_state: Any) -> dict[str, Any]:
    plan = session_state.get("investment_plan")
    plan_dict: dict[str, Any] | None = None
    if plan is not None:
        to_dict = getattr(plan, "to_dict", None)
        if callable(to_dict):
            plan_dict = dict(to_dict())
        elif isinstance(plan, dict):
            plan_dict = dict(plan)
    blob = {
        "schema": INVESTMENT_PLAN_PERSIST_SCHEMA,
        "plan_total_cash": session_state.get("plan_total_cash"),
        "plan_emergency": session_state.get("plan_emergency"),
        "plan_near_term": session_state.get("plan_near_term"),
        "plan_debt": session_state.get("plan_debt"),
        "plan_expenses": session_state.get("plan_expenses"),
        "plan_monthly": session_state.get("plan_monthly"),
        "plan_monthly_provided": session_state.get(PLAN_MONTHLY_PROVIDED_KEY),
        "plan_horizon": session_state.get("plan_horizon"),
        "plan_risk": session_state.get("plan_risk"),
        "investment_plan_generated": session_state.get("investment_plan_generated"),
        "investment_plan": plan_dict,
        "plan_compare_amounts_list": normalize_compare_amounts(session_state.get(PLAN_COMPARE_AMOUNTS_KEY)),
        "applied_plan_portfolio_value": session_state.get("applied_plan_portfolio_value"),
        "investment_plan_applied_portfolio_value": session_state.get("investment_plan_applied_portfolio_value"),
        "investment_plan_applied_source": session_state.get("investment_plan_applied_source"),
    }
    for key in PLAN_CASHFLOW_SESSION_KEYS:
        blob[key] = session_state.get(key)
    return blob


def apply_investment_plan_persist_blob(st: Any, blob: Any) -> None:
    if not isinstance(blob, dict):
        return
    schema = str(blob.get("schema") or "").strip()
    if schema and schema not in (INVESTMENT_PLAN_PERSIST_SCHEMA, "investment-plan-v0"):
        return
    ss = st.session_state
    amounts = normalize_compare_amounts(blob.get("plan_compare_amounts_list"))
    if amounts:
        ss[PLAN_COMPARE_AMOUNTS_KEY] = list(amounts)
    ss.pop("plan_compare_return", None)
    for plan_key in (
        "plan_total_cash",
        "plan_emergency",
        "plan_near_term",
        "plan_debt",
        "plan_expenses",
        "plan_monthly",
        "plan_horizon",
        "plan_risk",
    ):
        if plan_key in blob and blob.get(plan_key) is not None:
            ss[plan_key] = blob[plan_key]
    if PLAN_MONTHLY_PROVIDED_KEY in blob:
        ss[PLAN_MONTHLY_PROVIDED_KEY] = bool(blob.get(PLAN_MONTHLY_PROVIDED_KEY))
    for key in PLAN_CASHFLOW_SESSION_KEYS:
        if key in blob and blob.get(key) not in (None, ""):
            ss[key] = blob[key]
    if blob.get("investment_plan_generated"):
        ss["investment_plan_generated"] = True
    try:
        from planning_portfolio_value import apply_applied_plan_from_persist_blob

        apply_applied_plan_from_persist_blob(ss, blob)
    except ImportError:
        if blob.get("applied_plan_portfolio_value") is not None:
            ss["applied_plan_portfolio_value"] = blob["applied_plan_portfolio_value"]
        if blob.get("investment_plan_applied_portfolio_value") is not None:
            ss["investment_plan_applied_portfolio_value"] = blob["investment_plan_applied_portfolio_value"]
        if blob.get("investment_plan_applied_source"):
            ss["investment_plan_applied_source"] = blob["investment_plan_applied_source"]
    plan_raw = blob.get("investment_plan")
    if plan_raw:
        try:
            ss["investment_plan"] = _normalize_investment_plan(plan_raw)
            ss["investment_plan_generated"] = True
        except Exception:
            pass


def maybe_autosave_investment_plan(st: Any, *, source: str = "plan_change") -> None:
    """Persist plan blob when meaningful fields change (debounced by fingerprint)."""
    ss = st.session_state
    fp = investment_plan_persist_fingerprint(ss)
    if fp == ss.get("_investment_plan_last_persist_fp"):
        return
    try:
        from investment_persistent_state import notify_investment_plan_change

        notify_investment_plan_change(st, source=source, fingerprint=fp)
    except ImportError:
        pass


def render_investment_plan_save_status(st: Any) -> None:
    status = st.session_state.pop("_investment_plan_save_status", None)
    if status == "saved":
        st.caption("Changes saved.")
    elif status == "error":
        msg = st.session_state.pop("_investment_plan_save_error", "Could not save plan.")
        st.warning(msg)


def _portfolio_inputs_tab_label(*, beginner_mode: bool) -> str:
    from components.beginner_navigation import ADVANCED_TAB_LABELS, BEGINNER_TAB_LABELS

    labels = BEGINNER_TAB_LABELS if beginner_mode else ADVANCED_TAB_LABELS
    return labels[2]


def request_navigate_to_how_much_plan_inputs(st: Any, *, beginner_mode: bool | None = None) -> str:
    """
    Schedule navigation to Portfolio Inputs / Build Portfolio and scroll to plan inputs.

    Uses the live experience mode (not insight metadata) so tab labels match the UI.
    """
    ss = st.session_state
    if beginner_mode is None:
        try:
            from investment_persistent_state import current_experience_mode

            beginner_mode = "beginner" in str(current_experience_mode(st) or "").lower()
        except ImportError:
            exp = str(ss.get("experience") or ss.get("experience_mode") or "").lower()
            beginner_mode = "beginner" in exp
    tab = _portfolio_inputs_tab_label(beginner_mode=bool(beginner_mode))
    ss["_pending_investment_tab"] = tab
    ss["investment_active_tab"] = tab
    ss["_pending_scroll_target"] = HOW_MUCH_PLAN_SCROLL_ANCHOR
    ss["_force_plan_inputs_expanded"] = True
    if beginner_mode:
        ss["beginner_plan_input_tab"] = BEGINNER_PLAN_INPUT_TABS[0]
    try:
        from investment_persistent_state import notify_investment_tab_change

        notify_investment_tab_change(st, tab, source="how_much_plan_nav")
    except ImportError:
        pass
    return tab


def request_navigate_to_my_portfolio(st: Any, *, beginner_mode: bool | None = None) -> str:
    """Schedule navigation to the My Portfolio (Real Portfolio ledger) tab."""
    from components.beginner_navigation import (
        BEGINNER_REAL_PORTFOLIO_TAB_LABEL,
        REAL_PORTFOLIO_TAB_LABEL,
    )

    ss = st.session_state
    if beginner_mode is None:
        try:
            from investment_persistent_state import current_experience_mode

            beginner_mode = "beginner" in str(current_experience_mode(st) or "").lower()
        except ImportError:
            exp = str(ss.get("experience") or ss.get("experience_mode") or "").lower()
            beginner_mode = "beginner" in exp
    tab = BEGINNER_REAL_PORTFOLIO_TAB_LABEL if beginner_mode else REAL_PORTFOLIO_TAB_LABEL
    ss["_pending_investment_tab"] = tab
    ss["investment_active_tab"] = tab
    ss.pop("_pending_scroll_target", None)
    ss.pop("_force_plan_inputs_expanded", None)
    try:
        from investment_persistent_state import notify_investment_tab_change

        notify_investment_tab_change(st, tab, source="my_portfolio_nav")
    except ImportError:
        pass
    return tab


def _plan_cashflow_int_or_none(session_state: Any, key: str) -> int | None:
    raw = session_state.get(key)
    if raw is None or raw == "":
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def _render_plan_cashflow_inputs(*, key_prefix: str) -> None:
    """Monthly surplus inputs used by the Monthly Contribution Advisor."""
    ss = st.session_state
    st.markdown("##### Monthly cash flow (for contribution guidance)")
    st.caption(
        "These fields power AMI monthly contribution recommendations. They save with your workspace."
    )
    c1, c2 = st.columns(2)
    with c1:
        income_default = _plan_cashflow_int_or_none(ss, "monthly_income")
        income = st.number_input(
            "Monthly after-tax income ($)",
            min_value=0,
            max_value=5_000_000,
            value=int(income_default) if income_default is not None else 0,
            step=500,
            key=f"{key_prefix}_monthly_income",
        )
        ss["monthly_income"] = int(income) if income > 0 else None
        expenses_default = _plan_cashflow_int_or_none(ss, "monthly_expenses")
        expenses = st.number_input(
            "Monthly essential expenses ($)",
            min_value=0,
            max_value=5_000_000,
            value=int(expenses_default) if expenses_default is not None else 0,
            step=250,
            key=f"{key_prefix}_monthly_expenses",
        )
        ss["monthly_expenses"] = int(expenses) if expenses > 0 else None
    with c2:
        job_options = list(JOB_STABILITY_OPTIONS)
        current_job = str(ss.get("job_stability") or "").strip()
        job_index = job_options.index(current_job) if current_job in job_options else 0
        job = st.selectbox(
            "Job stability (optional)",
            job_options,
            index=job_index,
            format_func=lambda x: "Not specified" if not x else x,
            key=f"{key_prefix}_job_stability",
        )
        ss["job_stability"] = str(job or "").strip()
        ss["plan_employer_match"] = st.text_input(
            "Employer retirement match (optional)",
            value=str(ss.get("plan_employer_match") or ""),
            placeholder="e.g. 50% up to 6% of salary",
            key=f"{key_prefix}_plan_employer_match",
        ).strip()
        ss["plan_retirement_goal"] = st.text_input(
            "Retirement goal (optional)",
            value=str(ss.get("plan_retirement_goal") or ""),
            placeholder="e.g. retire at 60 with $2M",
            key=f"{key_prefix}_plan_retirement_goal",
        ).strip()


def render_how_much_to_invest(
    settings: dict,
    tickers: list[str] | None = None,
    weights: np.ndarray | None = None,
    key_prefix: str = "invest_plan",
) -> core.InvestmentPlanResult | None:
    """Beginner-friendly section: how much cash to keep vs. invest."""
    beginner = is_beginner_mode(settings)
    render_how_much_plan_scroll_anchor()
    force_open = bool(st.session_state.pop("_force_plan_inputs_expanded", False))
    title = "How Much Should I Invest?"
    lead = (
        "Simple answers: how much to keep in cash vs. put into your portfolio."
        if beginner
        else "Educational cash-flow planning before setting portfolio value."
    )
    st.markdown(f"#### {title}")
    st.caption(lead)
    render_investment_plan_save_status(st)
    seed_plan_widget_keys_from_canonical(st.session_state, key_prefix=key_prefix)

    with st.expander(
        "Adjust your numbers" if beginner else "Inputs",
        expanded=force_open or not beginner,
    ):
        _render_plan_cashflow_inputs(key_prefix=key_prefix)
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            total_cash = st.number_input(
                "Total available cash / savings ($)",
                min_value=0,
                max_value=50_000_000,
                value=plan_integer_from_session(
                    "plan_total_cash",
                    coerce_plan_integer(settings.get("initial_value"), 100_000),
                ),
                step=5_000,
                key=f"{key_prefix}_plan_total_cash",
            )
            emergency = st.number_input(
                "Emergency fund needed ($)",
                min_value=0,
                max_value=10_000_000,
                value=plan_integer_from_session("plan_emergency", 20_000),
                step=1_000,
                key=f"{key_prefix}_plan_emergency",
            )
            near_term = st.number_input(
                "Money needed in the next 1–2 years ($)",
                min_value=0,
                max_value=10_000_000,
                value=plan_integer_from_session("plan_near_term", 0),
                step=1_000,
                key=f"{key_prefix}_plan_near_term",
            )
        with c2:
            debt = st.number_input(
                "Existing debt or obligations ($)",
                min_value=0,
                max_value=10_000_000,
                value=plan_integer_from_session("plan_debt", 0),
                step=1_000,
                key=f"{key_prefix}_plan_debt",
            )
            expenses = st.number_input(
                "Planned large expenses ($)",
                min_value=0,
                max_value=10_000_000,
                value=plan_integer_from_session("plan_expenses", 0),
                step=1_000,
                key=f"{key_prefix}_plan_expenses",
            )
            monthly = st.text_input(
                f"{CURRENT_MONTHLY_INVESTMENT_LABEL} ($)",
                value=format_current_monthly_investment_for_widget(st.session_state),
                help=CURRENT_MONTHLY_INVESTMENT_HELP,
                placeholder="Leave blank if unknown",
                key=f"{key_prefix}_plan_monthly_text",
            )
            parsed_monthly, monthly_provided, monthly_error = parse_current_monthly_investment_input(
                monthly
            )
            if monthly_error:
                st.warning(monthly_error)
            elif monthly_provided:
                st.session_state[PLAN_MONTHLY_PROVIDED_KEY] = True
                st.session_state.plan_monthly = int(round(float(parsed_monthly or 0)))
            else:
                st.session_state[PLAN_MONTHLY_PROVIDED_KEY] = False
        r1, r2 = st.columns(2)
        with r1:
            horizon = st.slider(
                "Investment time horizon (years)",
                1,
                40,
                plan_integer_from_session("plan_horizon", 15),
                key=f"{key_prefix}_plan_horizon",
            )
        with r2:
            risk = st.selectbox(
                "Risk tolerance",
                list(PLAN_RISK_OPTIONS),
                index=_plan_risk_index(st.session_state),
                key=f"{key_prefix}_plan_risk",
            )
            st.session_state.plan_risk = str(risk)

    st.session_state.plan_total_cash = int(total_cash)
    st.session_state.plan_emergency = int(emergency)
    st.session_state.plan_near_term = int(near_term)
    st.session_state.plan_debt = int(debt)
    st.session_state.plan_expenses = int(expenses)
    st.session_state.plan_horizon = int(horizon)

    generate_label = "Generate investment plan" if beginner else "Generate plan"
    if st.button(generate_label, type="primary", key=f"{key_prefix}_generate_plan"):
        st.session_state.investment_plan_generated = True
        maybe_autosave_investment_plan(st, source="plan_generate")
    if not st.session_state.get("investment_plan_generated"):
        st.caption("Enter your numbers above, then click **Generate investment plan** to see results.")
        maybe_autosave_investment_plan(st, source="plan_inputs")
        return None

    plan = _compute_investment_plan_safe(
        total_available=float(total_cash),
        emergency_fund_needed=float(emergency),
        money_needed_1_2_years=float(near_term),
        existing_debt_obligations=float(debt),
        planned_large_expenses=float(expenses),
        horizon_years=int(horizon),
        risk_tolerance=risk,
        monthly_contribution=current_monthly_investment_for_plan(st.session_state),
    )
    st.session_state.investment_plan = plan
    maybe_autosave_investment_plan(st, source="plan_compute")

    _render_plan_results(
        plan,
        key_prefix=key_prefix,
        beginner=beginner,
        total_cash=float(total_cash),
        emergency=float(emergency),
        horizon_years=int(horizon),
        risk_tolerance=str(risk),
    )

    st.caption(DISCLAIMER)
    maybe_autosave_investment_plan(st, source="plan_inputs")
    return plan
