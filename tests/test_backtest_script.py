"""06_backtest.py: CLI wiring only; refuses real-data runs until the vault exists (Phase 2.3), and the ledger check accepts
In-Sample years only."""

import importlib.util

import pandas as pd
import pytest

from src.config import ROOT


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("backtest_script", ROOT / "06_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_to_run_without_a_flag(script):
    with pytest.raises(SystemExit) as raised:
        script.main([])
    assert "vault" in str(raised.value)


@pytest.mark.parametrize("year", [2019, 2020, 2024])
def test_ledger_check_refuses_years_reaching_the_oos(script, year):
    with pytest.raises(SystemExit) as raised:
        script.main(["--ledger-years", "2012", str(year)])
    assert "In-Sample" in str(raised.value)


def test_read_raw_cuts_at_the_in_sample_end(script, tmp_path, monkeypatch):
    days = pd.bdate_range("2019-12-20", "2020-01-10")
    frame = pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=pd.DatetimeIndex(days, name="Date"))
    (tmp_path / "data" / "raw" / "yahoo").mkdir(parents=True)
    frame.to_csv(tmp_path / "data" / "raw" / "yahoo" / "XLK.csv")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    raw = script.read_raw_in_sample(["XLK"], pd.Timestamp("2019-12-27"))
    assert raw["XLK"].index.max() == pd.Timestamp("2019-12-27")


def test_random_placebo_inputs_are_seeded(script):
    mondays = pd.date_range("2010-01-04", periods=5, freq="7D")
    index = pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])
    pd.testing.assert_frame_equal(script.random_scores(index, 1), script.random_scores(index, 1))
    betas = script.random_betas(index, 1)
    assert (betas["IVV"] == 1.0).all() and betas.drop(columns="IVV").stack().between(0.6, 1.4).all()


def test_oos_guard_refuses_a_return_realised_after_the_in_sample_end(script):
    is_end = pd.Timestamp("2019-12-27")
    script.refuse_oos_returns(pd.Series(pd.to_datetime(["2019-12-23", "2019-12-27", None])), is_end)  # passes
    with pytest.raises(SystemExit) as raised:
        script.refuse_oos_returns(pd.Series(pd.to_datetime(["2019-12-23", "2019-12-30"])), is_end)
    assert "2019-12-30" in str(raised.value)


def test_ledger_check_stops_before_any_oos_return_even_with_frozen_lock(script, synthetic_market, tmp_path, monkeypatch):
    # if the In-Sample cut of the raw files failed, the guard still stops the run before any return is computed;
    # an existing FROZEN.lock does not unlock this script (contract 15: only 08_run_oos.py)
    (tmp_path / "FROZEN.lock").write_text("signed")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "read_raw_in_sample", lambda tickers, is_end: {t: synthetic_market.raw[t] for t in tickers})
    monkeypatch.setattr(script, "run_ledger", lambda *args, **kwargs: pytest.fail("ledger ran on an OOS return"))
    with pytest.raises(SystemExit) as raised:
        script.main(["--ledger-years", "2012"])
    assert "after the In-Sample end" in str(raised.value)
    assert not (tmp_path / "outputs").exists()
