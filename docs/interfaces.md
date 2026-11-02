# Interface contract

The single authoritative description of every boundary between modules. Together with the validators in
`src/contracts.py`, it is what Eliya's and Mattia's code is built and tested against. Every producer calls the matching
`validate_*` function on what it returns, and every consumer may call it on what it receives.

**Sources.** Formulas, names and thresholds come from `docs/preregistration.md` (tag `prereg-v1`, plus Amendment 1) through
`config.yaml`; section numbers below (§05, §06, …) are the pre-registration's. If this file and the pre-registration ever
disagree, the pre-registration governs and the disagreement is a bug in this file. "Contract n" refers to section n of this file.

**Changes.** A change to a signature, name or format below ships in the same pull request as the code that needs it,
updates `src/contracts.py` and its tests, is logged in `docs/decisions.md`, and is approved by the other owner. Nobody
adapts silently to the other side's code. Adding an optional keyword argument with a default that keeps the old
behaviour is not a contract change. Renaming, removing, reordering or retyping anything below is.

## 0. Conventions

| Item | Rule |
| --- | --- |
| Universe | From `config.yaml`, never hard-coded. `SECTORS` = `data.tickers` (XLB XLE XLF XLI XLK XLP XLU XLV XLY, in that order); `HEDGE` = `data.hedge` (IVV); `BENCHMARK` = `data.benchmark` (SPY, never traded). `TRADED` = `SECTORS + [HEDGE]` (10 columns). `TRADABLES` = `TRADED + [BENCHMARK]` (11 columns, the price tables). `src.contracts.universe()` returns them. |
| Dates | tz-naive pandas timestamps at midnight, `datetime64` dtype of any resolution. Calendar days unless "session" is said. |
| Session | A trading day of the US equity calendar: the union of the session dates of the 11 tradables (`docs/methods.md`). VIX-only holidays are not sessions. |
| Week t | One row of the weekly index: the calendar week from Monday `date_open` to Friday `date_close` (nominal labels, kept in holiday weeks). Its *last session* is Friday, or Thursday when Friday is a holiday. Its *first session* is Monday, or the next session when Monday is a holiday. |
| Known after Friday close t | A value on row t uses only information available after the close of the last session of week t: closes up to that session, and market-state values lagged one session (Amendment 1). Never an open, high or low of a later session, never a value published later. |
| `t − k w` | The value at the last session of the week k rows earlier in the weekly index. |
| Missing values | `NaN` in float frames, `NaT` in date series. No forward filling across sessions of prices; missing inputs are handled where this file says so. |
| Returns | Simple returns unless "log" is said. Rates in `daily_market` are in percent per year, as published by FRED. |
| Order | Rows sorted ascending by date, unique; columns in the universe order above. |

## 1. Daily frames

Produced by `01_download_data.py` (`data/processed/`, git-ignored) and read by `src/features.py`.

- **Prices** (`daily_open`, `daily_close`): `pd.DataFrame`, index `pd.DatetimeIndex` named `date` (sessions only,
  strictly increasing, no weekends); columns a subset of `TRADABLES` in universe order; `float64`; fully adjusted for splits
  and dividends (`src/data.py: adjust_ohlc`; the adjusted close is the total-return index TR). Values are `> 0`, or `NaN`
  before a ticker's first date only. Validator: `validate_daily_frame`.
- **Market states, daily** (`daily_market`): same index; columns `VIX`, `DGS3MO`, `DGS10`, `BAA10Y`; `float64`.
  Contract value at session s (Amendment 1): **the last observation dated on or before the session before s**. Note that
  `data/processed/daily_market.csv` as written at Gate 1 holds VIX of the *same* session and FRED values lagged one
  *calendar* day; `src/features.py` must build the one-session lag itself and test it (a Monday after a holiday uses the
  value of the session before the holiday).

## 2. Weekly index

`pd.MultiIndex` with levels `["date_open", "date_close"]`, exactly as in the course skeleton (`src/data.py: weekly_panel`):
`date_open` is a Monday, `date_close = date_open + 4 days` is the Friday of the same week, rows strictly increasing and
unique, weeks without any session dropped. Weekly prices: `weekly_open[t]` = first adjusted open of week t (`O(t)`),
`weekly_close[t]` = last adjusted close of week t (`C(t)`). Validator: `validate_weekly_index`.

## 3. Asset features (§06)

- `pd.DataFrame` with index `pd.MultiIndex` levels `["date_close", "ticker"]`: `date_close` is the Friday label of week t
  (the `date_close` level of the weekly index), `ticker` is a `str` in `SECTORS`; every `date_close` present has all 9
  sectors; sorted by `(date_close, ticker)`.
