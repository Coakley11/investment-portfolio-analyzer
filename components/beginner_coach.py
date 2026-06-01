"""Beginner Mode UI — portfolio coach (action-oriented, minimal quant jargon)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import portfolio_core as core
from components.beginner_navigation import mark_portfolio_built
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


def render_goal_cards(*, key_prefix: str = "goal_card") -> None:
    """Step 1 — large goal cards; one click loads the recommended portfolio."""
    st.markdown("#### Step 1 — Choose your goal")
    st.caption("Tap a card to load a recommended portfolio. You can fine-tune weights later.")
    selected = st.session_state.get("beginner_goal_card")
    cols = st.columns(3)
    for i, card in enumerate(GOAL_CARDS):
        with cols[i % 3]:
            active = selected == card["id"]
            border = "#4da3ff" if active else "#334155"
            bg = "rgba(77,163,255,0.12)" if active else "rgba(20,28,43,0.85)"
            st.markdown(
                f"""
                <div style="background:{bg};border:2px solid {border};border-radius:12px;
                padding:0.85rem 0.75rem;margin-bottom:0.5rem;min-height:7.5rem;">
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
                st.session_state.beginner_goal_card = card["id"]
                st.session_state.guide_goal_choice = card["goal_key"]
                st.session_state.health_objective = card["objective"]
                if card["preset"] in core.PORTFOLIO_PRESETS:
                    st.session_state.holdings_df = pd.DataFrame(core.PORTFOLIO_PRESETS[card["preset"]])
                    st.session_state.preset_applied = card["preset"]
                    st.session_state.guide_portfolio_loaded = True
                    mark_portfolio_built()
                st.session_state.run_health = False
                st.session_state.pop("health_result", None)
                st.session_state.pop("health_result_fingerprint", None)
                st.rerun()
    if st.session_state.get("preset_applied"):
        st.success(f"Portfolio loaded: **{st.session_state.preset_applied}**")


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
        st.caption(f"Objective: {objective.replace('_', ' ').title()}")
        breakdown = health.score_breakdown
        for name, pts in list(breakdown.items())[:6]:
            st.markdown(f"- **{name}:** {pts:.1f} pts")
        st.caption("Switch to **Advanced Mode** for formulas, charts, and optimization.")


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
