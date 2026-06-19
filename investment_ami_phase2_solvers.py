"""Phase 2 Investment AMI solvers — structured analyst answers and new families."""

from __future__ import annotations

import re
from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_exposure import resolve_tech_exposure
from investment_ami_valuation import resolve_valuation_context
from investment_ami_instant_solver import (
    InvestmentSolverResult,
    InvestmentSolverRoute,
    _TECH_TICKERS,
    _beginner,
    _parse_weight_pct,
    _portfolio_label,
    _route_for_intent,
    _weight_rows,
)


def _default_risk_notes(beginner: bool) -> str:
    if beginner:
        return (
            "This is educational analysis based on your entered weights — not personal financial advice. "
            "Past performance and simple concentration checks do not predict future results."
        )
    return (
        "Educational portfolio analysis only; not investment advice. "
        "Metrics are snapshot-based from session weights and historical health metrics where available."
    )


def _parse_scenario_drawdown_pct(
    ctx: dict[str, Any],
    *,
    question: str = "",
    default: float = 20.0,
) -> float:
    """Resolve tech/scenario drawdown % from params or question text (never raises)."""
    params = dict(ctx.get("scenario_params") or {})
    raw = params.get("tech_drawdown_pct")
    parsed = _parse_weight_pct(raw)
    if parsed is not None and 0 < parsed <= 100:
        return parsed
    if isinstance(raw, (int, float)) and 0 < float(raw) <= 100:
        return float(raw)
    q = str(question or ctx.get("question") or "").strip().lower()
    for pattern in (
        r"(?:fall|falls|drop|drops|decline|declines|down)[^\d%]{0,24}(\d+(?:\.\d+)?)\s*%?",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:drop|drawdown|fall|decline)",
        r"tech[^\d%]{0,20}(\d+(?:\.\d+)?)\s*%?",
    ):
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if 0 < val <= 100:
                    return val
            except (TypeError, ValueError):
                continue
    return default


def _tickers_mentioned_in_question(question: str) -> list[str]:
    q = re.sub(r"[^A-Z0-9 ]", " ", str(question or "").upper())
    known = ("VOO", "QQQ", "VTI", "SPY", "IVV", "SCHD", "VYM", "VNQ", "BND", "VXUS", "VGT", "MGK")
    return [t for t in known if re.search(rf"\b{t}\b", q)]