- Columns, exactly and in this order (`features.asset`): `MOM26_1`, `MOM52_4`, `REV1`, `VOL13`, `DD13`, `BETA52`;
  `float64`; no `±inf`; `NaN` only while a window is not yet full (warm-up).
- Values are known after Friday close t and **cross-sectionally z-scored** across the 9 sectors on each `date_close`:
  `z = (x − mean) / std` with the sample standard deviation (`ddof=1`); a week where every sector has the same raw value
  gets `z = 0`. This uses same-date information only.
- Raw definitions, before z-scoring (TR = adjusted close; windows end at the last session of week t, inclusive):

| Column | Definition |
| --- | --- |
| `MOM26_1` | `ln TR(t − 1w) − ln TR(t − 26w)` |
| `MOM52_4` | `ln TR(t − 4w) − ln TR(t − 52w)` |
| `REV1` | `ln TR(t) − ln TR(t − 1w)` |
| `VOL13` | sample std (`ddof=1`) of daily simple returns whose end session lies in weeks t−12 … t, × √252 (S22-1) |
| `DD13` | `TR(t) / max(daily TR over the sessions of weeks t−12 … t) − 1` |
| `BETA52` | `cov(r_i, r_SPY) / var(r_SPY)` of daily simple returns whose end session lies in weeks t−51 … t (same `ddof` in both) |

- M0\* variants (§07 fallback) use the same construction with other lookbacks: `MOM13_1`, `MOM26_1`, `MOM52_1` =
  `ln TR(t − 1w) − ln TR(t − L w)` for L in `models.M0_star.lookback_weeks`. They live in their own frame, not in the
  six-column frame above.
- Validator: `validate_features` (pass `columns=` for frames other than the six pre-registered columns).

## 4. Market states (§06, Amendments 1 and 2)

- `pd.DataFrame` indexed by the weekly index; columns exactly `BEAR24`, `MKT_VAR`, `VIX`, `TERM`, `CREDIT`
  (`features.states`); `float64`; `NaN` only in the warm-up. Common to all assets.
- Values are **unscaled**. `BEAR24` is a 0/1 indicator and is never winsorised or standardised (Amendment 2 C1). The
  continuous states `MKT_VAR`, `VIX`, `TERM`, `CREDIT` are winsorised and standardised on training rows only, inside the
  model pipeline (§06 "scaling fitted on training folds only"). `VIX_Z`, the pre-registered state, is that in-fold
  standardisation of `VIX`; it exists only inside the pipeline and never as a column of this frame (Amendment 2 C7).

| Column | Value on row t |
| --- | --- |
| `BEAR24` | `1.0` if SPY's total return over the prior 104 weeks is negative, `TR_SPY(t) / TR_SPY(t − 104w) − 1 < 0`, else `0.0` |
| `MKT_VAR` | sample variance (`ddof=1`) of daily SPY simple returns over the 126 sessions ending at the last session of week t |
| `VIX` | VIX close of the session before the last session of week t (lagged one session; Amendment 1, Amendment 2 C6) |
| `TERM` | `DGS10 − DGS3MO` (percentage points), each lagged one session |
| `CREDIT` | `BAA10Y` (percentage points), lagged one session |

- Validator: `validate_market_states` (also requires `BEAR24` in {0, 1}, a `VIX` column and no `*_Z` column).

## 5. Model inputs and interactions (§06, §07)

- Design matrix `X`: index `["date_close", "ticker"]` as in contract 3; `float64` columns.
  M0 and M0\*: one momentum column. M1: the six asset features. M2 and M3: the six asset features plus the five
  interactions below. M5: the M-rung it extends plus approved agent features (§06 "Agent-proposed features").
- Interaction columns are the product of the z-scored asset feature and the state(s), built in the model pipeline
  after in-fold scaling: `BEAR24` enters as its raw 0/1 value (Amendment 2 C1); `MKT_VAR` and `VIX_Z` (the in-fold
  standardised `VIX`, C7) enter scaled. Names are the terms joined by `_x_` (`src.contracts.interaction_name`), in
  `features.interactions` order:
  `BETA52_x_BEAR24_x_MKT_VAR` (primary), `BETA52_x_BEAR24`, `MOM26_1_x_BEAR24`, `MOM26_1_x_MKT_VAR`, `VOL13_x_VIX_Z`.
  No other interaction exists.

## 6. Labels (§05)

