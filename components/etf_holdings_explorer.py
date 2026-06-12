"""Advanced Mode — ETF Holdings Explorer UI."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import etf_holdings as eh
from components.ui_helpers import APP_DISCLAIMER


def _section_header(title: str, lead: str = "") -> None:
    st.markdown(f"### {title}")
    if lead:
        st.markdown(lead)


def _data_source_badge(source: str) -> str:
    labels = {
        "live": "Live data (Yahoo Finance)",
        "sample": "Sample / illustrative holdings",
        "unavailable": "Holdings unavailable — try another symbol",
    }
    return labels.get(source, source)


def render_etf_ticker_chip_bar(
    tickers: list[str],
    *,
    key_prefix: str = "etf_chip",
) -> None:
    """Clickable ETF chips — sets session etf_explorer_ticker and switches tab."""
    etfs = [t.upper() for t in tickers if str(t).strip()]
    if not etfs:
        return
    st.caption("Click an ETF to open **ETF Holdings Explorer**:")
    cols = st.columns(min(len(etfs), 6))
    for i, sym in enumerate(etfs[:12]):
        with cols[i % len(cols)]:
            if st.button(sym, key=f"{key_prefix}_{sym}", use_container_width=True):
                st.session_state["etf_explorer_ticker"] = sym
                st.session_state["_pending_investment_tab"] = "ETF Holdings Explorer"
                st.rerun()


def render_etf_holdings_explorer(
    holdings_df: pd.DataFrame,
    *,
    settings: dict[str, Any] | None = None,
) -> None:
    _section_header(
        "ETF Holdings Explorer",
        f"See what your ETFs actually hold — underlying stocks, sectors, and overlap. {APP_DISCLAIMER}",
    )

    portfolio_etfs = eh.portfolio_etf_tickers(holdings_df)
    default_t = st.session_state.get("etf_explorer_ticker") or (portfolio_etfs[0][0] if portfolio_etfs else "VTI")
    picker_options = list(dict.fromkeys([t for t, _ in portfolio_etfs] + list(eh.POPULAR_ETF_TICKERS)))

    c1, c2 = st.columns([2, 1])
    with c1:
        selected = st.selectbox(
            "ETF ticker",
            options=picker_options,
            index=picker_options.index(default_t) if default_t in picker_options else 0,
            key="etf_explorer_select",
        )
    with c2:
        custom = st.text_input("Or enter ticker", value="", key="etf_explorer_custom").strip().upper()
    ticker = custom or str(selected).upper()

    try:
        result = eh.lookup_etf(ticker)
    except ValueError:
        st.warning("Enter a valid ETF ticker.")
        return

    st.caption(_data_source_badge(result.data_source))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ETF", result.ticker)
    m2.metric("Issuer", result.issuer[:24])
    m3.metric("Asset class", result.asset_class)
    exp = f"{result.expense_ratio_pct:.2f}%" if result.expense_ratio_pct is not None else "—"
    m4.metric("Expense ratio", exp)
    st.markdown(f"**{result.name}** · {result.category}")

    if result.holdings.empty:
        st.info("No holdings breakdown available for this symbol.")
        return

    show_n = st.radio(
        "Show holdings",
        ["Top 10", "Top 25", "All available"],
        horizontal=True,
        key="etf_holdings_depth",
        label_visibility="collapsed",
    )
    n = {"Top 10": 10, "Top 25": 25, "All available": 999}[show_n]
    display = result.holdings.head(n).copy()
    if "weight" in display.columns:
        display["weight_pct"] = display["weight"].map(lambda x: f"{float(x) * 100:.2f}%")
    price_col = display.get("price")
    if price_col is not None:
        display["price"] = display["price"].map(lambda x: f"${x:,.2f}" if x else "—")
    st.dataframe(
        display[["symbol", "name", "weight_pct", "sector", "price"]].rename(
            columns={
                "symbol": "Ticker",
                "name": "Company",
                "weight_pct": "Weight in ETF",
                "sector": "Sector",
                "price": "Price",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    if not result.sectors.empty:
        st.markdown("#### Sector breakdown")
        st.dataframe(result.sectors, use_container_width=True, hide_index=True)

    hhi = eh.concentration_hhi(result.holdings["weight"])
    st.metric("Concentration score (HHI)", f"{hhi:.3f}", help="Higher = top holdings dominate the ETF.")

    if portfolio_etfs:
        st.markdown("---")
        st.markdown("#### Your portfolio — underlying exposure")
        st.caption("Combines overlapping holdings across ETFs you own.")
        holdings_map: dict[str, pd.DataFrame] = {ticker: result.holdings}
        for etf, _w in portfolio_etfs:
            if etf == ticker:
                continue
            try:
                holdings_map[etf] = eh.lookup_etf(etf).holdings
            except Exception:
                holdings_map[etf] = pd.DataFrame()
        exposure = eh.aggregate_underlying_exposure(portfolio_etfs, holdings_by_etf=holdings_map)
        if not exposure.empty:
            top = exposure.head(15).copy()
            top["portfolio_weight_pct"] = top["portfolio_weight_pct"].map(lambda x: f"{x:.2f}%")
            st.dataframe(
                top[["symbol", "name", "portfolio_weight_pct", "sector", "sources"]].rename(
                    columns={
                        "symbol": "Ticker",
                        "name": "Company",
                        "portfolio_weight_pct": "Est. portfolio %",
                        "sector": "Sector",
                        "sources": "From ETFs",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            port_hhi = eh.concentration_hhi(exposure["portfolio_weight"])
            st.metric("Portfolio underlying concentration (HHI)", f"{port_hhi:.3f}")

        etf_list = [t for t, _ in portfolio_etfs]
        warnings = eh.overlap_warnings(etf_list, holdings_map)
        for w in warnings:
            st.warning(w)

        if len(etf_list) >= 2:
            st.markdown("#### ETF overlap comparison")
            rows = []
            for i, t1 in enumerate(etf_list):
                for t2 in etf_list[i + 1 :]:
                    ov = eh.pairwise_etf_overlap(holdings_map.get(t1, pd.DataFrame()), holdings_map.get(t2, pd.DataFrame()))
                    rows.append({"ETF A": t1, "ETF B": t2, "Overlap": f"{ov * 100:.1f}%"})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