def structured_concentration_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    rows = _weight_rows(ctx)
    if not rows:
        direct = (
            "Add holdings with weights first — I need your portfolio mix to judge concentration."
            if beginner
            else "No holdings weights in context — populate Portfolio Health weights before concentration analysis."
        )
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=(
                "Concentration measures how much of your portfolio sits in a few fund sleeves. "
                "Without weights, I cannot score top-fund or top-3 allocation exposure."
            ),
            recommended_actions="Enter tickers and target weights, then ask again.",
            risk_notes=_default_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            math_idea="Top-weight and top-3 concentration bands.",
            problem_type="portfolio_concentration",
            model_name="Investment concentration analyst",
            confidence_pct=60,
        )

    top_ticker, top_pct = rows[0]
    top3 = sum(p for _, p in rows[:3])
    flag = "high" if top_pct >= 35 else "moderate" if top_pct >= 25 else "low"

    if beginner:
        if top_pct >= 35:
            direct = f"Yes — your portfolio looks concentrated. **{top_ticker}** is about **{top_pct:.1f}%** of the mix."
        elif top_pct >= 25:
            direct = f"Moderately concentrated — **{top_ticker}** is about **{top_pct:.1f}%**."
        else:
            direct = f"Not highly concentrated in one fund sleeve. Largest holding **{top_ticker}** is **{top_pct:.1f}%**."
        analyst = (
            f"Your top three fund sleeves (**{', '.join(t for t, _ in rows[:3])}**) add up to about **{top3:.1f}%**. "
            "Portfolio performance will be heavily influenced by those top sleeves — returns and drawdowns "
            "will largely track their combined moves rather than a broad diversified index."
        )
        tradeoffs = (
            "**More concentration** → simpler portfolio, clearer bets, but bigger swings from one sleeve.\n"
            "**More diversification** → smoother ride, less single-sleeve shock, but you may lag a hot sector."
        )
        actions = (
            "If concentration feels uncomfortable, consider trimming the largest weight toward your target mix "
            "or adding a complementary asset class (e.g., bonds or a broad market fund)."
        )
    else:
        direct = (
            f"Concentration scan ({_portfolio_label(ctx)}): top **{top_ticker}** **{top_pct:.1f}%**; "
            f"top-3 **{top3:.1f}%** → **{flag}** fund-level concentration."
        )
        analyst = (
            f"Top-3 weight **{top3:.1f}%** implies meaningful **allocation concentration** — portfolio P&L will "
            f"be driven primarily by {top_ticker} and the other top fund sleeves, not by market-wide diversification. "
            "Risk **increases** if top weights drift higher; it **eases** if you rebalance toward targets or add "
            "uncorrelated sleeves."
        )
        tradeoffs = (
            "Higher top-weight concentration increases tracking error vs a broad benchmark and amplifies "
            "drawdowns if the dominant sleeve underperforms. Lower concentration reduces sleeve-level shock "
            "but may dilute intentional tilts."
        )
        actions = (
            f"Monitor **{top_ticker}** vs target band; rebalance if top weight exceeds policy tolerance "
            "(often 25–35% for single-fund sleeves in diversified portfolios)."
        )

    key_vars = "\n".join(
        f"- **{t}**: **{p:.1f}%**" for t, p in rows[:5]
    ) + f"\n- **Top-3 weight**: **{top3:.1f}%**"

    what_if = (
        f"If **{top_ticker}** fell **10%**, a rough static impact is about **{top_pct * 0.10:.1f}%** on the total portfolio "
        f"(ignoring correlation and other moves)."
    )
    if not beginner:
        what_if += (
            f"\nIf top-3 holdings fell together **10%**, illustrative portfolio impact ≈ **{top3 * 0.10:.1f}%**."
        )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables=key_vars,
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if,
        recommended_actions=actions,
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        math_idea="Top-weight and top-3 weight concentration bands.",
        problem_type="portfolio_concentration",
        model_name="Investment concentration analyst",
        variables=f"top_weight={top_pct:.1f}%",
        assumptions=["Weights reflect current portfolio session.", "Not personal financial advice."],
        confidence_pct=84,
        computed={"top_ticker": top_ticker, "top_weight_pct": top_pct, "top3_weight_pct": round(top3, 1)},
    )