- `pd.DataFrame` with the feature index `["date_close", "ticker"]` (9 sectors per week) and two columns:
  - `y` (`float64`): `y[t, i] = R_fwd[t, i] − mean_j R_fwd[t, j]`, the mean over the 9 sectors (IVV and SPY excluded);
  - `label_end` (`datetime64`): the **actual session date of `O(t+2)`**, the first session of week t+2 (not the nominal
    Monday); identical for the 9 rows of a week.
- Rows exist only for weeks whose forward return is defined (the last two weeks have none).
- Invariants: `Σ_i y[t, i] = 0` within 1e-12 per week; `label_end > date_close`; `label_end ≥ realised_on` (contract 7), equal
  unless the Monday of week t+2 is a holiday.
- Purging (§05): a model fitted at cutoff c uses only rows with `label_end ≤ c − embargo` (contract 13). Every fit asserts it.
- Validator: `validate_labels`.

## 7. Forward returns, `realised_on`, `period` (§05, §10)

Three objects on the full weekly index, produced by `src/backtest.py: forward_returns` (Mattia):

| Object | Type | Definition |
| --- | --- | --- |
| `fwd` | `pd.DataFrame`, columns `TRADABLES`, `float64` | `fwd[t] = O(t+2) / O(t+1) − 1` on adjusted weekly opens (`execution.type: open_to_open`); the last two rows are `NaN` |
| `realised_on` | `pd.Series` named `realised_on`, `datetime64` | `date_open` of week t+2, as in the skeleton's `execution_dates`; `NaT` on the last two rows |
| `period` | `pd.Series` named `period`, values `"IS"`/`"OOS"` | `"IS"` if `realised_on ≤ split.in_sample_end` (2019-12-27), else `"OOS"`; missing where `realised_on` is `NaT` |

The signal of week t is executed at `O(t+1)` and its return realised at `O(t+2)` (§05). Assigning periods with
`label_end` instead of `realised_on` gives the same result. The first OOS-realised return is at the open of
Monday 2019-12-30; the last In-Sample signal week is the one ending 2019-12-13. Validator: `validate_forward_returns`.

## 8. Scores (§07, §09)

- `pd.DataFrame` indexed by the weekly index (the weeks a model scores), columns `SECTORS`, `float64`; higher means more
  attractive; `NaN` marks a missing score; no `±inf`. Missing inputs (Amendment 2 C3): after the warm-up, if any sector
  score or any required `BETA52` (9 sectors and IVV) is missing in week t, the previous week's signals and target weights
  are carried forward unchanged and the book is rebalanced to them (drift turnover still charged); the event is logged with
  the week and the missing fields. A carried week also carries the previous `hedge`, `residual_beta`, `net_exposure` and
  `cap_binds`, so `w_IVV = h / (1 + |h|)` still holds. Before the first fully valid week the book is flat.
- From a model's output: `ScoreModel.score` returns a `pd.Series` on `["date_close", "ticker"]`; unstack `ticker` and
  attach `date_open = date_close − 4 days` to obtain the weekly index.
- Validator: `validate_scores`.

## 9. Signals (§09)

- `pd.DataFrame` indexed by the weekly index, columns `TRADED` (9 sectors, then IVV), dtype `int8`, values in {−1, 0, 1}, no
  missing values.
- Sectors: sort scores descending; exact ties are broken alphabetically by ticker (the earlier ticker ranks higher); ranks 1
  to `signal.top_k` (2) get +1, the `signal.bottom_k` (2) lowest ranks get −1, the rest 0. Every row has exactly two +1 and
  two −1 among the sectors. (k = 1 and 3 are sensitivity runs only, never selected; their validator calls pass
  `top_k=k, bottom_k=k` to `validate_signals` and `k=k` to `validate_weights`; sizing per Amendment 2 C4, contract 11.)
- IVV: `sign(h)` from contract 11, 0 when the hedge is inside the dead-band (Amendment 2 C2).
- Validator: `validate_signals`.

## 10. Betas for sizing (§06, §09)

`pd.DataFrame` indexed by the weekly index, columns `TRADED`, `float64`: raw (not z-scored) `BETA52` of each sector and of
IVV against SPY, known after Friday close t, used to size the positions taken at `O(t+1)`. `NaN` in the warm-up only.
Validator: `validate_betas`.

## 11. Sizing (§09) → `SizingResult`

`src/sizing.py` (Mattia): `signals_from_scores(scores, top_k, bottom_k)` returns the sector signals;
`target_weights(sector_signals, betas, core_weight, cap, dead_band)` returns a `SizingResult`. Parameters come from
`config.yaml` (`signal.*`). With `s_i` the sector signals and `β̂` the betas of row t:

```text
β_c   = Σ_i core_weight · s_i · β̂_i                       core_weight = 0.25 (k = 2); 0.5 / k for k = 1, 3 (Amendment 2 C4)
h     = clip(−β_c / β̂_IVV, −cap, cap)                      cap = 0.5;  h = 0 if |h| / (1 + |h|) < 0.02 (Amendment 2 C2)
w_i   = core_weight · s_i / (1 + |h|)                       w_IVV = h / (1 + |h|)
β_res = (β_c + h · β̂_IVV) / (1 + |h|)                       net exposure = Σ w = h / (1 + |h|)
```

`SizingResult` (frozen dataclass in `src/contracts.py`), all on the same weekly index:

| Field | Type | Content |
| --- | --- | --- |
| `weights` | `DataFrame[TRADED]`, `float64` | target weights `w`, held from `O(t+1)` to `O(t+2)` |
| `signals` | `DataFrame[TRADED]`, `int8` | sector signals and the IVV signal `sign(h)` |
| `hedge` | `Series` `float64` | `h` before scaling |
| `residual_beta` | `Series` `float64` | `β_res`; 0 within 1e-12 unless the cap binds or the dead-band zeroes the hedge |
| `net_exposure` | `Series` `float64` | `h / (1 + \|h\|)` |
| `cap_binds` | `Series` `bool` | `\|β_c / β̂_IVV\| > cap` |

Weight invariants (`validate_weights`): `Σ|w| = 1` within 1e-12 on every row with positions (an all-zero row is flat);
`sign(w) = signal` element-wise when signals are given; the sector legs are dollar-neutral (`Σ_sectors w = 0` within
1e-12) and of equal size `core_weight · (1 − |w_IVV|)`, with `core_weight = core_weight_for(k)` (0.25 for k = 2,
`0.5 / k` in the sensitivity runs, C4); `|w_IVV| ≤ cap / (1 + cap)`; `w_IVV` is 0 or at least `signal.hedge_deadband`
(2% of capital, C2). In dead-band weeks the residual beta is `β_c`, reported with the cap weeks.

## 12. Backtest (§09) → `BacktestResult`

`src/backtest.py: run(sizing, fwd, period, cost_bps, borrow_annual) -> BacktestResult` (Mattia). The engine never computes
signals and never reads files. `cost_bps` is in basis points per dollar traded (10 → 0.0010); `borrow_annual` is a decimal
rate (0.02). Costs and borrow come from `costs.*`.

```text
gross_t    = Σ_i w_{t,i} R^fwd_{t,i}
w^pre_{t,i} = w_{t-1,i} (1 + R^fwd_{t-1,i}) / (1 + Σ_j w_{t-1,j} R^fwd_{t-1,j}),   w^pre = 0 before the first week
turnover_t = Σ_i |w_{t,i} − w^pre_{t,i}|
costs_t    = (cost_bps / 10 000) · turnover_t
borrow_t   = borrow_annual · 7/365 · Σ_{i: w_{t,i} < 0} |w_{t,i}|
net_t      = gross_t − costs_t − borrow_t                  no cash interest
```

`BacktestResult` (frozen dataclass in `src/contracts.py`; also importable from `src.backtest`). Every field is indexed by
the same weekly index: the consecutive weeks that have weights and a realised forward return for every `TRADED` column. Each
`Series` is named after its field.

| Field | Type | Content |
| --- | --- | --- |
| `weights` | `DataFrame[TRADED]`, `float64` | target weights `w_t` (passes `validate_weights`) |
| `gross` | `Series` `float64` | `gross_t` |
| `net` | `Series` `float64` | `net_t` |
| `turnover` | `Series` `float64` | `turnover_t ≥ 0` (1.0 in the first scored week, entered from cash; the OOS period continues the same book, Amendment 2 C5) |
| `costs` | `Series` `float64` | `costs_t ≥ 0` |
| `borrow` | `Series` `float64` | `borrow_t ≥ 0` |
| `residual_beta` | `Series` `float64` | from `SizingResult` |
| `net_exposure` | `Series` `float64` | from `SizingResult`; equals `Σ_i w_{t,i}` within 1e-12 |
| `hedge` | `Series` `float64` | `h` from `SizingResult`; `w_IVV = h / (1 + \|h\|)` within 1e-12 |
| `period` | `Series` of `"IS"`/`"OOS"` | from contract 7 |

