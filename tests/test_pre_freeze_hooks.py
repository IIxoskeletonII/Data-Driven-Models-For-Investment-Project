"""The two pre-freeze hooks of Session 3.7 (decisions S37-2 and S37-3), tested from the decision log.

S37-2: 03_build_features.py: build_forward_returns(daily_open, daily_close, is_end, truncate_at=None, lock_path=None)
cuts both inputs at truncate_at (is_end when None) and labels each week "IS" or "OOS" by realised_on against is_end; a
truncate_at after is_end needs an existing FROZEN.lock passed as lock_path (OOSAccessError otherwise), a truncate_at
before is_end is refused (ValueError), and the default behaviour is unchanged.

S37-3: src/vault.py: Vault.momentum_variants(as_of), the public reader of the momentum_variants table, sealed and logged
like the other table readers.

The data are the shared synthetic market of tests/conftest.py (contract 18) and frames built here by hand; every lock
file and access log is under a temporary folder. No real data are read.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import contracts
from src.config import load_config
from src.vault import OOSAccessError, Vault

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
LATE = pd.Timestamp("2020-06-26")  # a Friday after the In-Sample end, inside the synthetic market (ends 2020-12-31)
TRADABLES = list(contracts.universe(CFG).tradables)
SECTORS = list(contracts.universe(CFG).sectors)
VARIANTS = [f"MOM{lookback}_1" for lookback in CFG["models"]["M0_star"]["lookback_weeks"]]
DAY = pd.Timedelta(days=1)


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("build_features_pre_freeze", ROOT / "03_build_features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def lock(tmp_path) -> Path:
    path = tmp_path / "FROZEN.lock"
    path.write_text("signed\n", encoding="utf-8", newline="\n")
    return path


def by_close(table: pd.DataFrame) -> pd.DataFrame:
    return table.set_axis(pd.DatetimeIndex(table.index.get_level_values("date_close")))


# ---------------------------------------------------------------- S37-2: build_forward_returns


def test_forward_returns_default_equals_the_three_argument_call(script, synthetic_market):
    """truncate_at=None (explicit or omitted) gives the frame of the old three-argument call."""
    m = synthetic_market
    old = script.build_forward_returns(m.daily_open, m.daily_close, IS_END)
    pd.testing.assert_frame_equal(old, script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=None))
    pd.testing.assert_frame_equal(old, script.build_forward_returns(m.daily_open, m.daily_close, IS_END, None, None))


def test_forward_returns_truncate_at_is_end_equals_the_default(script, synthetic_market):
    m = synthetic_market
    pd.testing.assert_frame_equal(script.build_forward_returns(m.daily_open, m.daily_close, IS_END),
                                  script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=IS_END))


def test_forward_returns_default_is_still_in_sample_only(script, synthetic_market):
    """Default behaviour unchanged: last week 2019-12-27, last realised_on 2019-12-23, only "IS" periods."""
    m = synthetic_market
    table = script.build_forward_returns(m.daily_open, m.daily_close, IS_END)
    closes = pd.DatetimeIndex(table.index.get_level_values("date_close"))
    assert closes.max() == IS_END
    assert pd.DatetimeIndex(table["realised_on"]).dropna().max() == ts("2019-12-23")
    assert set(table["period"].dropna()) == {"IS"}


def test_forward_returns_with_lock_given_and_truncate_at_is_end_equals_the_default(script, synthetic_market, lock):
    m = synthetic_market
    pd.testing.assert_frame_equal(
        script.build_forward_returns(m.daily_open, m.daily_close, IS_END),
        script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=IS_END, lock_path=lock))


@pytest.mark.parametrize("day", ["2019-12-20", "2019-06-28", "2015-01-02"])
def test_forward_returns_truncate_at_before_is_end_is_refused(script, synthetic_market, lock, day):
    m = synthetic_market
    with pytest.raises(ValueError):
        script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=ts(day))
    with pytest.raises(ValueError):
        script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=ts(day), lock_path=lock)


@pytest.mark.parametrize("day", ["2019-12-30", "2020-01-03", "2020-06-26", "2020-12-31"])
def test_forward_returns_truncate_at_after_is_end_without_lock_path_is_refused(script, synthetic_market, day):
    m = synthetic_market
    with pytest.raises(OOSAccessError):
        script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=ts(day))


def test_forward_returns_truncate_at_after_is_end_with_a_missing_lock_is_refused(script, synthetic_market, tmp_path):
    m = synthetic_market
    missing = tmp_path / "FROZEN.lock"
    assert not missing.exists()
    with pytest.raises(OOSAccessError):
        script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=LATE, lock_path=missing)


@pytest.fixture
def extended(script, synthetic_market, lock) -> pd.DataFrame:
    m = synthetic_market
    return script.build_forward_returns(m.daily_open, m.daily_close, IS_END, truncate_at=LATE, lock_path=lock)


def test_forward_returns_extended_passes_contract_7(script, extended):
    fwd, realised_on, period = script.split_forward_returns(extended)
    contracts.validate_forward_returns(fwd, realised_on, period, is_end=IS_END)
    assert list(fwd.columns) == TRADABLES


def test_forward_returns_extended_is_cut_at_truncate_at(extended):
    closes = pd.DatetimeIndex(extended.index.get_level_values("date_close"))
    assert closes.max() == LATE
    realised = pd.DatetimeIndex(extended["realised_on"]).dropna()
    assert realised.max() <= LATE
    assert pd.DatetimeIndex(extended["realised_on"])[-2:].isna().all()
    assert extended[TRADABLES].iloc[-2:].isna().all().all()


def test_forward_returns_period_is_assigned_from_realised_on_against_is_end(extended):
    """period "IS" iff realised_on <= is_end, "OOS" iff after, missing iff realised_on is NaT (contract 7)."""
    realised = pd.Series(pd.DatetimeIndex(extended["realised_on"]), index=extended.index)
    period = extended["period"]
    nat = realised.isna()
    assert period[nat].isna().all()
    assert (period[~nat & (realised <= IS_END)] == "IS").all()
    assert (period[~nat & (realised > IS_END)] == "OOS").all()
    assert set(period.dropna()) == {"IS", "OOS"}
    assert (realised[period == "OOS"] > IS_END).all()
    assert (realised[period == "IS"] <= IS_END).all()


def test_forward_returns_extended_labels_the_boundary_weeks(extended):
    """2019-12-13 is realised on 2019-12-23 (IS); 2019-12-20 and 2019-12-27 now have returns realised on 2019-12-30 and
    2020-01-06, both OOS (the first OOS return is at the open of Mon 2019-12-30)."""
    table = by_close(extended)
    assert table.at[ts("2019-12-13"), "realised_on"] == ts("2019-12-23")
    assert table.at[ts("2019-12-13"), "period"] == "IS"
    assert table.at[ts("2019-12-20"), "realised_on"] == ts("2019-12-30")
    assert table.at[ts("2019-12-20"), "period"] == "OOS"
    assert table.at[ts("2019-12-27"), "realised_on"] == ts("2020-01-06")
    assert table.at[ts("2019-12-27"), "period"] == "OOS"
    assert table.loc[[ts("2019-12-20"), ts("2019-12-27")], TRADABLES].notna().all().all()


def test_forward_returns_extended_in_sample_rows_equal_the_default(script, synthetic_market, extended):
    """The rows realised In-Sample are the same numbers and dates as in the default (In-Sample) table."""
    m = synthetic_market
    default = script.build_forward_returns(m.daily_open, m.daily_close, IS_END)
    in_sample = default.index[default["period"].eq("IS").to_numpy()]
    pd.testing.assert_frame_equal(extended.loc[in_sample, TRADABLES], default.loc[in_sample, TRADABLES])
    assert (pd.DatetimeIndex(extended.loc[in_sample, "realised_on"])
            == pd.DatetimeIndex(default.loc[in_sample, "realised_on"])).all()
    assert (extended.loc[in_sample, "period"] == "IS").all()


def test_forward_returns_extended_oos_value_is_the_hand_computed_open_to_open_return(synthetic_market, extended):
    """fwd[t] = O(t+2)/O(t+1) - 1 for an Out-of-Sample week (Fri 2020-01-03)."""
    opens = synthetic_market.weekly_open
    closes = pd.DatetimeIndex(opens.index.get_level_values("date_close"))
    row = int(np.flatnonzero(closes == ts("2020-01-03"))[0])
    table = by_close(extended)
    for ticker in ["XLK", "IVV", "SPY"]:
        expected = opens[ticker].iloc[row + 2] / opens[ticker].iloc[row + 1] - 1
        assert table.at[ts("2020-01-03"), ticker] == pytest.approx(expected, rel=1e-14)
    assert table.at[ts("2020-01-03"), "period"] == "OOS"


def test_forward_returns_extended_ignores_prices_after_truncate_at(script, synthetic_market, lock, extended):
    m = synthetic_market
    opens, closes = m.daily_open.copy(), m.daily_close.copy()
    opens.loc[opens.index > LATE] *= 3.0
    closes.loc[closes.index > LATE] *= 0.5
    pd.testing.assert_frame_equal(
        extended, script.build_forward_returns(opens, closes, IS_END, truncate_at=LATE, lock_path=lock))


def test_forward_returns_default_ignores_prices_after_is_end_even_with_a_lock(script, synthetic_market, lock):
    """A lock alone does not extend the cut: without truncate_at the inputs are still cut at is_end."""
    m = synthetic_market
    default = script.build_forward_returns(m.daily_open, m.daily_close, IS_END)
    opens, closes = m.daily_open.copy(), m.daily_close.copy()
    opens.loc[opens.index > IS_END] *= 3.0
    closes.loc[closes.index > IS_END] *= 0.5
    pd.testing.assert_frame_equal(default, script.build_forward_returns(opens, closes, IS_END, lock_path=lock))


# ---------------------------------------------------------------- S37-3: Vault.momentum_variants


def variant_frame() -> pd.DataFrame:
    """MOM13_1, MOM26_1, MOM52_1 (contract 3: index (date_close, ticker)) on the Fridays of 2018-2020."""
    fridays = pd.date_range("2018-01-05", "2020-12-25", freq="W-FRI")
    rows = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(37)
    frame = pd.DataFrame(rng.normal(size=(len(rows), len(VARIANTS))), index=rows, columns=VARIANTS)
    contracts.validate_features(frame, columns=VARIANTS)
    return frame


VARIANT_FRAME = variant_frame()


@pytest.fixture
def venv(tmp_path):
    paths = {"lock": tmp_path / "FROZEN.lock", "log": tmp_path / "logs" / "vault_access_log.jsonl"}
    vault = Vault(IS_END, lock_path=paths["lock"], log_path=paths["log"],
                  frames={"momentum_variants": VARIANT_FRAME.copy()}, cfg=CFG)
    return vault, paths


def log_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def closes_of(frame: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


def expected_rows(as_of) -> pd.DataFrame:
    return VARIANT_FRAME.loc[np.asarray(closes_of(VARIANT_FRAME) <= ts(as_of))]


@pytest.mark.parametrize("as_of", ["2018-06-01", "2019-06-28", "2019-12-27"])
def test_momentum_variants_returns_the_rows_up_to_as_of(venv, as_of):
    vault, _ = venv
    rows = vault.momentum_variants(ts(as_of))
    pd.testing.assert_frame_equal(rows, expected_rows(as_of))
    assert closes_of(rows).max() == ts(as_of)
    assert list(rows.index.names) == ["date_close", "ticker"]
    assert list(rows.columns) == VARIANTS


def test_momentum_variants_between_fridays_returns_the_last_friday_before(venv):
    vault, _ = venv
    rows = vault.momentum_variants(ts("2019-07-03"))  # a Wednesday
    assert closes_of(rows).max() == ts("2019-06-28")


def test_momentum_variants_accepts_a_string_date(venv):
    vault, _ = venv
    pd.testing.assert_frame_equal(vault.momentum_variants("2019-12-27"), expected_rows("2019-12-27"))


def test_momentum_variants_ok_call_is_logged_once(venv):
    vault, paths = venv
    vault.momentum_variants(IS_END)
    lines = log_lines(paths["log"])
    assert len(lines) == 1
    assert lines[0]["method"] == "momentum_variants"
    assert lines[0]["result"] == "ok"
    assert lines[0]["as_of"] == "2019-12-27"
    assert "utc" in lines[0]


def test_momentum_variants_every_call_appends_one_line(venv):
    vault, paths = venv
    vault.momentum_variants(ts("2018-06-01"))
    vault.momentum_variants(ts("2019-06-28"))
    with pytest.raises(OOSAccessError):
        vault.momentum_variants(ts("2020-01-03"))
    lines = log_lines(paths["log"])
    assert [line["method"] for line in lines] == ["momentum_variants"] * 3
    assert [line["result"] for line in lines] == ["ok", "ok", "refused"]
    assert [line["as_of"] for line in lines] == ["2018-06-01", "2019-06-28", "2020-01-03"]


@pytest.mark.parametrize("day", ["2019-12-28", "2019-12-30", "2020-01-03", "2020-12-25"])
def test_momentum_variants_after_the_in_sample_end_is_refused_and_logged(venv, day):
    vault, paths = venv
    with pytest.raises(OOSAccessError):
        vault.momentum_variants(ts(day))
    lines = log_lines(paths["log"])
    assert len(lines) == 1
    assert lines[0] == {**lines[0], "method": "momentum_variants", "result": "refused", "as_of": day}


def test_momentum_variants_lock_without_unlock_stays_sealed(venv):
    vault, paths = venv
    paths["lock"].write_text("signed\n", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        vault.momentum_variants(ts("2020-06-26"))
    assert log_lines(paths["log"])[-1]["result"] == "refused"


def test_momentum_variants_after_lock_and_unlock_reads_oos_rows(venv):
    vault, paths = venv
    paths["lock"].write_text("signed\n", encoding="utf-8")
    vault.unlock()
    rows = vault.momentum_variants(ts("2020-06-26"))
    pd.testing.assert_frame_equal(rows, expected_rows("2020-06-26"))
    assert closes_of(rows).max() == ts("2020-06-26")
    last = log_lines(paths["log"])[-1]
    assert last["method"] == "momentum_variants" and last["result"] == "ok" and last["as_of"] == "2020-06-26"


def test_momentum_variants_missing_table_is_logged_as_refused(tmp_path):
    log = tmp_path / "log.jsonl"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, frames={}, cfg=CFG)
    with pytest.raises(Exception):  # noqa: B017 - any failure of the read is logged as refused
        vault.momentum_variants(IS_END)
    lines = log_lines(log)
    assert lines and lines[-1]["method"] == "momentum_variants" and lines[-1]["result"] == "refused"


def test_momentum_variants_reads_momentum_variants_csv_from_data_dir(tmp_path):
    """Without frames, the table is momentum_variants.csv of data_dir (contract 3)."""
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    VARIANT_FRAME.to_csv(data_dir / "momentum_variants.csv", lineterminator="\n", float_format="%.17g",
                         date_format="%Y-%m-%d")
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", data_dir=data_dir, cfg=CFG)
    rows = vault.momentum_variants(ts("2019-06-28"))
    expected = expected_rows("2019-06-28")
    np.testing.assert_allclose(rows.to_numpy(), expected.to_numpy(), rtol=0, atol=0)
    assert closes_of(rows).equals(closes_of(expected))


def test_momentum_variants_returns_a_copy(venv):
    vault, _ = venv
    first = vault.momentum_variants(IS_END)
    first.iloc[:, :] = 0.0
    pd.testing.assert_frame_equal(vault.momentum_variants(IS_END), expected_rows(IS_END))
