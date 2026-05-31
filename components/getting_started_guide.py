"""In-app tutorial and user guide for the Investment Portfolio Analyzer."""

from __future__ import annotations

import streamlit as st

APP_DISCLAIMER = "Educational and analytical tool. Not financial advice."

GUIDE_CSS = """
<style>
.guide-hero {
    background: linear-gradient(135deg, #0c1524 0%, #152238 55%, #1a2d4a 100%);
    border: 1px solid #2d3f57;
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
}
.guide-hero h3 { color: #f1f5f9; margin: 0 0 0.4rem 0; font-size: 1.15rem; }
.guide-hero p { color: #94a3b8; margin: 0; font-size: 0.9rem; line-height: 1.5; }
.guide-disclaimer {
    background: rgba(245, 166, 35, 0.10);
    border: 1px solid rgba(245, 166, 35, 0.35);
    border-radius: 10px;
    padding: 0.65rem 0.9rem;
    color: #f5d08a;
    font-size: 0.85rem;
    margin: 0.75rem 0 1rem 0;
}
.guide-nav-hint {
    background: rgba(77, 163, 255, 0.08);
    border-left: 3px solid #4da3ff;
    padding: 0.55rem 0.85rem;
    border-radius: 0 8px 8px 0;
    font-size: 0.86rem;
    color: #cbd5e1;
    margin: 0.5rem 0 0.75rem 0;
}
.guide-feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.45rem;
    margin: 0.65rem 0 0.85rem 0;
}
.guide-feature-chip {
    background: rgba(20, 28, 43, 0.85);
    border: 1px solid #334155;
    color: #cbd5e1;
    font-size: 0.78rem;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
}
.guide-step-num {
    display: inline-block;
    background: #4da3ff;
    color: #0b1220;
    font-weight: 700;
    font-size: 0.72rem;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    margin-right: 0.35rem;
}
.guide-portfolio-table {
    font-size: 0.88rem;
    color: #cbd5e1;
}
.guide-portfolio-table td { padding: 0.2rem 0.75rem 0.2rem 0; }
</style>
"""


def _nav_hint(tab_name: str, detail: str = "") -> None:
    extra = f" — {detail}" if detail else ""
    st.markdown(
        f'<div class="guide-nav-hint">📍 <b>Where to go:</b> Open the '
        f'<b>{tab_name}</b> tab at the top of this page{extra}.</div>',
        unsafe_allow_html=True,
    )