Validator: `validate_backtest_result(result, cost_bps=None, borrow_annual=None, *, k=None, core_weight=None)`; with the
rates given it also checks the cost and borrow formulas within 1e-12. Sensitivity books (k = 1, 3) pass `k=k` or
`core_weight=0.5 / k` (`core_weight_for(k)`), here and in `validate_weights`; an explicit `core_weight` takes precedence. The backtest is one continuous book from the first scored week to the data
end; metrics, equity curves (rebased to 100) and behaviour statistics are computed per period (Amendment 2 C5).

## 13. Walk-forward folds (§07, §10) → `WalkForwardFold`

`src/labels.py: walk_forward_folds(weeks, label_end, cfg) -> list[WalkForwardFold]` (Eliya). `weeks` is the weekly index,
`label_end` the per-week `label_end` series on it.

- In-Sample weeks only (`realised_on ≤ in_sample_end`). Training starts at the first scored week (first `date_close` after
  `split.warmup_end`, i.e. 2003-01-03) and expands. Test folds are the calendar years `split.test_years` (2008 … 2019) by
  `date_close`; the 2019 fold ends at the last In-Sample week (2019-12-13).
- Refits are quarterly (`split.refit`): the first In-Sample week of each calendar quarter of a test year is a refit point.
  12 years × 4 quarters = 48 records, in chronological order. The test windows partition the In-Sample weeks from the first
  week of 2008 to the last In-Sample week, without gaps or overlaps.
- The model of a record is fitted after the close of `test_start` (cutoff c = `test_start`) and scores the weeks
  `test_start … test_end`.

`WalkForwardFold` (frozen dataclass in `src/contracts.py`):

| Field | Type | Meaning |
| --- | --- | --- |
| `test_year` | `int` | calendar year of the test fold |
| `refit` | `int` | quarter of the refit, 1 … 4 |
| `train_start` | `Timestamp` | `date_close` of the first training week |
| `train_end` | `Timestamp` | `date_close` of the last training week: the last week with `label_end ≤ purge_end` |
| `purge_end` | `Timestamp` | latest `label_end` allowed in training: `test_start − split.embargo_weeks × 7 days` (purge of overlapping labels plus a one-week embargo, §05) |
| `test_start` | `Timestamp` | `date_close` of the first week scored by this fit (the cutoff) |
| `test_end` | `Timestamp` | `date_close` of the last week scored by this fit |

Invariants (`validate_folds`): `train_start ≤ train_end < test_start ≤ test_end`; `purge_end = test_start − 7 days ×
embargo_weeks`; `train_end + 10 days ≤ purge_end` (the label of the last training week ends at the earliest on the
Monday of week t+2), and with `label_end` given, the exact `label_end` of the `train_end` week `≤ purge_end`;
consecutive records have `next.test_start > test_end` with no In-Sample week in between; every fit asserts
`max(label_end of its training rows) ≤ purge_end`. OOS refits (§07, "the same refits continue during OOS") are produced by
`08_run_oos.py` after the freeze with the same rule, never before.

## 14. Model protocol (§07)

```python
class ScoreModel(Protocol):          # src/contracts.py
    name: str
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ScoreModel": ...
    def score(self, X: pd.DataFrame) -> pd.Series: ...
```

- `X`: design matrix of contract 5; `y`: `float64` series named `y` on the same index, already purged by the caller (contract 13).
- `fit` returns `self`. `score` returns a `float64` series named `score` with exactly `X`'s index; higher means more
  attractive; it does not change the fitted model.
- Deterministic: seeds from `config.seed`; LightGBM with `deterministic=True`, `num_threads=1`, `seed`. No file or network
  access, no global state, no data other than the arguments. M0 implements the protocol with a no-op `fit`.

## 15. Vault (§10) and trial log

`src/vault.py` (Eliya), the only path from data to models and agents.

- `OOSAccessError(PermissionError)`: raised for any request touching a date after `is_end` (2019-12-27) while
  `FROZEN.lock` does not exist, and even then except through the explicit unlock path of `08_run_oos.py`. The refusal is
  logged.
- `Vault(is_end, lock_path=ROOT / "FROZEN.lock", log_path=ROOT / "outputs" / "vault_access_log.jsonl")`:

| Method | Returns |
| --- | --- |
| `features(as_of)` | asset features (contract 3), rows with `date_close ≤ as_of` |
| `market_states(as_of)` | market states (contract 4), rows with `date_close ≤ as_of` |
| `labels(as_of)` | labels (contract 6), rows with `label_end ≤ as_of` |
| `run_walkforward(spec)` | weekly scores (contract 8) of a model spec over the In-Sample folds (contract 13); appends one row to `docs/trial_log.csv` |

