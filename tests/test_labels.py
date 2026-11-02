"""Labels, purged walk-forward folds and the purge assertion of src/labels.py (§05, §07, §10; contracts 6 and 13; S22-7).

Calendars are built here from business days minus US holidays (pandas holiday rules), forward returns are random
frames on the weekly index, and every expected date is computed independently in the test.
"""

import numpy as np
import pandas as pd
import pytest
from pandas.tseries.holiday import (
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
    sunday_to_monday,
)

from src import contracts, labels
from src.config import load_config

CFG = load_config()
UNIVERSE = contracts.universe(CFG)
SECTORS = list(UNIVERSE.sectors)
TRADABLES = list(UNIVERSE.tradables)
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
WARMUP_END = pd.Timestamp(CFG["split"]["warmup_end"])  # 2002-12-31
FIRST_TEST_YEAR, LAST_TEST_YEAR = CFG["split"]["test_years"]  # 2008, 2019
EMBARGO = CFG["split"]["embargo_weeks"]  # 1
DAY = pd.Timedelta(days=1)
ContractError = contracts.ContractError


# US equity holidays: New Year, MLK, Presidents, Good Friday, Memorial, Independence, Labor, Thanksgiving, Christmas
HOLIDAY_RULES = (
    Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
    USMartinLutherKingJr,
    USPresidentsDay,
    GoodFriday,
    USMemorialDay,
    Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
    USLaborDay,
    USThanksgivingDay,
    Holiday("Christmas", month=12, day=25, observance=nearest_workday),
)


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


def make_sessions(start: str, end: str) -> pd.DatetimeIndex:
    holidays = pd.DatetimeIndex(sorted({day for rule in HOLIDAY_RULES for day in rule.dates(start, end)}))
    return pd.bdate_range(start, end).difference(holidays).rename("date")


def weekly_index_of(sessions: pd.DatetimeIndex) -> pd.MultiIndex:
    """(Monday, Friday) of every calendar week that holds a session (contract 2)."""
    fridays = pd.DatetimeIndex(np.unique((sessions + pd.to_timedelta(4 - sessions.day_of_week, unit="D")).values))
    return pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])


def random_fwd(weeks: pd.MultiIndex, seed: int = 0) -> pd.DataFrame:
    """Forward returns on the weekly index for the 11 tradables; the last two rows are NaN (contract 7)."""
    rng = np.random.default_rng(seed)
    fwd = pd.DataFrame(rng.normal(0.001, 0.02, (len(weeks), len(TRADABLES))), index=weeks, columns=TRADABLES)
    fwd.iloc[-2:] = np.nan
    return fwd


def expected_label_end(weeks: pd.MultiIndex, sessions: pd.DatetimeIndex) -> list:
    """First session on or after date_open of the row two places later; NaT for the last two rows."""
    opens = pd.DatetimeIndex(weeks.get_level_values("date_open"))
    out = []
    for r in range(len(weeks)):
        if r + 2 >= len(weeks):
            out.append(pd.NaT)
        else:
            out.append(sessions[sessions.searchsorted(opens[r + 2])])
    return out


# ---------------------------------------------------------------- make_labels


@pytest.fixture(scope="module")
def small():
    """2021 calendar with Monday holidays; one week removed from both the calendar and the index (no session)."""
    sessions = make_sessions("2021-01-04", "2021-12-31")
    sessions = sessions[(sessions < ts("2021-08-09")) | (sessions > ts("2021-08-13"))]  # no session in that week
    weeks = weekly_index_of(sessions)
    fwd = random_fwd(weeks, seed=1)
    fwd["IVV"] = 5.0  # huge values outside the sectors: must not enter the cross-sectional mean
    fwd["SPY"] = -0.9
    fwd.iloc[-2:] = np.nan
    fwd.loc[(slice(None), ts("2021-06-11")), SECTORS[3]] = np.nan  # one sector missing in one week
    return sessions, weeks, fwd


