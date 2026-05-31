"""Plain-English guide for choosing macro assumptions — beginner education."""

from __future__ import annotations

import streamlit as st


def render_macro_assumptions_guide(*, expanded: bool = False) -> None:
    """How Do I Choose These Assumptions? — educational section for beginners."""

    with st.expander("How Do I Choose These Assumptions?", expanded=expanded):
        st.markdown(
            """
            You do **not** need to be an economist. These settings describe what you think the
            economy might look like over the next year or so. Reasonable guesses are fine —
            the app uses them to stress-test your portfolio, not to predict the future.
            """
        )

        st.markdown("### Interest Rates")
        st.markdown(
            """
            **What this means:** How expensive it is to borrow money and how much safe savings pay.

            | Setting | Plain English |
            |---------|---------------|
            | **Rising Rates** | The Fed is raising rates or borrowing costs are going up. Bonds often struggle; cash pays more. |
            | **Stable Rates** | Rates are roughly unchanged — a neutral starting point if you are unsure. |
            | **Falling Rates** | Rates are coming down. Often helps bonds and growth stocks. |
            | **High Rate Environment** | Rates stay elevated for a while — cash and short-term bonds look attractive. |

            **Where to learn more:** Federal Reserve announcements (federalreserve.gov), Treasury yield charts
            on financial sites, and headlines about “Fed rate cuts” or “rate hikes.”
            """
        )

        st.markdown("### Inflation")
        st.markdown(
            """
            **What this means:** How fast everyday prices (groceries, rent, gas) are rising.

            | Setting | Plain English |
            |---------|---------------|
            | **Low Inflation** | Prices rise slowly (~2% or less per year). |
            | **Moderate Inflation** | Normal range — prices creep up but are manageable. |
            | **High Inflation** | Prices rise quickly; cash loses buying power; bonds can hurt. |
            | **Deflation** | Prices fall — rare, but can stress debt and growth. |

            **Where to learn more:** Monthly CPI (Consumer Price Index) reports from the Bureau of Labor
            Statistics, government economic releases, and financial news summaries.
            """
        )

        st.markdown("### Recession Probability")
        st.markdown(
            """
            **What this means:** Your estimate of how likely a serious economic downturn is in the next year.

            The app uses this to flag portfolios that may be too aggressive if a recession hits.

            **Signals people watch (you do not need to master these):**
            - **Unemployment** — rising job losses often precede recessions
            - **Economic growth (GDP)** — shrinking economy = recession
            - **Yield curve** — when short-term Treasury yields exceed long-term ones, some see a warning sign
            - **Consumer spending** — when people pull back, growth slows

            **Important:** You do not need to predict perfectly. Many beginners use **20–30%** as a
            middle-ground estimate when unsure.
            """
        )

        st.markdown("### Valuation Environment")
        st.markdown(
            """
            **What this means:** Whether the stock market looks cheap, fair, or expensive compared to history.

            | Setting | Plain English |
            |---------|---------------|
            | **Cheap** | Stocks trade below typical levels — more room for recovery. |
            | **Fair Value** | Normal starting point if you are unsure. |
            | **Expensive** | Prices are high vs. earnings — future returns may be lower. |
            | **Bubble-like** | Extreme optimism — higher risk of a sharp correction. |

            This is an **estimate**, not a precise measurement. Financial news often discusses
            “market valuations” or P/E ratios in simple terms.
            """
        )

        st.markdown("### Economic Regimes")
        st.markdown(
            """
            **What this means:** The broad “mood” of the economy right now.

            | Regime | Plain English |
            |--------|---------------|
            | **Expansion** | Economy growing, jobs adding, businesses doing well. |
            | **Slow Growth** | Still growing, but weakly — “muddling through.” |
            | **Recession** | Economy shrinking, layoffs rising, spending down. |
            | **Recovery** | Coming out of a recession — growth returning. |
            | **Stagflation** | Slow growth **and** high inflation at the same time. |
            | **AI / Tech Boom** | Technology leading the market — higher growth, higher concentration risk. |
            | **Credit Crisis** | Stress in banks or debt markets — flight to safety. |

            If unsure, **Expansion** or **Slow Growth** are reasonable defaults in normal times.
            """
        )

        st.markdown("---")
        st.markdown("#### Future enhancement (coming idea)")
        st.caption(
            "Eventually this app may suggest macro settings automatically from live data "
            "(current inflation, Fed Funds Rate, unemployment, Treasury yields). "
            "Example: *“Based on current data, Moderate Inflation / High Rate Environment may be appropriate.”* "
            "For now, use the defaults or pick what matches recent news."
        )
