"""Beginner Mode UI — portfolio coach (action-oriented, minimal quant jargon)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import portfolio_core as core
from components.beginner_navigation import mark_portfolio_built
try:
    from components.calculation_transparency import objective_alignment_plain_english
except ImportError:  # pragma: no cover - stale deploy fallback

    def objective_alignment_plain_english(avg_drift: float, objective: str = "") -> str:
        obj = (objective or "your selected goal").replace("_", " ").strip()
        if avg_drift < 0.03:
            closeness = "close to"
        elif avg_drift < 0.06:
            closeness = "somewhat different from"
        else:
            closeness = "significantly different from"
        return (
            f"Your portfolio is **{closeness}** the allocation associated with "
            f"**{obj}**."
        )
from components.ui_helpers import APP_DISCLAIMER, format_money

DISCLAIMER = f"Educational model only. {APP_DISCLAIMER}"

GOAL_CARDS: list[dict[str, str]] = [
    {
        "id": "retirement",
        "title": "Retirement",
        "emoji": "🏖️",
        "blurb": "Long-term saving with more stability than all-growth mixes.",
        "preset": "Retirement",
        "objective": "retirement",
        "goal_key": "Save for retirement",
    },
    {
        "id": "growth",
        "title": "Long-Term Growth",
        "emoji": "📈",
        "blurb": "Growth over many years — you can handle some market ups and downs.",
        "preset": "Balanced",
        "objective": "balanced growth",
        "goal_key": "Grow my money long term",
    },
    {
        "id": "income",
        "title": "Income",
        "emoji": "💵",
        "blurb": "Dividends and interest matter more than fast price gains.",
        "preset": "Dividend Income",
        "objective": "income",
        "goal_key": "Generate income",
    },
    {
        "id": "balanced",
        "title": "Balanced",
        "emoji": "⚖️",
        "blurb": "A middle path — stocks, bonds, and diversifiers together.",
        "preset": "Balanced",
        "objective": "balanced growth",
        "goal_key": "Grow my money long term",
    },
    {
        "id": "preservation",
        "title": "Capital Preservation",
        "emoji": "🛡️",
        "blurb": "Limit big losses even if growth is slower.",
        "preset": "Conservative",
        "objective": "capital preservation",
        "goal_key": "Protect my money",
    },
    {
        "id": "cash",
        "title": "Short-Term Cash",
        "emoji": "🏦",
        "blurb": "Money you may need soon — stability first.",
        "preset": "Conservative",
        "objective": "short-term cash management",
        "goal_key": "Keep cash safe short-term",
    },
]


def _money(x: float) -> str:
    return format_money(x)


def render_beginner_analysis_pipeline() -> None:
    """Simple visual explanation of how historical data flows through the app."""
    st.markdown("#### How the analysis works")
    steps = [
        ("1", "Select a historical analysis period", "Use **Start** and **End** in the sidebar."),
        (
            "2",
            "The app studies how your investments behaved",
            "It downloads prices for that period and learns from daily moves.",
        ),
        (
            "3",
            "The app estimates returns, volatility, and risk",
            "These power health scores, dollar guidance, and advanced tools.",
        ),
        (
            "4",
            "The app evaluates portfolio health",
            "Run **Analyze Portfolio** to see your score and coach suggestions.",
        ),
        (
            "5",
            "Macro assumptions use current economic data",
            "Beginner Mode loads public inflation, rates, and jobs data — no guessing required.",
        ),
    ]
    for num, title, detail in steps:
        st.markdown(
            f"""
            <div style="display:flex;gap:0.75rem;align-items:flex-start;background:#141c2b;
            border:1px solid #334155;border-radius:10px;padding:0.75rem 0.9rem;margin-bottom:0.5rem;">
            <div style="flex:0 0 2rem;height:2rem;border-radius:999px;background:rgba(77,163,255,0.2);
            color:#4da3ff;font-weight:700;display:flex;align-items:center;justify-content:center;">
            {num}</div>
            <div>
            <div style="font-weight:600;color:#f1f5f9;">{title}</div>
            <div style="color:#94a3b8;font-size:0.88rem;line-height:1.45;margin-top:0.2rem;">{detail}</div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(
        "Your investment dates are separate from this historical window — see sidebar **Start** / **End** help."
    )


