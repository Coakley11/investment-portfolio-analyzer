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
REAL_PORTFOLIO_BUILD_ID = "2026-09-10-contribution-target-sources-v1"
SESSION_CONTRIBUTION_PENDING_KEY = "_contribution_record_pending"
SESSION_CONTRIBUTION_ACTIVE_SOURCE_KEY = "_contribution_advisor_active_source"


def _ss() -> Any:
    return st.session_state


def _ensure_known_ticker_identity_corrections() -> list[str]:
    """
    Rewrite known corrupted trade tickers in the authoritative ledger and persist once.

    Identity-only (e.g. VN! → VNQ). Does not invent sells/buys or change economics.
    Invalidates downstream weight/target caches so Positions and Contribution Advisor
    rebuild from the corrected ledger consistently.
    """
    records = _ss().get(SESSION_TRANSACTIONS_KEY)
    if not isinstance(records, list) or not records:
        return []
    repaired, notes = pe.apply_known_ticker_identity_corrections(records)
    if not notes:
        return []
    _ss()[SESSION_TRANSACTIONS_KEY] = repaired
    _ss()["_real_portfolio_ledger_touched"] = True
    _invalidate_portfolio_derived_session_state()
    ok, msg = _persist_portfolio_ledger_change(trigger="portfolio_ticker_identity_correction")
    if ok:
        _ss()["_ticker_identity_correction_notice"] = notes
    else:
        _ss()["_ticker_identity_correction_notice"] = notes + [f"Persist deferred: {msg}"]
    return notes