def structured_portfolio_risk_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    rows = _weight_rows(ctx)
    risk_level = str(ctx.get("risk_level") or "").strip()
    vol = str(ctx.get("volatility") or "").strip()
    exposure = resolve_tech_exposure(ctx)
    tech_pct = float(exposure.get("total_pct") or 0)
    embedded_tech = float(exposure.get("embedded_pct") or 0)
    top_ticker, top_pct = rows[0] if rows else ("—", 0.0)
    top3 = sum(p for _, p in rows[:3]) if rows else 0.0

    if beginner:
        direct = "Your biggest risks right now are concentration, sector tilt, and how much volatility you are carrying."
        analyst = (
            f"Largest position **{top_ticker}** at **{top_pct:.1f}%** can move the whole portfolio — "
            "that is **concentration risk**: one sleeve drives outcomes. "
            + (
                f"Estimated technology exposure is **{tech_pct:.1f}%** "
                f"({'including embedded exposure in broad/dividend funds' if embedded_tech > 0 else 'direct tech sleeves'}) — "
                "meaningful if tech sells off. "
                if tech_pct >= 10
                else ""
            )
            + (f"Health check labels risk as **{risk_level}**." if risk_level else "")
            + " Risk **rises** if top weights grow; **falls** if you diversify or add defensive assets."
        )
        key_vars = "\n".join(
            filter(
                None,
                [
                    f"- Largest holding: **{top_ticker}** **{top_pct:.1f}%**" if rows else None,
                    f"- Top-3 concentration: **{top3:.1f}%**" if rows else None,
                    f"- Technology exposure (direct + embedded): **{tech_pct:.1f}%**" if tech_pct else None,
                    f"- Risk label: **{risk_level}**" if risk_level else None,
                    f"- Historical volatility: **{vol}**" if vol else None,
                ],
            )
        )
        tradeoffs = (
            "**Growth tilt** can boost returns in strong markets but increases drawdown risk.\n"
            "**Defensive sleeves** (bonds, dividend, cash) reduce swings but may lag in rallies."
        )
        what_if = "If your largest holding fell **10%**, expect a noticeable portfolio dip — exact size depends on its weight."
        actions = (
            "Review whether top weights and tech tilt match your comfort level. "
            "If not, rebalance toward targets or add diversifiers."
        )
    else:
        direct = (
            f"Primary risk drivers: top-weight **{top_ticker}** **{top_pct:.1f}%**, "
            f"top-3 **{top3:.1f}%**"
            + (f", tech proxy **{tech_pct:.1f}%**" if tech_pct else "")
            + (f", health risk **{risk_level}**" if risk_level else "")
            + "."
        )
        analyst = (
            "Risk stacks from **concentration** (idiosyncratic), **factor/sector tilt** (systematic), "
            "and **historical volatility**. Dominant sleeves drive short-term variance. "
            "Severity is **elevated** when top-3 exceeds ~60% or tech proxy exceeds ~35%; "
            "**moderate** below those bands. Rebalancing and defensive sleeves reduce exposure."
        )
        key_vars = "\n".join(
            filter(
                None,
                [
                    f"- Top-weight risk: **{top_ticker}** **{top_pct:.1f}%**" if rows else None,
                    f"- Top-3 concentration: **{top3:.1f}%**" if rows else None,
                    f"- Technology exposure (direct + embedded): **{tech_pct:.1f}%**" if tech_pct else None,
                    f"- Historical volatility: **{vol}**" if vol else None,
                    f"- Health risk level: **{risk_level}**" if risk_level else None,
                    f"- Max drawdown (historical): **{ctx.get('max_drawdown')}**" if ctx.get("max_drawdown") else None,
                ],
            )
        )
        tradeoffs = (
            "Reducing concentration lowers sleeve-level shock but may trim intentional factor bets. "
            "Adding defensive assets cuts variance but creates opportunity cost in equity rallies."
        )
        what_if = (
            f"Static shock: **{top_ticker}** **-10%** → ~**{top_pct * 0.10:.1f}%** portfolio impact.\n"
            f"Tech sleeve **-20%** → ~**{tech_pct * 0.20:.1f}%** impact (proxy, ignoring correlation)."
            if tech_pct
            else f"Static shock: **{top_ticker}** **-10%** → ~**{top_pct * 0.10:.1f}%** portfolio impact."
        )
        actions = (
            "Set rebalance bands for top weights and sector proxies; stress-test before adding overlapping index funds."
        )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables=key_vars or "—",
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if,
        recommended_actions=actions,
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        math_idea="Concentration + sector tilt + historical volatility frame risk.",
        problem_type="portfolio_risk",
        model_name="Investment risk analyst",
        confidence_pct=81,
        computed={"top_weight_pct": top_pct, "top3_weight_pct": round(top3, 1), "tech_proxy_pct": round(tech_pct, 1)},
    )