- Optional keyword arguments (S22-8; they keep the behaviour above): `Vault(..., *, data_dir=ROOT / "data" / "processed",
  frames=None, cfg=None)` reads `features.csv`, `market_states.csv`, `labels.csv` (and `momentum_variants.csv`) from
  `data_dir` unless in-memory `frames` are given; `unlock()` raises `OOSAccessError` unless `FROZEN.lock` exists and is
  called only by `08_run_oos.py`; `run_walkforward(spec, evaluate=None, *, trial_path=...)` fills `is_sharpe` and
  `is_mdd` only when an evaluator is passed (the engine, from Phase 2.3).
  A spec holds only `rung`, `feature`, `author`, `kind`, `notes`, `as_of`, `end` (other keys refused); `Vault(is_end)`
  refuses an `is_end` after `split.in_sample_end`; every failed call is logged as `refused` (S22-12).
- This access log is separate from `oos_access_log.json`, the single-entry log written only by `08_run_oos.py` (§10),
  which CI checks.
- Every call appends one JSON line to the access log (git-ignored under `outputs/`): UTC time, method, `as_of` or spec hash,
  result (`ok` or `refused`).
- `append_trial(row, path=ROOT / "docs" / "trial_log.csv")` appends one trial with the columns of `docs/data_dictionary.md`:
  `trial_id, timestamp, author, kind, rung, spec_hash, params_json, is_sharpe, is_mdd, notes`. Every configuration evaluated
  on In-Sample data, by a human or an agent, is one row; the count feeds the Deflated Sharpe Ratio (§10, §11).
- Agents reach the vault only through the MCP server `ddmi-vault` (`src/agents/vault_server.py`, protocol section 08)
  with three tools, `get_features(as_of)`, `run_walkforward(spec)` and `get_trial_history()`, which wrap the methods above,
  show sectors as anonymised codes A1 … A9 and return summary metrics, never price series.

## Resolved points

Found by the contract audit on 2 Nov 2026 and resolved by Amendment 2 to `docs/preregistration.md` (C1–C7), with decision
entries S2-8 to S2-14 in `docs/decisions.md`. The table keeps the original questions for the record.

| ID | Question | Pre-registration text | Resolution |
| --- | --- | --- | --- |
| P1 | Is the 0/1 `BEAR24` standardised in-fold? A standardised indicator is non-zero in normal weeks, so the BEAR24 interactions would be active every week. | §06: states scaled on training folds; BEAR24 is "crash insurance", H3 reports "the exact weeks it was active" | **Resolved: Amendment 2 C1** (S2-8). `BEAR24` stays 0/1; only the continuous states are scaled in-fold |
| P2 | Dead-band test: `\|h\| < 0.02` (operating manual) or hedge weight `\|h\| / (1 + \|h\|) < 0.02` ("below 2% of capital")? With the dead-band, residual beta is not exactly zero in those weeks. | §09 step 4: "0 if the hedge rounds to zero (below 2% of capital)"; "ex-ante beta is exactly zero unless the cap binds" | **Resolved: Amendment 2 C2** (S2-9). `h = 0` if `\|h\| / (1 + \|h\|) < 0.02` |
| P3 | Missing score or beta: keep last week's target weights (`w_t = w_{t−1}`), or keep the signals and re-size? Any NaN sector, or all? | §09 step 5: "last week's positions are kept and the event is logged" | **Resolved: Amendment 2 C3** (S2-10). Previous signals and target weights carried forward and rebalanced to; event logged; flat before the first valid week |
| P4 | Sensitivity k = 1 or 3: with core weight 0.25 the gross would be 0.5 or 1.5. | §09: "1 and 3 are reported as sensitivity" | **Resolved: Amendment 2 C4** (S2-11). Core weight `0.5 / k` per name |
| P5 | Does the OOS run start from cash (turnover 1.0 at 2019-12-30) or continue the In-Sample book? | §09, §10: silent | **Resolved: Amendment 2 C5** (S2-12). One continuous book; statistics per period |

## 16. Metrics and inference

- `src/metrics.py` (Mattia) implements the definitions of the course skeleton's `docs/metrics.md` on weekly return series
  (`pd.Series` on the weekly index, `float64`, P = 52): `performance(r, rf)`, `return_stats(r)`, `behaviour(signals,
  weights)`, `market(r, m, rf)` return `dict[str, float]`; ratios with a zero denominator are `NaN`.
  `tbill_weekly_returns(dgs3mo, weeks)` turns the daily FRED yield (%) into weekly returns on the weekly index, lagged one
  session (Amendment 1); `period_average_rf(rf_weekly, period)` gives the annual average per period.
