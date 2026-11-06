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

### Signals, sizing and the hedge (`src/sizing.py`)

Each Friday t, the 9 sector scores (known after the close) are sorted in descending order. Exact ties are broken
alphabetically, so the earlier ticker ranks higher. Ranks 1 and 2 get +1, the two lowest ranks get −1, and the rest get 0
(§09; `signals_from_scores`).

The core weight is 0.25 × signal, so the core is 50% long and 50% short. In the k = 1 and k = 3 sensitivity runs it is
0.5 / k per name (Amendment 2 C4). With β̂ the BETA52 of week t, read through the vault (S23-4):

    β_c = Σ_i 0.25 · s_i · β̂_i,     h = clip(−β_c / β̂_IVV, −0.5, 0.5)
    h = 0 (IVV signal 0) if |h| / (1 + |h|) < 0.02          (Amendment 2 C2, S21-1)
    w_i = 0.25 · s_i / (1 + |h|),    w_IVV = h / (1 + |h|),    Σ|w| = 1

The IVV signal is the sign of h. Residual beta (β_c + h · β̂_IVV) / (1 + |h|) is non-zero only when the cap binds
(|β_c / β̂_IVV| > 0.5) or the dead-band sets h to 0. Net exposure is h / (1 + |h|). Both are reported every week
(`target_weights`).

**Missing inputs** (§09 step 5, Amendment 2 C3, S21-2). A week can trade only if it has all 9 sector scores and all 10
BETA52 (the 9 sectors and IVV, held or not). A zero or non-finite IVV beta counts as missing, because the hedge is
undefined there. A week that misses any of them keeps last week's signals, target weights, hedge, residual beta, net
exposure and cap flag. The engine rebalances the drifted weights back to those targets, so turnover from drift is still
charged. The event is logged (logger `src.sizing`, level WARNING) with the week and the missing fields. Before the first
fully valid week the book is flat. Its first week is entered from cash.

### The weekly return (`src/backtest.py`)

`forward_returns` gives R_fwd[t] = O(t+2) / O(t+1) − 1 on the adjusted opens, the realisation date (the open of week
t + 2) and the period: In-Sample if that date is on or before 2019-12-27, Out-of-Sample otherwise (contract 7). `run`
then computes, for the target weights w of week t:

    gross_t    = Σ_i w_{t,i} · R_fwd_{t,i}
    w_pre_t    = w_{t−1} · (1 + R_fwd_{t−1}) / (1 + net_{t−1})        (Amendment 3 C2, S21-9; 0 before the first week)
    turnover_t = Σ_i |w_{t,i} − w_pre_{t,i}|
    costs_t    = c · turnover_t,       c = cost in bps / 10,000
    borrow_t   = b · 7/365 · Σ_{i: w<0} |w_{t,i}|
    net_t      = gross_t − costs_t − borrow_t

No interest is credited on cash or short collateral (§09). The three cost scenarios pair `costs.bps` and `costs.borrow`
by position: 5 bps with 1%, 10 bps with 2% (the baseline) and 20 bps with 5% (S23-7). The book is one continuous series
over both periods (Amendment 2 C5). The first Out-of-Sample trade is costed from the drifted In-Sample positions, while the
reported behaviour statistics restart from flat in each period (S21-13). The engine never computes signals and never
reads files. `06_backtest.py` stops before the engine runs if any real-data forward return is realised after
2019-12-27, whether `FROZEN.lock` exists or not (S21-14).

## Metrics and the risk-free rate (`src/metrics.py`)

The definitions are those of the course skeleton's `docs/metrics.md`, on simple weekly returns with P = 52 periods per
year (§11). Annualised return is (Π(1 + r))^(52/T) − 1. Volatility is the sample standard deviation × √52. Max drawdown
is min_t E_t / max_{τ≤t} E_τ − 1, with the starting capital as the first peak. Ratios with a zero denominator are NaN.

- **Risk-free rate** (S21-4). The weekly T-bill return is DGS3MO / 100 · 7/365, the day count of the borrow charge. The
  rate of week t is the last FRED observation dated on or before the session before the last session of week t
  (Amendment 1), so it is known after Friday close t.
- **Sharpe, three conventions** (§09, S21-5). Headline: (annualised return − rf_annual) / volatility, with rf_annual =
  (Π(1 + rf))^(52/T) − 1 over the same weeks (`period_average_rf`). Zero-cost long/short: annualised return /
  volatility. Textbook √52 · mean / std, for information only. The headline Sharpe is also reported with the
  skeleton's constant 2% (§11). The §07 gate and the shift check use the headline Sharpe with the weekly T-bill (Amendment 6 C1, S32-9).