def etf_overlap_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    pairs = ctx.get("etf_overlap_pairs")
    rows = _weight_rows(ctx)
    tickers = [t for t, _ in rows]
    mentioned = _tickers_mentioned_in_question(question)

    if isinstance(pairs, list) and mentioned and len(mentioned) >= 2:
        for p in pairs:
            pair_str = str(p.get("pair") or "")
            if mentioned[0] in pair_str and mentioned[1] in pair_str:
                pairs = [p] + [x for x in pairs if x is not p]
                break
        else:
            try:
                import etf_holdings as eh

                t1, t2 = mentioned[0], mentioned[1]
                h1 = eh.lookup_etf(t1).holdings
                h2 = eh.lookup_etf(t2).holdings
                ov = eh.pairwise_etf_overlap(h1, h2) * 100
                pairs = [{"pair": f"{t1}/{t2}", "overlap_pct": round(ov, 1)}] + list(pairs or [])
            except Exception:
                pass

    if not isinstance(pairs, list) or not pairs:
        if len(tickers) >= 2:
            direct = (
                f"You hold **{'**, **'.join(tickers[:4])}** — overlap data was not loaded. "
                "Open ETF Holdings or retry after holdings sync."
            )
        else:
            direct = "Add at least two ETF tickers to analyze overlap."
        sections = build_analyst_sections(
            direct_answer=direct,
            recommended_actions="Use the ETF Holdings tab to inspect underlying overlap, then ask again.",
            risk_notes=_default_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="etf_overlap",
            model_name="ETF overlap analyst",
            confidence_pct=55,
        )

    top_pair = max(pairs, key=lambda p: float(p.get("overlap_pct") or 0))
    t1, t2 = str(top_pair.get("pair", "/")).split("/", 1) if "/" in str(top_pair.get("pair", "")) else ("?", "?")
    ov = float(top_pair.get("overlap_pct") or 0)
    compare_mode = len(mentioned) >= 2 and mentioned[0] in (t1, t2) and mentioned[1] in (t1, t2)
    growth_tilt = t2 in {"QQQ", "VGT", "ARKK", "TQQQ"} or t1 in {"QQQ", "VGT", "ARKK", "TQQQ"}

    if compare_mode and beginner:
        if ov >= 50:
            direct = (
                f"**Usually not both** — **{t1}** and **{t2}** overlap about **{ov:.0f}%**. "
                "You mostly duplicate the same large US stocks."
            )
        elif ov >= 35:
            direct = (
                f"**Optional, not both at large weights** — **{ov:.0f}%** overlap between **{t1}** and **{t2}**."
            )
        else:
            direct = f"**Can own both** at moderate weights — overlap is **{ov:.0f}%**, lower duplication."
        analyst = (
            f"**{t1}** is a broad US market fund; **{t2}** is {'growth/tech tilted' if growth_tilt else 'a different factor sleeve'}. "
            "Overlap means you double-count the same underlying names."
        )
    elif compare_mode and not beginner:
        direct = (
            f"ETF comparison **{t1} vs {t2}**: overlap **{ov:.1f}%** — "
            + ("high duplication; prefer one core sleeve." if ov >= 35 else "moderate overlap; size sleeves intentionally.")
        )
        analyst = (
            f"**{t1}** = broad beta exposure; **{t2}** = {'growth/tech concentration' if growth_tilt else 'alternate factor'}. "
            "Combined overlap raises effective mega-cap weight and reduces independent diversification."
        )
    elif beginner:
        direct = (
            f"**{t1}** and **{t2}** share about **{ov:.0f}%** of the same underlying holdings — "
            + ("that is meaningful duplication." if ov >= 35 else "some overlap is normal for broad US funds.")
        )
        analyst = (
            "Owning two funds with similar holdings means you may think you are diversified when both "
            "move with the same large stocks (often Apple, Microsoft, NVIDIA in index ETFs)."
        )
    else:
        direct = f"Highest pairwise overlap: **{t1}/{t2}** ≈ **{ov:.1f}%** (sum of min inner weights)."
        analyst = (
            "High overlap increases effective concentration in shared mega-cap names and reduces "
            "independent diversification benefit between sleeves."
        )

    key_vars = "\n".join(
        f"- **{p.get('pair')}**: **{float(p.get('overlap_pct') or 0):.1f}%**" for p in pairs[:5]
    )
    tradeoffs = (
        "**Stacking similar index ETFs** → simpler implementation, but hidden duplication.\n"
        "**Consolidating to one core sleeve** → cleaner exposure, easier rebalancing."
    )
    actions = (
        f"Consider keeping one primary US equity sleeve instead of both **{t1}** and **{t2}** "
        "if overlap exceeds your tolerance (~35%)."
        if ov >= 35
        else "Overlap is moderate — verify sector goals before adding a third broad equity fund."
    )
    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables=key_vars,
        tradeoffs=tradeoffs,
        recommended_actions=actions,
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="etf_overlap",
        model_name="ETF overlap analyst",
        confidence_pct=82 if ov else 60,
        computed={"max_overlap_pct": ov, "max_overlap_pair": top_pair.get("pair")},
    )


