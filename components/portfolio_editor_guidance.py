"""Portfolio editor instructions and beginner ETF quick-add controls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

import portfolio_core as core
from components.ui_helpers import RUN_PORTFOLIO_ANALYSIS_LABEL


def render_workflow_journey_banner(*, beginner_mode: bool) -> None:
    """Lightweight Build → Analyze → Review helper below the workflow chips."""
    if beginner_mode:
        st.caption(
            f"**Your path:** ① Choose a goal → ② Build your portfolio → "
            f"③ Click **{RUN_PORTFOLIO_ANALYSIS_LABEL}** → ④ Review results on Portfolio Health."
        )
    else:
        st.caption(
            f"**Workflow:** Confirm holdings → **{RUN_PORTFOLIO_ANALYSIS_LABEL}** on Analysis → "
            "review score and recommendations on Portfolio Health."
        )


def render_portfolio_editor_guidance(*, beginner_mode: bool) -> None:
    """Explain how to edit holdings, weights, and ticker symbols."""
    title = "How to build your portfolio" if beginner_mode else "Portfolio editor guide"
    with st.expander(title, expanded=beginner_mode):
        st.markdown(
            """
**Add a holding**
- Click the **+** row at the bottom of the table and type a ticker, **or**
- Use the **Quick-add popular ETFs** buttons below this guide.

**Remove a holding**
- Click the row you want to remove, then press **Delete** / trash (or clear the Ticker cell).

**Change allocation percentages**
- Edit the **Weight (%)** column for each fund.
- Aim for weights that add up to **100%** (the app normalizes small rounding gaps).

**What is a ticker symbol?**
- A short code for a fund or stock on Yahoo Finance — for example **VTI** (US total market)
  or **BND** (US bonds).

**How to find valid tickers**
- Search on [Yahoo Finance](https://finance.yahoo.com/) or your broker’s fund screener.
- Use the fund name on the provider site (Vanguard, Schwab, iShares) — the ticker is listed there.
- Stick to common ETFs until you are comfortable; invalid symbols will fail analysis.
            """.strip()
        )
        st.caption(
            f"When holdings look right, click **Use this portfolio** (or **Confirm portfolio**), "
            f"then open **Analysis** and click **{RUN_PORTFOLIO_ANALYSIS_LABEL}**."
        )


def render_common_etf_quick_add(
    apply_preset: Callable[[str], None],
    st_obj: Any | None = None,
) -> bool:
    """
    Six preset buttons for VTI, BND, VYM, SCHD, VXUS, VNQ.

    Returns True when a preset was applied (caller should rerun).
    """
    _st = st_obj or st
    _st.markdown("**Quick-add popular ETFs**")
    _st.caption(
        "Adds the fund to your table if it is not already there — set the **Weight (%)** yourself."
    )
    cols = _st.columns(len(core.COMMON_ETF_QUICK_ADD))
    clicked = False
    for col, preset_key in zip(cols, core.COMMON_ETF_QUICK_ADD):
        info = core.ASSET_PRESETS[preset_key]
        ticker = info["ticker"]
        with col:
            if _st.button(
                ticker,
                key=f"etf_quick_{ticker}",
                use_container_width=True,
                help=f"{preset_key} · {info['category']}",
            ):
                apply_preset(preset_key)
                clicked = True
    return clicked
