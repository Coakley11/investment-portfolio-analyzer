"""How much should I invest? — educational cash planning."""

from __future__ import annotations

from typing import Any

import numpy as np
import streamlit as st

import portfolio_core as core
from components.ui_helpers import APP_DISCLAIMER, format_money_cents, holding_dollar_from_weight, is_beginner_mode, request_sidebar_portfolio_value

DISCLAIMER = f"Educational estimate only. {APP_DISCLAIMER}"

# User-facing label for short_term_investable (internal field name unchanged).
CONSERVATIVE_ALLOCATION_LABEL = "Conservative / short-term reserve"
CONSERVATIVE_ALLOCATION_HELP = (
    "Cash the model suggests keeping in lower-risk or short-horizon holdings "
    "(not the same as your 1–2 year spending reserve above). "
    "Often held in bonds, T-bills, or cash-like assets until you deploy it."
)

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
    request_sidebar_portfolio_value(amount, force=True)
    st.session_state.capital_deployed = True
    st.session_state.investment_plan_applied_portfolio_value = int(round(float(amount)))
    st.session_state.investment_plan_applied_source = str(source)


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
    if list_key not in st.session_state or not isinstance(st.session_state.get(list_key), list):
        st.session_state[list_key] = []

    inv = round(float(plan.amount_potentially_investable))
    lt = round(float(plan.long_term_suggested))
    st.markdown("##### Compare investment amounts")
    st.caption("Add any dollar amounts to compare simple one-year model projections (optional).")

    c_add, c_scenario = st.columns([2, 1])
    with c_add:
        new_amt = st.number_input(
            "Custom amount ($)",
            min_value=0,
            max_value=50_000_000,
            value=0,
            step=1_000,
            key=f"{key_prefix}_compare_new_amount",
        )
        if st.button("Add amount", key=f"{key_prefix}_compare_add"):
            merged = normalize_compare_amounts(list(st.session_state[list_key]) + [new_amt])
            st.session_state[list_key] = merged
            st.rerun()
    with c_scenario:
        if st.button(f"Add max investable ({_money(inv)})", key=f"{key_prefix}_compare_add_inv"):
            st.session_state[list_key] = normalize_compare_amounts(list(st.session_state[list_key]) + [inv])
            st.rerun()
        if st.button(f"Add long-term ({_money(lt)})", key=f"{key_prefix}_compare_add_lt"):
            st.session_state[list_key] = normalize_compare_amounts(list(st.session_state[list_key]) + [lt])
            st.rerun()

    amounts = normalize_compare_amounts(st.session_state.get(list_key))
    st.session_state[list_key] = amounts

    if not amounts:
        st.caption("No comparison amounts yet — add a custom value or use a scenario button.")
        return

    st.markdown("**Current comparison amounts**")
    for idx, amt in enumerate(amounts):
        c_label, c_remove = st.columns([4, 1])
        with c_label:
            st.text(_money(amt))
        with c_remove:
            if st.button("Remove", key=f"{key_prefix}_compare_rm_{idx}"):
                remaining = [a for i, a in enumerate(amounts) if i != idx]
                st.session_state[list_key] = remaining
                st.rerun()

    edit_amt = st.number_input(
        "Edit selected amount ($)",
        min_value=0.0,
        max_value=50_000_000.0,
        value=float(amounts[0]),
        step=1000.0,
        key=f"{key_prefix}_compare_edit_value",
    )
    edit_idx = st.number_input(
        "Index to replace (0 = first)",
        min_value=0,
        max_value=max(0, len(amounts) - 1),
        value=0,
        step=1,
        key=f"{key_prefix}_compare_edit_idx",
    )
    if st.button("Save edited amount", key=f"{key_prefix}_compare_save_edit"):
        updated = list(amounts)
        if 0 <= int(edit_idx) < len(updated):
            updated[int(edit_idx)] = float(edit_amt)
        st.session_state[list_key] = normalize_compare_amounts(updated)
        st.rerun()

    if st.button("Clear all comparison amounts", key=f"{key_prefix}_compare_clear"):
        st.session_state[list_key] = []
        st.rerun()

    compare_amounts = normalize_compare_amounts(st.session_state.get(list_key))
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
    )
    for key in keys:
        fb = defaults.get(key) if defaults else None
        if fb is None:
            fb = 0 if key != "plan_emergency" else 20_000
        if key not in session_state:
            continue
        session_state[key] = coerce_plan_integer(session_state.get(key), int(fb))


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
    monthly_contribution: float,
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
    if monthly_contribution > 0:
        summary.append(f"Optional monthly contribution noted: {_money(monthly_contribution)}/month")

    return core.InvestmentPlanResult(
        total_available=total,
        suggested_emergency_reserve=emergency,
        short_term_cash_amount=short_term,
        debt_reserve=debt,
        amount_potentially_investable=investable,
        long_term_suggested=float(long_term),
        short_term_investable=float(short_inv),
        monthly_contribution=float(monthly_contribution),
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


def render_how_much_to_invest(
    settings: dict,
    tickers: list[str] | None = None,
    weights: np.ndarray | None = None,
    key_prefix: str = "invest_plan",
) -> core.InvestmentPlanResult | None:
    """Beginner-friendly section: how much cash to keep vs. invest."""
    beginner = is_beginner_mode(settings)
    title = "How Much Should I Invest?"
    lead = (
        "Simple answers: how much to keep in cash vs. put into your portfolio."
        if beginner
        else "Educational cash-flow planning before setting portfolio value."
    )
    st.markdown(f"#### {title}")
    st.caption(lead)

    with st.expander("Adjust your numbers" if beginner else "Inputs", expanded=not beginner):
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
            monthly = st.number_input(
                "Monthly contribution (optional) ($)",
                min_value=0,
                max_value=500_000,
                value=plan_integer_from_session("plan_monthly", 0),
                step=100,
                key=f"{key_prefix}_plan_monthly",
            )
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
                ["Low", "Medium", "High"],
                index=1,
                key=f"{key_prefix}_plan_risk",
            )

    st.session_state.plan_total_cash = int(total_cash)
    st.session_state.plan_emergency = int(emergency)

    generate_label = "Generate investment plan" if beginner else "Generate plan"
    if st.button(generate_label, type="primary", key=f"{key_prefix}_generate_plan"):
        st.session_state.investment_plan_generated = True
    if not st.session_state.get("investment_plan_generated"):
        st.caption("Enter your numbers above, then click **Generate investment plan** to see results.")
        return None

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
    return plan
