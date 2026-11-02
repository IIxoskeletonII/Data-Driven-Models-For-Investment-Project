"""Independent position-and-cash ledger (shares, raw opens, dividend cash flows, splits) used to verify the vectorised
engine on three In-Sample years (protocol section 09, "Ledger reconciliation").

Deliberately written differently from src/backtest.py: an explicit loop over weeks with share counts and a cash account,
execution sessions found on the daily calendar (not on the weekly panel), costs paid in cash on the traded value and
borrow paid in cash on the short value at entry.

Two price modes:
- "adjusted" (Level A, bookkeeping): the same adjusted opens as the engine (src.data.adjust_ohlc), no corporate actions;
- "raw" (Level B, corporate actions): actual opens rebuilt from Yahoo's split-adjusted Open by undoing the later split
  factors, share counts multiplied on split dates, dividends paid in cash on ex-dates (credited to longs, debited to
  shorts). Yahoo's dividend adjustment uses the previous close, so Level B differs from the engine in ex-dividend weeks
  by the dividend-reinvestment term of dividend_reinvestment_term (Amendment 3 C1).
"""

import numpy as np
import pandas as pd

MODES = ("adjusted", "raw")
LEDGER_COLUMNS = ["nav_start", "ret", "traded", "costs", "borrow", "dividends", "splits", "nav_end"]


def _later_split_product(raw: pd.DataFrame) -> pd.Series:
    """Product of the split ratios strictly after each date (1 after the last split)."""
    ratio = raw["Stock Splits"].where(raw["Stock Splits"] > 0, 1.0).astype(np.float64).to_numpy()
    later = np.r_[np.cumprod(ratio[::-1])[::-1][1:], 1.0]
    return pd.Series(later, index=raw.index)


def actual_prices(raw: pd.DataFrame) -> pd.DataFrame:
    """Actual traded open, actual dividend per share and split ratio of one ticker, from Yahoo auto_adjust=False rows.

    Yahoo's Open and Dividends are divided by the split ratios that come later; multiplying by their product undoes it.
    Returns columns `open`, `dividend` (cash per actual share on the ex-date) and `split` (ratio on the first session at
    the new price, 1 otherwise).
    """
    later = _later_split_product(raw)
    return pd.DataFrame({
        "open": raw["Open"].astype(np.float64) * later,
        "dividend": raw["Dividends"].astype(np.float64) * later,
        "split": raw["Stock Splits"].where(raw["Stock Splits"] > 0, 1.0).astype(np.float64),
    }, index=raw.index)