def _resolved_goal_card(st_obj: Any | None = None) -> dict[str, str] | None:
    """Map session state to the active beginner goal card, if any."""
    ss = st_obj.session_state if st_obj is not None else st.session_state
    card_id = ss.get("beginner_goal_card")
    if card_id:
        for card in GOAL_CARDS:
            if card.get("id") == card_id:
                return card
    goal_key = ss.get("guide_goal_choice")
    if goal_key:
        for card in GOAL_CARDS:
            if card.get("goal_key") == goal_key:
                return card
    return None


def render_goal_cards(*, key_prefix: str = "goal_card", change_goal_mode: bool = False) -> None:
    """
    Step 1 — large goal cards; one click loads the recommended portfolio.

    UX invariant (Beginner): always render every goal card on the Goal step.
    Never hide the picker because a goal is already selected — highlight the
    current choice and let the user switch anytime.
    """
    if change_goal_mode:
        st.markdown(
            """
            <div id="goal-card-picker" style="background:rgba(77,163,255,0.08);border:2px solid #4da3ff;
            border-radius:12px;padding:0.65rem 0.85rem;margin:0 0 0.75rem 0;">
            <div style="font-weight:700;color:#f1f5f9;">Pick a new goal</div>
            <div style="color:#94a3b8;font-size:0.88rem;margin-top:0.25rem;">
            Tap a card below to load its portfolio template. Analysis steps will need to be run again.
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("#### Step 1 — Choose your goal")
    current = _resolved_goal_card()
    if current:
        preset = st.session_state.get("preset_applied")
        preset_note = f" · Portfolio: **{preset}**" if preset else ""
        st.success(
            f"**Current goal: {current['title']}**{preset_note} — highlighted below. "
            "Tap any card to switch goals."
        )
    else:
        st.caption(
            "Tap a card to load a recommended portfolio. You can change your goal here anytime."
        )
    selected_id = current["id"] if current else None
    cols = st.columns(3)
    for i, card in enumerate(GOAL_CARDS):
        with cols[i % 3]:
            active = selected_id == card["id"]
            border = "#4da3ff" if active else "#334155"
            bg = "rgba(77,163,255,0.12)" if active else "rgba(20,28,43,0.85)"
            current_badge = (
                '<div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.06em;'
                'color:#86efac;font-weight:700;margin-bottom:0.25rem;">Current</div>'
                if active
                else ""
            )
            st.markdown(
                f"""
                <div style="background:{bg};border:2px solid {border};border-radius:12px;
                padding:0.85rem 0.75rem;margin-bottom:0.5rem;min-height:7.5rem;">
                {current_badge}
                <div style="font-size:1.6rem;line-height:1;">{card['emoji']}</div>
                <div style="font-weight:700;color:#f1f5f9;font-size:1rem;margin:0.35rem 0 0.2rem 0;">
                {card['title']}</div>
                <div style="color:#94a3b8;font-size:0.82rem;line-height:1.4;">{card['blurb']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                f"Use {card['title']}",
                key=f"{key_prefix}_{card['id']}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                try:
                    from investment_workflow import snapshot_plan_labels

                    _prior_goal = snapshot_plan_labels(st)
                except ImportError:
                    _prior_goal = None
                st.session_state.beginner_goal_card = card["id"]
                st.session_state.guide_goal_choice = card["goal_key"]
                st.session_state.health_objective = card["objective"]
                if card["preset"] in core.PORTFOLIO_PRESETS:
                    st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[card["preset"]])
                    st.session_state.preset_applied = card["preset"]
                    st.session_state.guide_portfolio_loaded = True
                    try:
                        from investment_activity import log_goal_selected, log_portfolio_created

                        log_goal_selected(
                            st,
                            goal_title=card["title"],
                            objective=card["objective"],
                        )
                        log_portfolio_created(
                            st,
                            preset=card["preset"],
                            holdings_count=len(st.session_state.holdings_df),
                        )
                    except Exception:
                        pass
                try:
                    from investment_workflow import (
                        invalidate_workflow_from,
                        record_goal_selection,
                    )

                    invalidate_workflow_from("goal", st)
                    record_goal_selection(
                        st,
                        goal_title=card["title"],
                        preset=card.get("preset"),
                        objective=card["objective"],
                        beginner=True,
                        prior=_prior_goal,
                    )
                    from investment_workflow import capture_goal_selection_debug

                    if _prior_goal is not None:
                        capture_goal_selection_debug(
                            st, before=_prior_goal, card=card, source="beginner_card"
                        )
                except ImportError:
                    st.session_state.run_health = False
                    st.session_state.pop("health_result", None)
                    st.session_state.pop("health_result_fingerprint", None)
                mark_portfolio_built(st)
                try:
                    from investment_workflow import persist_plan_after_goal_selection

                    persist_plan_after_goal_selection(st)
                except ImportError:
                    pass
                st.rerun()
    if st.session_state.get("preset_applied"):
        st.success(f"Portfolio loaded: **{st.session_state.preset_applied}**")
    try:
        from investment_workflow import render_goal_selection_diagnostics

        render_goal_selection_diagnostics(
            st, beginner_mode=True, expanded=not change_goal_mode
        )
    except ImportError:
        pass


def render_beginner_goal_tab(*, change_goal_mode: bool = False) -> None:
    """
    Beginner ``① Choose Goal`` tab.

    Always shows the full goal-card grid first (see ``render_goal_cards``).
    Optional macro/pipeline sections stay collapsed so cards stay in view.
    """
    st.markdown(
        f'<p style="color:#f5d08a;font-size:0.85rem;">{APP_DISCLAIMER}</p>',
        unsafe_allow_html=True,
    )
    render_goal_cards(change_goal_mode=change_goal_mode)
    with st.expander("Current economic environment (optional)", expanded=False):
        try:
            from components.beginner_macro import render_beginner_macro_panel

            render_beginner_macro_panel()
        except ImportError:
            st.caption("Macro panel unavailable.")
    with st.expander("How the analysis works (optional)", expanded=False):
        render_beginner_analysis_pipeline()


def render_portfolio_visual_table(
    tickers: list[str],
    weights,
    initial_value: float,
    *,
    key_prefix: str = "port_vis",
) -> None:
    """Step 3 — Asset | % | Dollar Amount."""
    st.markdown("#### Your portfolio mix")
    w = core.normalize_weights(weights)
    rows = []
    for i, t in enumerate(tickers):
        pct = float(w[i]) * 100
        dollars = pct / 100.0 * initial_value
        rows.append({"Asset": t, "%": f"{pct:.0f}%", "Dollar Amount": _money(dollars)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    try:
        import dashboard_charts as charts

        alloc_df = pd.DataFrame({"Ticker": tickers, "Weight (%)": [float(x) * 100 for x in w]})
        st.plotly_chart(charts.allocation_chart(alloc_df), use_container_width=True)
    except Exception:
        pass


def _render_health_score_card(health: core.PortfolioHealthResult) -> None:
    color_class = {
        "green": "health-card-green",
        "yellow": "health-card-yellow",
        "orange": "health-card-orange",
        "red": "health-card-red",
    }.get(health.score_color, "health-card-yellow")
    st.markdown(
        f"""
        <div class="health-card {color_class}">
            <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:#94a3b8;">
                Portfolio Health Score
            </div>
            <div style="font-size:2.4rem;font-weight:700;color:#f1f5f9;line-height:1.1;">
                {health.score:.0f}<span style="font-size:1rem;color:#94a3b8;"> / 100</span>
            </div>
            <div style="font-size:1rem;font-weight:600;color:#e2e8f0;margin-top:0.25rem;">
                {health.score_label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_beginner_analyze_results(health: core.PortfolioHealthResult, *, objective: str) -> None:
    """Step 4 — health score, status, top strengths/concerns, recommended next step."""
    _render_health_score_card(health)
    st.markdown(
        f'<div class="insight-card" style="margin-top:0.75rem;">📋 <b>Status:</b> {health.status_message}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("**Goal alignment**")
    st.markdown(objective_alignment_plain_english(health.avg_drift, objective))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Top strengths**")
        for item in health.whats_working[:3]:
            st.markdown(f'<div class="health-working">✓ {item}</div>', unsafe_allow_html=True)
        if not health.whats_working:
            st.caption("Run analysis to see strengths.")
    with c2:
        st.markdown("**Top concerns**")
        for item in health.whats_not_working[:3]:
            st.markdown(f'<div class="health-not">⚠ {item}</div>', unsafe_allow_html=True)
        if not health.whats_not_working:
            st.caption("No major concerns flagged.")
    if health.action_plan.headline:
        st.markdown(
            f"""
            <div style="background:rgba(77,163,255,0.10);border:1px solid rgba(77,163,255,0.4);
            border-radius:10px;padding:0.85rem 1rem;margin-top:0.75rem;">
            <div style="font-size:0.72rem;text-transform:uppercase;color:#4da3ff;font-weight:600;">
            Recommended next step</div>
            <div style="color:#f1f5f9;font-weight:600;margin-top:0.35rem;">{health.action_plan.headline}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with st.expander("Why? — more detail", expanded=False):
        st.markdown("**Goal alignment**")
        st.markdown(objective_alignment_plain_english(health.avg_drift, objective))
        st.markdown(
            "**What the coach also considers:** diversification, risk level, and how your mix "
            "fits the current economic assumptions — without requiring you to read formulas."
        )
        if health.recommendation_details:
            d0 = health.recommendation_details[0]
            st.markdown(f"**Top note:** {d0.issue}")
            st.markdown(f"**Why it may matter:** {d0.why_it_matters}")
        st.caption("Switch to **Advanced Mode** for score breakdowns, charts, and full methodology.")


def render_beginner_rebalance_cards(
    health: core.PortfolioHealthResult,
    *,
    settings: dict,
    initial_value: float | None = None,
    key_prefix: str = "beg_rebal",
) -> None:
    """Simplified rebalance: current vs suggested, dollars, reason, timeline."""
    from components.rebalancing_panel import _is_pre_investment, _top_rebalance_moves

    pv = float(initial_value if initial_value is not None else settings["initial_value"])
    reb = health.rebalance_df
    if "Current ($)" not in reb.columns and not reb.empty:
        reb = core.enrich_rebalance_with_dollars(reb, pv)
    moves = _top_rebalance_moves(reb, pv, max_items=4)
    pre = _is_pre_investment()
    title = "Suggested allocation adjustment" if pre else "Rebalancing ideas"
    st.markdown(f"#### {title}")
    if not moves:
        st.success("Your mix is close to the model objective. Review again during your monthly check-in.")
        return
    for m in moves:
        direction = "increase" if m["change_d"] > 0 else "reduce"
        st.markdown(
            f"""
            <div style="background:#141c2b;border:1px solid #334155;border-radius:10px;
            padding:0.85rem 1rem;margin-bottom:0.55rem;">
            <div style="font-weight:700;color:#f1f5f9;">{m['ticker']}</div>
            <div style="color:#cbd5e1;font-size:0.9rem;margin-top:0.4rem;line-height:1.55;">
            <b>Current:</b> {m['current_pct']:.0f}% · {_money(m['current_d'])}<br>
            <b>Suggested:</b> {m['suggested_pct']:.0f}% · {_money(m['suggested_d'])}<br>
            <b>Difference:</b> Consider {direction} by about {_money(abs(m['change_d']))}<br>
            <b>Reason:</b> Aligns with your selected portfolio objective.<br>
            <b>When:</b> Consider reviewing during your next monthly portfolio review.
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


__all__ = [
    "GOAL_CARDS",
    "_resolved_goal_card",
    "render_beginner_analysis_pipeline",
    "render_beginner_analyze_results",
    "render_beginner_goal_tab",
    "render_beginner_rebalance_cards",
    "render_goal_cards",
    "render_portfolio_visual_table",
]
