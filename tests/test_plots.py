"""src/plots.py: curves rebased to 100 per period and dated by realisation, drawdowns, exposures, the cost bridge and the
placebo histogram; every chart writes an HTML and a PNG file (decision S32-6)."""

import numpy as np
import pandas as pd
import pytest

from src import plots
from src.contracts import BacktestResult


def _weeks(n: int, start: str = "2019-11-04") -> pd.MultiIndex:
    mondays = pd.date_range(start, periods=n, freq="7D")
    return pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])


def _realised(index: pd.MultiIndex) -> pd.Series:
    return pd.Series(pd.DatetimeIndex(index.get_level_values("date_open")) + pd.Timedelta(days=14), index=index)


def test_equity_starts_at_100_on_the_execution_date_and_is_dated_by_realisation():
    index = _weeks(3)
    returns = pd.DataFrame({"M0": [0.10, -0.50, 0.20]}, index=index)
    period = pd.Series("IS", index=index)
    curves = plots.period_curves(returns, period, _realised(index), "equity")
    equity = curves["IS"]["M0"]
    assert equity.index[0] == pd.Timestamp("2019-11-11")  # open of week t+1: date_open of the second week
    assert list(equity.index[1:]) == list(_realised(index))  # open of week t+2
    np.testing.assert_allclose(equity.to_numpy(), [100, 110, 55, 66], rtol=0, atol=1e-12)
    drawdown = plots.period_curves(returns, period, _realised(index), "drawdown")["IS"]["M0"]
    np.testing.assert_allclose(drawdown.to_numpy(), [0, 0, -0.5, -0.4], rtol=0, atol=1e-12)


def test_each_period_restarts_at_100():
    index = _weeks(4)
    returns = pd.DataFrame({"M0": [0.1, 0.1, 0.1, 0.1]}, index=index)
    period = pd.Series(["IS", "IS", "OOS", "OOS"], index=index)
    curves = plots.period_curves(returns, period, _realised(index), "equity")
    assert list(curves) == ["IS", "OOS"]
    assert curves["OOS"]["M0"].iloc[0] == 100 and curves["OOS"]["M0"].iloc[-1] == pytest.approx(121)


def test_period_curves_refuse_missing_returns_and_unknown_kinds():
    index = _weeks(2)
    period = pd.Series("IS", index=index)
    with pytest.raises(ValueError, match="missing"):
        plots.period_curves(pd.DataFrame({"M0": [0.1, np.nan]}, index=index), period, _realised(index), "equity")
    with pytest.raises(ValueError, match="kind"):
        plots.period_curves(pd.DataFrame({"M0": [0.1, 0.1]}, index=index), period, _realised(index), "level")


def test_bridge_adds_up_to_net():
    weekly = pd.DataFrame({"gross": [0.01, -0.02], "costs": [0.001, 0.0005], "borrow": [0.0002, 0.0002]})
    weekly["net"] = weekly["gross"] - weekly["costs"] - weekly["borrow"]
    values = plots.bridge_values(weekly)
    assert list(values.index) == ["Gross", "Costs", "Borrow", "Net"]
    assert values["Gross"] == pytest.approx(-0.005 * 52) and values["Costs"] == pytest.approx(-0.00075 * 52)
    assert values["Gross"] + values["Costs"] + values["Borrow"] == pytest.approx(values["Net"], abs=1e-15)
    weekly.loc[0, "net"] += 0.01
    with pytest.raises(ValueError, match="gross"):
        plots.bridge_values(weekly)


def test_series_style_follows_the_entity():
    assert plots.series_style("M0") == (plots.RUNG_COLORS["M0"], "solid")
    assert plots.series_style("M3_d2") == (plots.RUNG_COLORS["M3"], "dash")
    assert plots.series_style("M0_star") == (plots.RUNG_COLORS["M0_star"], "solid")
    assert plots.series_style("SPY") == (plots.BENCHMARK_COLORS["SPY"], "solid")
    assert plots.series_style("T-bill") == (plots.BENCHMARK_COLORS["T-bill"], "dot")
    assert plots.series_style("X9")[0] == plots.OTHER_COLOR


def test_exposure_frame_from_a_backtest_result():
    index = _weeks(2)
    weights = pd.DataFrame(0.0, index=index, columns=["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "IVV"])
    weights.loc[:, ["XLB", "XLE"]] = 0.25 / 1.2
    weights.loc[:, ["XLF", "XLI"]] = -0.25 / 1.2
    weights["IVV"] = -0.2 / 1.2
    zero = pd.Series(0.0, index=index)
    result = BacktestResult(weights=weights, gross=zero, net=zero, turnover=zero, costs=zero, borrow=zero,
                            residual_beta=zero, net_exposure=pd.Series(-0.2 / 1.2, index=index), hedge=zero - 0.2,
                            period=pd.Series("IS", index=index))
    frame = plots.exposure_frame(result)
    np.testing.assert_allclose(frame["long_exposure"], 0.5 / 1.2)
    np.testing.assert_allclose(frame["short_exposure"], -0.7 / 1.2)
    np.testing.assert_allclose(frame["long_exposure"] + frame["short_exposure"], frame["net_exposure"], atol=1e-15)
    with pytest.raises(ValueError, match="missing columns"):
        plots.exposure_frame(frame.drop(columns="residual_beta"))


def test_every_chart_writes_html_and_png(tmp_path):
    index = _weeks(30)
    rng = np.random.default_rng(0)
    period = pd.Series("IS", index=index)
    realised = _realised(index)
    returns = pd.DataFrame({"M0": rng.normal(0, 0.01, 30), "T-bill": 0.0003, "SPY": rng.normal(0, 0.02, 30)}, index=index)
    weekly = pd.DataFrame({"gross": rng.normal(0, 0.01, 30), "costs": 0.0004, "borrow": 0.0002, "long_exposure": 0.45,
                           "short_exposure": -0.55, "net_exposure": -0.1, "residual_beta": 0.0}, index=index)
    weekly["net"] = weekly["gross"] - weekly["costs"] - weekly["borrow"]
    plots.equity_curves(returns, period, realised, tmp_path / "equity")
    plots.drawdowns(returns, period, realised, tmp_path / "drawdown")
    plots.exposures(weekly, tmp_path / "exposure")
    plots.cost_bridge(weekly, tmp_path / "bridge")
    plots.placebo_histogram(pd.Series(rng.normal(0, 0.3, 100)), {"M0": 0.1, "M3_d2": -0.2}, tmp_path / "placebo")
    for name in ("equity", "drawdown", "exposure", "bridge", "placebo"):
        assert (tmp_path / f"{name}.html").stat().st_size > 0
        assert (tmp_path / f"{name}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (tmp_path / "plotly.min.js").exists()  # written once; the HTML files open offline
    assert 'src="plotly.min.js"' in (tmp_path / "equity.html").read_text(encoding="utf-8")
