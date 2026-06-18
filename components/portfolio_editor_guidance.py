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


def render_beginner_portfolio_instructions() -> None:
    """Single instruction box for the beginner Portfolio Inputs page."""
    st.info(
        f"""**Build your portfolio:**

- Add a holding with the **+** row at the bottom of the table, or use **Quick Add ETFs** in the side panel.
- Edit **ticker**, **weight**, and **asset type** directly in the table.
- Select a row and click the **trash can** to delete it.
- Make sure weights add to **100%**.
- Click **{RUN_PORTFOLIO_ANALYSIS_LABEL}**."""
    )


def render_portfolio_editor_guidance(*, beginner_mode: bool) -> None:
    """Portfolio editor tips — one simple box for beginner, reference expander for advanced."""
    if beginner_mode:
        render_beginner_portfolio_instructions()
        return

    with st.expander("Portfolio editor reference", expanded=False):
        st.markdown(
            f"""
| Action | How |
|--------|-----|
| **Add** | **+** row at the table bottom, sidebar **Portfolio Presets**, or quick-add ETF buttons below |
| **Remove** | Select a row, then **🗑 Delete selected row** |
| **Replace** | Edit the **Ticker** cell, or delete the row and add a new one |
| **Asset type** | Auto-detected from ticker (editable in table); see **Fund details** below |

Use sidebar **Portfolio Presets** to load sample allocations. **Ticker** = Yahoo Finance symbol (e.g. **VTI**, **BND**, **QQQ**).
            """.strip()
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