def diversification_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    breakdown = ctx.get("asset_class_breakdown")
    rows = _weight_rows(ctx)
    if isinstance(breakdown, dict) and breakdown:
        items = sorted(((k, float(v)) for k, v in breakdown.items()), key=lambda x: x[1], reverse=True)
        top_class, top_pct = items[0]
        equity_pct = sum(p for k, p in items if "equity" in k.lower())
        bond_pct = sum(p for k, p in items if "bond" in k.lower() or "bill" in k.lower())
        n_classes = len(items)
        if top_pct >= 70 or n_classes < 2:
            judgment = "Not fully diversified"
        elif n_classes >= 3 and top_pct < 50:
            judgment = "Yes — moderately diversified"
        elif n_classes >= 2 and top_pct < 60:
            judgment = "Partially diversified — room to improve"
        else:
            judgment = "Moderately diversified with concentration in one sleeve"
    elif rows:
        top_class, top_pct = "Equity (default)", sum(p for _, p in rows)
        equity_pct, bond_pct = top_pct, 0.0
        items = [("Equity (default)", top_pct)]
        judgment = "Partially diversified — single asset-class proxy from weights"
    else:
        direct = "Add holdings to assess diversification across asset classes."
        sections = build_analyst_sections(
            direct_answer=direct,
            risk_notes=_default_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="diversification",
            model_name="Diversification analyst",
            confidence_pct=55,
        )

    if beginner:
        direct = (
            f"**{judgment}.** Your mix is led by **{top_class}** at about **{top_pct:.1f}%**."
            + (f" Equities total ~**{equity_pct:.1f}%**." if equity_pct else "")
        )
        analyst = (
            "Diversification means spreading across asset classes (stocks, bonds, real estate, cash) "
            "so one type of market stress does not drive everything."
        )
        if bond_pct < 10 and equity_pct > 70:
            actions = "You are equity-heavy — adding bonds or defensive sleeves can reduce portfolio swings."
        else:
            actions = "Compare this mix to your goal; fill missing asset classes if the balance feels off."
    else:
        direct = (
            f"**{judgment}.** Asset-class mix: **{top_class}** **{top_pct:.1f}%** dominant; "
            f"equity **{equity_pct:.1f}%**, defensive/bond **{bond_pct:.1f}%**."
        )
        analyst = "Diversification quality depends on asset-class balance, geographic spread, and correlation — not ticker count alone."
        actions = "Use target weights to close gaps in underrepresented asset classes; monitor effective overlap among equity ETFs."

    key_vars = "\n".join(f"- **{k}**: **{p:.1f}%**" for k, p in items[:6])
    tradeoffs = (
        "**More asset classes** → smoother drawdowns potential, but more funds to manage.\n"
        "**Equity-heavy mix** → higher growth potential, larger bear-market swings."
    )
    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables=key_vars,
        tradeoffs=tradeoffs,
        recommended_actions=actions,
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="diversification",
        model_name="Diversification analyst",
        confidence_pct=80,
        computed={"equity_pct": round(equity_pct, 1), "bond_pct": round(bond_pct, 1)},
    )


