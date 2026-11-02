# Methods

How the data is acquired, adjusted, aligned and checked. Later gates extend this page with the features, models, sizing and
evaluation; every claim links to the code or test that implements it. Section numbers refer to the DDMI Research Protocol v4.1.

## Data acquisition (`01_download_data.py`)

- **Download once.** Raw data is downloaded only when `data/raw/` does not exist, or with `--refresh`. Otherwise the archived
  files are verified against the SHA-256 recorded in `data/raw/manifest.json`, and nothing is downloaded.
- **Yahoo Finance.** One batched `yfinance` call for the 9 sectors, IVV, SPY and ^VIX, with `auto_adjust=False,
  actions=True`, from `data.start` through `data.end` (Friday 16 Oct 2026). Failed calls are retried up to 5 times, with
  waits of 5, 10, 20 and 40 seconds. Each ticker is saved with Open, High, Low, Close, Adj Close, Volume, Dividends, Stock
  Splits and, when Yahoo reports it, Capital Gains.
- **FRED.** DGS3MO, DGS10 and BAA10Y from the public CSV endpoint (no API key), kept from one month before `data.start`
  through `data.end`.
- **Stooq** (second source). The CSV endpoint is tried for the 11 tradables. In this snapshot, it returned an HTML page
  instead of a CSV for every ticker. The reason is recorded in the manifest and in the QA report, and no attempt is made
  to bypass the page.
- **Provenance.** `data/raw/manifest.json` records, for every file, the source, the call or URL, the fetch time (UTC), the
  row count, the first and last date, and the SHA-256. For FRED, it also records the SHA-256 of the HTTP response.
  `data/checksums.json`, which is committed, holds the same metadata for the raw and processed files, without the data.
  After a fresh download, any file that differs from the committed checksums is reported: vendor revisions are shown,
  not hidden.
- **Byte-stable files.** Every CSV is written with LF line endings, ISO dates and the float format `%.17g`, which is the
  exact round trip of a float64 and identical on every OS. Running the script again on the same raw data gives identical
  bytes; this was checked by comparing `data/checksums.json` across two runs. In git, data files are marked `binary`, so
  line-ending conversion can never change a checksum.
- **Versions.** Python 3.12.14, yfinance 1.7.0 and pandas 3.1.0, pinned with every other package in `uv.lock`. yfinance's
  internal pandas deprecation warnings are hidden from the console by a filter that matches only warnings raised inside
  yfinance (`src/data.py: quiet_yfinance_deprecations`).

## Price adjustment (`src/data.py: adjust_ohlc`)

With `auto_adjust=False`, Yahoo's **Open, High, Low and Close are adjusted for splits but not for dividends**, and **Adj Close
is adjusted for both**. The archived data confirms both statements (`docs/qa_report.md`):

- **Split-adjusted.** Yahoo's own Close and Open show no jump at the 2:1 splits of 5 Dec 2025 (XLB, XLE, XLK, XLU, XLY), or
  at the 1.231 split factor Yahoo books for XLF on 19 Sep 2016. The largest absolute return within two sessions of any of
  these events is 1.87%.
- **Not dividend-adjusted.** The factor f = Adj Close / Close changes only on distribution ex-dates, and there by exactly
  f(t−1) / f(t) = 1 − D(t) / Close(t−1). The largest change on any other day is 1.6e-6, and over the whole history, the
  cumulative adjustment matches the sum of the dividend factors within 7e-7 log points for every ticker.

Our fully adjusted prices apply the same day's factor to the open, high and low:

```
f(t) = Adj Close(t) / Close(t)
Open_adj(t) = Open(t) · f(t),   High_adj(t) = High(t) · f(t),   Low_adj(t) = Low(t) · f(t),   Close_adj(t) = Adj Close(t)
```

So open-to-open returns include dividends: across an ex-date t, Open_adj(t) / Open_adj(t−1) = [Open(t) / Open(t−1)] /
[1 − D(t) / Close(t−1)]. This is tested in `tests/test_data.py`. Capital-gain distributions would enter the factor in the
same way, and the reconciliation adds them to D when Yahoo reports them. In this snapshot, the Capital Gains column is zero
on every row for every ticker.

Yahoo books the September 2016 distribution of XLRE shares by XLF as a split factor, so the adjusted XLF series treats
that value as reinvested in XLF (`docs/composition_breaks.md`).

## Calendar and alignment

- **Equity calendar.** The union of the session dates of the 11 tradables (9 sectors, IVV, SPY). On two US market
  holidays (2026-05-25 and 2026-09-07), Cboe published VIX values. These rows stay in the raw ^VIX file but are not
  sessions.
- **No forward filling of prices.** The processed daily tables are the adjusted prices reindexed on the equity calendar.
  A missing price would stay missing, and the coverage audit counts none in the scored window.
- **FRED, lagged one day** (`src/data.py: lag_to_sessions`). A value observed for day d is first used on the first
  session after d. When FRED has no value for a day (for example a bond-market holiday on which stocks trade), the
  session keeps the last available value. This applies to a macro series, never to a traded price.
