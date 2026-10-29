"""DDMI v4.1 data smoke test: run once on your laptop before any other work.

Checks that every series the protocol needs is downloadable, starts early enough,
has no gaps in the scored window, and that adjusted prices behave. Prints PASS/FAIL
per check. It saves nothing and computes no strategy results, so pre-registration
stays valid.

Tickers and dates are read from config.yaml; the checks are those of the original smoke_test_data.py, with two
corrections of 29 Oct (docs/decisions.md): the gap checks use the equity calendar, and a failing check no longer
crashes the report.

Run:  uv run python 00_smoke_test_data.py
"""

import io
import urllib.request

import pandas as pd
import yfinance as yf

from src.config import load_config
from src.data import quiet_yfinance_deprecations

quiet_yfinance_deprecations()
cfg = load_config()
SECTORS = cfg["data"]["tickers"]
HEDGE, BENCH, VIX = cfg["data"]["hedge"], cfg["data"]["benchmark"], cfg["data"]["vix"]
FRED = cfg["data"]["fred"]
END_DAY = pd.Timestamp(cfg["data"]["end"])
START, END = cfg["data"]["start"], str((END_DAY + pd.Timedelta(days=1)).date())  # END exclusive in yfinance -> data through END_DAY
SCORED_FROM = str((pd.Timestamp(cfg["split"]["warmup_end"]) + pd.Timedelta(days=1)).date())  # first scored week (section 10)
IS_END = pd.Timestamp(cfg["split"]["in_sample_end"])
NEED_BY = {**{t: "1999-01-31" for t in SECTORS}, HEDGE: "2000-12-31", BENCH: "1998-12-31", VIX: "1998-12-31"}

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + str(detail) if detail else ''}")  # str(): detail may be a dict


# 1. Prices
tickers = SECTORS + [HEDGE, BENCH, VIX]
adj = yf.download(tickers, start=START, end=END, auto_adjust=True, progress=False)
raw = yf.download(tickers, start=START, end=END, auto_adjust=False, actions=True, progress=False)
close, opens = adj["Close"], adj["Open"]

for t in tickers:
    s = close[t].dropna()
    check(f"{t} downloaded", len(s) > 0, f"{len(s)} daily rows")
    if len(s):
        first = s.index[0]
        check(f"{t} history starts by {NEED_BY[t]}", first <= pd.Timestamp(NEED_BY[t]), f"first = {first.date()}")
        check(f"{t} data through mid-Oct 2026", s.index[-1] >= END_DAY - pd.Timedelta(days=1), f"last = {s.index[-1].date()}")

# 2. Gaps in the scored window, on the equity calendar: the union of the session dates of the tradable tickers.
# ^VIX is not used to build the calendar: Cboe publishes VIX on some US market holidays (correction of 29 Oct).
TRADABLES = SECTORS + [HEDGE, BENCH]
sessions = close[TRADABLES].dropna(how="all").index
print(f"[INFO] Dates with {VIX} data but no equity session (not counted as gaps): "
      f"{[str(d.date()) for d in close.index[close[VIX].notna()].difference(sessions)] or 'none'}")
check(f"Every equity session has a {VIX} value", close[VIX].reindex(sessions).notna().all(),
      f"{close[VIX].reindex(sessions).isna().sum()} sessions without {VIX}")


def missing_in_window(prices, names):
    """Missing values per ticker on the equity calendar of the scored window, each ticker from its own first date."""
    counts = {}
    for t in names:
        start = max(pd.Timestamp(SCORED_FROM), prices[t].first_valid_index())
        counts[t] = int(prices[t].reindex(sessions[sessions >= start]).isna().sum())
    return pd.Series(counts)


missing = missing_in_window(close, TRADABLES)
check("No missing closes in scored window", missing.sum() == 0, missing[missing > 0].to_dict() or "none")
missing_open = missing_in_window(opens, SECTORS + [HEDGE])
check("No missing opens in scored window (needed for open-to-open)", missing_open.sum() == 0,
      missing_open[missing_open > 0].to_dict() or "none")

# 3. Adjustment sanity: big daily moves get flagged, and adjusted vs raw total-return gap ~ dividend yield
rets = close[SECTORS + [HEDGE, BENCH]].pct_change()
big = (rets.abs() > 0.10).sum()
print(f"[INFO] Daily moves above 10% (review manually, expect some in 2008-09 and Mar 2020): {big[big > 0].to_dict()}")
for t in SECTORS + [HEDGE, BENCH]:
    a, r = close[t].dropna(), raw["Close"][t].dropna()
    yrs = (a.index[-1] - a.index[0]).days / 365.25
    gap = (a.iloc[-1] / a.iloc[0]) ** (1 / yrs) - (r.iloc[-1] / r.iloc[0]) ** (1 / yrs)
    check(f"{t} adjusted minus raw annual return looks like a dividend yield", 0.003 < gap < 0.06, f"{gap:.2%}/yr")
splits = raw["Stock Splits"][SECTORS + [HEDGE, BENCH]]
print(f"[INFO] Split events found: {splits[splits > 0].stack().dropna().to_dict() or 'none'}")  # pandas 3: stack keeps NaN

# 4. Weekly panel size (what the models actually train on)
weekly = close[SECTORS].resample("W-FRI").last().dropna(how="all")
is_weeks = len(weekly.loc[SCORED_FROM:IS_END])
oos_weeks = len(weekly.loc[IS_END + pd.Timedelta(days=1):])
print(f"[INFO] Scored weeks: In-Sample {is_weeks}, OOS {oos_weeks} "
      f"(x {len(SECTORS)} assets = {is_weeks * len(SECTORS)} IS training rows)")

# 5. FRED via the public CSV endpoint (no API key needed)
for sid in FRED:
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        df = pd.read_csv(io.StringIO(urllib.request.urlopen(url, timeout=30).read().decode()))
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"])
        vals = pd.to_numeric(df["value"], errors="coerce").dropna()
        check(f"FRED {sid}", df["date"].min() <= pd.Timestamp("1998-12-31") and len(vals) > 1000,
              f"{df['date'].min().date()} to {df['date'].max().date()}")
    except Exception as e:  # noqa: BLE001
        check(f"FRED {sid}", False, repr(e))

print(f"\n{sum(results)}/{len(results)} checks passed")