def _invalidate_portfolio_derived_session_state() -> None:
    """Drop stale weight/target/result caches after ledger identity changes."""
    ss = _ss()
    ss.pop("_contribution_advisor_result", None)
    ss.pop("_portfolio_sizing_result", None)
    ss.pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
    for key in (SESSION_CONTRIBUTION_TARGETS_KEY,):
        saved = ss.get(key)
        if isinstance(saved, dict):
            remapped: dict[str, Any] = {}
            for map_key, val in saved.items():
                sym = str(map_key or "").strip().upper()
                if sym == "VN!":
                    sym = "VNQ"
                if sym:
                    remapped[sym] = val
            ss[key] = remapped
    try:
        from investment_ami.decision_support.contribution_advisor import STRATEGY_TARGET_WEIGHTS_KEY

        saved_strategy = ss.get(STRATEGY_TARGET_WEIGHTS_KEY)
        if isinstance(saved_strategy, dict):
            remapped_s: dict[str, Any] = {}
            for map_key, val in saved_strategy.items():
                sym = str(map_key or "").strip().upper()
                if sym == "VN!":
                    sym = "VNQ"
                if sym:
                    remapped_s[sym] = val
            ss[STRATEGY_TARGET_WEIGHTS_KEY] = remapped_s
    except Exception:
        pass
    # Force Streamlit widget keys for contribution targets to re-seed from fresh weights.
    for k in list(ss.keys()):
        if str(k).startswith("contrib_tgt_"):
            ss.pop(k, None)


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
    cash_ledger = pe.compute_cash_ledger_summary(transactions)
    net_contributions = cash_ledger.total_deposits - cash_ledger.total_withdrawals
    _metric_row(
        [c1, c2, c3, c4, c5, c6],
        [
            "Total Portfolio Value",
            "Securities cost basis",
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
    st.caption(
        f"Net external contributions (deposits − withdrawals): **{pe.format_currency(net_contributions)}**. "
        "Securities cost basis is purchase cost of open holdings — not the same as contributions, "
        "and deposits are not counted as investment gain. "
        "This **Total Portfolio Value** is your Real Portfolio ledger NAV — independent of the "
        "sidebar **Planning portfolio value** used for analytical/simulation dollars."
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
            ok_ticker, sym, ticker_err = pe.validate_trade_ticker(ticker)
            if not ok_ticker:
                st.error(ticker_err or "Enter a valid ticker for buy/sell transactions.")
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
                "Current strategy target",
            ],
            key="contribution_advisor_target_source_v2",
            help=(
                "Three isolated sources: (1) percentages you type, (2) OBJECTIVE_ALLOCATIONS for your "
                "stated investment objective (labeled), (3) a saved strategy target that does not "
                "auto-drift with market prices. Switching sources recalculates — stale previews are cleared."
            ),
        )

    source_map = {
        "My target weights (explicit)": "user_explicit",
        "Recommended from stated objective (labeled)": "stated_objective_recommended",
        "Current strategy target": "current_strategy",
    }
    target_source = source_map[source_label]

    # Switching target source must never leave another source's preview/review recordable.
    prev_active = str(_ss().get(SESSION_CONTRIBUTION_ACTIVE_SOURCE_KEY) or "")
    if prev_active and prev_active != target_source:
        _ss().pop("_contribution_advisor_result", None)
        _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
    _ss()[SESSION_CONTRIBUTION_ACTIVE_SOURCE_KEY] = target_source

    from investment_ami.decision_support.contribution_advisor import (
        OBJECTIVE_SLEEVE_MAPPING_ASSUMPTION,
        STRATEGY_TARGET_WEIGHTS_KEY,
        canonical_stated_objective,
        objective_category_targets,
        strategy_targets_from_session,
        weights_from_values_as_percent,
    )

    explicit: dict[str, float] | None = None
    redistribute_unrepresented = False
    resolved_targets_for_fp: dict[str, float] | None = None

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
        resolved_targets_for_fp = dict(explicit)
        st.caption(f"Target sum: **{sum(explicit.values()):.1f}%**")

    elif target_source == "stated_objective_recommended":
        raw_obj = _ss().get("health_objective") or snap.health_objective or ""
        obj_key = canonical_stated_objective(str(raw_obj))
        st.markdown("**Recommended from stated objective (labeled)**")
        st.caption(
            "Uses the model allocation in OBJECTIVE_ALLOCATIONS for your stated investment "
            "objective — not Portfolio Health rebalance weights, Guided Adjustment, optimizer "
            "corners, or DEFAULT_HOLDINGS. Does not mutate your explicit personal targets."
        )
        if not obj_key:
            st.warning(
                "No valid stated investment objective is set. Establish one in Portfolio Health / "
                "goal setup (e.g. Balanced Growth) before calculating. Contribution Advisor will "
                "not invent an objective."
            )
            if str(raw_obj).strip():
                st.caption(f"Current session value (unrecognized): `{raw_obj}`")
        else:
            cats = objective_category_targets(obj_key) or {}
            st.info(f"**Selected objective:** `{obj_key}` · **Source:** `OBJECTIVE_ALLOCATIONS`")
            st.caption(
                "Category targets: "
                + ", ".join(f"{name} {wt * 100:.0f}%" for name, wt in cats.items())
            )
            st.caption(OBJECTIVE_SLEEVE_MAPPING_ASSUMPTION)
            # Preview sleeve coverage against current priced holdings (no write).
            from investment_ami.decision_support.contribution_advisor import (
                holding_targets_from_stated_objective,
            )

            vals: dict[str, float] = {}
            for h in snap.holdings:
                if h.current_price is None:
                    continue
                vals[h.ticker] = vals.get(h.ticker, 0.0) + float(h.current_value or 0.0)
            if float(snap.cash or 0.0) > 0:
                vals["$CASH"] = float(snap.cash)

            # Sleeve membership for labeling (same rules as advisor).
            sleeve_members: dict[str, list[str]] = {"Equity": [], "Bonds": [], "Cash_and_TBills": []}
            for h in snap.holdings:
                if h.current_price is None:
                    continue
                ac = str(h.asset_class or "")
                if ac in ("Stocks", "ETFs"):
                    sleeve_members["Equity"].append(h.ticker)
                elif ac == "Bonds":
                    sleeve_members["Bonds"].append(h.ticker)
                elif ac == "Cash":
                    sleeve_members["Cash_and_TBills"].append(h.ticker)
            if "$CASH" in vals:
                sleeve_members["Cash_and_TBills"].append("$CASH")
            unrep = [name for name, wt in cats.items() if wt > 1e-9 and not sleeve_members.get(name)]
            if unrep:
                st.warning(
                    "Unrepresented objective sleeve(s): "
                    + ", ".join(f"{n} ({cats[n] * 100:.0f}%)" for n in unrep)
                    + ". These are **not** silently renormalized away."
                )
                redistribute_unrepresented = st.checkbox(
                    "Provisionally redistribute unrepresented sleeves into existing holdings",
                    value=False,
                    key="contrib_redistribute_unrepresented",
                    help=(
                        "Opt-in only. Scales represented holding targets to 100% and labels the "
                        "assumption. Does not add a new ticker for the missing sleeve."
                    ),
                )
            else:
                st.success("All objective sleeves have at least one matching priced ledger holding.")

            preview_tgts, _, preview_meta = holding_targets_from_stated_objective(
                snap,
                vals,
                obj_key,
                redistribute_unrepresented=redistribute_unrepresented,
            )
            if preview_tgts:
                st.markdown("**Resulting ticker targets (preview)**")
                st.caption(
                    " · ".join(f"{t} {w * 100:.1f}%" for t, w in sorted(preview_tgts.items()))
                )
                resolved_targets_for_fp = {k: v * 100.0 for k, v in preview_tgts.items()}
            elif preview_meta.get("unrepresented_sleeves") and not redistribute_unrepresented:
                st.caption(
                    "Calculate stays blocked until sleeves are represented or redistribution is acknowledged."
                )

    elif target_source == "current_strategy":
        st.markdown("**Current strategy target**")
        st.caption(
            "This is a **saved** strategy you accept — not a live snapshot of today's market "
            "weights. Prices may drift; the strategy target stays fixed until you explicitly update it."
        )
        saved_strategy = strategy_targets_from_session(_ss())
        if saved_strategy:
            ordered = sorted(saved_strategy.items(), key=lambda kv: (-float(kv[1]), kv[0]))
            st.info(
                "Saved strategy: "
                + " · ".join(f"**{t}** {float(w):.1f}%" for t, w in ordered)
            )
            resolved_targets_for_fp = dict(saved_strategy)
        else:
            st.warning(
                "No strategy target saved yet. If the portfolio is on strategy, use the button "
                "below to establish one. Contribution Advisor will not treat drifting live weights "
                "as the target."
            )

        live_vals = {
            h.ticker: float(h.current_value or 0.0)
            for h in snap.holdings
            if h.current_price is not None and float(h.current_value or 0.0) > 0
        }
        if float(snap.cash or 0.0) > 0:
            live_vals["$CASH"] = float(snap.cash)
        live_pct = weights_from_values_as_percent(live_vals)
        if live_pct:
            st.caption(
                "Live market weights (informational only): "
                + " · ".join(f"{t} {w:.1f}%" for t, w in sorted(live_pct.items(), key=lambda kv: -kv[1]))
            )

        b1, b2 = st.columns(2)
        with b1:
            establish = st.button(
                "Use current allocation as strategy target",
                key="contrib_establish_strategy",
                help="Saves today's live weights as the durable strategy target (explicit action).",
            )
        with b2:
            update = st.button(
                "Update strategy target from current allocation",
                key="contrib_update_strategy",
                disabled=not bool(saved_strategy),
                help="Replace the saved strategy with today's live weights (explicit action).",
            )
        if establish or update:
            if not live_pct:
                st.error("No priced holdings available to establish a strategy target.")
            else:
                _ss()[STRATEGY_TARGET_WEIGHTS_KEY] = dict(live_pct)
                _ss()["_real_portfolio_ledger_touched"] = True
                _ss().pop("_contribution_advisor_result", None)
                _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
                ok, msg = _persist_portfolio_ledger_change(trigger="strategy_target_weights_change")
                if ok:
                    st.success("Strategy target saved. It will persist across reruns and restore with the ledger.")
                else:
                    st.warning(f"Strategy target saved in session; persist deferred: {msg}")
                st.rerun()

    if beginner:
        st.caption(
            "Tip: if one holding is behind its target, most of the new money usually goes there first."
        )

    run = st.button("Calculate allocation", type="primary", key="contribution_advisor_run")
    if run:
        # New calculation invalidates any pending record confirmation.
        _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
        result = recommend_contribution_allocation_from_session(
            _ss(),
            contribution_amount=float(amount),
            target_source=target_source,  # type: ignore[arg-type]
            explicit_holding_targets=explicit,
            redistribute_unrepresented_objective_sleeves=redistribute_unrepresented,
            include_cash=True,
        )
        payload = result.to_dict()
        if result.ok:
            from investment_ami.decision_support.contribution_recorder import (
                attach_application_metadata_to_payload,
            )

            records = _ss().get(SESSION_TRANSACTIONS_KEY) or []
            meta_targets = result.meta.get("resolved_targets") if isinstance(result.meta, dict) else None
            fp_targets = meta_targets if isinstance(meta_targets, dict) else (resolved_targets_for_fp or explicit)
            payload = attach_application_metadata_to_payload(
                payload,
                records=records if isinstance(records, list) else [],
                contribution_amount=float(amount),
                target_source=target_source,
                targets=fp_targets,
                workspace_token=_contribution_workspace_token(),
            )
        _ss()["_contribution_advisor_result"] = payload
        # Decision support only — never write deposits/buys from Calculate.
        if not result.ok:
            st.error(_streamlit_prose(result.explanation))
            for w in result.warnings:
                st.warning(_streamlit_prose(w))
            return

    prior = _ss().get("_contribution_advisor_result")
    if isinstance(prior, dict) and prior.get("ok"):
        prior_source = str(prior.get("target_source") or "")
        from investment_ami.decision_support.contribution_advisor import normalize_target_source

        if normalize_target_source(prior_source) != normalize_target_source(target_source):
            # Stale recommendation from another target source — never show as recordable.
            _ss().pop("_contribution_advisor_result", None)
            _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
            return
        _render_contribution_result(prior)
        fp_targets = None
        if isinstance(prior.get("meta"), dict):
            fp_targets = prior["meta"].get("resolved_targets")
        if not isinstance(fp_targets, dict):
            fp_targets = resolved_targets_for_fp or explicit
        _render_contribution_record_controls(
            prior,
            contribution_amount=float(amount),
            target_source=target_source,
            explicit=fp_targets if isinstance(fp_targets, dict) else explicit,
        )
    elif not run:
        return


def _contribution_workspace_token() -> str:
    ss = _ss()
    meta = ss.get("_suite_workspace_persist_meta")
    if isinstance(meta, dict):
        for key in ("workspace_id", "user_id", "account_id"):
            val = meta.get(key)
            if val:
                return str(val)
    for key in ("auth_email", "suite_auth_email", "user_email"):
        val = ss.get(key)
        if val:
            return str(val)
    return "local"


def _persist_transaction_records(records: list[dict]) -> tuple[bool, str]:
    """Replace the session ledger with validated records and persist once."""
    txns = pe.transactions_from_records(records)
    set_portfolio_transactions(txns)
    return _persist_portfolio_ledger_change(trigger="portfolio_transactions_change")


def _streamlit_prose(text: str) -> str:
    """Escape ``$`` so Streamlit Markdown does not collapse currency into LaTeX."""
    try:
        from investment_ami_answer_format import escape_streamlit_markdown_prose

        return escape_streamlit_markdown_prose(str(text or ""))
    except ImportError:
        return str(text or "").replace("$", "\\$")


def _render_contribution_result(payload: dict) -> None:
    st.success(_streamlit_prose(payload.get("explanation") or "Allocation ready."))
    st.caption(
        "Decision support only until you explicitly **Record this contribution**. "
        "Calculate does **not** write deposits or buys, and does not count the contribution "
        "as investment profit."
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
                st.markdown(f"- {_streamlit_prose(a)}")
    st.caption(APP_DISCLAIMER)


def _render_contribution_record_controls(
    payload: dict,
    *,
    contribution_amount: float,
    target_source: str,
    explicit: dict[str, float] | None,
) -> None:
    from investment_ami.decision_support.contribution_recorder import (
        build_simulated_application_plan,
        event_already_applied,
        fingerprints_match,
        ledger_state_fingerprint,
        recommendation_fingerprint,
    )

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    application_id = str(meta.get("application_id") or "").strip()
    stored_fp = meta.get("recommendation_fingerprint") if isinstance(meta.get("recommendation_fingerprint"), dict) else {}
    applied_flag = bool(meta.get("applied"))
    records = _ss().get(SESSION_TRANSACTIONS_KEY) or []
    if not isinstance(records, list):
        records = []

    if application_id and (applied_flag or event_already_applied(records, application_id)):
        st.info(_streamlit_prose("This recommendation was already recorded into the ledger."))
        return

    pending = _ss().get(SESSION_CONTRIBUTION_PENDING_KEY)
    # Show review whenever a pending plan exists for this Calculate result (or the only pending plan).
    if isinstance(pending, dict) and pending.get("purchases") is not None:
        pending_aid = str(pending.get("application_id") or "").strip()
        if (not application_id) or (not pending_aid) or pending_aid == application_id:
            _render_contribution_review(pending, payload)
            return
        # Orphan pending from a prior recommendation — drop it.
        _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)

    st.markdown("##### Record this contribution")
    st.caption(
        "Step 1 of 2: prepare a **review** of the deposit and simulated buys. "
        "This button does **not** write to the ledger."
    )

    rows = payload.get("rows") or []
    adds = {
        str(r.get("ticker") or "").upper(): float(r.get("recommended_add") or 0.0)
        for r in rows
        if isinstance(r, dict)
    }
    live_fp = recommendation_fingerprint(
        ledger_fp=ledger_state_fingerprint(records),
        contribution_amount=float(contribution_amount),
        target_source=target_source,
        targets=explicit,
        recommended_adds=adds,
        portfolio_value_before=float(payload.get("portfolio_value_before") or 0.0),
        workspace_token=_contribution_workspace_token(),
    )
    if stored_fp and not fingerprints_match(stored_fp, live_fp):
        st.warning(
            "Inputs or the ledger changed since Calculate. "
            "Recalculate allocation before recording."
        )
        return

    if not application_id or not stored_fp:
        st.warning("This recommendation is missing recording metadata. Recalculate allocation.")
        return

    security_adds = {k: v for k, v in adds.items() if k not in ("$CASH", "CASH") and v > 0.0005}
    if not security_adds:
        st.caption("Nothing to record — recommended security purchases are $0.")
        return

    if st.button("Record this contribution", type="secondary", key="contribution_record_start"):
        quotes, sources, asset_types, err = _collect_simulated_fill_quotes(security_adds)
        if err:
            st.error(_streamlit_prose(err))
            return
        plan_result = build_simulated_application_plan(
            application_id=application_id,
            contribution_amount=float(payload.get("contribution_amount") or contribution_amount),
            recommended_adds=security_adds,
            quotes=quotes,
            fingerprint=stored_fp,
            quote_sources=sources,
            asset_types=asset_types,
        )
        if not plan_result.ok or plan_result.plan is None:
            st.error(_streamlit_prose(plan_result.message))
            return
        # Preview only — ledger is unchanged until Confirm & Record.
        _ss()[SESSION_CONTRIBUTION_PENDING_KEY] = plan_result.plan.to_dict()
        st.rerun()


def _collect_simulated_fill_quotes(
    security_adds: dict[str, float],
) -> tuple[dict[str, float], dict[str, str], dict[str, str], str]:
    """Fetch current marks for simulated fills. Returns (quotes, sources, asset_types, error)."""
    quotes: dict[str, float] = {}
    sources: dict[str, str] = {}
    asset_types: dict[str, str] = {}
    try:
        from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot
        from investment_ami.decision_support.real_portfolio_recommendation_rules import (
            STALE_QUOTE_AGE_SECONDS,
        )

        built = build_real_portfolio_snapshot(_ss())
        if built.ok and built.snapshot is not None:
            if built.snapshot.market_data_status in ("partial", "unavailable"):
                return {}, {}, {}, "Market data is incomplete. Recalculate when quotes are available."
            age = built.snapshot.market_data_age_seconds
            if (
                built.snapshot.market_data_status == "cached"
                and age is not None
                and age > STALE_QUOTE_AGE_SECONDS
            ):
                return {}, {}, {}, "Market quotes look stale. Recalculate with fresher marks before recording."
            for h in built.snapshot.holdings:
                if h.ticker not in security_adds:
                    continue
                if h.current_price is None or float(h.current_price) <= 0:
                    return {}, {}, {}, f"Missing market quote for {h.ticker}. Recalculate when marks are available."
                if "missing_price" in (h.data_quality_flags or ()):
                    return {}, {}, {}, f"Unusable mark for {h.ticker}. Recalculate when quotes are fresh."
                quotes[h.ticker] = float(h.current_price)
                sources[h.ticker] = str(h.price_source or "snapshot")
                asset_types[h.ticker] = "etf"
    except Exception as exc:  # noqa: BLE001
        return {}, {}, {}, f"Could not refresh market marks: {exc}"

    for t in security_adds:
        if t in quotes:
            continue
        px, src = pe.fetch_latest_price(t)
        if px is None or px <= 0:
            return {}, {}, {}, f"Missing market quote for {t}."
        quotes[t] = float(px)
        sources[t] = src or "market_data_provider"
        asset_types[t] = "etf"
    return quotes, sources, asset_types, ""


def _render_contribution_review(pending: dict, payload: dict) -> None:
    """Pre-mutation review: deposit + every buy with quote/shares. No ledger writes here."""
    from investment_ami.decision_support.contribution_recorder import (
        STATUS_ALREADY_APPLIED,
        STATUS_STALE,
        ContributionApplicationPlan,
        PlannedPurchase,
        apply_contribution_plan_to_records,
        fingerprints_match,
        ledger_state_fingerprint,
        plan_review_table_rows,
    )

    amount = float(pending.get("contribution_amount") or 0.0)
    purchases = pending.get("purchases") or []
    application_id = str(pending.get("application_id") or "")
    total_cost = float(
        pending.get("total_purchase_cost")
        or sum(float(p.get("cost") or 0) for p in purchases)
    )

    st.markdown(_streamlit_prose(f"##### Record ${amount:,.2f} Contribution"))
    st.info(
        _streamlit_prose(
            "Review the exact ledger transactions below. Nothing has been written yet. "
            "Confirm & Record will mutate the app ledger; Cancel discards this review."
        )
    )

    st.markdown(_streamlit_prose(f"**External contribution — cash deposit:** +${amount:,.2f}"))
    st.markdown("**Simulated purchases** (current market quote as execution price):")

    review_rows = plan_review_table_rows(pending)
    buy_rows = [r for r in review_rows if r["kind"] == "buy"]
    if buy_rows:
        df = pd.DataFrame(
            [
                {
                    "Ticker": r["ticker"],
                    "Recommended $": round(float(r["recommended_dollars"]), 2),
                    "Current Quote": round(float(r["execution_price"] or 0), 4),
                    "Estimated Shares": float(r["estimated_shares"] or 0),
                    "Purchase $": round(float(r["cost"]), 2),
                    "Quote source": r.get("price_source") or "",
                }
                for r in buy_rows
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown(_streamlit_prose(f"**Total purchases:** ${total_cost:,.2f}"))
    if abs(total_cost - amount) > 0.02:
        st.error(_streamlit_prose("Purchase total does not match the contribution. Recalculate."))
        _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
        return

    st.markdown(
        _streamlit_prose(
            f"Contribution event id: `{application_id or '—'}` · source: `contribution_advisor` · "
            f"policy: `{pending.get('execution_policy') or 'simulated_fill_at_current_mark'}`"
        )
    )
    st.markdown(
        "- This will write **one cash-deposit** transaction plus the **listed buy** transactions to the app ledger.\n"
        "- Fills use **current market quotes** as **simulated** execution prices and estimated fractional shares.\n"
        "- This does **NOT** place brokerage orders.\n"
        "- The external contribution is **not** investment profit."
    )

    # Freshness gate before enabling Confirm.
    records = _ss().get(SESSION_TRANSACTIONS_KEY) or []
    if not isinstance(records, list):
        records = []
    stored_fp = pending.get("fingerprint") if isinstance(pending.get("fingerprint"), dict) else {}
    live_ledger_fp = ledger_state_fingerprint(records)
    stale = False
    if stored_fp and live_ledger_fp != str(stored_fp.get("ledger_fp") or ""):
        stale = True
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    calc_fp = meta.get("recommendation_fingerprint") if isinstance(meta.get("recommendation_fingerprint"), dict) else {}
    if calc_fp and stored_fp and not fingerprints_match(calc_fp, stored_fp):
        stale = True
    if stale:
        st.warning(
            "This review is out of date (ledger or recommendation changed). "
            "Cancel and recalculate — Confirm is disabled."
        )
        if st.button("Cancel review", key="contribution_record_cancel_stale"):
            _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
            st.rerun()
        return

    c1, c2 = st.columns(2)
    with c1:
        confirm = st.button("Confirm & Record", type="primary", key="contribution_record_confirm")
    with c2:
        cancel = st.button("Cancel", key="contribution_record_cancel")

    if cancel:
        _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
        st.rerun()
        return

    if not confirm:
        return

    plan = ContributionApplicationPlan(
        application_id=application_id,
        contribution_amount=amount,
        trade_date=str(pending.get("trade_date") or ""),
        execution_policy=str(pending.get("execution_policy") or ""),
        deposit_record=dict(pending.get("deposit_record") or {}),
        buy_records=tuple(dict(r) for r in (pending.get("buy_records") or [])),
        purchases=tuple(
            PlannedPurchase(
                ticker=str(p.get("ticker") or ""),
                recommended_dollars=float(p.get("recommended_dollars") or 0),
                execution_price=float(p.get("execution_price") or 0),
                shares=float(p.get("shares") or 0),
                cost=float(p.get("cost") or 0),
                price_source=str(p.get("price_source") or ""),
                asset_type=str(p.get("asset_type") or "etf"),
            )
            for p in purchases
        ),
        fingerprint=dict(pending.get("fingerprint") or {}),
        warnings=tuple(pending.get("warnings") or ()),
        meta=dict(pending.get("meta") or {}),
    )

    result = apply_contribution_plan_to_records(
        records,
        plan,
        current_fingerprint=plan.fingerprint,
        require_fingerprint_match=True,
    )
    if not result.ok:
        st.error(_streamlit_prose(result.message))
        if result.status == STATUS_STALE:
            _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
        return

    if result.already_applied or result.status == STATUS_ALREADY_APPLIED:
        _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
        _ss().pop("_contribution_advisor_result", None)
        st.info(_streamlit_prose(result.message))
        st.rerun()
        return

    written = 1 + len(plan.purchases)
    ok, msg = _persist_transaction_records([dict(t) for t in result.transactions])
    _ss().pop(SESSION_CONTRIBUTION_PENDING_KEY, None)
    _ss().pop("_contribution_advisor_result", None)
    if ok:
        st.success(
            _streamlit_prose(
                f"{result.message} Wrote {written} ledger row(s) "
                f"(1 deposit + {len(plan.purchases)} buy(s)). {msg}"
            )
        )
    else:
        st.error(
            _streamlit_prose(
                f"{result.message} Session ledger updated ({written} rows), "
                f"but durable save reported: {msg}"
            )
        )
    st.rerun()


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

    # Repair known corrupted tickers (VN! → VNQ) before any sub-tab reads the ledger.
    _ensure_known_ticker_identity_corrections()
    notice = _ss().pop("_ticker_identity_correction_notice", None)
    if notice:
        for line in notice:
            st.info(line)

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
