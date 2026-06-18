"""Portfolio holdings editor — add/remove controls, auto asset types."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import etf_holdings as eh

_ASSET_TYPE_OPTIONS = ["Equity", "Bonds", "T-Bills", "REIT", "Dividend ETF", "Other"]


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
    return out


def _tickers_in_df(df: pd.DataFrame) -> list[str]:
    clean = df.dropna(subset=["Ticker"]).copy()
    clean["Ticker"] = clean["Ticker"].astype(str).str.strip().str.upper()
    return [t for t in clean["Ticker"].tolist() if t]


def _ticker_signature(df: pd.DataFrame) -> tuple[str, ...]:
    return tuple(_tickers_in_df(df))


def _enrich_for_mode(df: pd.DataFrame, st_obj: Any, *, beginner_mode: bool) -> pd.DataFrame:
    """Auto-fill asset types when tickers change; preserve manual edits in beginner mode."""
    out = _normalize_holdings_df(df)
    sig = _ticker_signature(out)
    sig_key = "_holdings_ticker_sig"
    if beginner_mode and _session_get(st_obj, sig_key) == sig:
        return out
    enriched = eh.enrich_holdings_asset_types(out)
    _session_set(st_obj, sig_key, sig)
    return enriched


def remove_holdings_row(st_obj: Any, row_index: int) -> bool:
    """Remove a single row by positional index. Returns True when removed."""
    df = _normalize_holdings_df(_session_get(st_obj, "holdings_df"))
    if df.empty or row_index < 0 or row_index >= len(df):
        return False
    out = df.drop(index=row_index).reset_index(drop=True)
    _session_set(st_obj, "holdings_df", out)
    _session_set(st_obj, "portfolio_built", False)
    _session_pop(st_obj, "_holdings_ticker_sig", None)
    return True


def _row_delete_labels(df: pd.DataFrame) -> list[str]:
    labels: list[str] = []
    for i, row in df.iterrows():
        ticker = str(row.get("Ticker") or "").strip().upper() or "(empty)"
        try:
            weight = float(row.get("Weight (%)") or 0)
            weight_text = f"{weight:.1f}%"
        except (TypeError, ValueError):
            weight_text = "—"
        labels.append(f"Row {int(i) + 1}: {ticker} — {weight_text}")
    return labels


def render_delete_row_control(st_obj: Any | None = None, *, beginner_mode: bool = False) -> bool:
    """
    Select a table row and delete it with a visible trash button.

    Returns True when a row was removed (caller should rerun).
    """
    _st = st_obj or st
    df = _normalize_holdings_df(_session_get(_st, "holdings_df"))
    if df.empty:
        return False

    labels = _row_delete_labels(df)
    pick_col, btn_col = _st.columns([4, 1])
    with pick_col:
        selected = _st.selectbox(
            "Row to delete",
            options=list(range(len(labels))),
            format_func=lambda i: labels[i],
            key="portfolio_delete_row_select",
            label_visibility="collapsed" if beginner_mode else "visible",
        )
    with btn_col:
        _st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if _st.button(
            "🗑 Delete selected row",
            key="portfolio_delete_row_btn",
            use_container_width=True,
            help="Remove the selected holding from your portfolio",
        ):
            if remove_holdings_row(_st, int(selected)):
                ticker = labels[int(selected)].split(":")[1].split("—")[0].strip()
                _st.session_state["_portfolio_editor_flash"] = (
                    "success",
                    f"Removed **{ticker}** from your portfolio.",
                )
                return True
            _st.session_state["_portfolio_editor_flash"] = (
                "warning",
                "Could not remove that row — try again.",
            )
            return True

    flash = _st.session_state.pop("_portfolio_editor_flash", None)
    if isinstance(flash, tuple) and len(flash) == 2:
        level, msg = flash
        if level == "success":
            _st.success(msg)
        elif level == "warning":
            _st.warning(msg)
        else:
            _st.info(msg)

    return False


def _render_fund_metadata(df: pd.DataFrame, st_obj: Any) -> None:
    """Advanced-only fund details panel."""
    meta = eh.holdings_metadata_table(df)
    if meta.empty:
        return
    st_obj.markdown("**Fund details (auto-detected)**")
    st_obj.caption("Classification updates when you change tickers in the table above.")
    st_obj.dataframe(
        meta,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ticker": st_obj.column_config.TextColumn(width="small"),
            "Fund": st_obj.column_config.TextColumn(width="medium"),
            "Category": st_obj.column_config.TextColumn(width="large"),
            "Asset Type": st_obj.column_config.TextColumn(width="small"),
        },
    )


def render_holdings_editor_table(
    st_obj: Any | None = None,
    *,
    beginner_mode: bool = False,
) -> pd.DataFrame:
    """Render the holdings data editor and return the edited dataframe."""
    _st = st_obj or st
    df = _normalize_holdings_df(_session_get(_st, "holdings_df"))

    if not beginner_mode:
        _st.markdown("**Your holdings**")
        _st.caption(
            "Use the **+** at the bottom of the table to add a row. "
            "**Asset type** is auto-detected when you enter a ticker."
        )

    asset_type_column: Any
    if beginner_mode:
        asset_type_column = st.column_config.SelectboxColumn(
            options=_ASSET_TYPE_OPTIONS,
            help="Usually auto-filled when you enter a ticker — change only if needed",
        )
    else:
        asset_type_column = st.column_config.TextColumn(
            disabled=True,
            help="Auto-detected from ticker",
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
            "Asset Type": asset_type_column,
        },
        key="holdings_editor",
        hide_index=True,
    )

    if render_delete_row_control(_st, beginner_mode=beginner_mode):
        return None  # caller reruns after row removal

    enriched = _enrich_for_mode(edited, _st, beginner_mode=beginner_mode)
    _session_set(_st, "holdings_df", enriched)

    if not beginner_mode:
        _render_fund_metadata(enriched, _st)

    return enriched


def render_portfolio_inputs_section(
    st_obj: Any | None = None,
    *,
    beginner_mode: bool = False,
    apply_asset_preset: Any | None = None,
) -> pd.DataFrame | None:
    """
    Portfolio Inputs editor block.

    Beginner: one instruction box, simple table, trash delete.
    Advanced: reference expander, quick-add ETFs, fund metadata.

    Returns edited holdings_df, or None if a rerun was triggered mid-render.
    """
    _st = st_obj or st

    try:
        from components.portfolio_editor_guidance import (
            render_common_etf_quick_add,
            render_portfolio_editor_guidance,
        )

        render_portfolio_editor_guidance(beginner_mode=beginner_mode)

        if not beginner_mode and apply_asset_preset and render_common_etf_quick_add(apply_asset_preset, _st):
            return None
    except ImportError:
        pass

    return render_holdings_editor_table(_st, beginner_mode=beginner_mode)
