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
            f"**Path:** Goal → Portfolio → **{RUN_PORTFOLIO_ANALYSIS_LABEL}** → Health → Recommendations. "
            "Each step has one button to mark it done."
        )
    else:
        st.caption(
            f"**Path:** Confirm holdings → **{RUN_PORTFOLIO_ANALYSIS_LABEL}** → Review Health → "
            "Confirm recommendations. Risk & Macro charts are optional extras."
        )


def render_portfolio_editor_guidance(*, beginner_mode: bool) -> None:
    """Explain how to edit holdings, weights, and ticker symbols."""
    title = "How to build your portfolio" if beginner_mode else "Portfolio editor guide"
    with st.expander(title, expanded=beginner_mode):
        st.markdown(
            """
| Action | How |
|--------|-----|
| **Add** | Click **+** at the table bottom, or tap an ETF button below |
| **Remove** | Select the row → Delete (or clear Ticker) |
| **Change %** | Edit **Weight (%)** — aim for **100%** total |

**Ticker** = fund code on Yahoo Finance (e.g. **VTI**, **BND**). Search [Yahoo Finance](https://finance.yahoo.com/) or your broker to find one.
            """.strip()
        )
        st.caption(
            f"Done editing? Click **Use this portfolio**, then **{RUN_PORTFOLIO_ANALYSIS_LABEL}** on the Analysis tab."
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