def test_make_labels_index_columns_and_contract(small):
    sessions, weeks, fwd = small
    out = labels.make_labels(fwd, sessions)
    contracts.validate_labels(out)
    assert list(out.columns) == ["y", "label_end"]
    assert list(out.index.names) == ["date_close", "ticker"]
    assert out.index.is_monotonic_increasing
    fridays = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    complete = fwd[SECTORS].notna().all(axis=1).to_numpy()
    expected_fridays = list(fridays[complete])
    assert list(pd.DatetimeIndex(out.index.get_level_values("date_close").unique())) == expected_fridays
    assert ts("2021-06-11") not in set(out.index.get_level_values("date_close"))


def test_make_labels_y_is_relative_to_the_sector_mean(small):
    sessions, _, fwd = small
    out = labels.make_labels(fwd, sessions)
    for friday in ["2021-03-05", "2021-07-02", "2021-11-26"]:
        row = fwd.xs(ts(friday), level="date_close")[SECTORS].iloc[0].to_numpy()
        y = out.xs(ts(friday), level="date_close")["y"].loc[SECTORS].to_numpy()
        np.testing.assert_allclose(y, row - row.mean(), rtol=0, atol=1e-15)


def test_make_labels_label_end_is_first_session_of_the_row_two_later(small):
    sessions, weeks, fwd = small
    out = labels.make_labels(fwd, sessions)
    expected = pd.Series(expected_label_end(weeks, sessions), index=pd.DatetimeIndex(weeks.get_level_values("date_close")))
    per_week = out["label_end"].groupby(level="date_close").first()
    for friday, value in per_week.items():
        assert ts(value) == ts(expected[friday]), friday
    # week t+2 starts on Martin Luther King Day (Monday 2021-01-18): label_end is Tuesday
    assert ts(per_week.loc[ts("2021-01-08")]) == ts("2021-01-19")
    # Good Friday week: label_end of the week two rows later is a plain Monday
    assert ts(per_week.loc[ts("2021-03-26")]) == ts("2021-04-05")
    # rows, not calendar weeks: the week of 2021-08-09 has no session, so two rows after 2021-07-30 is 2021-08-16
    assert ts(per_week.loc[ts("2021-07-30")]) == ts("2021-08-16")


def test_label_end_by_week_has_nat_where_there_is_no_label(small):
    sessions, weeks, fwd = small
    out = labels.make_labels(fwd, sessions)
    per_week = labels.label_end_by_week(out, weeks)
    assert per_week.name == "label_end"
    assert list(per_week.index) == list(weeks)
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    missing = pd.isna(per_week.to_numpy())
    assert list(closes[missing]) == [ts("2021-06-11")] + list(closes[-2:])
    expected = expected_label_end(weeks, sessions)
    for i in np.flatnonzero(~missing):
        assert ts(per_week.iloc[i]) == ts(expected[i])


def test_labels_ignore_forward_returns_realised_after_t(small):
    """Rows whose label_end is after t are perturbed; labels with label_end <= t are bit-identical."""
    sessions, weeks, fwd = small
    t = ts("2021-09-17")
    position = list(weeks.get_level_values("date_close")).index(t)
    perturbed = fwd.copy()
    rng = np.random.default_rng(9)
    rows = slice(position - 1, len(weeks) - 2)  # rows r >= pos(t) - 1 have label_end after the Monday of week t
    perturbed.iloc[rows] = rng.normal(0, 0.05, perturbed.iloc[rows].shape)
    base = labels.make_labels(fwd, sessions)
    other = labels.make_labels(perturbed, sessions)
    a, b = base[base["label_end"] <= t], other[other["label_end"] <= t]
    assert len(a) > 0
    assert a.index.equals(b.index)
    assert np.array_equal(a["y"].to_numpy(), b["y"].to_numpy())
    assert np.array_equal(a["label_end"].to_numpy(), b["label_end"].to_numpy())
    assert not np.array_equal(base["y"].to_numpy(), other["y"].to_numpy())


# ---------------------------------------------------------------- walk-forward folds


@pytest.fixture(scope="module")
def long_calendar():
    sessions = make_sessions("2001-01-01", "2020-12-31")
    weeks = weekly_index_of(sessions)
    out = labels.make_labels(random_fwd(weeks, seed=2), sessions)
    label_end = labels.label_end_by_week(out, weeks)
    folds = labels.walk_forward_folds(weeks, label_end, CFG)
    return sessions, weeks, label_end, folds