def valuation_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    vctx = resolve_valuation_context(question, ctx)
    target = vctx.get("target_ticker")
    ticker_data = dict(vctx.get("ticker_data") or {})
    assessment = dict(vctx.get("assessment") or {})
    macro_env = str(vctx.get("macro_env") or "Fair Value")
    macro_fx = dict(vctx.get("macro_effects") or {})
    port_w = vctx.get("portfolio_weight_pct")
    sym = str(ticker_data.get("ticker") or target or "").strip().upper()
    name = str(ticker_data.get("name") or sym or "this holding")
    pe = ticker_data.get("pe")
    style = str(ticker_data.get("style") or "broad")
    label = str(assessment.get("label") or "unknown")
    headline = str(assessment.get("headline") or "")
    ey = assessment.get("earnings_yield_pct")
    impl_g = assessment.get("implied_growth_pct")
    fair_mid = assessment.get("fair_pe_mid")

    if not sym:
        direct = (
            "Name a ticker or ETF (for example VOO or SCHD) so I can frame whether it looks expensive or fair."
            if beginner
            else "Specify a ticker/ETF in the question — valuation analysis needs a target security."
        )
        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=(
                "Valuation is security-specific. Broad market P/E, fund style, and your macro assumptions "
                "all shape whether an investment looks rich or cheap."
            ),
            recommended_actions="Ask e.g. “Is SCHD expensive?” or “What growth rate is implied for VOO?”",
            risk_notes=_default_risk_notes(beginner),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            problem_type="valuation",
            model_name="Valuation analyst",
            confidence_pct=55,
        )

    if style == "bond":
        direct = (
            f"**{sym}** is a bond fund — equity P/E is not the right lens. Focus on **yield**, **duration**, "
            "and how **rate changes** affect price."
        )
        analyst = (
            "Bond valuation is driven by interest rates and credit quality, not earnings multiples. "
            f"Your macro valuation setting (**{macro_env}**) mainly affects **equity** sleeves in the portfolio."
        )
    elif label == "unknown" or pe is None:
        direct = f"I cannot pin a reliable P/E on **{sym}** right now — use fund style and macro backdrop instead."
        analyst = (
            f"Without a clean multiple, analysts still ask: what growth must **{name}** deliver to justify today's price? "
            f"Macro valuation environment: **{macro_env}**."
        )
    else:
        direct = f"**{sym}** {headline}"
        if port_w:
            direct += f" It is **{port_w:.1f}%** of your portfolio."
        analyst = (
            f"At P/E **{pe:.1f}**, earnings yield is about **{ey:.1f}%** — the market is pricing in roughly "
            f"**{impl_g:.1f}%** long-run growth (educational estimate vs a ~10% required return). "
            f"For **{style}** funds, a typical fair P/E band centers near **{fair_mid:.0f}**. "
            f"Your Portfolio Health macro setting is **{macro_env}**, which shifts forward equity return "
            f"by about **{macro_fx.get('equity_return_shift_pct', 0):+.1f}%** on your **{vctx.get('equity_pct', 0):.0f}%** equity sleeve."
        )

    q_lower = str(question or "").lower()
    asks_growth = any(p in q_lower for p in ("growth rate", "implied", "assumptions matter", "what assumptions"))
    asks_expensive = any(p in q_lower for p in ("expensive", "overvalued", "cheap", "undervalued", "fair"))

    key_lines = [
        f"- Target: **{sym}** ({ticker_data.get('category', 'ETF')})",
        f"- Valuation label: **{label.replace('_', ' ')}**",
        f"- Macro valuation environment: **{macro_env}**",
        f"- Portfolio equity sleeve: **{vctx.get('equity_pct', 0):.0f}%**",
    ]
    if pe is not None:
        key_lines.extend(
            [
                f"- Trailing P/E: **{pe:.1f}** ({ticker_data.get('pe_source', 'estimate')})",
                f"- Earnings yield (1/P/E): **{ey:.1f}%**",
                f"- Implied growth (est.): **{impl_g:.1f}%**",
                f"- Style fair P/E midpoint: **{fair_mid:.0f}**" if fair_mid else "",
            ]
        )
    if port_w:
        key_lines.append(f"- Your portfolio weight in **{sym}**: **{port_w:.1f}%**")
    key_lines = [ln for ln in key_lines if ln]

    if asks_growth and impl_g is not None:
        tradeoffs = (
            f"**Higher implied growth ({impl_g:.1f}%)** means the market already expects strong earnings — "
            "surprises must beat that bar.\n"
            "**Lower growth assumptions** would justify a cheaper multiple — downside if growth disappoints."
        )
    elif asks_expensive:
        tradeoffs = (
            "**Buying rich multiples** can work if growth delivers — but margin of safety is thinner.\n"
            "**Waiting for cheaper entry** reduces upside timing risk but may mean sitting in cash longer."
        )
    else:
        tradeoffs = (
            "**Style matters** — growth ETFs tolerate higher P/E than dividend/value funds.\n"
            "**Macro backdrop matters** — expensive markets can stay rich until rates or earnings shift."
        )

    sens = list(vctx.get("sensitivity") or [])
    if sens and not beginner:
        what_if = "\n".join(f"- **{s['scenario']}** → {s['impact']}" for s in sens[:3])
    elif pe is not None and impl_g is not None:
        what_if = (
            f"- If growth expectations fall 2% → P/E compression risk on **{sym}**\n"
            f"- If macro shifts to **Expensive** → ~**{abs(macro_fx.get('equity_return_shift_pct') or 1.5):.1f}%** "
            f"headwind on equity sleeve\n"
            f"- If earnings grow faster than **{impl_g:.1f}%** implied → multiple may hold or expand"
        )
    else:
        what_if = f"- Macro **{macro_env}** → equity return shift ~**{macro_fx.get('equity_return_shift_pct', 0):+.1f}%**"

    if label in {"expensive", "moderately rich"}:
        actions = (
            f"If **{sym}** feels rich, consider whether you already get similar exposure elsewhere, "
            "or dollar-cost average rather than lump-sum adding."
        )
    elif label == "cheap":
        actions = (
            f"**{sym}** looks relatively cheap for its style — confirm the thesis fits your allocation "
            "before sizing up."
        )
    else:
        actions = (
            f"For **{sym}**, focus on whether implied growth (~**{impl_g:.1f}%**)" if impl_g else f"For **{sym}**, focus"
        ) + " matches your view — valuation is about expectations, not just today's price."

    if port_w and port_w >= 20 and label in {"expensive", "moderately rich"}:
        actions += f" At **{port_w:.0f}%** portfolio weight, multiple compression on **{sym}** would be noticeable."

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=tradeoffs,
        what_if_scenarios=what_if,
        recommended_actions=actions,
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    conf = 78 if pe is not None else 62
    if ticker_data.get("pe_source") == "live":
        conf = min(85, conf + 4)
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="valuation",
        model_name="Valuation analyst",
        confidence_pct=conf,
        computed={
            "target_ticker": sym,
            "pe": pe,
            "valuation_label": label,
            "implied_growth_pct": impl_g,
            "macro_valuation": macro_env,
            "portfolio_weight_pct": port_w,
        },
    )


