"""Dollar-focused rebalancing guidance for beginners."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import portfolio_core as core
from components.ui_helpers import APP_DISCLAIMER, is_beginner_mode


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _top_rebalance_moves(
    rebalance_df: pd.DataFrame,
    initial_value: float,
    *,
    min_pp: float = 1.0,
    max_items: int = 5,
) -> list[dict]:
    if rebalance_df.empty or initial_value <= 0:
        return []
    if "Current (%)" not in rebalance_df.columns or "Objective (%)" not in rebalance_df.columns:
        return []
    moves: list[dict] = []
    for _, row in rebalance_df.iterrows():
        cur_pct = float(row["Current (%)"])
        obj_pct = float(row["Objective (%)"])
        ch_pp = obj_pct - cur_pct
        if abs(ch_pp) < min_pp:
            continue
        cur_d = cur_pct / 100.0 * initial_value
        obj_d = obj_pct / 100.0 * initial_value
        ch_d = ch_pp / 100.0 * initial_value
        moves.append(
            {
                "ticker": row["Ticker"],
                "current_pct": cur_pct,
                "suggested_pct": obj_pct,
                "current_d": cur_d,
                "suggested_d": obj_d,
                "change_d": ch_d,
                "change_pp": ch_pp,
            }
        )
    moves.sort(key=lambda m: abs(m["change_d"]), reverse=True)
    return moves[:max_items]


def _is_pre_investment() -> bool:
    return not bool(st.session_state.get("capital_deployed"))


def render_rebalancing_panel(
    health: core.PortfolioHealthResult,
    *,
    settings: dict,
    initial_value: float | None = None,
    key_prefix: str = "rebal",
) -> None:
    """Show current vs suggested dollars, why, where money might go, and review timing."""
    beginner = is_beginner_mode(settings)
    pre_invest = _is_pre_investment()
    pv = float(initial_value if initial_value is not None else settings["initial_value"])
    reb = health.rebalance_df
    if "Current ($)" not in reb.columns and not reb.empty:
        reb = core.enrich_rebalance_with_dollars(reb, pv)

    moves = _top_rebalance_moves(reb, pv)
    if pre_invest:
        st.markdown("#### 📐 Suggested allocation adjustment")
        st.caption(
            "You have not marked capital as deployed yet — this compares your **planned mix** to the "
            f"**objective mix** for your goal (portfolio value **{_money(pv)}** for illustration). {APP_DISCLAIMER}"
        )
    else:
        st.markdown("#### 🔄 Rebalancing guidance")
        st.caption(f"Dollar amounts use portfolio value **{_money(pv)}**. {APP_DISCLAIMER}")

    if not moves:
        st.success(
            "The model does not suggest large allocation changes right now. "
            "Check again during your monthly or quarterly review."
        )
        return

    increases = [m for m in moves if m["change_d"] > 0]
    decreases = [m for m in moves if m["change_d"] < 0]

    for m in decreases:
        reduce_amt = abs(m["change_d"])
        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg,rgba(231,76,60,0.08) 0%,#141c2b 100%);
            border:1px solid #334155;border-left:4px solid #e74c3c;border-radius:10px;
            padding:0.85rem 1rem;margin-bottom:0.65rem;">
            <div style="font-weight:700;color:#f1f5f9;font-size:1rem;">{m['ticker']}</div>
            <div style="color:#cbd5e1;font-size:0.9rem;margin-top:0.35rem;line-height:1.55;">
            <b>Current:</b> {_money(m['current_d'])} ({m['current_pct']:.1f}%)<br>
            <b>Suggested:</b> {_money(m['suggested_d'])} ({m['suggested_pct']:.1f}%)<br>
            <b>Difference:</b> Consider reducing approximately <span style="color:#fca5a5;">{_money(reduce_amt)}</span>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for m in increases:
        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg,rgba(46,204,113,0.08) 0%,#141c2b 100%);
            border:1px solid #334155;border-left:4px solid #2ecc71;border-radius:10px;
            padding:0.85rem 1rem;margin-bottom:0.65rem;">
            <div style="font-weight:700;color:#f1f5f9;font-size:1rem;">{m['ticker']}</div>
            <div style="color:#cbd5e1;font-size:0.9rem;margin-top:0.35rem;line-height:1.55;">
            <b>Current:</b> {_money(m['current_d'])} ({m['current_pct']:.1f}%)<br>
            <b>Suggested:</b> {_money(m['suggested_d'])} ({m['suggested_pct']:.1f}%)<br>
            <b>Difference:</b> Consider increasing approximately <span style="color:#86efac;">{_money(m['change_d'])}</span>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("Why is the model suggesting this?", expanded=beginner):
        if health.recommendation_details:
            d0 = health.recommendation_details[0]
            st.markdown(f"**What it noticed:** {d0.issue}")
            st.markdown(f"**Why it may matter:** {d0.why_it_matters}")
            st.markdown(f"**Possible benefit:** {d0.possible_benefit}")
        else:
            if pre_invest:
                st.markdown(
                    "Your planned mix may differ from the objective allocation for your selected goal. "
                    "This is a suggested starting allocation — not a requirement to trade today."
                )
            else:
                st.markdown(
                    "Your current mix may have drifted from the objective the model uses for comparison. "
                    "Rebalancing is about moving closer to a target mix — not a requirement to trade today."
                )
        if increases and decreases:
            dec_names = ", ".join(m["ticker"] for m in decreases[:3])
            inc_names = ", ".join(m["ticker"] for m in increases[:3])
            st.markdown(
                f"**Where might money go?** In this framing, reductions in **{dec_names}** "
                f"could conceptually fund increases in **{inc_names}**. Many investors spread changes over time."
            )

    with st.expander("When should I review this?", expanded=False):
        st.markdown(
            "- **Monthly:** Skim these cards during your routine check-in — no action required unless drift is large.\n"
            "- **Quarterly:** A common time to consider gradual adjustments if several holdings are off target.\n"
            "- **Annually:** Revisit whether your objective and target mix still match your life situation."
        )