- `src/stats.py` (Eliya) implements §11 inference on weekly series: `paired_block_bootstrap`, `rank_ic`,
  `deflated_sharpe_ratio`, `pbo_cscv`, `sharpe_difference_test`, and `selection_gate`, the §07 rule applied to In-Sample
  walk-forward results (Sharpe uplift ≥ `selection.sharpe_uplift`, drawdown tolerance `selection.mdd_tolerance`, bootstrap
  probability ≥ `selection.bootstrap_prob`; first passing candidate in `models.candidate_order`, else M0\*).

## 17. Where everything lives (stubs until their phase)

Every function below exists now with its signature and docstring and raises `NotImplementedError("Phase x.y, owner")`
until implemented. Dataclasses, `OOSAccessError` and the validators are real code now. The names, the data they exchange
(contracts 1 to 15) and the validator signatures are binding; a stub's exact argument list is a proposal that its owner
may refine in the phase pull request, which the other author reviews.

| Module | Public names | Phase, owner |
| --- | --- | --- |
| `src/contracts.py` | `ContractError`, `Universe`, `universe`, `interaction_name`, `interaction_columns`, `core_weight_for`, `SizingResult`, `BacktestResult`, `WalkForwardFold`, `ScoreModel`, `validate_*` | 2.0, Eliya (done) |
| `src/sizing.py` | `signals_from_scores`, `target_weights` | 2.1, Mattia |
| `src/backtest.py` | `forward_returns`, `run`, `BacktestResult` (re-export) | 2.1, Mattia |
| `src/ledger.py` | `run_ledger` | 2.1, Mattia |
| `src/metrics.py` | `performance`, `return_stats`, `behaviour`, `market`, `tbill_weekly_returns`, `period_average_rf` | 2.1, Mattia |
| `src/features.py` | `lag_one_session`, `asset_features`, `momentum_variants`, `market_states`, `sizing_betas`; helpers `weekly_index`, `last_sessions`, `raw_asset_features`, `cross_sectional_zscore` | 2.2, Eliya |
| `src/labels.py` | `make_labels`, `walk_forward_folds`; helpers `label_end_by_week`, `assert_purged` | 2.2, Eliya |
| `src/vault.py` | `OOSAccessError`, `Vault`, `append_trial` | 2.2, Eliya |
| `src/models.py` | `fit_transform_train`, `transform_test`, `M0`, helpers `fit_state_scaling`, `scale_states` (2.2); `RidgeModel`, `LightGBMModel`, `ensemble_scores`, `select_m0_star_lookback` (3.1) | Eliya |
| `src/agents/vault_server.py`, `src/agents/graph.py` | `get_features`, `run_walkforward`, `get_trial_history`; `build_graph`, `run_lab` | 3.3, Eliya |
| `src/stats.py` | `paired_block_bootstrap`, `rank_ic`, `deflated_sharpe_ratio`, `pbo_cscv`, `sharpe_difference_test`, `selection_gate` | 3.1, Eliya |
| `src/plots.py` | `equity_curves`, `drawdowns`, `exposures` (with `07_evaluate.py`) | 3.2, Mattia |

### Validators and helpers of `src/contracts.py` (exact signatures)

Every validator returns `None` and raises `ContractError` (a subclass of `ValueError`) with a message that names the object,
the rule broken and, where it applies, the first offending week and column. Arguments left at `None` are read from
`config.yaml`.