def scenario_stress_answer(ctx: dict[str, Any], *, beginner: bool, question: str = "") -> InvestmentSolverResult:
    params = dict(ctx.get("scenario_params") or {})
    tech_dd = _parse_scenario_drawdown_pct(ctx, question=question, default=20.0)
    rate_shock = str(params.get("rate_shock") or ctx.get("health_rate_env") or "").strip()
    rows = _weight_rows(ctx)
    exposure = resolve_tech_exposure(ctx)
    direct_pct = float(exposure.get("direct_pct") or 0)
    embedded_pct = float(exposure.get("embedded_pct") or 0)
    total_tech_pct = float(exposure.get("total_pct") or direct_pct + embedded_pct)
    embedded_holdings = list(exposure.get("embedded_holdings") or [])
    bond_pct = sum(
        p for t, p in rows if t in {"BND", "AGG", "TLT", "BIL", "SCHZ", "IEF"}
    )
    equity_pct = max(0.0, 100.0 - bond_pct) if rows else 0.0

    tech_impact = total_tech_pct * (tech_dd / 100.0)
    embedded_bits = ", ".join(
        f"**{h['ticker']}** (~{h.get('contribution_pct', 0):.1f}% tech contribution)"
        for h in embedded_holdings[:3]
    )

    if beginner:
        if direct_pct <= 0 and embedded_pct > 0:
            direct = (
                f"You do not hold a dedicated technology ETF, but embedded tech exposure is about "
                f"**{embedded_pct:.1f}%** of your portfolio. A **{tech_dd:.0f}%** tech drawdown could "
                f"still reduce the portfolio by roughly **{tech_impact:.1f}%** (simple estimate)."
            )
        elif total_tech_pct > 0:
            direct = (
                f"A **{tech_dd:.0f}%** technology drawdown could reduce your portfolio by about "
                f"**{tech_impact:.1f}%** based on **{total_tech_pct:.1f}%** total tech exposure."
            )
        else:
            direct = (
                f"With minimal technology exposure detected, a tech-only **{tech_dd:.0f}%** shock "
                f"would likely have a **small direct impact** — other sectors would matter more."
            )
        analyst = (
            "Technology exposure comes from **direct tech funds** (like QQQ) and **embedded exposure** "
            "inside broad/dividend ETFs (like VTI, SCHD, VYM). Even without a tech ETF, a sector selloff "
            "can still hit your portfolio through those underlying holdings."
        )
        if embedded_bits:
            analyst += f" Largest embedded contributors: {embedded_bits}."
        what_if = (
            f"**Tech drawdown {tech_dd:.0f}%** → ~**{tech_impact:.1f}%** portfolio impact "
            f"(total tech exposure **{total_tech_pct:.1f}%**).\n"
            f"Bond/defensive sleeve **{bond_pct:.1f}%** may offset some equity stress."
        )
    else:
        if direct_pct <= 0 and embedded_pct > 0:
            direct = (
                f"No dedicated tech sleeve; **embedded tech exposure ≈ {embedded_pct:.1f}%**. "
                f"Tech shock **-{tech_dd:.0f}%** → illustrative portfolio impact **~{tech_impact:.1f}%**."
            )
        else:
            direct = (
                f"Tech shock **-{tech_dd:.0f}%** → portfolio impact **~{tech_impact:.1f}%** "
                f"(direct **{direct_pct:.1f}%** + embedded **{embedded_pct:.1f}%** = **{total_tech_pct:.1f}%**)."
            )
        analyst = (
            "Scenario model: portfolio impact ≈ (direct tech weight + Σ fund_weight × tech_sector_weight_in_fund) × shock. "
            "Embedded exposure captures technology holdings inside diversified and dividend ETFs."
        )
        if embedded_bits:
            analyst += f" Top embedded: {embedded_bits}."
        what_if = (
            f"- Direct tech sleeves: **{direct_pct:.1f}%**\n"
            f"- Embedded tech exposure: **{embedded_pct:.1f}%**\n"
            f"- Combined tech exposure: **{total_tech_pct:.1f}%**\n"
            f"- Shock **-{tech_dd:.0f}%** → **~{tech_impact:.1f}%** portfolio\n"
            f"- Equity sleeve **~{equity_pct:.1f}%** | Bond/defensive **{bond_pct:.1f}%**"
            + (f"\n- Rate environment: **{rate_shock}**" if rate_shock else "")
        )

    key_lines = [
        f"- Direct technology ETFs: **{direct_pct:.1f}%**",
        f"- Embedded technology exposure: **{embedded_pct:.1f}%**",
        f"- Total technology exposure (est.): **{total_tech_pct:.1f}%**",
        f"- Bond/defensive: **{bond_pct:.1f}%**",
    ]
    for h in embedded_holdings[:4]:
        key_lines.append(
            f"- **{h['ticker']}**: {h.get('portfolio_weight_pct')}% of portfolio × "
            f"{h.get('tech_weight_in_fund_pct')}% tech in fund ≈ **{h.get('contribution_pct')}%**"
        )

    actions = (
        "If embedded tech exposure is higher than you realized, consider whether your dividend/broad sleeves "
        "already give enough growth tilt — or add defensive assets if tech volatility feels too high."
        if embedded_pct > direct_pct
        else "If tech shock impact exceeds comfort, trim dedicated tech sleeves or rebalance toward targets."
    )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables="\n".join(key_lines),
        tradeoffs=(
            "**Ignoring embedded exposure** understates tech shock risk in broad/dividend portfolios.\n"
            "**Focusing only on ETF labels** misses underlying sector composition."
        ),
        what_if_scenarios=what_if,
        recommended_actions=actions,
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="scenario_stress",
        model_name="Portfolio scenario analyst",
        confidence_pct=82 if total_tech_pct > 0 else 68,
        computed={
            "tech_drawdown_pct": tech_dd,
            "direct_tech_pct": round(direct_pct, 2),
            "embedded_tech_pct": round(embedded_pct, 2),
            "total_tech_pct": round(total_tech_pct, 2),
            "illustrative_impact_pct": round(tech_impact, 2),
        },
    )


