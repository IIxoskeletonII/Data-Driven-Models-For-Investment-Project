"""Charts of protocol section 11: equity curves from 100 per period (log scale), drawdowns, exposures, the gross → costs →
borrow bridge and the placebo distribution. Each function writes an interactive HTML file (plotly; plotly.js is written
once into the same folder, so the files open offline) and a static PNG (matplotlib), from `path` with the suffixes .html
and .png. Phase 3.2 (Mattia); decision S32-6.

Dates follow the course skeleton: an equity or drawdown point is dated when its return is realised (`realised_on`, the
open of week t+2), and each period starts at 100 on the execution date of its first week (the open of week t+1).
Exposures are dated by the week of the signal (`date_close`). Strategies take the categorical colours by rung in a fixed
order; benchmarks are grey; a variant of a rung (e.g. M3_d2) takes its rung's colour with a dashed line.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from plotly.subplots import make_subplots

from src.contracts import BacktestResult

# categorical slots in fixed order, one per rung (colour follows the entity, never its rank)
RUNG_COLORS = {"M0": "#2a78d6", "M1": "#eb6834", "M2": "#1baf7a", "M3": "#eda100", "M5": "#e87ba4", "ENS": "#008300",
               "M0_star": "#6250d6", "M6": "#8b5a2b", "M7": "#11a8c8", "M8": "#8fb800", "M9": "#b0178f"}  # M6 to M9: S42-9
OTHER_COLOR = "#e34948"
BENCHMARK_COLORS = {"T-bill": "#9a9992", "SPY": "#5f5e58", "Equal weight": "#b9b8b0"}
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
PERIODS = ("IS", "OOS")
MPL_DASH = {"solid": "-", "dash": "--", "dot": ":"}


def series_style(name: str) -> tuple[str, str]:
    """(colour, dash) of a series: benchmarks grey (the T-bill dotted, SPY and the equal-weight basket solid); a rung its
    fixed colour; a variant `<rung>_<x>` its rung's colour, dashed; any other name red."""
    if name in BENCHMARK_COLORS:
        return BENCHMARK_COLORS[name], "dot" if name == "T-bill" else "solid"
    if name in RUNG_COLORS:
        return RUNG_COLORS[name], "solid"
    rung = "M0_star" if name.startswith("M0_star") else name.split("_")[0]
    return RUNG_COLORS.get(rung, OTHER_COLOR), "dash"


def _paths(path: Path) -> tuple[Path, Path]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.parent / f"{path.name}.html", path.parent / f"{path.name}.png"


def _write_html(fig: go.Figure, html: Path, title: str, hovermode: str = "x unified") -> None:
    fig.update_layout(title=title, template="plotly_white", hovermode=hovermode, font={"color": TEXT},
                      legend={"orientation": "h", "y": -0.15})
    # div_id fixed by the file name: plotly's default is a random id, so two runs would differ (S39-5)
    fig.write_html(html, include_plotlyjs="directory", full_html=True, div_id=f"plot-{html.stem}")


def _new_figure(n_panels: int, height: float = 4.5) -> tuple[Figure, list]:
    fig = Figure(figsize=(6.5 * n_panels + 1.5, height), layout="constrained")
    axes = fig.subplots(1, n_panels, squeeze=False)[0]
    for ax in axes:
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED)
    return fig, list(axes)


def _periods(period: pd.Series) -> list[str]:
    present = [p for p in PERIODS if (period == p).any()]
    if not present:
        raise ValueError("no week is labelled IS or OOS")
    return present


def _start_date(index: pd.MultiIndex, realised_on: pd.Series) -> pd.Timestamp:
    """Execution date of the first week of a period: date_open of the next week (the open of week t+1), or 7 days before
    the first realisation when the period has a single week."""
    if len(index) > 1:
        return pd.Timestamp(index[1][0])
    return pd.Timestamp(realised_on.iloc[0]) - pd.Timedelta(days=7)


def period_curves(returns: pd.DataFrame, period: pd.Series, realised_on: pd.Series, kind: str) -> dict[str, pd.DataFrame]:
    """Equity (`kind="equity"`, E = 100·Π(1 + r), 100 at the start of each period) or drawdown (`"drawdown"`,
    E / running max − 1) of every column, per period, indexed by realisation date with the period's start date first.

    returns: weekly simple returns (decimals) on the weekly index, one column per series; period and realised_on on the
    same index (contract 7). Returns {period: frame}.
    """
    if kind not in ("equity", "drawdown"):
        raise ValueError(f"kind must be 'equity' or 'drawdown', got {kind!r}")
    if returns.isna().any().any():
        raise ValueError("returns have missing values")
    labels = period.reindex(returns.index)
    out = {}
    for name in _periods(labels):
        mask = (labels == name).to_numpy()
        r = returns[mask]
        dates = pd.DatetimeIndex(realised_on.reindex(r.index), name="date")
        equity = 100 * (1 + r).cumprod()
        equity.index = dates
        start = pd.DataFrame(100.0, index=pd.DatetimeIndex([_start_date(r.index, realised_on.reindex(r.index))],
                                                           name="date"), columns=r.columns)
        curve = pd.concat([start, equity])
        out[name] = curve if kind == "equity" else curve / curve.cummax() - 1
    return out