- **Other ratios.** Sortino uses the same rf over the downside root mean square of all weeks × √52. Jensen alpha uses
  the mean weekly rf: (r̄ − rf_w − β(m̄ − rf_w)) · 52, which equals the skeleton formula for a constant rate.
- **Behaviour** (S21-6). The skeleton's signal statistics use N = 10 traded columns (9 sectors and IVV). Net and gross
  exposure and the turnover of the target weights, Σ|w_t − w_{t−1}|, are reported alongside. The charged turnover is
  the drifted-weight turnover of the engine.
- **Per period** (Amendment 2 C5). `period_metrics` computes every metric separately on the In-Sample and Out-of-Sample
  weeks of one book, with the equity rebased to 100 and the behaviour statistics restarted at the first week of each
  period.

## In-Sample evaluation, placebo and the one-week-shift check (`06_backtest.py`, `07_evaluate.py`)

- **Backtests.** `06_backtest.py --model NAME` or `--all` backtests any folder of `outputs/walkforward/` with a
  `scores.csv` (S32-1). Names may hold single inner dots, such as `M1_a0.1` (S32-9). Scores are refused if their
  `used.yaml` fails `check_used`, or if `summary.json` holds a `spec_hash` other than the one 05's spec gives under the
  current `config.yaml` (S32-10). Each backtest writes `weekly.csv`: the baseline book's returns, costs, borrow,
  turnover, residual beta, net, long and short exposure, the T-bill and the stress-scenario returns (S23-10, S32-2). No
  per-ticker series is written.
- **One-week-shift check** (§12, S32-3, S32-9). The delayed book gives week t the scores of week t − 1 and keeps the
  hedge rule, sized with week t's BETA52. Both books are compared on their common weeks at baseline costs. The verdict
  is FAIL only if the delayed book has the higher headline Sharpe and the paired block bootstrap (5,000 resamples, mean
  block 4 weeks, seed 42, T-bill Sharpe) gives P(delayed > base) ≥ `selection.bootstrap_prob` (0.80). Otherwise it is
  PASS. A FAIL is investigated, never fixed by changing a setting.
- **Placebo** (§11, S32-4). 1,000 books, book i (0-based) with standard normal sector scores drawn with seed 42 +
  1,000,000 + i, go through the same sizing, hedge, costs and engine on the scored weeks of the reference model, M0. The statistic is the
  headline net Sharpe. A model's percentile is 100 · (#{placebo < model} + ½ · #{placebo = model}) / 1,000, on the same
  weeks. Random books are redrawn every week, so they trade far more than a model. The percentile of the gross zero-cost
  Sharpe is therefore reported alongside.
- **Not trials** (S32-5). The delayed books and the placebo books get no row in `docs/trial_log.csv`. They are
  diagnostics of configurations that already have one.