def solve_phase2_or_structured(
    intent: str,
    ctx: dict[str, Any],
    *,
    beginner: bool,
    question: str = "",
) -> tuple[InvestmentSolverRoute, InvestmentSolverResult] | None:
    if intent == "portfolio_concentration":
        result = structured_concentration_answer(ctx, beginner=beginner)
    elif intent == "portfolio_risk":
        result = structured_portfolio_risk_answer(ctx, beginner=beginner)
    elif intent == "etf_overlap":
        result = etf_overlap_answer(ctx, beginner=beginner, question=question)
    elif intent == "diversification":
        result = diversification_answer(ctx, beginner=beginner)
    elif intent == "scenario_stress":
        result = scenario_stress_answer(ctx, beginner=beginner, question=question)
    elif intent == "macro_rates":
        from investment_ami_macro import macro_rates_answer

        result = macro_rates_answer(ctx, beginner=beginner, question=question)
    elif intent == "macro_recession":
        from investment_ami_macro import macro_recession_answer

        result = macro_recession_answer(ctx, beginner=beginner, question=question)
    elif intent == "macro_inflation":
        from investment_ami_macro import macro_inflation_answer

        result = macro_inflation_answer(ctx, beginner=beginner, question=question)
    elif intent == "allocation_recommendation":
        from investment_ami_allocation import allocation_recommendation_answer

        result = allocation_recommendation_answer(ctx, beginner=beginner, question=question)
    elif intent == "valuation":
        result = valuation_answer(ctx, beginner=beginner, question=question)
    else:
        return None
    route = _route_for_intent(intent)
    result.problem_type = route.problem_type
    result.model_name = route.model_name
    return route, result