def _line_chart(curves: dict[str, pd.DataFrame], path: Path, title: str, *, log_y: bool, percent: bool) -> None:
    html, png = _paths(path)
    names = list(curves)
    fig = make_subplots(rows=1, cols=len(names), subplot_titles=names, shared_yaxes=False)
    for col, name in enumerate(names, start=1):
        for series in curves[name].columns:
            color, dash = series_style(series)
            fig.add_trace(go.Scatter(x=curves[name].index, y=curves[name][series], name=series, legendgroup=series,
                                     showlegend=col == 1, mode="lines", line={"color": color, "width": 2, "dash": dash},
                                     hovertemplate="%{y:.1%}" if percent else "%{y:.1f}"), row=1, col=col)
        fig.update_yaxes(type="log" if log_y else "linear", tickformat=".0%" if percent else None, row=1, col=col)
    _write_html(fig, html, title)

    entries = max(len(curves[name].columns) for name in names)
    figure, axes = _new_figure(len(names), height=max(4.5, 0.27 * entries + 0.8))  # a long legend must fit (S42-9)
    for ax, name in zip(axes, names, strict=True):
        for series in curves[name].columns:
            color, dash = series_style(series)
            ax.plot(curves[name].index, curves[name][series], color=color, linewidth=2,
                    linestyle=MPL_DASH[dash], label=series)
        if log_y:
            ax.set_yscale("log")
            plain = FuncFormatter(lambda value, _: f"{value:g}")
            ax.yaxis.set_major_formatter(plain)
            ax.yaxis.set_minor_formatter(plain)
        if percent:
            ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        ax.set_title(name, color=TEXT)
    axes[-1].legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    figure.suptitle(title, color=TEXT)
    figure.savefig(png, dpi=120)


def equity_curves(returns: pd.DataFrame, period: pd.Series, realised_on: pd.Series, path: Path, *,
                  title: str = "Equity (starting at 100 in each period, log scale)") -> None:
    """Equity curves of weekly returns (one column per series, e.g. a strategy's net returns, the T-bill, SPY and the
    equal-weight basket), each starting at 100 in each period, on a shared dated axis, log scale (§11; Amendment 2 C5).
    Points are dated by realisation (realised_on). Writes `path`.html and `path`.png.
    """
    _line_chart(period_curves(returns, period, realised_on, "equity"), path, title, log_y=True, percent=False)


def drawdowns(returns: pd.DataFrame, period: pd.Series, realised_on: pd.Series, path: Path, *,
              title: str = "Drawdown (per period)") -> None:
    """Drawdown curves E / max E − 1 of weekly returns per period (§11), dated by realisation. Writes `path`.html and
    `path`.png."""
    _line_chart(period_curves(returns, period, realised_on, "drawdown"), path, title, log_y=False, percent=True)


def exposure_frame(result: BacktestResult | pd.DataFrame) -> pd.DataFrame:
    """Weekly long, short and net exposure (Σ w⁺, Σ w⁻, Σ w; IVV included), the IVV weight and the residual beta, on the
    weekly index. From a BacktestResult (computed from its weights), or from a frame with the columns long_exposure,
    short_exposure, net_exposure and residual_beta (06_backtest.py weekly.csv)."""
    if isinstance(result, BacktestResult):
        w = result.weights
        return pd.DataFrame({"long_exposure": w.clip(lower=0).sum(axis=1), "short_exposure": w.clip(upper=0).sum(axis=1),
                             "net_exposure": result.net_exposure, "residual_beta": result.residual_beta})
    needed = ["long_exposure", "short_exposure", "net_exposure", "residual_beta"]
    absent = [c for c in needed if c not in result.columns]
    if absent:
        raise ValueError(f"exposures: missing columns {absent}")
    return result[needed].astype(np.float64)