- **VIX.** `data/processed/daily_market.csv` stores the VIX close of the same session. The as-of rule of section 04
  ("market series, lagged one day") is applied when the features are built (Gate 2). Note: the VIX index is disseminated
  until 16:15 ET, after the 16:00 ET information cutoff of section 05.

## Weekly panel (`src/data.py: weekly_panel`)

As in the course skeleton: the weekly open is the first adjusted open of the week, and the weekly close is the last
adjusted close. Weeks are indexed by (date_open, date_close) = (Monday, Friday), so a holiday week keeps its labels: the
open of a week with a Monday holiday is Tuesday's open, and the close of a week with a Good Friday is Thursday's close.
Weeks without any session are dropped. Tested in `tests/test_data.py`.

The signal of week t earns O(t+2) / O(t+1) − 1, realised at the open of week t+2. A week is In-Sample if that open falls
on or before the In-Sample end (Friday 27 Dec 2019), and Out-of-Sample otherwise, as in the skeleton.

## Data QA (`02_validate_data.py`, `src/validate.py`)

The QA gates of section 04 are implemented as functions tested on a synthetic fixture with planted defects
(`tests/test_validate.py`). Their thresholds are fixed in the `qa:` section of `config.yaml`, set before the data was
downloaded. The generated report is `docs/qa_report.md`, and its tables are in `data/qa/` (returns, counts and flags only,
no price levels).

## Engine and ledger accounting (Phase 2.1)

### Ledger reconciliation and the dividend-reinvestment term (Amendment 3)

`src/ledger.py` replays the target weights with share counts and a cash account: execution at the first session after
Friday t, valuation at the first session after Friday t + 7 days; costs paid in cash on the traded value; borrow paid on
the short value at entry; no interest on cash. Level A uses the engine's adjusted opens; Level B uses actual opens
(Yahoo's split-adjusted Open × the product of later split factors), multiplies share counts by the split factor and pays
dividends in cash on the ex-date (shorts pay).

The engine's adjusted open of day d is Open(d)·AdjClose(d)/Close(d), and Yahoo builds the factor backwards with
f(e−1) = f(e)·(1 − D/C(e−1)) at each ex-date e. The adjusted series therefore reinvests each dividend at C(e−1) − D, while
the ledger keeps it as cash. For a position of weight w in week t, with execution session s1 (actual open O1), valuation
session s2 (actual open O2), ex-dates e_1 < … < e_n in (s1, s2] with cash dividends D_k per actual share, actual closes C
and split factors q:

    m(d)        = Π q over (s1, d]                         shares held per share bought at s1
    δ_k         = D_k / (C(e_k − 1) / q(e_k))               dividend over the previous close, in ex-date units
    1 + R_E     = m(s2) · (O2 / O1) / Π_k (1 − δ_k)         engine (adjusted opens)
    1 + R_L     = (m(s2) · O2 + Σ_k m(e_k) · D_k) / O1      ledger (cash dividends)
    term_{t,i}  = w_{t,i} · (R_L − R_E)

The term is computed from the dividend series and prices only (`dividend_reinvestment_term`), never from the measured
difference. A split factor without a dividend gives a term of exactly 0. Level B passes if
|ledger_t − engine_t − Σ_i term_{t,i}| ≤ 1e-6 every week.

Measured on real In-Sample data (2005, 2012, 2016, 2018; 10 seeded random ±2/±2 weight books per year with seeded random
betas, no strategy signal; 2,090 book-weeks; zero cost): raw |ledger − engine| max 5.86e-5, mean 1.46e-6 (by year 1.02e-6
to 1.89e-6); term max 5.88e-5; remainder max 5.11e-7, equal to the largest difference in weeks without a dividend. The
remainder is Yahoo's float32 storage of Adj Close (day-to-day factor noise up to 7e-7 on days without a dividend). XLF on
2016-09-19 is the real-estate (XLRE) spin-off, which Yahoo books as a 1.231 split factor; it is not a true split. The
ledger treats it as a split, which preserves value like the adjusted series (5 book-weeks held; remainder there
≤ 1.34e-7). The true 2:1 splits of December 2025 are Out-of-Sample and are not used. Level A: zero cost max 4.4e-16; with
costs and borrow, after Amendment 3 C2, max 3.7e-16 at 10 bps and 2%, and at most 4.4e-16 in all three cost scenarios
(5 bps/1%, 10 bps/2%, 20 bps/5%); 2.31e-6 at 10 bps/2% with the pre-registered denominator. On the synthetic market
(exact float64 factors) the term equals the difference within 1e-12 and the planted 2:1 split contributes 0 within 1e-12.

Economic size: the mean raw difference is about 1.5e-6 per week, under 0.01% per year (52 × 1.46e-6 ≈ 7.6e-5).

Scope beyond the pre-registration: §09 asks for the ledger on three In-Sample years; the reconciliation covers four
(2005, 2012, 2016, 2018), because 2016 holds the only split factor of the In-Sample data (S21-11). §09 pre-registers the
no-cost check at 1e-6; the Level A check with costs and borrow at 1e-10, in all three cost scenarios, is ours
(Amendment 3 C2, S21-9). The settings are in the `ledger:` section of `config.yaml`; `06_backtest.py --ledger-years`
replays them and refuses any return realised after the In-Sample end (S21-14).