- **`07_evaluate.py`** (S32-7). It reads every backtest folder, the shift checks and the placebo after `check_used`.
  It stops, writing nothing, if any weekly row is not In-Sample. SPY (never traded) and the equal-weight basket (1/9 of
  each sector's forward return, rebalanced weekly, no cost) come from the raw prices cut at the In-Sample end. It writes
  `outputs/metrics/is_models.csv` (one row per model, baseline costs, with the rank IC of `src.stats.rank_ic` and the
  placebo percentile), `is_benchmarks.csv`, `shift_check.csv`, `placebo.csv` and the plots.
- **Plots** (S32-6). Equity and drawdown points are dated by the realisation date. Each period starts at 100 on the
  execution date of its first week, on a log axis. Each rung has a fixed colour, and a fixed configuration uses its
  rung's colour, dashed. The cost bridge shows the arithmetic mean weekly return × 52 (gross, − costs, − borrow, = net),
  so the steps add up exactly. Every HTML plot has a fixed div id, so a rerun writes identical files (S39-5).
- **Two rounds** (Amendment 9, S42-2). `is_models.csv` lists round 1 (the pre-registered ladder: M0, the candidates of
  `models.candidate_order`, M0\* and the fixed names `M1_a*`, `M2_a*`, `M3_d*`, `M0_L*`) and then round 2 (M6 to M9 and
  the fixed names `M6_a*`, `M7_a*_h*`, `M8_d*_h*`) as two sections. Columns `round`, `section` and `role` (hurdle,
  candidate, fallback or fixed configuration) mark them. Any other folder name stops the evaluation. When
  `outputs/metrics/selection_gate.json` exists, it is checked as in `08_run_oos.py` (S42-1). The candidates' rows then
  carry the gate status, the pass verdict and the bootstrap threshold of their round (0.80 or 0.90). The `verdict` column
  labels round 1's selection (the first passing round-1 candidate, else M0\*) as the primary pre-registered result
  (Amendment 9 C3). Once the gate file holds round 2, it also labels the model traded under the order of both rounds.

The §07 selection gate itself is applied by `05_train_walkforward.py --select` (S37-4), not by `07_evaluate.py`.

## The Out-of-Sample run, the freeze and the rerun rule (`08_run_oos.py`)

- **The gate file** (S34-3, S42-1). `outputs/metrics/selection_gate.json` must list the candidates of
  `models.candidate_order` followed by `round2.candidate_order` (Amendment 9 C3), each `evaluated` or `absent`. Every
  evaluated row must hold its Sharpe, drawdown and P(uplift > 0), M0's Sharpe and drawdown, and the four verdicts. The
  verdicts must follow from those numbers: Sharpe ≥ M0's + 0.15, drawdown at most 2 points worse than M0's, and P ≥ 0.80
  in round 1 or ≥ 0.90 in round 2 (`round2.selection.bootstrap_prob`). Every row must share one hurdle, and `selected`
  must be the first passing candidate in the order, else M0\*. A file that lists round 1 only (the file of S37-9) is
  refused by the freeze. An evaluated round-2 candidate is refused until its Out-of-Sample refit exists (session 4.2b).
- **`--freeze`** (S34-3). It refuses, writing nothing, if the working tree is not clean (untracked files count), if
  `FROZEN.lock` or an access-log entry already exists, or if the gate file or any artefact is missing, built with
  another config, stale by `spec_hash`, or absent from the trial log. `FROZEN.lock` records the code commit, the SHA-256
  of `config.yaml` and `docs/trial_log.csv`, the trial count, the split and data end, the selected model, the models of
  the run with their spec hashes, the grid value chosen at the last In-Sample refit of each tuned rung (Amendment 6 C2),
  and the SHA-256 of every In-Sample table, `features_config.yaml`, the gate file and the walk-forward files of every
  model. Text files are hashed with CRLF read as LF. Only `FROZEN.lock` and `docs/decisions.md` (the signatures) may
  change after the freeze.
- **The run of record** (S34-4). It refuses unless the lock parses, the tree is clean, the frozen commit is an ancestor of
  HEAD, only the allowed files changed since the freeze, every recorded hash matches, and
  `outputs/oos_access_log.json` has no entry. It then writes the single log entry (time, commit, HEAD, lock hash,
  selected model, data end) before the vault is unlocked, so every access is logged even if a later step fails.
- **Tables** (S34-5, S38-1). The full-range tables are rebuilt through 03's unlock path into `data/processed/oos/`, so
  the frozen In-Sample tables stay byte-identical. The forward returns are built first, with the period boundary at
  2019-12-27, the truncation at `data.end` and the lock path. The builder itself refuses without `FROZEN.lock`. Every
  model input is read through the unlocked vault.
- **Refits** (§07, Amendment 6 C2, S34-6). The quarterly refits continue with `src.labels.walk_forward_folds`,
  extended to `data.end`, from the 2019 Q4 refit to the last week with a realised label. Every fit asserts the purge. The models are the
  selected one, every evaluated candidate, M0 and M0\* (ENS adds its members). Each tuned rung keeps its frozen grid
  value, and only its parameters are refitted. The In-Sample weeks keep their frozen scores. The 2019 Q4 refit's
  In-Sample weeks are compared with them (max |difference| and identity of the ±1 signals, tolerance 1e-12; S34-2). A
  difference is reported, not a reason to stop.
- **Books** (Amendment 2 C5, S34-7). One continuous book per model in the three cost scenarios, from prices and DGS3MO
  cut at `data.end`. Its baseline In-Sample returns are checked against the frozen `outputs/backtests/<model>/weekly.csv`.
  Outputs go under `outputs/oos/`: per model `scores.csv`, `weekly.csv`, `metrics.csv`, `summary.json` and `used.yaml`,
  plus `run.json`.
- **Rerun** (§10 step 4, Amendment 8 C1, S36-1). A rerun is allowed only after a decision with the fields `Bug`,
  `Fix commit` and `Fix files`. Before any Out-of-Sample access, `--rerun ID` checks the following: the run of record is
  logged for the current lock; no entry names the decision yet; the fix commit comes after the freeze and is an
  ancestor of HEAD; it changes exactly the Fix files; and those name no config, trial log, lock or artefact. It then
  appends one entry naming the decision and writes to `data/processed/oos_reruns/<ID>/` and `outputs/oos_reruns/<ID>/`,
  so the run of record stays untouched. `tests/test_oos_access_log.py` (CI) fails if the log holds more than one entry
  plus one per recorded rerun decision, or names a decision twice.
- **`07_evaluate.py --period OOS`** (S34-8 to S34-11, S38-2). It runs only if `FROZEN.lock` exists and the log holds
  exactly one entry for it. It writes per-period metrics, benchmarks and plots. The market-neutral tests (S34-9) are:
  the OLS beta to SPY with a Newey–West interval; the correlation; the mean in SPY-down weeks and months, with a
  stationary-bootstrap interval (block 4 weeks, or 1 month); and the mean weekly return, the share of positive rolling
  52-week windows and the return of each calendar year. The bonus is claimed only if all pass, for the selected model
  only. The secondary bonus compares the headline Sharpe and drawdown with SPY, with the Ledoit–Wolf test (S34-10). The
  DSR and PBO use the trial matrix declared by `outputs/metrics/selection_bias.json`, rebuilt from its sources and
  checked against its In-Sample values within 1e-12 (S38-2).

## Packaging (`make_submission.py`)

- **Files** (S2-3, S35-1 to S35-3). `project/` holds exactly `git ls-files` + `data/raw/**` + `data/processed/**` +
  `outputs/**`, never a walk of the folder. Assistant and tool settings files and synthetic outputs are left out and
  listed. The course requires the raw data, the processed data and the results in the zip. The raw vendor data stays out
  of the public repository only.
- **Refusals** (S35-2, S35-5). The build stops, writing nothing and listing every problem, if: a `.env` file is present;
  any file holds a key-like string (the test suite's fake sentinel aside); a tracked file has uncommitted changes;
  `README.md`, `pyproject.toml`, `uv.lock` or `config.yaml` is missing; or the presentation is not a PDF with a `%PDF-`
  header.
- **Stale outputs** (S35-3, S42-3). Every settings file is checked with `check_used` against what its writer saves under
  the current `config.yaml`, and a settings file without a known writer stops the build. The round-2 settings live in
  `round2:`, outside every `used.yaml` (S40-1). So for each round-2 model folder, the `summary.json` of its walk-forward
  folder, and of its backtest folder when that ships, must also hold the `spec_hash` that 05's spec gives under the
  current config.
- **Zip** (S35-4). Entries are sorted, deflated, dated 1980-01-01 and given mode 0644, so the same files give the same
  bytes. The slides are stored at the root as `presentation.pdf`. The manifest lists every entry's SHA-256 and size,
  the file count, the total size, and the zip's size and SHA-256.

## One-command In-Sample pipeline (`run_all.py`)

- **Steps** (S39-2). In order: `01_download_data.py` (verify only; it refuses to start without
  `data/raw/manifest.json`, so it never downloads), `03_build_features.py`, `05_train_walkforward.py` for every rung and
  fixed name of 05 (read from 05 at run time), `06_backtest.py --all`, the shift check of every rung, the placebo,
  `05 --agent-returns`, `05 --select`, `07_evaluate.py`, and last `06_backtest.py --ledger-years`. It never runs
  `04_agent_lab.py` (agent results replay from the committed caches), `08_run_oos.py`, `00_smoke_test_data.py` or
  `02_validate_data.py`.
- **Stops.** The first step that exits with a non-zero code stops the run. A table of every step (status, seconds,
  note) is printed at every stop and at the end.
- **After the freeze** (S39-3). With `FROZEN.lock` present, it runs only with `--after-freeze`, which skips
  `--agent-returns` and `--select` (their outputs are frozen).
- **Clean tree** (S39-4). In a git checkout it refuses a dirty tree, and fails if the run changed the tree. Outside one
  (the submission zip), it says that the check is skipped.
- **Identical outputs** (S39-5). Every step runs with `PYTHONHASHSEED` = `config.seed`. Two runs on one machine give
  byte-identical files under `data/processed/` and `outputs/`, except the append-only access logs. Between machines,
  reproduction is judged by tolerance and identity of the signals, never by file hashes (S34-2).
