"""Shared Plotly chart styling for the portfolio dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Bloomberg-inspired palette
COLORS = {
    "primary": "#4da3ff",
    "accent": "#f5a623",
    "positive": "#2ecc71",
    "negative": "#e74c3c",
    "muted": "#5a6d82",
    "grid": "#2d3a4f",
    "bg": "#121820",
}

CHART_SEQUENCE = ["#4da3ff", "#f5a623", "#2ecc71", "#9b59b6", "#e74c3c", "#1abc9c", "#3498db"]


def base_layout(**kwargs) -> dict:
    layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLORS["bg"],
        font=dict(family="Segoe UI, Roboto, sans-serif", color="#d4dce8", size=12),
        margin=dict(l=48, r=24, t=48, b=40),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    layout.update(kwargs)
    return layout


def apply_axes(fig: go.Figure, y_title: str = "", x_title: str = "") -> go.Figure:
    fig.update_xaxes(
        showgrid=True,
        gridcolor=COLORS["grid"],
        zeroline=False,
        title=x_title,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=COLORS["grid"],
        zeroline=False,
        title=y_title,
    )
    return fig


def growth_chart(growth_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=growth_df["Date"],
            y=growth_df["Portfolio Value"],
            mode="lines",
            name="Portfolio",
            line=dict(color=COLORS["primary"], width=2.5),
            fill="tozeroy",
            fillcolor="rgba(77, 163, 255, 0.12)",
        )
    )
    fig.update_layout(**base_layout(title="Portfolio Growth", height=400))
    return apply_axes(fig, "Value ($)", "Date")


def allocation_chart(holdings_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=holdings_df["Ticker"],
            values=holdings_df["Weight"],
            hole=0.52,
            textinfo="label+percent",
            textposition="outside",
            marker=dict(colors=CHART_SEQUENCE, line=dict(color="#0e1117", width=2)),
            hovertemplate="<b>%{label}</b><br>Weight: %{percent}<br>Value share: %{value:.1%}<extra></extra>",
        )
    )
    fig.update_layout(**base_layout(title="Asset Allocation", height=400, showlegend=True))
    return fig


def correlation_heatmap(corr: pd.DataFrame) -> go.Figure:
    fig = px.imshow(
        corr,
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        labels=dict(color="Correlation"),
    )
    fig.update_layout(**base_layout(title="Correlation Matrix (Heatmap)", height=440))
    return fig


def rolling_chart(df: pd.DataFrame, title: str, y_title: str) -> go.Figure:
    fig = go.Figure()
    for col in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df[col], mode="lines", name=col, line=dict(width=2))
        )
    fig.update_layout(**base_layout(title=title, height=360))
    fig.update_yaxes(tickformat=".1%")
    return apply_axes(fig, y_title, "Date")


def monte_carlo_paths(chart_df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    bands = [
        ("5th Percentile", COLORS["negative"], "dot"),
        ("25th Percentile", COLORS["muted"], "dash"),
        ("Median", COLORS["primary"], "solid"),
        ("75th Percentile", COLORS["muted"], "dash"),
        ("95th Percentile", COLORS["positive"], "dot"),
    ]
    for name, color, dash in bands:
        if name not in chart_df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=chart_df["Day"],
                y=chart_df[name],
                name=name,
                line=dict(color=color, width=2.5 if name == "Median" else 1.5, dash=dash),
            )
        )
    fig.update_layout(**base_layout(title=title, height=400))
    return apply_axes(fig, "Portfolio Value ($)", "Trading Days")


def monte_carlo_histogram(ending_values, initial_value: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=ending_values,
            nbinsx=40,
            marker_color=COLORS["primary"],
            opacity=0.85,
            name="Ending values",
        )
    )
    fig.add_vline(x=initial_value, line_dash="dash", line_color=COLORS["accent"], annotation_text="Start")
    fig.add_vline(x=initial_value * 2, line_dash="dot", line_color=COLORS["positive"], annotation_text="2×")
    fig.update_layout(**base_layout(title="Distribution of Ending Portfolio Values", height=360))
    return apply_axes(fig, "Frequency", "Ending Value ($)")


def benchmark_growth_chart(growth_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for i, col in enumerate(growth_df.columns):
        if col == "Date":
            continue
        fig.add_trace(
            go.Scatter(
                x=growth_df["Date"],
                y=growth_df[col],
                mode="lines",
                name=col,
                line=dict(color=CHART_SEQUENCE[i % len(CHART_SEQUENCE)], width=2.3),
            )
        )
    fig.update_layout(**base_layout(title="Cumulative Growth Comparison", height=430))
    return apply_axes(fig, "Value ($)", "Date")


def efficient_frontier_chart(
    frontier: pd.DataFrame,
    current: tuple[float, float, float],
    max_sharpe: tuple[float, float, float, str],
    min_vol: tuple[float, float, float, str],
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frontier["Volatility"],
            y=frontier["Return"],
            mode="lines",
            name="Efficient Frontier",
            line=dict(color=COLORS["primary"], width=3),
            hovertemplate="Vol: %{x:.1%}<br>Return: %{y:.1%}<extra></extra>",
        )
    )
    markers = [
        (current[0], current[1], "Your Portfolio", COLORS["accent"], "star", 16),
        (max_sharpe[0], max_sharpe[1], max_sharpe[3], COLORS["positive"], "diamond", 14),
        (min_vol[0], min_vol[1], min_vol[3], COLORS["negative"], "square", 14),
    ]
    for vol, ret, label, color, symbol, size in markers:
        fig.add_trace(
            go.Scatter(
                x=[vol],
                y=[ret],
                mode="markers+text",
                name=label,
                text=[label],
                textposition="top center",
                marker=dict(size=size, color=color, symbol=symbol, line=dict(width=1, color="#fff")),
                hovertemplate=f"<b>{label}</b><br>Vol: %{{x:.2%}}<br>Return: %{{y:.2%}}<extra></extra>",
            )
        )
    fig.update_layout(**base_layout(title="Efficient Frontier", height=480))
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%")
    return apply_axes(fig, "Expected Return (annual)", "Volatility (annual)")


def contribution_bar_chart(
    df: pd.DataFrame,
    value_col: str,
    title: str,
    y_label: str = "Contribution (%)",
) -> go.Figure:
    colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in df[value_col]]
    fig = go.Figure(
        go.Bar(
            x=df["Ticker"],
            y=df[value_col],
            marker_color=colors,
            hovertemplate="<b>%{x}</b><br>%{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(**base_layout(title=title, height=360))
    return apply_axes(fig, y_label, "Ticker")


def allocation_percentage_columns(alloc_df: pd.DataFrame) -> list[str]:
    """Weight (%) series only — never mix dollar columns onto a percentage chart."""
    return [c for c in alloc_df.columns if c != "Category" and str(c).endswith("(%)")]


def allocation_comparison_chart(alloc_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    categories = alloc_df["Category"].tolist()
    series_cols = allocation_percentage_columns(alloc_df)
    for i, col in enumerate(series_cols):
        fig.add_trace(
            go.Bar(
                name=str(col).replace(" (%)", ""),
                x=categories,
                y=alloc_df[col],
                marker_color=CHART_SEQUENCE[i % len(CHART_SEQUENCE)],
                hovertemplate=f"<b>{col}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
            )
        )
    fig.update_layout(
        **base_layout(
            title="Current vs Objective / Recommended (Weight %)",
            height=420,
            barmode="group",
            margin=dict(l=48, r=24, t=88, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.12, x=0),
        )
    )
    return apply_axes(fig, "Weight (%)", "Category")


def build_aligned_benchmark_growth(
    port_rets: pd.Series,
    benchmark_rets: pd.DataFrame,
    initial_value: float,
    *,
    benchmark_symbols: tuple[str, ...] = ("SPY", "QQQ"),
) -> pd.DataFrame:
    """
    Build a Portfolio / SPY / QQQ growth frame on a common DatetimeIndex.

    Aligns by date intersection so series assignment cannot produce all-NaN
    columns (RangeIndex vs DatetimeIndex bug).
    """
    if port_rets is None or len(port_rets) == 0:
        return pd.DataFrame(columns=["Date", "Portfolio", *benchmark_symbols])

    port = port_rets.copy()
    if not isinstance(port.index, pd.DatetimeIndex):
        port.index = pd.to_datetime(port.index)
    port = port.sort_index()
    port.name = "Portfolio"

    pieces: list[pd.Series] = [port]
    if benchmark_rets is not None and not benchmark_rets.empty:
        cmp = benchmark_rets.copy()
        if not isinstance(cmp.index, pd.DatetimeIndex):
            cmp.index = pd.to_datetime(cmp.index)
        cmp = cmp.sort_index()
        col_map = {str(c).strip().upper(): c for c in cmp.columns}
        for sym in benchmark_symbols:
            raw = col_map.get(sym.upper())
            if raw is None:
                continue
            pieces.append(cmp[raw].rename(sym.upper()))

    aligned = pd.concat(pieces, axis=1, join="inner").dropna(how="any")
    if aligned.empty:
        # Fall back to portfolio-only if benchmarks do not overlap.
        aligned = port.to_frame(name="Portfolio").dropna()
    growth = (1.0 + aligned).cumprod() * float(initial_value)
    out = growth.reset_index()
    date_col = out.columns[0]
    out = out.rename(columns={date_col: "Date"})
    return out


def benchmark_mini_chart(
    growth_df: pd.DataFrame,
    title: str = "Portfolio vs SPY / QQQ (market reference)",
) -> go.Figure:
    fig = go.Figure()
    for i, col in enumerate(growth_df.columns):
        if col == "Date":
            continue
        series = growth_df[col]
        if series is None or len(series) == 0 or not np.isfinite(pd.to_numeric(series, errors="coerce")).any():
            continue
        width = 3.0 if col.upper() in ("PORTFOLIO", "SPY") else 1.8
        fig.add_trace(
            go.Scatter(
                x=growth_df["Date"],
                y=series,
                mode="lines",
                name=col,
                line=dict(color=CHART_SEQUENCE[i % len(CHART_SEQUENCE)], width=width),
            )
        )
    fig.update_layout(**base_layout(title=title, height=320, margin=dict(l=48, r=24, t=64, b=40)))
    return apply_axes(fig, "Value ($)", "Date")


def macro_sensitivity_heatmap(heatmap_df: pd.DataFrame) -> go.Figure:
    asset_col = "Asset Type"
    scenarios = [c for c in heatmap_df.columns if c != asset_col]
    z = heatmap_df[scenarios].values
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=scenarios,
            y=heatmap_df[asset_col],
            colorscale=[
                [0.0, COLORS["negative"]],
                [0.5, COLORS["muted"]],
                [1.0, COLORS["positive"]],
            ],
            zmid=0,
            zmin=-1,
            zmax=1,
            hovertemplate="Asset: %{y}<br>Scenario: %{x}<br>Sensitivity: %{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(**base_layout(title="Macro Sensitivity by Asset Class (Model)", height=380))
    return apply_axes(fig, "", "Asset Type")