def _render_what_this_app_does() -> None:
    st.markdown(
        """
        <div class="guide-hero">
          <h3>Welcome — no finance background required</h3>
          <p>
            This app helps you <b>build, analyze, stress test, and monitor</b> investment portfolios
            using quantitative finance tools. Think of it as a structured workbook: you enter holdings,
            the app runs the math, and you interpret the results against your goals.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="guide-disclaimer">⚠️ {APP_DISCLAIMER}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("**What you can do here:**")
    features = [
        "Portfolio analytics",
        "Diversification analysis",
        "Risk measurement",
        "Monte Carlo simulation",
        "Portfolio optimization",
        "Benchmark comparison",
        "Macroeconomic analysis",
        "Portfolio health monitoring",
    ]
    chips = "".join(f'<span class="guide-feature-chip">{f}</span>' for f in features)
    st.markdown(f'<div class="guide-feature-grid">{chips}</div>', unsafe_allow_html=True)

    with st.expander("Who is this for?", expanded=False):
        st.markdown(
            """
            - **Beginners** learning how portfolios behave over time
            - **DIY investors** comparing allocations before making changes
            - **Students** practicing quantitative finance concepts with real market data

            You do not need to pick stocks like a professional. Start with broad ETFs (funds that track
            many companies or bonds), set percentages, and let the app show risk and return tradeoffs.
            """
        )

    with st.expander("How the tabs fit together", expanded=False):
        st.markdown(
            """
            | Tab | Purpose |
            |-----|---------|
            | **Getting Started Guide** | This tutorial — read first |
            | **Overview** | Summary metrics, benchmarks, recommendations |
            | **Portfolio Inputs** | Enter tickers and weights |
            | **Risk Analysis** | Correlations, concentration, scenarios |
            | **Portfolio Health** | Ongoing monitoring and rebalance ideas |
            | **Explain This Portfolio** | Plain-English memo of your allocation |
            | **Forward-Looking Macro Analysis** | Stress test under macro assumptions |
            | **Monte Carlo** | Range of possible future outcomes |
            | **Optimization** | Model-efficient allocations |
            | **Efficient Frontier** | Visual risk/return tradeoff curve |
            | **Math Problem Solving Lab** | Practice portfolio math |
            """
        )


def _render_workflow() -> None:
    st.markdown(
        "Follow these steps in order the first time you use the app. "
        "After that, jump to the sections you need."
    )

    with st.expander("Step 1 — Define Your Goal", expanded=True):
        st.markdown(
            """
            Before picking investments, decide **why** you are investing. Your goal shapes how much
            risk you can tolerate and how you will judge success.

            **Common objectives:**
            - **Retirement** — long horizon, balance growth and stability
            - **Long-term growth** — accept more volatility for higher expected return
            - **Income** — emphasize dividends and bond interest
            - **Capital preservation** — prioritize not losing money over maximizing gains
            - **Short-term cash management** — low volatility, high liquidity
            - **Balanced investing** — mix of stocks and bonds for moderate risk

            **Why objectives matter:** The same portfolio can look "good" or "bad" depending on your goal.
            A growth-heavy portfolio may score well on return but poorly for capital preservation.
            """
        )
        _nav_hint("Overview", "use the Portfolio Recommendation Engine to translate goals into a starting mix")

    with st.expander("Step 2 — Build a Portfolio"):
        st.markdown(
            """
            Go to **Portfolio Inputs** and enter:
            - **Ticker symbols** — Yahoo Finance codes (e.g. `SPY` = S&P 500 ETF)
            - **Allocation percentages** — how much of your portfolio each holding represents
            - **Asset type** — Equity, Bonds, T-Bills, REIT, etc. (helps classification and health checks)

            **Allocations should total 100%.** If they do not, the app auto-normalizes but you should fix
            them for clarity.

            You can also use **Portfolio Presets** in the sidebar (Conservative, Balanced, Aggressive, etc.)
            and click **Apply preset**.
            """
        )
        _nav_hint("Portfolio Inputs")

        st.markdown("**Example starter portfolios (must sum to 100%):**")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Conservative**")
            st.markdown(
                """
                | Ticker | Weight |
                |--------|--------|
                | SPY | 30% |
                | AGG | 50% |
                | BIL | 20% |

                *More bonds and cash; lower expected volatility.*
                """
            )
        with c2:
            st.markdown("**Balanced**")
            st.markdown(
                """
                | Ticker | Weight |
                |--------|--------|
                | SPY | 40% |
                | QQQ | 15% |
                | AGG | 30% |
                | VNQ | 15% |

                *Stocks + bonds + real estate.*
                """
            )
        with c3:
            st.markdown("**Growth**")
            st.markdown(
                """
                | Ticker | Weight |
                |--------|--------|
                | SPY | 40% |
                | QQQ | 35% |
                | IWM | 25% |

                *Equity-focused; higher risk and return potential.*
                """
            )

        st.info(
            "Tip: `SPY` tracks large U.S. companies, `AGG` is a broad bond fund, "
            "`BIL` is short-term Treasury bills (cash-like), `QQQ` is tech-heavy, "
            "`IWM` is smaller companies, `VNQ` is real estate."
        )

    with st.expander("Step 3 — Review Portfolio Summary"):
        st.markdown(
            """
            Open **Overview** to see historical performance statistics. These describe how your
            portfolio * behaved in the past* — they are not guarantees of the future.
            """
        )
        _nav_hint("Overview", "Portfolio Summary section at the top")

        metrics_help = [
            ("Annual Return", "Average yearly gain/loss based on daily returns in the selected period.", "8% means $100 grew to ~$108 over one year on average."),
            ("Volatility", "How much returns swing up and down (standard deviation, annualized).", "Higher = bumpier ride. Bond-heavy portfolios usually have lower volatility."),
            ("Sharpe Ratio", "Return earned per unit of total risk, vs. the risk-free rate.", "Above ~1.0 is generally strong. Compare across portfolios with similar goals."),
            ("Sortino Ratio", "Like Sharpe, but only penalizes downside volatility.", "Useful when you care more about losses than upside swings."),
            ("CAGR", "Compound Annual Growth Rate — smoothed yearly growth if returns compounded steadily.", "Good for comparing long-run growth paths."),
            ("Beta", "Sensitivity vs. SPY (market). 1.0 moves with the market; >1 is more aggressive.", "Beta 1.2 tends to rise/fall 20% more than SPY in market moves."),
            ("Max Drawdown", "Largest peak-to-trough decline in the analysis window.", "Shows worst historical loss from a high point — a stress-test for your comfort."),
        ]
        for name, definition, example in metrics_help:
            with st.expander(name, expanded=False):
                st.markdown(f"{definition}  \n\n*Example:* {example}")

    with st.expander("Step 4 — Analyze Risk"):
        st.markdown(
            """
            Risk is more than "how much could I lose?" — it is also **how holdings interact**.

            In **Risk Analysis** (Full analysis mode), review:
            - **Correlation Matrix** — do assets move together or offset each other?
            - **Diversification** — lower average correlation often improves risk-adjusted returns
            - **Risk concentration** — a few holdings may drive most of your volatility
            - **Drawdowns & scenarios** — hypothetical shocks to returns

            **Key idea:** Two assets with similar returns but low correlation can produce a smoother
            combined portfolio. That is the main benefit of diversification.
            """
        )
        _nav_hint("Risk Analysis", "switch sidebar to Full analysis mode, then click Run Risk & Macro Analysis")

    with st.expander("Step 5 — Compare Benchmarks"):
        st.markdown(
            """
            Benchmarks answer: *"Am I doing better or worse than a simple alternative?"*

            In **Overview → Benchmark Comparison**, compare against:
            - **SPY** — broad U.S. large-cap stocks (common "market" benchmark)
            - **QQQ** — Nasdaq 100, tech-heavy growth benchmark
            - **60/40** — 60% SPY + 40% AGG, classic balanced benchmark
            - **T-Bills (BIL)** — cash-like, minimal risk benchmark

            **How to compare:** Look at return, volatility, Sharpe, and max drawdown side by side.
            Beating SPY on return but with much higher drawdown may not fit a conservative goal.
            """
        )
        _nav_hint("Overview", "Benchmark Comparison section — click Run Benchmark Comparison")

    with st.expander("Step 6 — Run Monte Carlo"):
        st.markdown(
            """
            **Monte Carlo simulation** runs thousands of random future paths based on historical
            return and volatility patterns. It shows a **range of possibilities**, not a prediction.

            Key outputs:
            - **Probability of success / loss** — chance of ending above or below starting value
            - **Probability of reaching target value** — e.g. retirement goal
            - **Percentile outcomes** — 5th, 25th, median, 75th, 95th ending values

            **Interpretation:** Use percentiles to plan. The median is the "middle" outcome;
            the 5th percentile is a pessimistic scenario. Markets can do worse than history suggests.
            """
        )
        _nav_hint("Monte Carlo", "Full analysis mode — click Run Monte Carlo")

    with st.expander("Step 7 — Use the Optimizer"):
        st.markdown(
            """
            The **Optimizer** uses mean-variance math to suggest allocations on the efficient frontier:
            - **Maximum Sharpe** — best risk-adjusted return in the model
            - **Minimum Volatility** — lowest volatility in the model
            - **Efficient Frontier** tab — curve of optimal risk/return combinations

            You can set **constraints** (e.g. minimum bond/cash weight) so suggestions stay realistic.

            **Important:** Optimization is a **model**, not a guarantee. It assumes historical patterns
            continue and can over-concentrate in assets that looked best recently.
            """
        )
        _nav_hint("Optimization", "Full analysis mode — click Run Portfolio Optimizer")
        st.caption("Also see the **Efficient Frontier** tab for the visual tradeoff curve.")

    with st.expander("Step 8 — Use Portfolio Objectives"):
        st.markdown(
            """
            Objectives translate your goal into target asset mixes. The app supports:

            | Objective | Typical focus |
            |-----------|---------------|
            | **Capital Preservation** | Bonds and T-Bills; limit equity exposure |
            | **Conservative Growth** | Modest equity with substantial bonds/cash |
            | **Balanced Growth** | Classic stock/bond balance |
            | **Aggressive Growth** | High equity allocation |
            | **Income** | Dividends, bonds, REITs |
            | **Retirement** | Growth with drawdown protection |
            | **Short-Term Cash Management** | Mostly T-Bills and short bonds |
            | **Tech Growth** | Overweight technology (sidebar preset) |
            | **All-Weather** | Multi-asset mix across regimes (sidebar preset) |

            **Where objectives appear:**
            - **Overview → Portfolio Recommendation Engine** — generates a suggested allocation
            - **Portfolio Health → Portfolio Objective** — checks if your current mix aligns with your goal
            """
        )
        _nav_hint("Overview", "Portfolio Recommendation Engine")
        st.caption("Sidebar presets like Tech Growth and All Weather load example allocations instantly.")

    with st.expander("Step 9 — Use Macro Analysis"):
        st.markdown(
            """
            Macroeconomics affects asset classes differently. Use macro tools to stress-test assumptions:

            - **Interest Rates** — rising rates often hurt long bonds; falling rates can help them
            - **Inflation** — erodes real purchasing power; affects stocks and bonds unevenly
            - **Recession Probability** — higher recession risk usually increases equity stress
            - **Valuation Environment** — expensive markets may imply lower forward returns in models
            - **Economic Regimes** — expansion, stagflation, recovery, etc.

            **Forward-Looking Macro Analysis** adjusts projected return/volatility under your assumptions.
            **Portfolio Health** uses similar inputs to score macro fit.
            """
        )
        _nav_hint("Forward-Looking Macro Analysis")
        st.caption("Portfolio Health tab also has Interest Rate, Inflation, and Regime controls.")

    with st.expander("Step 10 — Review Portfolio Health"):
        st.markdown(
            """
            **Portfolio Health** is designed for ongoing monitoring — is your portfolio still aligned
            with your goals?

            After clicking **Refresh Portfolio Health**, review:
            - **Health Score** — composite 0–100 from return, risk, diversification, objective, macro fit
            - **What's Working** — strengths the model identifies
            - **What's Not Working** — risks or misalignments to watch
            - **Rebalancing Suggestions** — drift vs. recommended or optimized weights
            - **Macro Fit** — how the portfolio may behave under your macro assumptions
            - **Status Summary** — plain-English headline

            Use this monthly (see next section) to catch drift before it becomes a large gap from your plan.
            """
        )
        _nav_hint("Portfolio Health", "click Refresh Portfolio Health after setting macro assumptions")


def _render_monthly_routine() -> None:
    st.markdown("A simple cadence keeps analysis manageable and your portfolio aligned with goals.")

    with st.expander("Monthly checklist", expanded=True):
        st.markdown(
            """
            1. **Refresh market data** — reload the app or adjust the date range in the sidebar so metrics use recent prices.
            2. **Review Portfolio Health** — run a health refresh; read score, status, and rebalance suggestions.
            3. **Compare benchmarks** — in Overview, run benchmark comparison vs. SPY, 60/40, etc.
            4. **Review macro assumptions** — update interest rate, inflation, and recession sliders if your outlook changed.
            """
        )
        _nav_hint("Portfolio Health")

    with st.expander("Quarterly checklist"):
        st.markdown(
            """
            1. **Review allocations** — check if weights drifted from your target (see Holdings in Overview).
            2. **Rebalance if needed** — adjust Portfolio Inputs or apply a preset/recommendation; small drift may not require action.
            3. **Rerun optimizer** — see if the efficient allocation shifted materially (Full analysis mode).
            4. **Read Explain This Portfolio** — download the investment memo for a written summary.
            """
        )

    with st.expander("Annual checklist"):
        st.markdown(
            """
            1. **Reassess goals** — retirement timeline, income needs, or risk tolerance may have changed.
            2. **Reassess risk tolerance** — a year of gains or losses can change what drawdowns feel acceptable.
            3. **Update long-term assumptions** — horizon, initial portfolio value, and risk-free rate in the sidebar.
            4. **Run Monte Carlo with new targets** — align simulation target value with updated goals.
            """
        )

    st.success(
        "You do not need to run every analysis every visit. Start with Overview + Portfolio Health, "
        "then deepen with Risk, Monte Carlo, and Optimization as you learn."
    )


def _render_glossary() -> None:
    st.markdown("Hover terms where supported, or expand each entry for a plain-English definition.")

    glossary = [
        (
            "CAGR",
            "Compound Annual Growth Rate — the steady yearly rate that would grow your portfolio from start to end value.",
            "If $10,000 became $12,100 in 2 years, CAGR ≈ 10% per year.",
        ),
        (
            "Volatility",
            "Annualized standard deviation of returns. Measures how much values swing, not direction.",
            "15% volatility means typical yearly swings around that size (up or down).",
        ),
        (
            "Sharpe Ratio",
            "(Return − risk-free rate) ÷ volatility. Higher = more return per unit of risk.",
            "Sharpe of 0.5 is modest; above 1.0 is often considered strong in equity portfolios.",
        ),
        (
            "Sortino Ratio",
            "Like Sharpe but uses downside deviation only — focuses on harmful volatility.",
            "Useful when upside swings are welcome but losses are not.",
        ),
        (
            "Beta",
            "Sensitivity to SPY. Beta 1.5 ≈ 50% more movement than the market.",
            "Low-beta portfolios often fall less in downturns but may lag in strong bull markets.",
        ),
        (
            "Drawdown",
            "Decline from a previous peak. Max drawdown is the worst such drop in the period.",
            "A −30% max drawdown means the portfolio fell 30% from its high at some point.",
        ),
        (
            "Correlation",
            "How two assets move together (−1 to +1). +1 = lockstep; 0 = unrelated; −1 = opposite.",
            "Bonds and stocks often have lower correlation than two stock funds — diversification benefit.",
        ),
        (
            "Diversification",
            "Spreading investments so no single asset dominates risk. Low correlation helps.",
            "Owning SPY + AGG is more diversified than owning SPY + QQQ alone.",
        ),
        (
            "Monte Carlo",
            "Simulation method that generates many random future paths from statistical inputs.",
            "Shows probability ranges — not a single forecast.",
        ),
        (
            "Efficient Frontier",
            "Set of portfolios with the best expected return for each level of risk (in the model).",
            "Points below the frontier are suboptimal in mean-variance terms.",
        ),
        (
            "Rebalancing",
            "Adjusting holdings back to target weights after market moves change allocations.",
            "If SPY grows to 60% of a 50% target, selling some SPY restores the plan.",
        ),
        (
            "Risk-Free Rate",
            "Return on cash-like assets (e.g. T-Bills). Used as a hurdle in Sharpe ratio.",
            "Set in the sidebar; 4% means you expect at least that from safe assets.",
        ),
        (
            "Inflation",
            "Rise in prices over time. Reduces real purchasing power of future portfolio values.",
            "Macro tools adjust assumptions when inflation is high or low.",
        ),
        (
            "Recession Probability",
            "Your estimate of near-term economic contraction risk used in macro stress tests.",
            "Higher probability typically reduces modeled equity returns in forward analysis.",
        ),
    ]

    for term, definition, example in glossary:
        with st.expander(term, expanded=False):
            st.markdown(f"{definition}  \n\n*Example:* {example}")


def _render_sample_portfolios() -> None:
    st.markdown(
        "Use these as starting points in **Portfolio Inputs** or load similar mixes from **sidebar presets**. "
        "Adjust to your situation — they are educational examples, not recommendations."
    )

    samples = [
        (
            "Conservative",
            "Prioritize stability and capital preservation with modest growth.",
            [("BND", "50%", "Bonds"), ("VTI", "25%", "Equity"), ("VXUS", "10%", "Equity"), ("BIL", "15%", "T-Bills")],
            "Heavy bonds and cash; lower expected return and volatility. Suitable for short horizons or low risk tolerance.",
        ),
        (
            "Balanced",
            "Classic mix of global stocks, bonds, and real estate.",
            [("VTI", "40%", "Equity"), ("VXUS", "20%", "Equity"), ("BND", "30%", "Bonds"), ("VNQ", "10%", "REIT")],
            "Moderate risk; historically smoother than all-equity portfolios. Matches many long-term default allocations.",
        ),
        (
            "Growth",
            "Equity-focused for long horizons and higher risk tolerance.",
            [("VTI", "50%", "Equity"), ("VXUS", "25%", "Equity"), ("QQQ", "20%", "Equity"), ("BND", "5%", "Bonds")],
            "Higher expected return potential with larger drawdowns. Best for investors who can stay invested through downturns.",
        ),
        (
            "Retirement",
            "Income and stability with some growth for a long retirement horizon.",
            [("BND", "40%", "Bonds"), ("VTI", "30%", "Equity"), ("VXUS", "15%", "Equity"), ("SCHD", "10%", "Dividend ETF"), ("BIL", "5%", "T-Bills")],
            "Balances drawdown protection (bonds/cash) with dividend equity and global stocks.",
        ),
        (
            "Income",
            "Emphasizes dividends and bond interest.",
            [("SCHD", "35%", "Dividend ETF"), ("VYM", "25%", "Dividend ETF"), ("VNQ", "15%", "REIT"), ("BND", "25%", "Bonds")],
            "Targets cash flow from dividends and coupons; growth may lag pure equity portfolios.",
        ),
    ]

    for name, tagline, holdings, why in samples:
        with st.expander(f"{name} — {tagline}", expanded=name == "Balanced"):
            rows = "\n".join(
                f"| {ticker} | {weight} | {atype} |" for ticker, weight, atype in holdings
            )
            st.markdown(f"| Ticker | Weight | Type |\n|--------|--------|------|\n{rows}")
            st.markdown(f"**Why this exists:** {why}")
            st.caption(f"Sidebar preset: look for **{name}** under Portfolio Presets (names may vary slightly).")


def render_getting_started_guide() -> None:
    """Render the full in-app tutorial and user guide."""
    st.markdown(GUIDE_CSS, unsafe_allow_html=True)

    section = st.radio(
        "Quick navigation",
        [
            "1. What This App Does",
            "2. Recommended Workflow",
            "3. Monthly Routine",
            "4. Glossary",
            "5. Sample Portfolios",
        ],
        horizontal=True,
        label_visibility="collapsed",
        key="guide_section_nav",
    )

    st.markdown("---")

    if section.startswith("1."):
        _render_what_this_app_does()
    elif section.startswith("2."):
        _render_workflow()
    elif section.startswith("3."):
        _render_monthly_routine()
    elif section.startswith("4."):
        _render_glossary()
    else:
        _render_sample_portfolios()
