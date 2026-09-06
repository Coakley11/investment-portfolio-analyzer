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
    return f"${float(x):,.0f}"


def _money_signed(x: float) -> str:
    """Signed currency for dollar changes (e.g. -$850, +$425, $0)."""
    v = float(x)
    if abs(v) < 0.5:
        return "$0"
    sign = "-" if v < 0 else "+"
    return f"{sign}${abs(v):,.0f}"


def _escape_md_money(text: str) -> str:
    """Escape `$` so Streamlit markdown does not treat amounts as LaTeX."""
    return text.replace("$", r"\$")


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
    *,
    include_unchanged: bool = True,
    material_pp: float = 1.0,
) -> pd.DataFrame:
    """
    Full Guided target table (Step 3 / Step 5).

    By default includes zero-change holdings so Suggested % sums to 100% with
    orphan sleeves. Preview/Apply still read ``health.rebalance_df`` directly —
    this table is presentation only.
    """
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
        if not include_unchanged and abs(ch) < material_pp:
            continue
        cur_d = cur / 100 * initial_value
        obj_d = obj / 100 * initial_value
        ch_d = ch / 100 * initial_value
        rows.append(
            {
                "Asset": r["Ticker"],
                "Current %": f"{cur:.1f}%",
                "Suggested %": f"{obj:.1f}%",
                "Change %": f"{ch:+.1f}%",
                "Current $": _money(cur_d),
                "Suggested $": _money(obj_d),
                "Dollar Change": _money_signed(ch_d),
                "_cur_pct": cur,
                "_sug_pct": obj,
                "_chg_pct": ch,
                "_cur_dol": cur_d,
                "_sug_dol": obj_d,
                "_chg_dol": ch_d,
                "_orphan": core.is_orphan_rebalance_row(r),
            }
        )
    return pd.DataFrame(rows)


def guided_table_has_material_changes(
    adj_table: pd.DataFrame,
    *,
    material_pp: float = 1.0,
) -> bool:
    if adj_table is None or adj_table.empty:
        return False
    if "_chg_pct" in adj_table.columns:
        return bool(adj_table["_chg_pct"].abs().ge(material_pp).any())
    return True


def format_guided_step4_example(
    asset: str,
    cur_pct: float,
    cur_dol: float,
    sug_pct: float,
    sug_dol: float,
    chg_dol: float,
    *,
    for_markdown: bool = True,
) -> str:
    """
    Clean Step 4 prose: percent with dollar amounts in parentheses and a signed
    dollar change. When ``for_markdown`` is True, escape `$` for Streamlit KaTeX.
    """
    cur_m = _money(cur_dol)
    sug_m = _money(sug_dol)
    chg_m = _money_signed(chg_dol)
    text = (
        f"Adjust **{asset}** from {cur_pct:.1f}% ({cur_m}) toward "
        f"{sug_pct:.1f}% ({sug_m}), a change of approximately {chg_m}."
    )
    return _escape_md_money(text) if for_markdown else text


def parse_suggested_pct_sum(adj_table: pd.DataFrame) -> float:
    """Sum Suggested % values from the Guided display table."""
    if adj_table is None or adj_table.empty:
        return 0.0
    if "_sug_pct" in adj_table.columns:
        return float(adj_table["_sug_pct"].sum())
    total = 0.0
    for raw in adj_table.get("Suggested %", []):
        total += float(str(raw).replace("%", "").strip() or 0)
    return total



def _primary_issue(health: core.PortfolioHealthResult, beginner: bool) -> tuple[str, str, str]:
    """Return (issue, why, triggered_by) in plain language."""
    for d in health.recommendation_details[:3]:
        issue = translate_for_beginner(d.issue) if beginner else d.issue
        why = translate_for_beginner(d.why_it_matters) if beginner else d.why_it_matters
        triggered = str(d.triggered_by or "").strip()
        return issue, why, triggered
    return (
        "Your portfolio weights may have drifted from your selected objective.",
        "Drift can change how much risk you are taking compared to what you intended.",
        "",
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
        st.dataframe(
            adj_table.drop(
                columns=[c for c in adj_table.columns if str(c).startswith("_")],
                errors="ignore",
            ),
            use_container_width=True,
            hide_index=True,
        )

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
        if health.rebalance_df is not None and not health.rebalance_df.empty:
            if health.rebalance_df.apply(core.is_orphan_rebalance_row, axis=1).any():
                st.caption(
                    "Preview / Apply adjusts **among your current holdings only**. "
                    "Unrepresented objective sleeves (e.g. Cash / T-Bills) are shown in Guided "
                    "targets but are **not** added to My Portfolio automatically."
                )
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

    issue, why, triggered_by = _primary_issue(health, beginner)
    adj_table = _build_adjustment_table(health.rebalance_df, initial_value, include_unchanged=True)
    has_material_changes = guided_table_has_material_changes(adj_table)
    has_changes = not adj_table.empty

    if not has_material_changes and health.score >= 70:
        st.success(
            "The model does not suggest major allocation changes right now. "
            "You may still review recommendations during your next monthly check-in."
        )
        return

    if beginner and adj_tabs:
        with adj_tabs[0]:
            st.markdown("#### What the model noticed")
            st.markdown(issue)
            if triggered_by:
                st.caption(f"Triggered by: {triggered_by}")
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
        if triggered_by:
            st.caption(f"Triggered by: {triggered_by}")

    # Step 2
    with st.container(border=True):
        st.markdown("### Step 2 — Why it may matter")
        st.markdown(why)
        if health.recommendation_details:
            d0 = health.recommendation_details[0]
            st.markdown(f"**In plain terms:** {translate_for_beginner(d0.text) if beginner else d0.text}")
            if d0.evidence:
                sharpe_ev = d0.evidence.get("Sharpe ratio")
                if sharpe_ev:
                    st.caption(f"Model Sharpe ratio used for this flag: **{sharpe_ev}**")

    # Step 3
    with st.container(border=True):
        st.markdown("### Step 3 — Suggested allocation to test")
        if has_changes:
            st.dataframe(
                adj_table.drop(
                    columns=[c for c in adj_table.columns if str(c).startswith("_")],
                    errors="ignore",
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Full objective target (including unchanged holdings and any unrepresented sleeve). "
                "Suggested % sums to 100%. Unrepresented sleeves are not silently redistributed."
            )
        else:
            st.info("No large per-ticker drift detected — review category-level suggestions in Portfolio Health.")

    # Step 4
    with st.container(border=True):
        st.markdown("### Step 4 — How you could test the change")
        if has_changes:
            # Prefer a real holding for the example (not an orphan sleeve row).
            example = adj_table
            if "_orphan" in adj_table.columns:
                real = adj_table.loc[~adj_table["_orphan"].astype(bool)]
                if not real.empty:
                    example = real
            top = example.iloc[0]
            st.markdown(
                format_guided_step4_example(
                    str(top["Asset"]),
                    float(top.get("_cur_pct", 0)),
                    float(top.get("_cur_dol", 0)),
                    float(top.get("_sug_pct", 0)),
                    float(top.get("_sug_dol", 0)),
                    float(top.get("_chg_dol", 0)),
                )
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