```python
class ContractError(ValueError): ...

@dataclass(frozen=True)
class Universe:                     # universe(cfg: dict | None = None) -> Universe
    sectors: tuple[str, ...]        # data.tickers
    hedge: str                      # data.hedge
    benchmark: str                  # data.benchmark
    traded: tuple[str, ...]         # sectors + (hedge,)
    tradables: tuple[str, ...]      # traded + (benchmark,)

interaction_name(terms: Sequence[str]) -> str            # ("BETA52", "BEAR24") -> "BETA52_x_BEAR24"
interaction_columns(cfg: dict | None = None) -> list[str]  # the five names, in features.interactions order

validate_weekly_index(index: pd.Index) -> None
validate_daily_frame(frame: pd.DataFrame, columns: Sequence[str] | None = None) -> None   # default columns: tradables
validate_features(features: pd.DataFrame, columns: Sequence[str] | None = None) -> None   # default: features.asset
validate_market_states(states: pd.DataFrame) -> None
validate_labels(labels: pd.DataFrame) -> None
validate_scores(scores: pd.DataFrame) -> None
validate_signals(signals: pd.DataFrame, top_k: int | None = None, bottom_k: int | None = None) -> None
validate_betas(betas: pd.DataFrame) -> None
core_weight_for(k: int | None = None, cfg: dict | None = None) -> float   # 0.25 for k = 2 (or None), 0.5 / k (Amendment 2 C4)

validate_weights(weights: pd.DataFrame, signals: pd.DataFrame | None = None, *,
                 core_weight: float | None = None, cap: float | None = None,
                 k: int | None = None, dead_band: float | None = None) -> None   # core_weight_for(k), hedge_cap, hedge_deadband
validate_forward_returns(fwd: pd.DataFrame, realised_on: pd.Series, period: pd.Series,
                         is_end: pd.Timestamp | None = None) -> None
validate_backtest_result(result: BacktestResult, cost_bps: float | None = None, borrow_annual: float | None = None,
                         *, k: int | None = None, core_weight: float | None = None) -> None   # core_weight_for(k)
validate_folds(folds: Sequence[WalkForwardFold], embargo_weeks: int | None = None,
               label_end: pd.Series | None = None) -> None   # label_end: per-week series on the weekly index
```

For `validate_daily_frame`, `columns` is the set the frame may draw from (a subset in universe order is valid). For
`validate_features`, `columns` is the exact column list. In `validate_weights` and `validate_backtest_result`, the
tolerance is 1e-12. Validators never modify their arguments.

## 18. Shared synthetic fixture (`tests/conftest.py`)

Both workstreams test against one deterministic synthetic market; CI uses nothing else (no network, no licensed data).
`make_synthetic_market(seed=42, momentum=True)` in `tests/conftest.py` builds it (deterministic, cached). The pytest fixture
`synthetic_market` returns a fresh copy of the default market for each test, and the fixture `synthetic_market_factory`
returns the `make_synthetic_market` function itself (tests use the fixtures and never import `conftest`). Both return a
`SyntheticMarket` dataclass with these fields:

| Field | Content |
| --- | --- |
| `sessions` | `DatetimeIndex` named `date`: business days from 2011-01-03 to 2020-12-31 minus US market holidays (New Year, MLK, Presidents, Good Friday, Memorial, Independence, Labor, Thanksgiving, Christmas, with weekend observance) and the 29–30 Oct 2012 closure. Spans the 2019-12-27 In-Sample end. |
| `raw` | `dict[str, DataFrame]` for the 11 tradables, in Yahoo's `auto_adjust=False` format: `Open`, `High`, `Low`, `Close` (split-adjusted), `Adj Close` (split- and dividend-adjusted), `Volume`, `Dividends` (split-adjusted, on ex-dates), `Stock Splits` (factor on the split date, else 0) |
| `unadjusted_open`, `unadjusted_close` | daily frames of the actual traded prices: no split or dividend adjustment, so the planted split halves the price |
| `daily_open`, `daily_close` | adjusted daily frames (contract 1), from `src.data.adjust_ohlc` |
| `weekly_open`, `weekly_close` | from `src.data.weekly_panel` |
| `vix` | `Series` named `VIX` on the equity sessions plus two VIX-only holiday dates, unlagged |
| `fred` | `DataFrame` with `DGS3MO`, `DGS10`, `BAA10Y` (percent) on FRED business days (no Columbus or Veterans Day values; values on Good Friday; a few missing values), unlagged |
| `split` | `(ticker, date, ratio)` of the planted split: one 2:1 split of XLK |
| `true_beta` | `dict[str, float]`: planted beta to the market factor of each ticker (SPY ≈ 1, IVV ≈ SPY) |
| `drift` | weekly frame (weekly index × `SECTORS`) of the planted expected weekly log return of each sector |
| `is_end` | `Timestamp("2019-12-27")` |

Planted effects: each sector's expected return follows a slow, persistent process, so past relative winners keep winning
(cross-sectional momentum). With `momentum=True`, the mean weekly Spearman rank correlation between 26-1 week momentum
(`ln C(t−1)/C(t−26)` on weekly closes) and `fwd` (contract 7) over the sectors is at least 0.05 with a t-statistic of at least 3;
with `momentum=False` (no drift dispersion) its absolute value is below 0.03. IVV starts two months after the other
tickers (`NaN` before), to exercise first-date handling.
