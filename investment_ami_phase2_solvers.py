"""Phase 2 Investment AMI solvers — structured analyst answers and new families."""

from __future__ import annotations

from typing import Any

from investment_ami_answer_format import build_analyst_sections
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
                "Concentration measures how much of your portfolio sits in a few positions. "
                "Without weights, I cannot score single-name or top-3 exposure."
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
            direct = f"Not highly concentrated on one name. Largest holding **{top_ticker}** is **{top_pct:.1f}%**."
        analyst = (
            f"Your top three holdings (**{', '.join(t for t, _ in rows[:3])}**) add up to about **{top3:.1f}%**. "
            "When a few funds dominate, your portfolio tends to move with those positions — good when they rise, "
            "painful when one falls sharply."
        )
        tradeoffs = (
            "**More concentration** → simpler portfolio, clearer bets, but bigger swings from one position.\n"
            "**More diversification** → smoother ride, less single-name shock, but you may lag a hot sector."
        )
        actions = (
            "If concentration feels uncomfortable, consider trimming the largest weight toward your target mix "
            "or adding a complementary asset class (e.g., bonds or a broad market fund)."
        )
    else:
        direct = (
            f"Concentration scan ({_portfolio_label(ctx)}): top **{top_ticker}** **{top_pct:.1f}%**; "
            f"top-3 **{top3:.1f}%** → **{flag}** single-name concentration."
        )
        analyst = (
            f"Top-3 weight **{top3:.1f}%** implies meaningful **idiosyncratic risk** — portfolio volatility will "
            f"track {top_ticker} and peers in the top bucket more than a diversified index-like mix."
        )
        tradeoffs = (
            "Higher top-weight concentration increases tracking error vs a broad benchmark and amplifies "
            "drawdowns if the dominant sleeve underperforms. Lower concentration reduces single-factor shock "
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
    tech_pct = sum(p for t, p in rows if t in _TECH_TICKERS)
    top_ticker, top_pct = rows[0] if rows else ("—", 0.0)
    top3 = sum(p for _, p in rows[:3]) if rows else 0.0

    if beginner:
        direct = "Your biggest risks right now are concentration, sector tilt, and how much volatility you are carrying."
        analyst = (
            f"Largest position **{top_ticker}** at **{top_pct:.1f}%** can move the whole portfolio. "
            + (f"Tech-heavy funds add about **{tech_pct:.1f}%** of technology tilt. " if tech_pct >= 15 else "")
            + (f"Health check labels risk as **{risk_level}**." if risk_level else "")
        ).strip()
        key_vars = "\n".join(
            filter(
                None,
                [
                    f"- Largest holding: **{top_ticker}** **{top_pct:.1f}%**" if rows else None,
                    f"- Top-3 concentration: **{top3:.1f}%**" if rows else None,
                    f"- Tech/growth proxy: **{tech_pct:.1f}%**" if tech_pct else None,
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
            "and **historical volatility** where available. Dominant sleeve drives short-term P&L variance."
        )
        key_vars = "\n".join(
            filter(
                None,
                [
                    f"- Top-weight risk: **{top_ticker}** **{top_pct:.1f}%**" if rows else None,
                    f"- Top-3 concentration: **{top3:.1f}%**" if rows else None,
                    f"- Technology/growth proxy: **{tech_pct:.1f}%**" if tech_pct else None,
                    f"- Historical volatility: **{vol}**" if vol else None,
                    f"- Health risk level: **{risk_level}**" if risk_level else None,
                    f"- Max drawdown (historical): **{ctx.get('max_drawdown')}**" if ctx.get("max_drawdown") else None,
                ],
            )
        )
        tradeoffs = (
            "Reducing concentration lowers single-name shock but may trim intentional factor bets. "
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


def etf_overlap_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    pairs = ctx.get("etf_overlap_pairs")
    rows = _weight_rows(ctx)
    tickers = [t for t, _ in rows]

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

    if beginner:
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
    elif rows:
        top_class, top_pct = "Equity (default)", sum(p for _, p in rows)
        equity_pct, bond_pct = top_pct, 0.0
        items = [("Equity (default)", top_pct)]
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
            f"Your mix is led by **{top_class}** at about **{top_pct:.1f}%**."
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
            f"Asset-class mix: **{top_class}** **{top_pct:.1f}%** dominant; "
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


def scenario_stress_answer(ctx: dict[str, Any], *, beginner: bool) -> InvestmentSolverResult:
    params = dict(ctx.get("scenario_params") or {})
    tech_dd = _parse_weight_pct(params.get("tech_drawdown_pct")) or float(params.get("tech_drawdown_pct") or 20)
    rate_shock = str(params.get("rate_shock") or ctx.get("health_rate_env") or "").strip()
    rows = _weight_rows(ctx)
    tech_pct = sum(p for t, p in rows if t in _TECH_TICKERS)
    bond_pct = sum(
        p for t, p in rows if t in {"BND", "AGG", "TLT", "BIL", "SCHZ", "IEF"}
    )
    equity_pct = max(0.0, 100.0 - bond_pct) if rows else 0.0

    tech_impact = tech_pct * (tech_dd / 100.0)
    if beginner:
        direct = (
            f"If tech/growth funds fell **{tech_dd:.0f}%**, a rough impact is about **{tech_impact:.1f}%** "
            "on your total portfolio (simple static estimate)."
        )
        analyst = (
            f"You have about **{tech_pct:.1f}%** in tech-heavy funds. "
            "Scenario math assumes those funds move together — real markets are messier."
        )
        what_if = (
            f"**Tech drawdown {tech_dd:.0f}%** → ~**{tech_impact:.1f}%** portfolio hit.\n"
            f"Bond sleeve **{bond_pct:.1f}%** may offset some equity stress — depends on rate environment."
        )
    else:
        direct = (
            f"Scenario: tech/growth proxy **-{tech_dd:.0f}%** → illustrative portfolio impact **~{tech_impact:.1f}%** "
            f"(tech proxy weight **{tech_pct:.1f}%**)."
        )
        analyst = "Static shock model: portfolio impact ≈ sleeve weight × shock. Ignores correlation, beta, and cross-asset moves."
        what_if = (
            f"- Tech/growth **-{tech_dd:.0f}%**: **~{tech_impact:.1f}%** portfolio\n"
            f"- Equity sleeve **~{equity_pct:.1f}%** (non-tech moves not modeled)\n"
            f"- Bond/defensive **{bond_pct:.1f}%**"
            + (f"\n- Rate environment: **{rate_shock}**" if rate_shock else "")
        )

    sections = build_analyst_sections(
        direct_answer=direct,
        portfolio_analyst_view=analyst,
        key_variables=f"- Tech proxy weight: **{tech_pct:.1f}%**\n- Bond/defensive: **{bond_pct:.1f}%**",
        tradeoffs="Scenario analysis highlights vulnerability; it is not a forecast.",
        what_if_scenarios=what_if,
        recommended_actions=(
            "If tech shock impact exceeds comfort, trim tech-heavy sleeves or add diversifiers before the stress happens."
        ),
        risk_notes=_default_risk_notes(beginner),
        beginner=beginner,
    )
    return InvestmentSolverResult(
        short_answer=direct,
        analyst_sections=sections,
        problem_type="scenario_stress",
        model_name="Portfolio scenario analyst",
        confidence_pct=78,
        computed={"tech_drawdown_pct": tech_dd, "illustrative_impact_pct": round(tech_impact, 2)},
    )


def solve_phase2_or_structured(
    intent: str,
    ctx: dict[str, Any],
    *,
    beginner: bool,
) -> tuple[InvestmentSolverRoute, InvestmentSolverResult] | None:
    if intent == "portfolio_concentration":
        result = structured_concentration_answer(ctx, beginner=beginner)
    elif intent == "portfolio_risk":
        result = structured_portfolio_risk_answer(ctx, beginner=beginner)
    elif intent == "etf_overlap":
        result = etf_overlap_answer(ctx, beginner=beginner)
    elif intent == "diversification":
        result = diversification_answer(ctx, beginner=beginner)
    elif intent == "scenario_stress":
        result = scenario_stress_answer(ctx, beginner=beginner)
    else:
        return None
    route = _route_for_intent(intent)
    result.problem_type = route.problem_type
    result.model_name = route.model_name
    return route, result
