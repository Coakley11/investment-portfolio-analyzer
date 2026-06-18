"""Portfolio holdings editor — add/remove controls, quick loaders, auto asset types."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import portfolio_core as core
import etf_holdings as eh


def _session_get(st_obj: Any, key: str, default: Any = None) -> Any:
    ss = st_obj.session_state
    if hasattr(ss, "get"):
        return ss.get(key, default)
    return getattr(ss, key, default)


def _session_set(st_obj: Any, key: str, value: Any) -> None:
    ss = st_obj.session_state
    if hasattr(ss, "__setitem__"):
        ss[key] = value
    else:
        setattr(ss, key, value)


def _session_pop(st_obj: Any, key: str, default: Any = None) -> Any:
    ss = st_obj.session_state
    if hasattr(ss, "pop"):
        return ss.pop(key, default)
    val = getattr(ss, key, default)
    if hasattr(ss, "__delitem__") and key in ss:
        del ss[key]
    elif hasattr(ss, key):
        delattr(ss, key)
    return val


def _normalize_holdings_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["Ticker", "Weight (%)", "Asset Type"])
    out = df.copy()
    for col in ("Ticker", "Weight (%)", "Asset Type"):
        if col not in out.columns:
            out[col] = "" if col == "Ticker" else (0.0 if col == "Weight (%)" else "Equity")
    return eh.enrich_holdings_asset_types(out)


def _tickers_in_df(df: pd.DataFrame) -> list[str]:
    clean = df.dropna(subset=["Ticker"]).copy()
    clean["Ticker"] = clean["Ticker"].astype(str).str.strip().str.upper()
    return [t for t in clean["Ticker"].tolist() if t]


def load_portfolio_preset(st_obj: Any, preset_key: str, *, source: str = "quick_load") -> bool:
    """Replace holdings with a full preset portfolio. Returns True if loaded."""
    rows = core.PORTFOLIO_PRESETS.get(preset_key)
    if not rows:
        return False
    _session_set(st_obj, "holdings_df", pd.DataFrame(rows))
    _session_set(st_obj, "preset_applied", preset_key)
    _session_set(st_obj, "portfolio_built", False)
    _session_pop(st_obj, "health_summary", None)
    try:
        from investment_workflow import invalidate_workflow_from

        invalidate_workflow_from("portfolio")
    except ImportError:
        pass
    try:
        from investment_persistent_state import notify_portfolio_change

        notify_portfolio_change(st_obj, source=source)
    except Exception:
        pass
    return True


def add_holding_ticker(st_obj: Any, ticker: str, *, weight_pct: float = 0.0) -> bool:
    """Append a ticker row if not already present. Returns True when added."""
    sym = str(ticker or "").strip().upper()
    if not sym:
        return False
    df = _normalize_holdings_df(_session_get(st_obj, "holdings_df"))
    existing = set(_tickers_in_df(df))
    if sym in existing:
        return False
    info = eh.infer_portfolio_fund_info(sym)
    row = pd.DataFrame(
        [{"Ticker": sym, "Weight (%)": float(weight_pct), "Asset Type": info["asset_type"]}]
    )
    if df.empty:
        _session_set(st_obj, "holdings_df", row)
    else:
        _session_set(st_obj, "holdings_df", pd.concat([df, row], ignore_index=True))
    try:
        from investment_activity import log_ticker_analyzed

        log_ticker_analyzed(st_obj, ticker=sym)
    except Exception:
        pass
    return True


def remove_holding_ticker(st_obj: Any, ticker: str) -> bool:
    """Remove all rows matching ticker. Returns True when a row was removed."""
    sym = str(ticker or "").strip().upper()
    if not sym:
        return False
    df = _normalize_holdings_df(_session_get(st_obj, "holdings_df"))
    if df.empty:
        return False
    mask = df["Ticker"].astype(str).str.strip().str.upper() != sym
    if mask.all():
        return False
    _session_set(st_obj, "holdings_df", df.loc[mask].reset_index(drop=True))
    _session_set(st_obj, "portfolio_built", False)
    return True


def append_empty_row(st_obj: Any) -> None:
    """Add a blank row for manual ticker entry in the table."""
    df = _normalize_holdings_df(_session_get(st_obj, "holdings_df"))
    blank = pd.DataFrame([{"Ticker": "", "Weight (%)": 0.0, "Asset Type": "Equity"}])
    _session_set(st_obj, "holdings_df", pd.concat([df, blank], ignore_index=True))


def render_quick_portfolio_loaders(st_obj: Any | None = None) -> bool:
    """
    One-click Balanced / Growth / Tech / Dividend test portfolios.

    Returns True when a preset was loaded (caller should rerun).
    """
    _st = st_obj or st
    _st.markdown("**Load test portfolio**")
    _st.caption("Replaces your current holdings with a ready-made mix — ideal for AMI validation.")
    cols = _st.columns(len(core.PORTFOLIO_QUICK_LOADERS))
    clicked = False
    for col, (label, preset_key) in zip(cols, core.PORTFOLIO_QUICK_LOADERS.items()):
        with col:
            if _st.button(
                f"Load {label}",
                key=f"portfolio_quick_{preset_key}",
                use_container_width=True,
                help=f"Load the {label} sample portfolio",
            ):
                if load_portfolio_preset(_st, preset_key, source=f"quick_{label.lower()}"):
                    clicked = True
    return clicked


def render_add_remove_controls(st_obj: Any | None = None) -> bool:
    """
    Explicit add / remove / add-row controls above the holdings table.

    Returns True when session holdings changed (caller should rerun).
    """
    _st = st_obj or st
    changed = False

    _st.markdown("**Add or remove holdings**")
    add_col, remove_col, row_col = _st.columns([2, 2, 1])

    with add_col:
        new_ticker = _st.text_input(
            "Ticker symbol",
            placeholder="e.g. QQQ, BND, SCHD",
            key="portfolio_add_ticker_input",
            label_visibility="collapsed",
        )
        if _st.button("➕ Add holding", key="portfolio_add_ticker_btn", use_container_width=True):
            sym = str(new_ticker or "").strip().upper()
            if not sym:
                _st.session_state["_portfolio_editor_flash"] = ("warning", "Enter a ticker symbol first.")
                changed = True
            elif sym in set(_tickers_in_df(_normalize_holdings_df(_st.session_state.get("holdings_df")))):
                _st.session_state["_portfolio_editor_flash"] = (
                    "info",
                    f"**{sym}** is already in your portfolio — edit its weight in the table.",
                )
                changed = True
            elif add_holding_ticker(_st, sym):
                info = eh.infer_portfolio_fund_info(sym)
                _st.session_state["_portfolio_editor_flash"] = (
                    "success",
                    f"Added **{sym}** — {info['category_label']} ({info['asset_type']}). Set **Weight (%)** below.",
                )
                changed = True

    with remove_col:
        tickers = _tickers_in_df(_normalize_holdings_df(_st.session_state.get("holdings_df")))
        remove_choice = _st.selectbox(
            "Remove holding",
            ["— select —", *tickers],
            key="portfolio_remove_select",
            label_visibility="collapsed",
        )
        if _st.button("🗑 Remove holding", key="portfolio_remove_btn", use_container_width=True):
            if remove_choice == "— select —" or not tickers:
                _st.session_state["_portfolio_editor_flash"] = (
                    "warning",
                    "Choose a ticker to remove, or clear the **Ticker** cell in the table.",
                )
                changed = True
            elif remove_holding_ticker(_st, remove_choice):
                _st.session_state["_portfolio_editor_flash"] = (
                    "success",
                    f"Removed **{remove_choice}** from your portfolio.",
                )
                changed = True

    with row_col:
        _st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        if _st.button("➕ Empty row", key="portfolio_add_empty_row", use_container_width=True):
            append_empty_row(_st)
            _st.session_state["_portfolio_editor_flash"] = (
                "info",
                "Empty row added — type a ticker and weight in the table below.",
            )
            changed = True

    flash = _st.session_state.pop("_portfolio_editor_flash", None)
    if isinstance(flash, tuple) and len(flash) == 2:
        level, msg = flash
        if level == "success":
            _st.success(msg)
        elif level == "warning":
            _st.warning(msg)
        else:
            _st.info(msg)

    return changed


def render_holdings_editor_table(
    st_obj: Any | None = None,
    *,
    beginner_mode: bool = False,
) -> pd.DataFrame:
    """Render the holdings data editor and return the edited dataframe."""
    _st = st_obj or st
    df = _normalize_holdings_df(_st.session_state.get("holdings_df"))

    _st.markdown("**Your holdings**")
    _st.caption(
        "Edit **Ticker** and **Weight (%)** in the table. "
        "**Asset Type** is filled in automatically. "
        "You can also use the small **+** at the bottom-right of the table to add a row, "
        "or select a row and press **Delete** on your keyboard."
    )

    edited = _st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Ticker": st.column_config.TextColumn(
                help="Yahoo Finance symbol (e.g. VTI, BND, QQQ)",
                required=True,
            ),
            "Weight (%)": st.column_config.NumberColumn(
                min_value=0,
                max_value=100,
                format="%.1f",
                help="Percent of portfolio (should total 100%)",
            ),
            "Asset Type": st.column_config.TextColumn(
                disabled=True,
                help="Auto-detected from ticker — you do not need to set this manually",
            ),
        },
        key="holdings_editor",
        hide_index=True,
    )
    enriched = eh.enrich_holdings_asset_types(edited)
    _st.session_state.holdings_df = enriched

    meta = eh.holdings_metadata_table(enriched)
    if not meta.empty:
        _st.markdown("**Fund details (auto-detected)**")
        _st.dataframe(
            meta,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticker": st.column_config.TextColumn(width="small"),
                "Fund": st.column_config.TextColumn(width="medium"),
                "Category": st.column_config.TextColumn(width="large"),
                "Asset Type": st.column_config.TextColumn(width="small"),
            },
        )

    return enriched


def render_portfolio_inputs_section(
    st_obj: Any | None = None,
    *,
    beginner_mode: bool = False,
    apply_asset_preset: Any | None = None,
) -> pd.DataFrame | None:
    """
    Full Portfolio Inputs editor block: loaders, controls, table, quick-add ETFs.

    Returns edited holdings_df, or None if a rerun was triggered mid-render.
    """
    _st = st_obj or st

    try:
        from components.portfolio_editor_guidance import (
            render_common_etf_quick_add,
            render_portfolio_editor_guidance,
        )

        render_portfolio_editor_guidance(beginner_mode=beginner_mode)
    except ImportError:
        pass

    if render_quick_portfolio_loaders(_st):
        return None

    if render_add_remove_controls(_st):
        return None

    try:
        from components.portfolio_editor_guidance import render_common_etf_quick_add

        if apply_asset_preset and render_common_etf_quick_add(apply_asset_preset, _st):
            return None
    except ImportError:
        pass

    return render_holdings_editor_table(_st, beginner_mode=beginner_mode)
