"""Guided Portfolio Adjustment — step-by-step change workflow."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core
from components.beginner_copy import translate_for_beginner
from components.rebalancing_panel import render_rebalancing_panel
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode

DISCLAIMER = f"Model-based educational guidance. {APP_DISCLAIMER}"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _macro_timing_note(assumptions: core.ForwardMacroAssumptions | None) -> str | None:
    if assumptions is None:
        return None
    if assumptions.recession_probability >= 0.5:
        return (
            "Recession probability is elevated in your macro settings — "
            "the model suggests reviewing equity concentration for educational purposes."
        )
    if assumptions.inflation == "High Inflation":
        return "High inflation assumption — consider reviewing long-duration bonds in the model."
    if assumptions.rate_environment in ("Rising Rates", "High Rate Environment"):
        return "Rising/high rate environment — T-bills or shorter-duration bonds may be worth reviewing in the model."
    if assumptions.rate_environment == "Falling Rates":
        return "Falling rates environment — growth and bonds may benefit in some models."
    return None


def _build_adjustment_table(
    rebalance_df: pd.DataFrame,
    initial_value: float,
) -> pd.DataFrame:
    if rebalance_df.empty:
        return pd.DataFrame()
    cols_needed = {"Ticker", "Current (%)", "Objective (%)"}
    if not cols_needed.issubset(rebalance_df.columns):
        return pd.DataFrame()
    rows = []
    for _, r in rebalance_df.iterrows():
        cur = float(r["Current (%)"])
        obj = float(r["Objective (%)"])
        ch = obj - cur
        if abs(ch) < 1.0:
            continue
        rows.append(
            {
                "Asset": r["Ticker"],
                "Current %": f"{cur:.1f}%",
                "Suggested %": f"{obj:.1f}%",
                "Change %": f"{ch:+.1f}%",
                "Current $": _money(cur / 100 * initial_value),
                "Suggested $": _money(obj / 100 * initial_value),
                "Dollar Change": _money(ch / 100 * initial_value),
            }
        )
    return pd.DataFrame(rows)


def _primary_issue(health: core.PortfolioHealthResult, beginner: bool) -> tuple[str, str]:
    """Return (issue, why) in plain language."""
    for d in health.recommendation_details[:3]:
        issue = translate_for_beginner(d.issue) if beginner else d.issue
        why = translate_for_beginner(d.why_it_matters) if beginner else d.why_it_matters
        return issue, why
    return (
        "Your portfolio weights may have drifted from your selected objective.",
        "Drift can change how much risk you are taking compared to what you intended.",
    )


def _render_preview_apply_section(
    health: core.PortfolioHealthResult,
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    settings: dict,
    metrics: core.ExtendedPortfolioMetrics,
    returns: pd.DataFrame,
    adj_table: pd.DataFrame,
    has_changes: bool,
    key_prefix: str,
    beginner: bool,
) -> None:
    suggested_w = core.suggested_weights_from_rebalance(
        health.rebalance_df, tickers, weights, target_column="Objective (%)"
    )
    preview_key = f"{key_prefix}_preview_active"
    initial_value = float(settings["initial_value"])

    if has_changes:
        st.dataframe(adj_table, use_container_width=True, hide_index=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        preview = st.button("Preview Suggested Change", type="primary", key=f"{key_prefix}_preview_btn")
    with c2:
        apply = st.button("Apply Suggested Allocation", key=f"{key_prefix}_apply_btn")
    with c3:
        keep = st.button("Keep Current Portfolio", key=f"{key_prefix}_keep_btn")

    if keep:
        st.session_state.pop(preview_key, None)
        st.info("Keeping your current portfolio. No changes applied.")

    if preview or st.session_state.get(preview_key):
        st.session_state[preview_key] = True
        preview_metrics = core.compute_extended_metrics(
            returns, suggested_w, settings["risk_free"], initial_value
        )
        preview_df = pd.DataFrame(core.holdings_records_from_weights(tickers, suggested_w, asset_types))
        preview_df["Value ($)"] = (preview_df["Weight (%)"] / 100 * initial_value).map(_money)
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Est. volatility" if beginner else "Volatility",
            f"{preview_metrics.volatility * 100:.2f}%",
            delta=f"{(preview_metrics.volatility - metrics.volatility) * 100:+.2f}%",
        )
        m2.metric(
            "Est. 1Y value" if beginner else "Projected value (1Y)",
            _money(preview_metrics.projected_value),
            delta=_money(preview_metrics.projected_value - metrics.projected_value),
        )
        m3.metric(
            "Risk/reward score" if beginner else "Sharpe",
            f"{preview_metrics.sharpe_ratio:.2f}",
            delta=f"{preview_metrics.sharpe_ratio - metrics.sharpe_ratio:+.2f}",
        )
        st.caption("Preview is educational, not a guarantee. " + DISCLAIMER)

    if apply:
        st.session_state.holdings_df = pd.DataFrame(
            core.holdings_records_from_weights(tickers, suggested_w, asset_types)
        )
        st.session_state.run_health = False
        st.session_state.pop("health_result", None)
        st.session_state.pop("health_result_fingerprint", None)
        st.session_state.pop(preview_key, None)
        st.success("Suggested allocation applied. Re-run **Analyze Portfolio** to refresh.")
        st.rerun()


def render_guided_portfolio_adjustment(
    health: core.PortfolioHealthResult,
    *,
    tickers: list[str],
    weights: np.ndarray,
    asset_types: list[str],
    settings: dict,
    metrics: core.ExtendedPortfolioMetrics,
    returns: pd.DataFrame,
    assumptions: core.ForwardMacroAssumptions | None = None,
    key_prefix: str = "guided",
) -> None:
    beginner = is_beginner_mode(settings)
    initial_value = float(settings["initial_value"])

    if beginner:
        adj_tabs = st.tabs(["Issue", "Suggestion", "Preview / Apply", "Timing"])
    else:
        st.markdown("## Guided Portfolio Adjustment")
        st.caption(
            "If the model flagged something, this walkthrough shows what you might consider — "
            "in dollars and percentages. For educational purposes only."
        )
        adj_tabs = None

    issue, why = _primary_issue(health, beginner)
    adj_table = _build_adjustment_table(health.rebalance_df, initial_value)
    has_changes = not adj_table.empty

    if not has_changes and health.score >= 70:
        st.success(
            "The model does not suggest major allocation changes right now. "
            "You may still review recommendations during your next monthly check-in."
        )
        return

    if beginner and adj_tabs:
        with adj_tabs[0]:
            st.markdown("#### What the model noticed")
            st.markdown(issue)
        with adj_tabs[1]:
            st.markdown("#### Why it may matter")
            st.markdown(why)
            if health.recommendation_details:
                d0 = health.recommendation_details[0]
                st.markdown(f"**Suggestion:** {translate_for_beginner(d0.text) if beginner else d0.text}")
            render_rebalancing_panel(health, settings=settings, key_prefix=f"{key_prefix}_guided")
        with adj_tabs[2]:
            _render_preview_apply_section(
                health, tickers, weights, asset_types, settings, metrics, returns,
                adj_table, has_changes, key_prefix, beginner,
            )
        with adj_tabs[3]:
            st.markdown(
                "- Review during your next **monthly or quarterly** check-in.\n"
                "- No need to change immediately.\n"
                "- For long-term portfolios, avoid overreacting to short-term moves."
            )
            st.caption(DISCLAIMER)
        return

    # Advanced: stacked layout
    with st.container(border=True):
        st.markdown("### Step 1 — Identify the issue")
        st.markdown(f"**What the model noticed:** {issue}")

    # Step 2
    with st.container(border=True):
        st.markdown("### Step 2 — Why it may matter")
        st.markdown(why)
        if health.recommendation_details:
            d0 = health.recommendation_details[0]
            st.markdown(f"**In plain terms:** {translate_for_beginner(d0.text) if beginner else d0.text}")

    # Step 3
    with st.container(border=True):
        st.markdown("### Step 3 — Suggested allocation to test")
        if has_changes:
            st.dataframe(adj_table, use_container_width=True, hide_index=True)
            st.caption(
                "Based on your objective, the model suggests testing weights closer to the **Suggested %** column."
            )
        else:
            st.info("No large per-ticker drift detected — review category-level suggestions in Portfolio Health.")

    # Step 4
    with st.container(border=True):
        st.markdown("### Step 4 — How you could test the change")
        if has_changes:
            top = adj_table.iloc[0]
            st.markdown(
                f"Example: adjust **{top['Asset']}** from {top['Current %']} ({top['Current $']}) "
                f"toward {top['Suggested %']} ({top['Suggested $']}). "
                f"That is about **{top['Dollar Change']}** in dollar terms."
            )
            st.markdown(
                "You might shift money from overweight holdings to underweight ones "
                "(for example bonds/BIL if the model suggests more stability)."
            )
        macro_note = _macro_timing_note(assumptions)
        if macro_note:
            st.markdown(f"**Macro context:** {macro_note}")

    # Step 5 — Preview / Apply
    with st.container(border=True):
        st.markdown("### Step 5 — Preview or apply")
        _render_preview_apply_section(
            health, tickers, weights, asset_types, settings, metrics, returns,
            adj_table, has_changes, key_prefix, beginner,
        )

    # Step 6
    with st.container(border=True):
        st.markdown("### Step 6 — Timing guidance")
        st.markdown(
            "- This does **not** need to be changed immediately.\n"
            "- Consider reviewing during your next **monthly or quarterly** portfolio check-in.\n"
            "- If your time horizon is short, reviewing sooner **may** make sense.\n"
            "- For long-term portfolios, avoid overreacting to short-term market moves."
        )
        st.caption(DISCLAIMER)

    plan = st.session_state.get("investment_plan")
    if plan and beginner:
        if isinstance(plan, dict):
            total_avail = float(plan.get("total_available", plan.get("total_cash", 0)))
            short_term = float(plan.get("short_term_cash_amount", plan.get("short_term_reserve", 0)))
            long_term = float(plan.get("long_term_suggested", plan.get("suggested_long_term_amount", 0)))
        else:
            total_avail = float(getattr(plan, "total_available", 0))
            short_term = float(getattr(plan, "short_term_cash_amount", 0))
            long_term = float(getattr(plan, "long_term_suggested", 0))
        st.markdown("---")
        st.markdown("#### Investment amount context")
        st.markdown(
            f"If your total available cash is **{_money(total_avail)}** but you may need "
            f"**{_money(short_term)}** in the next year or two, the model suggests keeping "
            f"that portion in short-term/cash-like assets and analyzing about "
            f"**{_money(long_term)}** as long-term investable money."
        )
