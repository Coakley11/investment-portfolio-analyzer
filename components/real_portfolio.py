"""Real portfolio UI — dashboard, positions, transactions, and position sizing."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import dashboard_charts as charts
import portfolio_engine as pe
from components.ui_helpers import APP_DISCLAIMER

REAL_PORTFOLIO_SUBTABS = (
    "Dashboard",
    "Positions",
    "Transactions",
    "Allocate New Money",
    "Position Sizing",
)

SESSION_TRANSACTIONS_KEY = "portfolio_transactions"
SESSION_SUBTAB_KEY = "real_portfolio_subtab"
SESSION_CONTRIBUTION_TARGETS_KEY = "real_portfolio_contribution_target_weights"
# Visible in Transactions UI — bump when cash-form or ledger behavior changes.
REAL_PORTFOLIO_BUILD_ID = "2026-09-09-contribution-prices-v2-instrument-alloc"


def _ss() -> Any:
    return st.session_state


def get_portfolio_transactions() -> list[pe.PortfolioTransaction]:
    records = _ss().get(SESSION_TRANSACTIONS_KEY) or []
    if not isinstance(records, list):
        return []
    return pe.transactions_from_records(records)


def set_portfolio_transactions(transactions: list[pe.PortfolioTransaction]) -> None:
    _ss()[SESSION_TRANSACTIONS_KEY] = pe.transactions_to_records(transactions)
    _ss()["_real_portfolio_ledger_touched"] = True


def _persist_portfolio_ledger_change(*, trigger: str = "portfolio_transactions_change") -> tuple[bool, str]:
    try:
        from investment_persistent_state import persist_portfolio_transactions_after_change

        return persist_portfolio_transactions_after_change(st, trigger=trigger)
    except ImportError:
        return False, "Persistence unavailable."


def _persist_new_transaction(
    transactions: list[pe.PortfolioTransaction],
    txn: pe.PortfolioTransaction,
) -> None:
    set_portfolio_transactions(transactions + [txn])
    ok, msg = _persist_portfolio_ledger_change()
    if ok:
        st.success(msg)
    else:
        st.error(msg)
    st.rerun()


def _hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0f2847 0%,#141c2b 100%);
        border:1px solid rgba(77,163,255,0.35);border-radius:14px;padding:1.1rem 1.25rem;margin-bottom:1rem;">
        <div style="font-size:1.35rem;font-weight:700;color:#f1f5f9;">{title}</div>
        <div style="color:#94a3b8;font-size:0.92rem;margin-top:0.35rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_row(cols: list, labels: list[str], values: list[str], *, help_texts: list[str] | None = None) -> None:
    for col, label, value in zip(cols, labels, values):
        with col:
            st.metric(label, value)


def _gain_color(value: float) -> str:
    if value > 0:
        return "#2ecc71"
    if value < 0:
        return "#e74c3c"
    return "#94a3b8"


def _format_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _format_gain(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{pe.format_currency(value)}"


def _render_cash_accounting_summary(transactions: list[pe.PortfolioTransaction]) -> None:
    if not transactions:
        return
    ledger = pe.compute_cash_ledger_summary(transactions)
    with st.expander("Cash accounting breakdown", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Deposits", pe.format_currency(ledger.total_deposits))
        c2.metric("Withdrawals", pe.format_currency(ledger.total_withdrawals))
        c3.metric("Buy costs", pe.format_currency(ledger.total_buy_cost))
        c4.metric("Sell proceeds", pe.format_currency(ledger.total_sell_proceeds))
        c5.metric("Net cash", pe.format_currency(ledger.net_cash))
        st.caption(
            "Net cash = deposits − withdrawals − buy costs + sell proceeds. "
            "Order of entry does not affect this balance."
        )
        if ledger.net_cash < -0.01:
            st.warning(
                "Cash is negative — purchases exceed deposits. Add a deposit or review transaction amounts."
            )


def render_portfolio_dashboard(*, beginner: bool = False) -> None:
    transactions = get_portfolio_transactions()
    summary = pe.compute_portfolio_summary(transactions)
    positions, cash = pe.build_positions(transactions)

    if not transactions:
        st.info(
            "No transactions yet. Open **Transactions** to record buys, sells, and cash deposits. "
            "Your dashboard will populate automatically."
        )
        return

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _metric_row(
        [c1, c2, c3, c4, c5, c6],
        [
            "Total Portfolio Value",
            "Total Invested",
            "Total Gain/Loss $",
            "Total Gain/Loss %",
            "Cash Balance",
            "Holdings",
        ],
        [
            pe.format_currency(summary.total_portfolio_value),
            pe.format_currency(summary.total_invested_capital),
            _format_gain(summary.total_gain_loss_dollar),
            _format_pct(summary.total_gain_loss_pct),
            pe.format_currency(summary.cash_balance),
            str(summary.num_holdings),
        ],
    )

    if summary.cash_balance < -0.01:
        st.warning(
            f"Cash balance is {pe.format_currency(summary.cash_balance)} — "
            "purchases exceed recorded deposits. Review transactions or add a deposit."
        )

    _render_cash_accounting_summary(transactions)

    st.markdown("#### Allocation")
    st.caption(
        "Instrument type from your transactions (Stock / ETF / Bond / Cash / Other) — "
        "not underlying economic exposure. Bond ETFs entered as ETF count as ETFs here."
    )
    a1, a2, a3, a4, a5 = st.columns(5)
    buckets = summary.allocation_by_bucket
    for col, key in zip([a1, a2, a3, a4, a5], ["Stocks", "ETFs", "Bonds", "Cash", "Other"]):
        with col:
            st.metric(f"{key} %", f"{buckets.get(key, 0.0):.1f}%")

    if positions:
        pos_df = pe.positions_to_dataframe(positions)
        chart_df = pos_df[["Ticker", "Weight %"]].copy()
        chart_df["Weight"] = chart_df["Weight %"] / 100.0
        st.plotly_chart(
            charts.allocation_chart(chart_df[["Ticker", "Weight"]]),
            use_container_width=True,
        )

    st.markdown("#### Position Weights")
    if summary.largest_position:
        lp = summary.largest_position
        sp = summary.smallest_position
        w1, w2 = st.columns(2)
        with w1:
            st.caption(f"**Largest:** {lp.ticker} — {lp.weight_pct:.1f}% ({pe.format_currency(lp.market_value)})")
        with w2:
            if sp:
                st.caption(f"**Smallest:** {sp.ticker} — {sp.weight_pct:.1f}% ({pe.format_currency(sp.market_value)})")

        weight_df = pos_df[["Ticker", "Company Name", "Weight %", "Market Value"]].copy()
        weight_df["Market Value"] = weight_df["Market Value"].map(pe.format_currency)
        st.dataframe(weight_df, use_container_width=True, hide_index=True)

    st.markdown("#### Performance")
    p1, p2, p3 = st.columns(3)
    with p1:
        st.markdown("**Top Gainers**")
        if summary.top_gainers:
            for p in summary.top_gainers:
                if p.gain_loss_pct > 0:
                    st.markdown(
                        f"- **{p.ticker}** {_format_pct(p.gain_loss_pct)} "
                        f"({_format_gain(p.gain_loss_dollar)})"
                    )
        else:
            st.caption("No gainers yet.")
    with p2:
        st.markdown("**Top Losers**")
        if summary.top_losers:
            for p in summary.top_losers:
                st.markdown(
                    f"- **{p.ticker}** {_format_pct(p.gain_loss_pct)} "
                    f"({_format_gain(p.gain_loss_dollar)})"
                )
        else:
            st.caption("No losers yet.")
    with p3:
        st.markdown("**Biggest Positions**")
        for p in summary.biggest_positions:
            st.markdown(f"- **{p.ticker}** {p.weight_pct:.1f}% — {pe.format_currency(p.market_value)}")

    st.caption(f"Manual entry portfolio tracker. {APP_DISCLAIMER}")


def render_portfolio_positions(*, beginner: bool = False) -> None:
    transactions = get_portfolio_transactions()
    positions, cash = pe.build_positions(transactions)

    if not positions and not transactions:
        st.info("Add transactions to build your position list.")
        return

    st.caption(
        f"Live prices via yfinance (last traded / closing price). Cash balance: **{pe.format_currency(cash)}**"
    )
    split_adjusted = [p for p in positions if p.stock_splits_applied > 0]
    if split_adjusted:
        tickers = ", ".join(
            f"{p.ticker} ({p.stock_splits_applied} split{'s' if p.stock_splits_applied != 1 else ''})"
            for p in split_adjusted
        )
        st.caption(f"Share counts adjusted for stock splits: {tickers}.")
    if positions:
        sources = pe.fetch_price_sources([p.ticker for p in positions])
        if sources:
            src_line = ", ".join(f"{sym} ({src})" for sym, src in sorted(sources.items()))
            st.caption(f"Quote sources: {src_line}")
    df = pe.positions_to_dataframe(positions)
    if df.empty:
        st.warning("No open positions — cash-only portfolio or all positions sold.")
        return

    display = df.copy()
    display["Shares Owned"] = display["Shares Owned"].map(pe.format_shares)
    display["Avg Cost Basis"] = display["Avg Cost Basis"].map(pe.format_currency)
    display["Current Price"] = display["Current Price"].map(pe.format_currency)
    display["Market Value"] = display["Market Value"].map(pe.format_currency)
    display["Gain/Loss $"] = df["Gain/Loss $"].map(_format_gain)
    display["Gain/Loss %"] = df["Gain/Loss %"].map(_format_pct)
    display["Weight %"] = df["Weight %"].map(lambda x: f"{x:.2f}%")

    st.dataframe(display, use_container_width=True, hide_index=True)


_BUY_SELL_ASSET_TYPES = ("stock", "etf", "bond", "other")
_CASH_ACTIONS = frozenset({"cash_deposit", "cash_withdrawal"})


def render_portfolio_transactions(*, beginner: bool = False) -> None:
    transactions = get_portfolio_transactions()

    st.markdown("##### Add Transaction")
    st.caption(f"Form build: `{REAL_PORTFOLIO_BUILD_ID}` — Cash Deposit shows Date + Amount only.")
    action = st.selectbox(
        "Action",
        ["buy", "sell", "cash_deposit", "cash_withdrawal"],
        format_func=lambda x: x.replace("_", " ").title(),
        key="real_portfolio_txn_action",
    )
    is_cash = action in _CASH_ACTIONS

    with st.form("real_portfolio_add_txn", clear_on_submit=True):
        txn_date = st.date_input("Date")
        if is_cash:
            amount = st.number_input(
                "Amount ($)",
                min_value=0.0,
                value=0.0,
                step=100.0,
                help="Dollar amount to deposit or withdraw from cash balance.",
            )
            notes = st.text_input("Notes", placeholder="Optional")
        else:
            c1, c2 = st.columns(2)
            with c1:
                ticker = st.text_input("Ticker", placeholder="VOO")
                quantity = st.number_input("Quantity (shares)", min_value=0.0, value=0.0, step=1.0)
            with c2:
                price = st.number_input("Execution price ($)", min_value=0.0, value=0.0, step=0.01)
                notes = st.text_input("Notes", placeholder="Optional")
            asset_type = st.selectbox(
                "Asset type",
                list(_BUY_SELL_ASSET_TYPES),
                index=0,
                help="Used for allocation breakdown.",
            )
        submitted = st.form_submit_button("Add Transaction", type="primary")

    if submitted:
        if is_cash:
            if amount <= 0:
                st.error("Enter an amount greater than zero.")
            else:
                txn = pe.PortfolioTransaction(
                    id=pe._new_id(),
                    action=action,  # type: ignore[arg-type]
                    date=txn_date.isoformat(),
                    ticker="",
                    quantity=float(amount),
                    execution_price=1.0,
                    notes=notes,
                    company_name="Cash",
                    asset_type="cash",
                )
                _persist_new_transaction(transactions, txn)
        else:
            sym = str(ticker or "").strip().upper()
            if not sym:
                st.error("Enter a ticker for buy/sell transactions.")
            elif quantity <= 0:
                st.error("Quantity must be greater than zero.")
            elif price <= 0:
                st.error("Execution price must be greater than zero.")
            else:
                # Persist the selectbox instrument type as-is. Never pass ticker into
                # classification here — bond-fund economics belong in AMI/drift only.
                instrument = pe.canonicalize_instrument_type(asset_type)
                if instrument is None:
                    instrument = pe.resolve_instrument_type(asset_type, "")
                txn = pe.PortfolioTransaction(
                    id=pe._new_id(),
                    action=action,  # type: ignore[arg-type]
                    date=txn_date.isoformat(),
                    ticker=sym,
                    quantity=quantity,
                    execution_price=price,
                    notes=notes,
                    company_name=pe.infer_company_name(sym),
                    asset_type=instrument,
                )
                _persist_new_transaction(transactions, txn)

    st.markdown("##### Transaction History")
    if not transactions:
        st.caption("No transactions recorded yet.")
        return

    df = pe.transactions_display_dataframe(transactions)
    st.dataframe(
        pe.style_transaction_history_dataframe(df),
        use_container_width=True,
        hide_index=True,
    )

    _render_cash_accounting_summary(transactions)

    st.markdown("##### Remove Transaction")
    options = {f"{t.date} · {t.action} · {t.ticker or 'CASH'} · {t.quantity}": t.id for t in reversed(transactions)}
    pick = st.selectbox("Select transaction to delete", [""] + list(options.keys()))
    if st.button("Delete Selected", disabled=not pick):
        txn_id = options.get(pick)
        if txn_id:
            set_portfolio_transactions([t for t in transactions if t.id != txn_id])
            ok, msg = _persist_portfolio_ledger_change()
            if ok:
                st.success(msg)
            else:
                st.error(msg)
            st.rerun()


def render_allocate_new_money(*, beginner: bool = False) -> None:
    """Contribution Advisor UI — new-money-only placement against an explicit target source."""
    st.markdown("##### Allocate New Money")
    st.caption(
        "Decide where an additional contribution should go using your **real portfolio ledger** "
        "and a clearly selected target. New-money-only mode does not sell existing holdings. "
        "Decision support only — not a trade order."
    )

    from investment_ami.decision_support.contribution_advisor import (
        recommend_contribution_allocation_from_session,
    )
    from investment_ami.decision_support.real_portfolio_snapshot import (
        build_real_portfolio_snapshot,
        unpriced_holding_tickers,
    )

    built = build_real_portfolio_snapshot(_ss())
    if not built.ok or built.snapshot is None:
        st.info(
            "No real portfolio ledger yet. Add buys/sells/deposits under **Transactions** first. "
            "Model / demo holdings are never used for this recommendation."
        )
        return

    snap = built.snapshot
    missing = unpriced_holding_tickers(snap)
    if missing or snap.unpriced_holdings_count > 0 or snap.market_data_status in ("partial", "unavailable"):
        named = ", ".join(missing) if missing else "one or more holdings"
        st.warning(
            f"**Missing market marks for:** {named}. "
            "Dashboard/Positions may still show a cost-basis estimate for those names "
            "(avg-cost fallback). Contribution Advisor uses the ledger snapshot **without** "
            "inventing prices — precise $ allocation stays blocked until marks are available. "
            "Non-quotable tickers (CASH, US TREASURY, …) need a different instrument treatment."
        )
        # Show snapshot status so the user can compare with Positions.
        priced = [h for h in snap.holdings if h.current_price is not None]
        if priced:
            src = ", ".join(
                f"{h.ticker} @ {pe.format_currency(float(h.current_price))} ({h.price_source or 'quote'})"
                for h in priced[:8]
            )
            st.caption(f"Priced marks in use: {src}")
        if missing:
            st.caption(
                "Unpriced ledger positions: "
                + ", ".join(
                    f"{h.ticker} ({h.shares:g} sh, flags={','.join(h.data_quality_flags) or 'none'})"
                    for h in snap.holdings
                    if h.ticker in missing
                )
            )

    c1, c2 = st.columns([1, 2])
    with c1:
        amount = st.number_input(
            "New contribution ($)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            key="contribution_advisor_amount",
            help="External new money to invest — not treated as investment profit. Calculate does not record a deposit or buy.",
        )
    with c2:
        source_label = st.selectbox(
            "Target source",
            [
                "My target weights (explicit)",
                "Recommended from stated objective (labeled)",
                "Current mix (already on strategy)",
            ],
            key="contribution_advisor_target_source",
            help=(
                "Explicit targets are yours. Stated-objective mix is a recommended sleeve mapping — "
                "not a silently saved personal target. Current mix distributes like target = today."
            ),
        )

    source_map = {
        "My target weights (explicit)": "user_explicit",
        "Recommended from stated objective (labeled)": "stated_objective_recommended",
        "Current mix (already on strategy)": "current_mix",
    }
    target_source = source_map[source_label]

    explicit: dict[str, float] | None = None
    if target_source == "user_explicit":
        priced = [h for h in snap.holdings if h.current_price is not None]
        if not priced and snap.cash <= 0:
            st.warning("No priced holdings available.")
            return
        st.markdown("**My target weights (%)** — must sum near 100.")
        st.caption(
            "Draft fields below are **seeded from your current portfolio weights** as a starting "
            "point — not Health objective weights, not optimizer corners, and not a previously "
            "saved personal target. Edit them to define your explicit target."
        )
        saved = _ss().get(SESSION_CONTRIBUTION_TARGETS_KEY)
        if not isinstance(saved, dict):
            saved = {}
        # Prefer last edited explicit draft; otherwise seed from current mix (labeled above).
        cols = st.columns(min(4, max(1, len(priced) + (1 if snap.cash > 0 else 0))))
        explicit = {}
        for i, h in enumerate(priced):
            default = float(saved.get(h.ticker, h.current_weight))
            with cols[i % len(cols)]:
                explicit[h.ticker] = st.number_input(
                    f"{h.ticker} target %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(default),
                    step=1.0,
                    key=f"contrib_tgt_{h.ticker}",
                )
        if snap.cash > 0:
            with cols[len(priced) % len(cols)]:
                explicit["$CASH"] = st.number_input(
                    "$CASH target %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(saved.get("$CASH", snap.allocation_by_holding.get("$CASH", 0.0))),
                    step=1.0,
                    key="contrib_tgt_cash",
                )
        _ss()[SESSION_CONTRIBUTION_TARGETS_KEY] = dict(explicit)
        st.caption(f"Target sum: **{sum(explicit.values()):.1f}%**")

    if beginner:
        st.caption(
            "Tip: if one holding is behind its target, most of the new money usually goes there first."
        )

    run = st.button("Calculate allocation", type="primary", key="contribution_advisor_run")
    if not run:
        prior = _ss().get("_contribution_advisor_result")
        if isinstance(prior, dict) and prior.get("ok"):
            _render_contribution_result(prior)
        return

    result = recommend_contribution_allocation_from_session(
        _ss(),
        contribution_amount=float(amount),
        target_source=target_source,  # type: ignore[arg-type]
        explicit_holding_targets=explicit,
        include_cash=True,
    )
    payload = result.to_dict()
    _ss()["_contribution_advisor_result"] = payload
    # Decision support only — never write deposits/buys from Calculate.
    if not result.ok:
        st.error(result.explanation)
        for w in result.warnings:
            st.warning(w)
        return
    _render_contribution_result(payload)


def _render_contribution_result(payload: dict) -> None:
    st.success(payload.get("explanation") or "Allocation ready.")
    st.caption(
        "Decision support only — this calculation does **not** record a cash deposit or buy "
        "in your transaction ledger, and does not count the contribution as investment profit."
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Portfolio before", pe.format_currency(float(payload.get("portfolio_value_before") or 0)))
    m2.metric("New contribution", pe.format_currency(float(payload.get("contribution_amount") or 0)))
    m3.metric("Portfolio after", pe.format_currency(float(payload.get("portfolio_value_after") or 0)))
    m4.metric(
        "Abs. drift before → after",
        f"{100 * float(payload.get('aggregate_drift_before') or 0):.1f} → "
        f"{100 * float(payload.get('aggregate_drift_after') or 0):.1f} pp",
    )
    rows = payload.get("rows") or []
    if rows:
        df = pd.DataFrame(
            [
                {
                    "Holding": r["ticker"],
                    "Current Value": round(float(r["current_value"]), 2),
                    "Current %": round(100 * float(r["current_weight"]), 2),
                    "Target %": round(100 * float(r["target_weight"]), 2),
                    "Drift pp": round(100 * float(r["drift"]), 2),
                    "Add New Money": round(float(r["recommended_add"]), 2),
                    "Projected Value": round(float(r["projected_value"]), 2),
                    "Projected %": round(100 * float(r["projected_weight"]), 2),
                    "Remaining drift pp": round(100 * float(r["remaining_drift"]), 2),
                }
                for r in rows
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    if payload.get("assumptions"):
        with st.expander("Assumptions", expanded=False):
            for a in payload["assumptions"]:
                st.markdown(f"- {a}")
    st.caption(APP_DISCLAIMER)


def render_position_sizing(*, beginner: bool = False) -> None:
    transactions = get_portfolio_transactions()
    summary = pe.compute_portfolio_summary(transactions)

    st.markdown("##### Position Sizing Assistant")
    st.caption(
        "Estimate a reasonable position size based on your portfolio, cash, and risk tolerance. "
        "Educational guidance only."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        portfolio_size = st.number_input(
            "Portfolio size ($)",
            min_value=0.0,
            value=float(max(summary.total_portfolio_value, 0.0)),
            step=1000.0,
        )
    with c2:
        cash_available = st.number_input(
            "Cash available ($)",
            min_value=0.0,
            value=float(max(summary.cash_balance, 0.0)),
            step=500.0,
        )
    with c3:
        risk = st.selectbox("Risk tolerance", ["Conservative", "Moderate", "Aggressive"])

    c4, c5 = st.columns(2)
    with c4:
        target_ticker = st.text_input("Ticker for sizing (optional)", placeholder="VOO")
    with c5:
        add_amount = st.number_input("Additional investment ($)", min_value=0.0, value=0.0, step=500.0)

    if st.button("Calculate Suggested Size", type="primary"):
        result = pe.compute_position_sizing(
            transactions,
            portfolio_size=portfolio_size,
            cash_available=cash_available,
            risk_tolerance=risk,  # type: ignore[arg-type]
            target_ticker=target_ticker,
            additional_investment=add_amount,
        )
        st.session_state["_portfolio_sizing_result"] = result

    result = st.session_state.get("_portfolio_sizing_result")
    if isinstance(result, pe.PositionSizingResult):
        r1, r2, r3 = st.columns(3)
        r1.metric("Suggested Position Size", pe.format_currency(result.suggested_dollar_amount))
        r2.metric("Target Allocation %", f"{result.suggested_allocation_pct:.1f}%")
        r3.metric("Projected Weight", f"{result.projected_weight_pct:.1f}%")

        if result.concentration_warnings:
            st.markdown("**Concentration Warnings**")
            for w in result.concentration_warnings:
                st.warning(w)

        if result.allocation_bucket_preview:
            st.markdown("**Allocation Preview**")
            preview = result.allocation_bucket_preview
            cols = st.columns(4)
            for col, key in zip(cols, ["Stocks", "ETFs", "Cash", "Other"]):
                col.metric(key, f"{preview.get(key, 0.0):.1f}%")

    st.divider()
    st.markdown("##### What-If: Add Money to a Position")
    w1, w2, w3 = st.columns([2, 2, 1])
    with w1:
        whatif_ticker = st.text_input("What-if ticker", key="whatif_ticker", placeholder="QQQ")
    with w2:
        whatif_amount = st.number_input("Amount to add ($)", min_value=0.0, value=5000.0, step=500.0)
    with w3:
        st.write("")
        st.write("")
        run_whatif = st.button("Simulate", use_container_width=True)

    if run_whatif and whatif_ticker and whatif_amount > 0:
        sim = pe.simulate_add_to_position(transactions, whatif_ticker, whatif_amount)
        if not sim.get("ok"):
            st.error(sim.get("message", "Simulation failed."))
        else:
            st.success(
                f"Adding {pe.format_currency(sim['amount'])} to **{sim['ticker']}** "
                f"({pe.format_shares(sim['shares_added'])} @ {pe.format_currency(sim['price'])})"
            )
            s1, s2 = st.columns(2)
            s1.metric("Position Weight Before", f"{sim['position_weight_before']:.1f}%")
            s2.metric("Position Weight After", f"{sim['position_weight_after']:.1f}%")


def render_real_portfolio_tab(*, beginner: bool = False) -> None:
    """Main entry: sub-tab navigation for the real portfolio engine."""
    subtitle = (
        "Track what you actually own — positions, gains, and sizing guidance."
        if beginner
        else "Manual portfolio ledger: positions derived from transactions, live marks, allocation, and sizing."
    )
    _hero("My Portfolio", subtitle)
    try:
        from suite_deploy_marker import resolve_git_commit_short

        st.caption(f"Deploy commit: `{resolve_git_commit_short()}` · Real Portfolio UI: `{REAL_PORTFOLIO_BUILD_ID}`")
    except ImportError:
        st.caption(f"Real Portfolio UI: `{REAL_PORTFOLIO_BUILD_ID}`")

    labels = list(REAL_PORTFOLIO_SUBTABS)
    try:
        from investment_persistent_state import validate_state_option

        validate_state_option(st, SESSION_SUBTAB_KEY, labels, labels[0])
    except ImportError:
        if SESSION_SUBTAB_KEY not in _ss():
            _ss()[SESSION_SUBTAB_KEY] = labels[0]

    active = st.radio(
        "Portfolio section",
        labels,
        key=SESSION_SUBTAB_KEY,
        horizontal=True,
        label_visibility="collapsed",
    )

    if active == labels[0]:
        render_portfolio_dashboard(beginner=beginner)
    elif active == labels[1]:
        render_portfolio_positions(beginner=beginner)
    elif active == labels[2]:
        render_portfolio_transactions(beginner=beginner)
    elif active == labels[3]:
        render_allocate_new_money(beginner=beginner)
    elif active == labels[4]:
        render_position_sizing(beginner=beginner)