def is_weeks(weeks: pd.MultiIndex, label_end: pd.Series) -> pd.DatetimeIndex:
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    ends = pd.DatetimeIndex(label_end.to_numpy())
    return closes[np.asarray(ends <= IS_END)]


def test_folds_are_48_quarterly_records_in_order(long_calendar):
    _, _, _, folds = long_calendar
    assert len(folds) == 48
    assert [(f.test_year, f.refit) for f in folds] == [(y, q) for y in range(FIRST_TEST_YEAR, LAST_TEST_YEAR + 1)
                                                       for q in range(1, 5)]
    assert all(isinstance(f, contracts.WalkForwardFold) for f in folds)


def test_folds_hand_dates(long_calendar):
    _, _, _, folds = long_calendar
    first, second, last = folds[0], folds[1], folds[-1]
    assert first.test_start == ts("2008-01-04")
    assert first.purge_end == ts("2007-12-28")
    assert first.train_end == ts("2007-12-14")  # label_end Mon 2007-12-24; the next week's is Mon 2007-12-31
    assert first.test_end == ts("2008-03-28")
    assert second.test_start == ts("2008-04-04")
    assert last.test_end == ts("2019-12-13")
    assert all(f.train_start == ts("2003-01-03") for f in folds)  # first date_close after the warm-up


def test_folds_pass_validate_folds(long_calendar):
    _, _, label_end, folds = long_calendar
    contracts.validate_folds(folds, label_end=label_end)


def test_folds_training_rows_are_purged_and_maximal(long_calendar):
    _, weeks, label_end, folds = long_calendar
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    ends = pd.Series(pd.DatetimeIndex(label_end.to_numpy()), index=closes)
    for fold in folds:
        assert fold.purge_end == fold.test_start - pd.Timedelta(days=7 * EMBARGO)
        training = ends[(closes >= fold.train_start) & (closes <= fold.train_end)]
        assert training.notna().all()
        assert (training <= fold.purge_end).all()
        next_week = ends[closes > fold.train_end].iloc[0]
        assert next_week > fold.purge_end  # train_end is the last week with label_end <= purge_end
        assert fold.train_end < fold.test_start


def test_folds_test_windows_partition_the_in_sample_weeks_from_2008(long_calendar):
    _, weeks, label_end, folds = long_calendar
    in_sample = is_weeks(weeks, label_end)
    assert in_sample[-1] == ts("2019-12-13")
    expected = list(in_sample[in_sample.year >= FIRST_TEST_YEAR])
    tested = []
    for fold in folds:
        window = in_sample[(in_sample >= fold.test_start) & (in_sample <= fold.test_end)]
        assert window[0] == fold.test_start and window[-1] == fold.test_end
        assert fold.test_start.quarter == fold.refit and fold.test_start.year == fold.test_year
        tested.extend(window)
        training = in_sample[(in_sample >= fold.train_start) & (in_sample <= fold.train_end)]
        assert not set(training) & set(window)
    assert tested == expected
    assert len(tested) == len(set(tested))


def test_folds_refit_at_the_first_week_of_each_quarter(long_calendar):
    _, weeks, label_end, folds = long_calendar
    in_sample = is_weeks(weeks, label_end)
    for fold in folds:
        quarter_weeks = in_sample[(in_sample.year == fold.test_year) & (in_sample.quarter == fold.refit)]
        assert fold.test_start == quarter_weeks[0]


def test_assert_purged_accepts_clean_rows_and_rejects_a_late_or_missing_label_end(long_calendar):
    _, _, _, folds = long_calendar
    fold = folds[5]
    clean = pd.Series(pd.DatetimeIndex([fold.purge_end - 14 * DAY, fold.purge_end]), name="label_end")
    assert labels.assert_purged(clean, fold) is None
    late = pd.Series(pd.DatetimeIndex([fold.purge_end - 14 * DAY, fold.purge_end + DAY]), name="label_end")
    with pytest.raises(ContractError):
        labels.assert_purged(late, fold)
    missing = pd.Series(pd.DatetimeIndex([fold.purge_end - 14 * DAY, pd.NaT]), name="label_end")
    with pytest.raises(ContractError):
        labels.assert_purged(missing, fold)
