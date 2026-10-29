"""Read and write the data tables, adjust raw prices, build the weekly panel and align market series.

Conventions (as in the course skeleton):
- weekly tables are indexed by (date_open, date_close) = (Monday, Friday) of each week;
- the weekly open is the first open of the week, the weekly close the last close of the week;
- CSV files are written with LF line endings and a fixed float format, so a re-run gives identical bytes.
"""

import hashlib
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import Pandas4Warning

WEEK_COLUMNS = ["date_open", "date_close"]

FLOAT_FORMAT = "%.17g"  # shortest exact round trip of a float64, identical on every OS
DATE_FORMAT = "%Y-%m-%d"

PRICE_FIELDS = ["Open", "High", "Low", "Close"]
RAW_FIELDS = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"]


def quiet_yfinance_deprecations() -> None:
    """Hide the pandas deprecation warnings raised inside yfinance's own code (console noise only).

    The filter matches only warnings attributed to yfinance modules; warnings from our code still show.
    """
    warnings.filterwarnings("ignore", category=Pandas4Warning, module=r"yfinance\.")


def file_stem(ticker: str) -> str:
    """File name of a ticker: ^VIX -> VIX."""
    return ticker.replace("^", "")


def write_csv(table: pd.DataFrame, path: Path) -> None:
    """Write a table so that the same data always gives the same bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, lineterminator="\n", float_format=FLOAT_FORMAT, date_format=DATE_FORMAT, encoding="utf-8")


def read_daily(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run the scripts in order")
    return pd.read_csv(path, index_col=0, parse_dates=True)


def read_weekly(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run the scripts in order")
    return pd.read_csv(path, index_col=WEEK_COLUMNS, parse_dates=WEEK_COLUMNS)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def adjust_ohlc(raw: pd.DataFrame) -> pd.DataFrame:
    """Fully adjusted Open, High, Low, Close of one ticker.

    Yahoo's Close is adjusted for splits only; Adj Close also for dividends. The factor Adj Close / Close
    of each day is applied to Open, High and Low, so open-to-open returns include dividends.
    """
    factor = raw["Adj Close"] / raw["Close"]
    adjusted = raw[["Open", "High", "Low"]].mul(factor, axis=0)
    adjusted["Close"] = raw["Adj Close"]
    return adjusted


def weekly_panel(daily_open: pd.DataFrame, daily_close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """First open and last close of each week, indexed by (Monday, Friday) of the week.

    Holiday weeks keep their (Monday, Friday) labels: after a Monday holiday the weekly open is Tuesday's open,
    after a Good Friday the weekly close is Thursday's close. Weeks without any session are dropped.
    """
    close = daily_close.resample("W-FRI").last().dropna(how="all")
    opens = daily_open.resample("W-FRI").first().loc[close.index]
    fridays = close.index
    weeks = pd.MultiIndex.from_arrays([fridays - pd.Timedelta(days=4), fridays], names=WEEK_COLUMNS)
    opens.index, close.index = weeks, weeks
    return opens, close


def lag_to_sessions(series: pd.Series, sessions: pd.DatetimeIndex, lag_days: int = 1) -> pd.Series:
    """Value of a market series known at each session: the last observation dated at least lag_days earlier.

    With lag_days=1 the value observed for day d is first used on the first session after d.
    Missing observations are skipped, so a session takes the last available value (a macro series, not a price).
    """
    observed = series.dropna().sort_index()
    known_from = observed.index + pd.Timedelta(days=lag_days)
    position = np.searchsorted(known_from.values, sessions.values, side="right") - 1
    values = np.where(position >= 0, observed.to_numpy()[np.clip(position, 0, None)], np.nan)
    return pd.Series(values, index=sessions, name=series.name)