def exposures(result: BacktestResult | pd.DataFrame, path: Path, *, title: str = "Exposures (week of the signal)") -> None:
    """Weekly long, short and net exposure of the book (net = the IVV weight h / (1 + |h|), since the core is
    dollar-neutral) and, in a separate panel (another unit), the residual beta (§09, §11). Dated by date_close (week of
    the signal). Writes `path`.html and `path`.png."""
    frame = exposure_frame(result)
    dates = pd.DatetimeIndex(frame.index.get_level_values("date_close"))
    weights = {"Long (Σw > 0)": ("long_exposure", "#2a78d6"), "Short (Σw < 0)": ("short_exposure", "#eb6834"),
               "Net (IVV weight)": ("net_exposure", "#1baf7a")}
    html, png = _paths(path)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                        subplot_titles=["Exposure, share of capital", "Residual beta"])
    for label, (column, color) in weights.items():
        fig.add_trace(go.Scatter(x=dates, y=frame[column], name=label, mode="lines", line={"color": color, "width": 2},
                                 hovertemplate="%{y:.1%}"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=frame["residual_beta"], name="Residual beta", mode="lines",
                             line={"color": "#5f5e58", "width": 2}, hovertemplate="%{y:.3f}"), row=2, col=1)
    fig.update_yaxes(tickformat=".0%", row=1, col=1)
    _write_html(fig, html, title)

    figure = Figure(figsize=(9, 6), layout="constrained")
    top, bottom = figure.subplots(2, 1, sharex=True, height_ratios=[2, 1])
    for label, (column, color) in weights.items():
        top.plot(dates, frame[column], color=color, linewidth=1.5, label=label)
    top.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    top.set_title("Exposure, share of capital", color=TEXT)
    top.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    bottom.plot(dates, frame["residual_beta"], color="#5f5e58", linewidth=1.5)
    bottom.set_title("Residual beta", color=TEXT)
    for ax in (top, bottom):
        ax.grid(True, color=GRID, linewidth=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    figure.suptitle(title, color=TEXT)
    figure.savefig(png, dpi=120)


def bridge_values(weekly: pd.DataFrame, periods_per_year: int = 52) -> pd.Series:
    """Arithmetic annualised bridge from gross to net return: mean weekly gross, −costs, −borrow and net, × P. The steps
    add up exactly (net = gross − costs − borrow every week, §09). weekly: columns gross, costs, borrow, net."""
    mean = weekly[["gross", "costs", "borrow", "net"]].astype(np.float64).mean() * periods_per_year
    if not np.isclose(mean["gross"] - mean["costs"] - mean["borrow"], mean["net"], rtol=0, atol=1e-12):
        raise ValueError("net is not gross − costs − borrow")
    return pd.Series({"Gross": mean["gross"], "Costs": -mean["costs"], "Borrow": -mean["borrow"], "Net": mean["net"]})


def cost_bridge(weekly: pd.DataFrame, path: Path, *, periods_per_year: int = 52,
                title: str = "Gross → costs → borrow → net (mean weekly return × 52)") -> None:
    """Waterfall of the annualised arithmetic return from gross to net: trading costs on drifted-weight turnover, then
    short borrow (§09, §11 bridge). Writes `path`.html and `path`.png."""
    values = bridge_values(weekly, periods_per_year)
    html, png = _paths(path)
    fig = go.Figure(go.Waterfall(x=list(values.index), y=list(values), measure=["absolute", "relative", "relative", "total"],
                                 text=[f"{v:.2%}" for v in values], textposition="outside",
                                 increasing={"marker": {"color": "#2a78d6"}}, decreasing={"marker": {"color": "#eb6834"}},
                                 totals={"marker": {"color": "#5f5e58"}}, hovertemplate="%{x}: %{y:.2%}<extra></extra>"))
    fig.update_yaxes(tickformat=".1%")
    _write_html(fig, html, title, hovermode="closest")

    figure, (ax,) = _new_figure(1)
    level = 0.0
    for i, (label, value) in enumerate(values.items()):
        if label in ("Gross", "Net"):
            bottom, height, color = 0.0, value, "#2a78d6" if label == "Gross" else "#5f5e58"
        else:
            bottom, height, color = level, value, "#eb6834"
        ax.bar(i, height, bottom=bottom, color=color, width=0.6)
        ax.annotate(f"{value:.2%}", (i, bottom + height), ha="center", va="bottom" if height >= 0 else "top", color=TEXT)
        level = value if label == "Gross" else level + value
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks(range(len(values)), list(values.index))
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1%}")
    figure.suptitle(title, color=TEXT)
    figure.savefig(png, dpi=120)


def placebo_histogram(sharpes: pd.Series, marks: dict[str, float], path: Path, *,
                      title: str = "Placebo: net Sharpe of random ±2/±2 books (same hedge)") -> None:
    """Histogram of the placebo books' net Sharpe ratios with a vertical line per model in `marks` (§11 placebo).
    Writes `path`.html and `path`.png."""
    values = sharpes.dropna().astype(np.float64)
    if values.empty:
        raise ValueError("no placebo Sharpe ratio")
    html, png = _paths(path)
    fig = go.Figure(go.Histogram(x=values, nbinsx=40, marker={"color": "#b9b8b0"}, name="Placebo books",
                                 hovertemplate="Sharpe %{x}<br>%{y} books<extra></extra>"))
    for name, value in marks.items():
        color, dash = series_style(name)
        fig.add_vline(x=value, line={"color": color, "width": 2, "dash": dash}, annotation_text=name)
    _write_html(fig, html, title, hovermode="closest")

    figure, (ax,) = _new_figure(1)
    ax.hist(values, bins=40, color="#b9b8b0", edgecolor="white", linewidth=0.5)
    for name, value in marks.items():
        color, dash = series_style(name)
        ax.axvline(value, color=color, linewidth=2, linestyle=MPL_DASH[dash])
        ax.annotate(name, (value, ax.get_ylim()[1] * 0.95), color=TEXT, ha="left", va="top", xytext=(3, 0),
                    textcoords="offset points")
    ax.set_xlabel("Net Sharpe (T-bill, baseline costs)", color=MUTED)
    ax.set_ylabel("Books", color=MUTED)
    figure.suptitle(title, color=TEXT)
    figure.savefig(png, dpi=120)