def _daily_tables(raw: dict[str, pd.DataFrame], tickers: list[str], mode: str) -> tuple[pd.DatetimeIndex, dict]:
    """Session calendar (union of all the given tickers' dates) and per-ticker open, dividend and split arrays on it."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    sessions = pd.DatetimeIndex(sorted(set().union(*(frame.index for frame in raw.values()))))
    tables = {}
    for ticker in tickers:
        frame = raw[ticker]
        if mode == "raw":
            prices = actual_prices(frame)
        else:
            factor = frame["Adj Close"] / frame["Close"]
            prices = pd.DataFrame({"open": frame["Open"] * factor, "dividend": 0.0, "split": 1.0}, index=frame.index)
        prices = prices.reindex(sessions)
        tables[ticker] = {
            "open": prices["open"].to_numpy(dtype=np.float64),
            "dividend": prices["dividend"].fillna(0.0).to_numpy(dtype=np.float64),
            "split": prices["split"].fillna(1.0).to_numpy(dtype=np.float64),
        }
    return sessions, tables


def run_ledger(weights: pd.DataFrame, raw: dict[str, pd.DataFrame], initial_capital: float = 100.0, *,
               mode: str = "raw", cost_bps: float = 0.0, borrow_annual: float = 0.0) -> pd.DataFrame:
    """Weekly returns of a book replayed with shares and cash (§09 ledger reconciliation).

    weights: target weights of week t (weekly index × traded tickers), decided after Friday close t, on consecutive
    weeks. raw: per-ticker daily frames in Yahoo auto_adjust=False format. For every week t the book is rebalanced to the
    weights at the first session after Friday t (execution, O(t+1)) and valued at the first session after Friday t + 7
    days (realisation, O(t+2)), which is also the next week's execution session.

    At execution: NAV = cash + Σ shares·open; new shares = w·NAV / open (shorts are negative shares); the cost
    cost_bps/10 000 · Σ|Δshares|·open is paid in cash. Between execution (excluded) and realisation (included): splits
    multiply the shares, dividends pay shares × dividend in cash (shorts pay). At realisation the borrow
    borrow_annual · 7/365 · (short value at entry) is paid and NAV = cash + Σ shares·open. No interest on cash.

    mode "adjusted" uses the adjusted opens (Level A); "raw" uses actual opens with splits and cash dividends (Level B).
    Returns a float64 DataFrame on the weights' index with columns nav_start, ret (weekly return of the NAV, decimals),
    traded (traded value / NAV), costs and borrow (fractions of nav_start), dividends (net dividend cash / nav_start)
    splits (number of split events applied to held positions) and nav_end. A week whose realisation session lies after the data ends is dropped.
    """
    tickers = list(weights.columns)
    sessions, tables = _daily_tables(raw, tickers, mode)
    session_values = sessions.values
    fridays = pd.DatetimeIndex(weights.index.get_level_values("date_close"))
    cost_rate, borrow_rate = cost_bps / 10_000, borrow_annual * 7 / 365

    cash = float(initial_capital)
    shares = np.zeros(len(tickers))
    last_valuation = None
    rows, kept = [], []
    for row, friday in enumerate(fridays):
        start = np.searchsorted(session_values, (friday + pd.Timedelta(days=1)).to_datetime64(), side="left")
        end = np.searchsorted(session_values, (friday + pd.Timedelta(days=8)).to_datetime64(), side="left")
        if end >= len(sessions):
            break
        if last_valuation is not None and start != last_valuation:
            raise ValueError(f"weeks are not consecutive: the execution session {sessions[start].date()} is not the "
                             f"previous realisation session {sessions[last_valuation].date()}")
        open_start = np.array([tables[t]["open"][start] for t in tickers])
        open_end = np.array([tables[t]["open"][end] for t in tickers])
        target = weights.iloc[row].to_numpy(dtype=np.float64)

        held = shares != 0
        if np.isnan(open_start[held]).any():
            raise ValueError(f"no open on {sessions[start].date()} for a held ticker")
        nav_start = cash + float(np.sum(shares[held] * open_start[held]))
        needed = target != 0
        if np.isnan(open_start[needed]).any() or np.isnan(open_end[needed]).any():
            raise ValueError(f"no open around {sessions[start].date()} for a ticker with a target weight")

        new_shares = np.zeros(len(tickers))
        new_shares[needed] = target[needed] * nav_start / open_start[needed]
        trade_value = np.nan_to_num((new_shares - shares) * open_start)
        cost = cost_rate * float(np.abs(trade_value).sum())
        cash -= float(trade_value.sum()) + cost
        shares = new_shares
        short_value = float(-np.sum(np.where(shares < 0, shares * open_start, 0.0)))

        dividend_cash, split_events = 0.0, 0
        for day in range(start + 1, end + 1):
            for j, ticker in enumerate(tickers):
                if shares[j] == 0:
                    continue
                dividend = tables[ticker]["dividend"][day]
                if dividend:
                    dividend_cash += shares[j] * dividend
                ratio = tables[ticker]["split"][day]
                if ratio != 1.0:
                    shares[j] *= ratio
                    split_events += 1
        cash += dividend_cash
        borrow = borrow_rate * short_value
        cash -= borrow

        nav_end = cash + float(np.sum(np.where(shares != 0, shares * np.nan_to_num(open_end), 0.0)))
        rows.append([nav_start, nav_end / nav_start - 1, float(np.abs(trade_value).sum()) / nav_start, cost / nav_start,
                     borrow / nav_start, dividend_cash / nav_start, split_events, nav_end])
        kept.append(row)
        last_valuation = end

    return pd.DataFrame(rows, index=weights.index[kept], columns=LEDGER_COLUMNS, dtype=np.float64)


def dividend_reinvestment_term(weights: pd.DataFrame, raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Dividend-reinvestment term of Level B (Amendment 3 C1, docs/methods.md): the expected ledger-minus-engine return of
    each week and ticker, computed only from the dividend series and prices (never from the measured difference).

    Inputs per ticker, from Yahoo auto_adjust=False rows in actual units (src.ledger.actual_prices): actual opens O,
    actual closes C, cash dividends D_k on the ex-dates e_k and split factors q. For the week t, with execution session
    s1 (O1 = O(t+1)), valuation session s2 (O2 = O(t+2)) and the ex-dates e_1 < ... < e_n in (s1, s2]:
        m(d)   = product of the split factors q in (s1, d]                  shares held per share bought at s1
        δ_k    = D_k / (C(e_k − 1) / q(e_k))                                 dividend over the previous close, ex-date units
        engine 1 + R_E = m(s2) · (O2 / O1) / Π_k (1 − δ_k)                   Yahoo's factor f(e−1) = f(e)·(1 − δ)
        ledger 1 + R_L = (m(s2) · O2 + Σ_k m(e_k) · D_k) / O1                dividend held as cash, no interest
        term_{t,i} = w_{t,i} · (R_L − R_E)
    Yahoo's adjusted series reinvests each dividend at C(e − 1) − D, the ledger keeps it as cash; a split alone (m ≠ 1,
    no dividend) gives a term of exactly 0. Level B passes if |ledger − engine − Σ_i term_{t,i}| ≤ 1e-6 every week.
    Returns a float64 frame on the weights' index (rows) × tickers; rows whose valuation session is after the data end
    are dropped.
    """
    tickers = list(weights.columns)
    sessions = pd.DatetimeIndex(sorted(set().union(*(frame.index for frame in raw.values()))))
    session_values = sessions.values
    opens, dividends, splits, closes = {}, {}, {}, {}
    for ticker in tickers:
        actual = actual_prices(raw[ticker]).reindex(sessions)
        opens[ticker] = actual["open"].to_numpy()
        dividends[ticker] = actual["dividend"].fillna(0.0).to_numpy()
        splits[ticker] = actual["split"].fillna(1.0).to_numpy()
        closes[ticker] = (raw[ticker]["Close"] * _later_split_product(raw[ticker])).reindex(sessions).to_numpy()
    values = weights.to_numpy(dtype=np.float64)
    rows, kept = [], []
    for row, friday in enumerate(pd.DatetimeIndex(weights.index.get_level_values("date_close"))):
        start = np.searchsorted(session_values, (friday + pd.Timedelta(days=1)).to_datetime64(), side="left")
        end = np.searchsorted(session_values, (friday + pd.Timedelta(days=8)).to_datetime64(), side="left")
        if end >= len(sessions):
            break
        terms = np.zeros(len(tickers))
        for j, ticker in enumerate(tickers):
            w = values[row, j]
            if w == 0:
                continue
            o1, o2 = opens[ticker][start], opens[ticker][end]
            multiplier, reinvested, cash = 1.0, 1.0, 0.0
            for day in range(start + 1, end + 1):
                multiplier *= splits[ticker][day]
                dividend = dividends[ticker][day]
                if dividend:
                    previous_close = closes[ticker][day - 1] / splits[ticker][day]
                    reinvested *= 1 - dividend / previous_close
                    cash += multiplier * dividend
            engine_growth = multiplier * (o2 / o1) / reinvested
            ledger_growth = (multiplier * o2 + cash) / o1
            terms[j] = w * (ledger_growth - engine_growth)
        rows.append(terms)
        kept.append(row)
    return pd.DataFrame(rows, index=weights.index[kept], columns=tickers, dtype=np.float64)
