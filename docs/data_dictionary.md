# Data dictionary

Dates are ISO (`YYYY-MM-DD`), trading days of the US equity calendar unless stated. Prices are in USD per share. Weekly
tables are indexed by (`date_open`, `date_close`) = (Monday, Friday) of each week. Files under `data/raw/` and
`data/processed/` are local only (licensed data): see `docs/licensing.md`.

## Raw data (`data/raw/`, written by `01_download_data.py`)

| File | Rows | Columns |
| --- | --- | --- |
| `yahoo/<TICKER>.csv` for XLB XLE XLF XLI XLK XLP XLU XLV XLY IVV SPY | one per session of the ticker | `Date`, `Open`, `High`, `Low`, `Close` (split-adjusted), `Adj Close` (split- and dividend-adjusted), `Volume` (shares), `Dividends` (per share, on the ex-date), `Stock Splits` (factor on the split date, 0 otherwise), `Capital Gains` (per share, when reported) |
| `yahoo/VIX.csv` (^VIX) | one per day with a VIX value | same columns without `Capital Gains`; `Volume` is 0; `Adj Close` equals `Close` |
| `fred/<SERIES>.csv` for DGS3MO DGS10 BAA10Y | one per FRED business day (missing values empty) | `Date`, the series in percent per year: 3-month Treasury constant maturity, 10-year Treasury constant maturity, Moody's BAA corporate yield minus 10-year Treasury |
| `stooq/<TICKER>.csv` | not available in this snapshot | `Date`, `Open`, `High`, `Low`, `Close`, `Volume` |
| `manifest.json` | one entry per file | `source`, `call` or `url`, `fetched_utc`, `rows`, `first_date`, `last_date`, `bytes`, `sha256` (and `response_sha256`, `response_rows`, `kept` for FRED); `unavailable` lists the sources that could not be fetched, with the reason |
| `config.yaml` | | the data settings used (`check_used`) |

## Processed data (`data/processed/`, written by `01_download_data.py`)

| File | Rows | Columns |
| --- | --- | --- |
| `daily_open.csv`, `daily_high.csv`, `daily_low.csv`, `daily_close.csv` | one per equity session | the 11 tradables; fully adjusted prices (`docs/methods.md`); empty before a ticker's first date |
| `daily_market.csv` | one per equity session | `VIX` (close of the same session), `DGS3MO`, `DGS10`, `BAA10Y` (last value observed at least one day before the session) |
| `weekly_open.csv` | one per week | the 11 tradables: first adjusted open of the week |
| `weekly_close.csv` | one per week | the 11 tradables: last adjusted close of the week |
| `config.yaml` | | the data settings used (`check_used`) |

## Committed data

| File | Content |
| --- | --- |
| `data/checksums.json` | `raw`: the manifest (hashes and metadata of every raw file, no data); `processed`: rows, date range, columns, size and SHA-256 of every processed file |
| `data/qa/gates.csv` | gate, status (PASS, FAIL, NOT RUN), detail |
| `data/qa/calendar.csv` | per ticker: rows, first and last date, missing sessions, dates outside the equity calendar, weekend dates |
| `data/qa/raw_file_order.csv` | per raw file: duplicated, out-of-order and weekend dates |
| `data/qa/vix_only_dates.csv` | dates with a VIX value but no equity session |
| `data/qa/stale_sessions.csv` | sessions flagged as possibly forward-filled (repeated OHLC or zero volume), with the window (warm-up or scored) |
| `data/qa/big_moves_close.csv`, `big_moves_open.csv` | adjusted daily close-to-close or open-to-open returns above 10% in absolute value: date, ticker, return, SPY's return the same day, the second source's return (empty when unavailable) |
| `data/qa/corporate_action_windows.csv` | returns within two sessions of every Yahoo split factor: adjusted and Yahoo close-to-close and open-to-open, SPY, second source |
| `data/qa/reconciliation.csv` | per ticker: distribution events, total log adjustment versus sum of log distribution factors, largest errors, annual adjusted-minus-raw return gap, implied distribution yield |
| `data/qa/coverage.csv` | per ticker: first and last date, start of its scored window, sessions, missing opens and closes |
| `data/qa/weekly_counts.csv` | weeks in the panel, scored weeks In-Sample and Out-of-Sample |
| `data/qa/second_source.csv` | returns of Yahoo and the second source on the sampled dates (written only when the second source is available) |

## Documents

| File | Content |
| --- | --- |
| `docs/trial_log.csv` | one row per trial, human or agent: `trial_id`, `timestamp` (UTC), `author`, `kind` (`human` or `agent`), `rung`, `spec_hash`, `params_json`, `is_sharpe`, `is_mdd` (In-Sample walk-forward), `notes` |
