"""Data-quality checks of the QA gates (protocol section 04). Pure functions on prices, no strategy logic."""

import numpy as np
import pandas as pd

SPLIT_RATIOS = [2, 3, 4, 5, 10]


def duplicate_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index[index.duplicated()].unique()


def non_monotonic_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Dates that are not strictly after the previous row's date."""
    values = index.to_numpy()
    return index[1:][values[1:] <= values[:-1]]


def weekend_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index[index.day_of_week >= 5]


def non_positive_prices(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Rows where any of the columns is zero or negative (missing values are not counted)."""
    return frame[(frame[columns] <= 0).any(axis=1)]


def stale_sessions(frame: pd.DataFrame) -> pd.DataFrame:
    """Sessions that look forward-filled: Open, High, Low and Close all equal to the previous session's, or zero volume."""
    ohlc = frame[["Open", "High", "Low", "Close"]]
    repeated = (ohlc == ohlc.shift()).all(axis=1)
    no_volume = frame["Volume"] == 0
    flagged = repeated | no_volume
    return frame[flagged].assign(repeated_ohlc=repeated[flagged], zero_volume=no_volume[flagged])


def session_gaps(dates: pd.DatetimeIndex, sessions: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Sessions missing from dates (between its first and last date), and dates that are not sessions."""
    inside = sessions[(sessions >= dates.min()) & (sessions <= dates.max())]
    return inside.difference(dates), dates.difference(sessions)


def big_moves(prices: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Day-to-day moves above the threshold in absolute value, one row per (date, ticker)."""
    returns = prices.pct_change(fill_method=None)
    moves = returns.where(returns.abs() > threshold).stack().dropna().rename("return")
    return moves.rename_axis(["date", "ticker"]).reset_index()


def split_like_moves(close: pd.Series, tolerance: float, ratios: list[int] = SPLIT_RATIOS) -> pd.DataFrame:
    """Days when the price ratio to the previous session is close to a split ratio (k:1) or a reverse split (1:k)."""
    ratio = (close.shift() / close).dropna()
    rows = []
    for k in ratios:
        for label, target in [(f"{k}:1", k), (f"1:{k}", 1 / k)]:
            hit = (ratio / target - 1).abs() < tolerance
            rows += [{"date": day, "ratio": ratio[day], "looks_like": label} for day in ratio.index[hit]]
    return pd.DataFrame(rows, columns=["date", "ratio", "looks_like"])


def distributions(raw: pd.DataFrame) -> pd.Series:
    """Cash distributions per share: dividends, plus capital gains when the vendor reports them separately."""
    paid = raw["Dividends"].fillna(0)
    if "Capital Gains" in raw:
        paid = paid + raw["Capital Gains"].fillna(0)
    return paid


def adjustment_reconciliation(raw: pd.DataFrame) -> dict:
    """Reconcile the dividend adjustment Adj Close / Close with the reported distributions.

    With the factor f = Adj Close / Close, a distribution D paid on day t (ex-date) should give
    f(t-1) / f(t) = 1 - D / Close(t-1), and f should not move on other days.
    """
    raw = raw.dropna(subset=["Close", "Adj Close"])
    factor = raw["Adj Close"] / raw["Close"]
    step = (factor.shift() / factor).iloc[1:]
    paid = distributions(raw).iloc[1:]
    expected = 1 - paid / raw["Close"].shift().iloc[1:]
    event = paid > 0
    error = step - expected
    total_actual = float(np.log(factor.iloc[0] / factor.iloc[-1]))
    total_expected = float(np.log(expected[event]).sum())
    return {
        "events": int(event.sum()),
        "total_log_adjustment": total_actual,
        "total_log_distributions": total_expected,
        "total_gap": total_actual - total_expected,
        "max_event_error": float(error[event].abs().max()) if event.any() else 0.0,
        "max_unexplained_step": float(error[~event].abs().max()),
        "unexplained_steps_above_1e-4": int((error[~event].abs() > 1e-4).sum()),
    }


def annual_gap(adjusted: pd.Series, raw: pd.Series) -> float:
    """Annualised return of the adjusted series minus that of the raw series: about the dividend yield."""
    adjusted, raw = adjusted.dropna(), raw.dropna()
    years = (adjusted.index[-1] - adjusted.index[0]).days / 365.25
    return (adjusted.iloc[-1] / adjusted.iloc[0]) ** (1 / years) - (raw.iloc[-1] / raw.iloc[0]) ** (1 / years)


def distribution_yield(raw: pd.DataFrame) -> float:
    """Average annual distribution yield: sum of D(t) / Close(t-1) per year."""
    raw = raw.dropna(subset=["Close"])
    years = (raw.index[-1] - raw.index[0]).days / 365.25
    return float((distributions(raw) / raw["Close"].shift()).sum() / years)


def sample_dates(sessions: pd.DatetimeIndex, n: int, seed: int) -> pd.DatetimeIndex:
    """n distinct sessions drawn at random with a fixed seed, sorted."""
    rng = np.random.default_rng(seed)
    return pd.DatetimeIndex(np.sort(rng.choice(sessions.to_numpy(), size=n, replace=False)))


def compare_returns(first: pd.Series, second: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Close-to-close returns of two sources on the given dates, each from the previous session common to both."""
    common = first.dropna().index.intersection(second.dropna().index)
    a = first.loc[common].pct_change()
    b = second.loc[common].pct_change()
    dates = dates.intersection(common)
    table = pd.DataFrame({"first": a.loc[dates], "second": b.loc[dates]})
    table["difference"] = table["first"] - table["second"]
    return table.rename_axis("date")


# Second price source (QA cross-check). Files are placed by hand in data/raw/second_source/ (git-ignored, licensed).
SECOND_SOURCE_COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume"]
# investing.com "Historical Data" export, as downloaded: newest row first, US dates, thousands separators, volume
# with K/M/B suffixes. "Change %" is dropped; investing.com publishes no adjusted close, so adj_close stays empty.
INVESTING_COM_COLUMNS = {"Date": "date", "Price": "close", "Open": "open", "High": "high", "Low": "low", "Vol.": "volume"}
INVESTING_COM_DATE_FORMAT = "%m/%d/%Y"
VOLUME_SUFFIXES = {"K": 1e3, "M": 1e6, "B": 1e9}


def _number(text: str) -> float:
    """Parse a number written with optional thousands separators and a K/M/B suffix ('' or '-' is missing)."""
    text = text.strip().replace(",", "")
    if text in ("", "-"):
        return float("nan")
    scale = VOLUME_SUFFIXES.get(text[-1].upper(), 1.0)
    return float(text[:-1] if scale != 1.0 else text) * scale


def read_second_source(path) -> pd.DataFrame:
    """One ticker's second-source daily prices, indexed by an ascending DatetimeIndex named 'date'.

    Accepted formats: the standard columns date,open,high,low,close,adj_close,volume with ISO dates (adj_close may be
    empty), or an investing.com export mapped by INVESTING_COM_COLUMNS. Returns float64 columns
    open, high, low, close, adj_close, volume. Raises ValueError for any other header.
    """
    table = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    table.columns = [str(c).strip() for c in table.columns]
    columns = list(table.columns)
    if columns == SECOND_SOURCE_COLUMNS:
        dates = pd.to_datetime(table["date"], format="%Y-%m-%d")
    elif set(INVESTING_COM_COLUMNS) <= set(columns):
        table = table[list(INVESTING_COM_COLUMNS)].rename(columns=INVESTING_COM_COLUMNS).assign(adj_close="")
        dates = pd.to_datetime(table["date"], format=INVESTING_COM_DATE_FORMAT)
    else:
        raise ValueError(f"{path}: unrecognised columns {columns}; expected exactly {SECOND_SOURCE_COLUMNS} "
                         f"or an investing.com export with {list(INVESTING_COM_COLUMNS)}")
    values = SECOND_SOURCE_COLUMNS[1:]
    frame = pd.DataFrame({c: [_number(v) for v in table[c]] for c in values}, index=pd.DatetimeIndex(dates, name="date"))
    return frame.astype("float64").sort_index()


def compare_second_source(adjusted_close: pd.Series, split_close: pd.Series, second: pd.DataFrame,
                          dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Close-to-close returns of Yahoo and the second source on the sampled dates, for every convention pairing.

    The second source's close is compared with Yahoo's adjusted close and split-only close; its adj_close, when given,
    with Yahoo's adjusted close. Columns: yahoo_return, second_source_return, difference, yahoo, second_series.
    """
    pairs = [("adjusted", adjusted_close, "close"), ("split_only", split_close, "close")]
    if second["adj_close"].notna().any():
        pairs.append(("adjusted", adjusted_close, "adj_close"))
    tables = [compare_returns(yahoo, second[column], dates).assign(yahoo=convention, second_series=column)
              for convention, yahoo, column in pairs]
    return pd.concat(tables).rename(columns={"first": "yahoo_return", "second": "second_source_return"})
