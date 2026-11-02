# Pre-registration

**Project.** Regime-aware, dollar-neutral sector momentum with a beta hedge. LUISS *Data-Driven Models for Investment*
2026–27, group 7.

**Status.** Committed on 29 October 2026, before any strategy result. At this commit, the only computations on the data
are data-quality statistics on prices (`docs/qa_report.md`). No signal, feature-versus-future-return relationship,
backtest, model fit or strategy metric has been computed. The git timestamp of this file and the annotated tag
`prereg-v1` are the proof.

**Source.** Every section below is copied verbatim from the DDMI Research Protocol v4.1, Final Edition (29 Oct 2026). The
headings carry the protocol's section numbers; nothing in a copied section has been reworded.

| Source file | SHA-256 |
| --- | --- |
| `DDMI_Research_Protocol_v4.1_Final.md` (transcription source) | `425cde245d1f061a58ddf9c3296a8f4888d0623a7bc991020ac481a834e879e3` |
| `DDMI_Research_Protocol_v4.1_Final.pdf` (approved protocol) | `69bda7b8054ecf00a11cac55775194a7debf0b1347966d554485767c919e2ccf` |
| `config.yaml` at this commit (every numeric setting below) | `be42b2fe97502203c899043823d992cbb94d9c71c29c45d77c47921025c2d8f2` |

**Contents.** Hypotheses (section 02); universe (section 04, universe table); event clock and labels (05); features and
regime interactions (06); AI ladder, grids and selection rule (07); signal rule, sizing, hedge, return formula and costs
(09); split, walk-forward validation and the OOS vault (10); benchmarks, metrics, inference and the market-neutral bonus
tests (11). Notes recorded before this commit, and the amendment policy, close the document.

## 02 · Hypotheses and mechanism

Our claim: information about sectors diffuses into prices slowly, so relative winners keep winning for months. The exception comes after bear markets, when high-beta losers rebound hardest and momentum crashes, and that risk is partly predictable in advance.

**Mechanisms and evidence \[RESEARCH\]**

| Mechanism | Evidence | What it does NOT show |
| --- | --- | --- |
| Industry momentum: slow cross-sector capital rotation | Moskowitz & Grinblatt (1999) | That it survives for SPDR ETFs, weekly execution or post-2010 costs |
| Momentum across asset classes and countries | Asness, Moskowitz & Pedersen (2013) | Profitability in our 2020–2026 window |
| Momentum crashes follow bear markets, during rebounds; losers carry high beta; crash risk is forecast ex ante by a bear-market indicator interacted with market variance | Daniel & Moskowitz (2016) | That the effect is estimable on few bear episodes in ETF data |
| Nonlinear interactions improve return forecasts | Gu, Kelly & Xiu (2020) | Transfer to a 9-asset panel |
| News predicts returns; point-in-time models extract it without training leakage | He et al. (2025); Kelly et al. (2026) | That sector-aggregated news carries the same signal (M4 dropped from this submission) |

**Falsifiable claims and their nulls**

| ID | Claim | Null and decision evidence |
| --- | --- | --- |
| H1 | M0 rule momentum earns a positive net premium | H0: no positive net premium. Estimate, interval, regime dependence |
| H2 (primary) | The selected AI candidate beats matched M0 net of costs | H0: uplift ≤ 0. Paired block bootstrap of weekly differences; rank IC |
| H3 | The pre-registered interactions, led by BETA52 × BEAR24 × MKT\_VAR, improve rankings beyond additive features | H0: M2 = M1. Ablation; report the weeks each interaction was active |
| H4 (not tested) | Point-in-time news features add ranking value | Dropped on 29 Oct for time; reported as a planned extension |
| H5 | Agent-proposed features survive the same gate as human features after trial-count deflation | H0: DSR below threshold. Every trial reported |
| H6 (bonus) | The hedged book is market-neutral OOS | H0: \|beta\| ≥ 0.10 or down-market mean ≤ 0. Bonus criteria verbatim |

These claims, the split, the benchmark, the gate and the selection rule are committed to `docs/preregistration.md` before any In-Sample strategy result is computed. Git timestamps are the proof.

**Research discipline (from v3).** We study whether an effect survives, not how to force it to appear. A negative result reached rigorously is a valid conclusion.

## 04 · Universe, data contract, licensing (universe table only)

**Universe**

| Role | Tickers | History | Caveat |
| --- | --- | --- | --- |
| Core: US sectors | XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY | Dec 1998 → | GICS changes in 2016 (real estate) and 2018 (communication services) altered holdings; XLC and XLRE excluded for history length |
| Hedge instrument | IVV (iShares Core S&P 500) | May 2000 → | Tracks the same index as SPY; carries a discrete signal and a beta-sized weight |
| Benchmark, never traded | SPY | Jan 1993 → | Skeleton rule: the benchmark is never among the traded tickers |
| Extension: countries | iShares MSCI single-country ETFs (e.g. EWA, EWC, EWG, EWJ, EWU) | Verify per ticker | Dropped from this submission on 29 Oct; planned extension |
| Risk-free | FRED DGS3MO | Daily | Stated rate for Sharpe and the market-neutral benchmark |

## 05 · Event clock and labels

Every input carries the time it became knowable. A signal uses only inputs knowable by Friday 16:00 ET and trades at the next session's open, which is the skeleton's `open_to_open` convention \[COURSE\].

1. **Friday after the close (t).** Daily closes through Friday, VIX close, FRED values released by Friday, news published before 16:00 ET. Compute features, scores, signals and hedge size. No Friday-close fill.
2. **Next session open (Monday, or Tuesday after a holiday).** Execute at O(t+1) with the cost model in section 09.
3. **Hold one week.** No mid-week revision.
4. **Following session open O(t+2).** Exit or rebalance. The week's return is realised here, and only now may it enter a training label.

Forward return earned by the signal of week t:

```latex
R^{fwd}_{t,i} = \frac{O_{t+2,i}}{O_{t+1,i}} - 1
```

Training label (relative, so models rank rather than forecast the market):

```latex
y_{t,i} = R^{fwd}_{t,i} - \frac{1}{N}\sum_{j=1}^{N} R^{fwd}_{t,j}
```

**Purging and embargo.** Each label has `label_end = O(t+2)`. A model fitted at cutoff c uses only labels with `label_end ≤ c`. At every walk-forward boundary we purge overlapping labels and embargo one extra week. A unit test asserts both on every fit.

**Text timing (M4 only).** An article stamped Friday 16:05 ET belongs to the next week; date-only articles dated Friday are shifted to the next week.

**Data cutoff.** The data snapshot ends Friday 16 October 2026 \[PROPOSAL\]; the last evaluable signal is the week of 2 October.

## 06 · Features and regime interactions

The feature set is small and fixed before any result, and every feature has a mechanism, a formula and a lag. Interactions pair an asset-level feature with a market-wide state, because only those can reorder the cross-sectional ranking.

**Why a market state alone cannot reorder a ranking.** A market state m\_t is the same number for all assets in week t. With momentum alone, the score collapses to a rescaled momentum:

```latex
s_{t,i} = \beta_1 M_{t,i} + \beta_2 M_{t,i} m_t = (\beta_1 + \beta_2 m_t)\, M_{t,i}
```

The ranking only changes if the bracket flips sign, which inverts it entirely. Interactions with a different asset-level feature, above all market beta, are what let the model reorder assets.

**Asset-level features** (cross-sectionally z-scored each Friday)

| Feature | Definition | Mechanism |
| --- | --- | --- |
| MOM26\_1 | log TR(t−1w) / TR(t−26w) | Intermediate momentum (Moskowitz–Grinblatt horizon) |
| MOM52\_4 | log TR(t−4w) / TR(t−52w) | Classic 12-1 month momentum |
| REV1 | log TR(t) / TR(t−1w) | Short-term reversal or continuation |
| VOL13 | Std of daily returns over 13 weeks × √252 | Risk and noise |
| DD13 | TR(t) / max TR over 13 weeks − 1 | Recent stress |
| BETA52 | cov(asset, SPY) / var(SPY), daily, 52 weeks | Market exposure; the crash channel |

**Market states** (common to all assets; scaling fitted on training folds only)

| State | Definition | Source |
| --- | --- | --- |
| BEAR24 | 1 if SPY's cumulative total return over the prior 24 months (104 weeks) is negative, else 0 | Daniel & Moskowitz (2016) bear-market indicator |
| MKT\_VAR | Variance of daily SPY returns over the prior 126 trading days | Daniel & Moskowitz (2016) ex-ante market variance |
| VIX\_Z | VIX level, z-scored | Forward-looking fear |
| TERM, CREDIT | 10y–3m and BAA–10y spreads | Macro risk appetite |

**Why BEAR24 and not a direct rebound measure (agreed 29 Oct).** Daniel & Moskowitz forecast momentum crashes with ex-ante variables only: a negative 24-month market return, interacted with prior market variance. Crashes occur in the rebound that follows a bear market. A direct rebound measure is only observable once the rebound is under way, so it would either lag the crash or leak future prices. BEAR24 is therefore the ex-ante state, not a rebound detector, and the documentation says so.

**Pre-registered interactions (M2), no search over others**

1. BETA52 × BEAR24 × MKT\_VAR (primary; the Daniel–Moskowitz specification moved to the cross-section)
2. BETA52 × BEAR24
3. MOM26\_1 × BEAR24
4. MOM26\_1 × MKT\_VAR
5. VOL13 × VIX\_Z

**Honest caveat.** In our scored In-Sample, BEAR24 is expected to be active mainly around 2008–2010, and possibly never in the OOS window. The term is crash insurance estimated on very few episodes. The H3 ablation reports its fitted weight and the exact weeks it was active, and no claim rests on it alone.

**Text features (M4, dropped 29 Oct; design kept for the extension).** Articles mapped to a sector are embedded with the point-in-time model whose cutoff precedes the article's year; weekly embeddings are averaged over 4 weeks and reduced by PCA fitted on training folds only. The primary text feature is a walk-forward ridge forecast from embeddings to next-week relative return.

**Agent-proposed features (M5).** Expressible in the same feature DSL, lagged inputs only, and must pass the leakage tests before entering the ladder.

**Constraints (from v3).** Scaling and winsorising fitted inside each training fold; no same-week open, high or low in Friday features; a 104-week warm-up applied identically to every model.

## 07 · AI ladder and the selection rule

Each rung adds one idea to the rung below, on identical dates, costs and execution, so every uplift is attributable. One pre-registered rule picks the traded model: the simplest candidate that clears the gate.

| Rung | Model | Adds | Fixed grid |
| --- | --- | --- | --- |
| M0 | Rank on MOM26\_1 | The mechanism, no AI — the hurdle | none |
| M1 | Ridge on 6 asset features | Additive multi-feature ranking | λ ∈ {0.1, 1, 10} |
| M2 | M1 + 5 pre-registered interactions | Regime-conditional rankings (H3) | λ ∈ {0.1, 1, 10} |
| M3 | LightGBM on M2 inputs | Nonlinearity | depth ∈ {2, 3}; 200 trees; learning rate 0.03; fixed seed; deterministic; 1 thread |
| M4 (dropped 29 Oct) | Best of M2/M3 + point-in-time text | NLP (H4) | PCA dims ∈ {8, 16} |
| M5 | Best rung + approved agent features | Research-lab output (H5) | Inherited; agent trials counted |
| ENS | Equal-weight average of the cross-sectional rank scores of M1–M3 (+ M5 if it exists) | Combination | none |
| M0\* (fallback) | M0 with lookback chosen at each refit from {13, 26, 52} weeks by walk-forward In-Sample Sharpe | Optimisation method | {13, 26, 52} |

**Training schedule.** Expanding window, refit quarterly, labels purged and embargoed. The same refits continue during OOS on newly realised labels; tuning does not. The slides say so explicitly.

**Selection algorithm (single, pre-registered)**

1. Hurdle: M0, scored on the same In-Sample walk-forward test folds.
2. Candidates, in order of complexity: M1, M2, M3, M5, ENS.
3. Gate, applied to each candidate's walk-forward In-Sample results: net Sharpe ≥ M0 + 0.15; max drawdown at most 2 percentage points worse than M0; paired block bootstrap P(uplift > 0) ≥ 0.80. These thresholds are governance rules, not proof of superiority.
4. The first candidate in that order to pass all three is traded.
5. If none passes, M0\* is traded, so the trading system still contains an optimisation method. The report states plainly that the ML models failed to beat the baseline.
6. Every candidate, eligible or not, appears in the OOS scorecard.

**Considered and excluded**

| Model family | Reason |
| --- | --- |
| Time-series foundation models (Chronos, TimesFM, Moirai, Kronos) | Pre-trained on market data overlapping our OOS window; no point-in-time vintages |
| Modern LLMs as traders (TradingAgents-style) | Memorise historical financial data, and masking fails (Lopez-Lira et al., 2025); advantages fade over 20 years (FINSABER) |
| Fin-R1, Trading-R1 | Same leakage; usable only in a live forward log |
| FinBERT | Fine-tuning data dates from our In-Sample period; robustness check only, with leakage stated |

## 09 · Signals, sizing, costs, return formula

Each Friday every asset gets one discrete signal from a fixed rank rule. A dollar-neutral core holds the sector bets, an IVV hedge leg cancels the core's estimated beta, and the whole book is scaled to 100% gross with no leverage.

**Signal rule (exact, for the slides)**

1. Score every sector ETF with the traded model (section 07).
2. Sort descending; break exact ties alphabetically by ticker.
3. Ranks 1–2 → **+1**; the two lowest ranks → **−1**; all others → **0**. The count of 2 is pre-registered; 1 and 3 are reported as sensitivity, never selected.
4. Hedge signal: IVV gets −1 if the core's estimated beta is positive, +1 if negative, and 0 if the hedge rounds to zero (below 2% of capital).
5. If a required input is missing, last week's positions are kept and the event is logged.

**Sizing**

Core weights are 0.25 × signal, so the core is dollar-neutral: 50% long, 50% short. Core beta uses BETA52 from prior data only. The hedge weight cancels it, capped at 50% of core gross:

```latex
\beta_c = \sum_i 0.25\, s_i \hat\beta_i, \qquad h = \operatorname{clip}\!\left(-\frac{\beta_c}{\hat\beta_{IVV}},\, -0.5,\, 0.5\right)
```

All weights are then divided by (1 + |h|), so total gross exposure is exactly 100%:

```latex
w_i = \frac{0.25\, s_i}{1+|h|}, \qquad w_{IVV} = \frac{h}{1+|h|}, \qquad \beta_{residual} = \frac{\beta_c + h\,\hat\beta_{IVV}}{1+|h|}
```

Ex-ante beta is exactly zero unless the cap binds; when it binds, the residual beta is reported that week. Net dollar exposure, h/(1 + |h|), is reported weekly too. This fixes the v4 flaw where a 30–70% leg cap could leave a large residual beta.

**Return formula \[COURSE\].** Per asset, the return is R^fwd when the signal is +1, zero when 0, and −R^fwd when −1. The book sums them with the sizing weights, including IVV:

```latex
r_t = \sum_i w_{t,i} R^{fwd}_{t,i} \; - \; c \sum_i \left| w_{t,i} - w^{pre}_{t,i} \right| \; - \; b\, \frac{7}{365} \sum_{i:\, w_{t,i}<0} |w_{t,i}|
```

**Turnover from drifted weights.** Before each rebalance, last week's weights have moved with prices:

```latex
w^{pre}_{t,i} = \frac{w_{t-1,i}\,(1 + R^{fwd}_{t-1,i})}{1 + \sum_j w_{t-1,j} R^{fwd}_{t-1,j}}
```

**No cash interest.** The primary return credits no interest on cash or short collateral, because broker terms vary and we cannot verify them. Adjusted series already include dividends, so a short pays them once. Sharpe is reported two ways: the skeleton convention, (annual return − rf) / volatility, which is conservative here and is the headline; and the zero-cost long/short convention, annual return / volatility. The choice is stated on the results slide.

**Cost scenarios \[PROPOSAL, not broker quotes\]**

| Scenario | Trading cost per $ traded | Short borrow, annual |
| --- | --- | --- |
| Optimistic | 5 bps | 1% |
| Baseline (reported) | 10 bps | 2% |
| Adverse | 20 bps | 5% |

**Ledger reconciliation.** An independent position-and-cash ledger (shares, raw opens, dividend cash flows, splits, IVV) runs on three In-Sample years. Without costs it must match the vectorised engine within 1e-6 per week.

**Using it ourselves.** EU retail investors generally cannot buy US-listed ETFs (PRIIPs rules), and shorting needs margin or CFDs. A personal version would map to UCITS sector ETFs and is out of scope.

## 10 · Sample split, validation, single OOS run

In-Sample runs through Friday 27 December 2019 and Out-of-Sample from 2020 onward: about 6.8 years, roughly 29% of the scored sample. OOS contains the COVID crash and rebound, the 2022 bear market, the 2023–24 rally and the 2025 tariff shock; In-Sample contains 2008–09, 2011, 2015–16 and late 2018 \[PROPOSAL, agreed\].

| Period | Dates | Allowed |
| --- | --- | --- |
| Warm-up | Dec 1998 – Dec 2002 | Feature windows only (104-week BEAR24, 52-week beta); no scoring |
| In-Sample, walk-forward | Jan 2003 – 27 Dec 2019 | Initial training 2003–2007; 12 expanding yearly test folds 2008–2019, purged + 1-week embargo; all selection and tuning |
| Out-of-Sample | 30 Dec 2019 – data end (16 Oct 2026) | One run of the frozen system; scheduled quarterly refits allowed, tuning forbidden |

A week belongs to OOS when its return is realised after the In-Sample end date, as in the skeleton.

**Validation hierarchy (agreed with Mattia)**

1. **Primary: chronological expanding walk-forward.** Every gate decision in section 07 is computed on the 12 yearly test folds, each scored only by a model trained on earlier data.
2. **Auxiliary: PBO by CSCV.** Run on the In-Sample weekly return matrix of every candidate configuration (rungs × grid values × agent candidates), split into 16 blocks. It estimates how likely our selection process is to pick an overfit winner. It is a diagnostic, not a validation scheme, and it never chooses the model.
3. **Auxiliary: Deflated Sharpe Ratio** with N = every human and agent trial in the ledger.

**OOS vault protocol**

1. Until Gate 3, `src/vault.py` refuses to return any label or metric dated after the In-Sample end; a unit test proves it.
2. Freeze: `FROZEN.lock` records the config hash, code commit, trial-log hash and model artefacts; all five members sign it in `docs/decisions.md`.
3. One command, `run_oos.py`, checks the lock, runs once, and appends a timestamped entry to `oos_access_log.json`. CI fails if the log ever has more than one entry.
4. A bug found afterwards is fixed in a new commit and rerun, and both runs are shown with the reason. No retuning, ever.

**Hindsight disclosure (from v3).** We know what happened in 2020–2026. The vault prevents algorithmic leakage, not human knowledge of history; the slides say so.

## 11 · Benchmarks, metrics, inference, bonus tests

For a hedged, dollar-neutral book the honest benchmark is cash (the 3-month T-bill), as Vitale's lecture states, and the honest AI hurdle is matched M0. SPY and the equal-weight basket are context only; all benchmarks are fixed before the backtest runs.

| Comparator | Question it answers | Role |
| --- | --- | --- |
| 3-month T-bill | Does the book beat cash at its risk? | Primary benchmark |
| M0 rule momentum, matched | Does the AI add anything? | Primary AI hurdle (H2) |
| Equal-weight sector basket | How different is it from owning the universe? | Context (skeleton's "Equal weight") |
| SPY total return | How exposed is the book to the market? | Context; bonus reference; never traded |
| 1,000 random ±2/±2 portfolios with the same hedge rule, fixed seeds | How much is luck? | Placebo (skeleton's random baseline) |

**Metrics.** Every definition in the skeleton's `docs/metrics.md`, computed separately for In-Sample and OOS: cumulative and annualised return, volatility, Sharpe (both conventions, section 09), Sortino, max drawdown, Calmar, hit rate, average gain and loss, profit factor on weekly returns, best and worst week, skew, kurtosis, exposures, turnover, holding period, beta, correlation, alpha, tracking error, information ratio, up- and down-market means. Added: rank IC; a gross → after-costs → after-borrow bridge; weekly residual beta and net dollar exposure; rolling 52-week Sharpe and beta; regime cuts (bull/bear, high/low VIX, rising/falling rates, crisis windows).

**Risk-free rate.** Weekly FRED 3-month T-bill (time-varying), with its period average stated on the results slide; the skeleton's constant 2% is shown alongside for comparability.

**Equity curves.** Every series starts at 100 in each period, on a shared dated axis, log scale.

**Inference (pre-registered; one procedure each)**

| Test | Procedure | Answers | Status |
| --- | --- | --- | --- |
| Uplift vs M0 | Paired stationary block bootstrap, 5,000 resamples, 4-week mean block (8-week sensitivity) | H2 interval and P(uplift > 0) | Primary |
| Ranking skill | Weekly Spearman rank IC, HAC-adjusted mean | Model quality independent of sizing | Primary |
| Sharpe difference vs SPY | Ledoit–Wolf (2008) HAC test | Secondary bonus significance | Secondary |
| Selection bias | Deflated Sharpe Ratio, N = all human and agent trials | Is the winner more than the luckiest of N? | Auxiliary |
| Selection-process overfitting | PBO by CSCV, 16 blocks | Probability the In-Sample winner falls below the median | Auxiliary diagnostic |

**Bonus: market-neutral (primary target), thresholds fixed now**

1. OOS beta of the full book (including IVV) to SPY: |β| < 0.10, with a 95% HAC interval containing 0;
2. OOS correlation with SPY: |ρ| < 0.20;
3. Mean weekly return in SPY-down weeks > 0, with a bootstrap interval; the same for down months;
4. Consistency over time, as the bonus text asks for "consistent relevant returns over time": OOS mean weekly return > 0, plus the share of rolling 52-week windows with a positive return and the return in each calendar year of the OOS, all reported.

The alternative bonus (higher Sharpe and lower max drawdown than SPY, with a significance test) is reported as a secondary result. Only one bonus point exists, and we claim at most one.

## Notes recorded before this commit

These clarify, and do not change, the protocol. They are logged with their reasons in `docs/decisions.md`.

1. **OOS boundary (G1-3).** D5's "2020-01-01" in the decision sheet is shorthand for the boundary of section 10:
   `in_sample_end: 2019-12-27`, and each return is assigned to In-Sample or Out-of-Sample by its realisation date, as in
   the skeleton. The first OOS-realised return is at the open of Monday 30 Dec 2019.
2. **Script numbering (G1-2).** `04_text_signals.py` was removed (M4 dropped on 29 Oct), and the scripts were renumbered:
   `run_oos.py` became `08_run_oos.py`.
3. **Settings.** Every number above is also set in `config.yaml`, which the scripts read. If the two ever disagree,
   this document governs and the disagreement is a bug.

## Amendment policy

This document is append-only. A later change to anything pre-registered above is added at the end, as a dated amendment
that states what changes, why, who proposed and approved it, and whether any In-Sample or Out-of-Sample result had already
been seen. The text above is never edited in place. Each amendment is also logged in `docs/decisions.md`, and after Gate 4
(the single OOS run) no strategy change is allowed (protocol section 15).

## Amendments

Amendment 1 (2 Nov 2026): clarification of §04/§05. All market-state series (^VIX, DGS3MO, DGS10, BAA10Y) enter features
lagged one equity session. Reason: VIX settles after the 16:00 ET decision time; FRED values publish after the close. No
feature has been computed before this amendment. Proposed by Eliya; approved by Eliya and Mattia on 2 Nov 2026. No
In-Sample or Out-of-Sample result had been seen.

Amendment 2 (2 Nov 2026): clarifications before feature, signal and sizing code.
Proposed by Eliya Allam; approved by Mattia Cervelli through the review of this pull request.
No feature, score, signal, sizing or backtest result had been computed when it was committed.

C1 (§06, indicator state). BEAR24 is an indicator and is used as 0/1 everywhere. It is never winsorised or standardised. The in-fold winsorising and standardisation in §06 apply only to the continuous market states MKT_VAR, VIX, TERM and CREDIT. Reason: the pre-registered interactions BETA52 × BEAR24 and BETA52 × BEAR24 × MKT_VAR are meant to act only in the bear state (Daniel & Moskowitz, 2016); a standardised indicator would make them non-zero outside it.

C2 (§09 step 4, hedge dead-band). "Below 2% of capital" refers to the final IVV weight: if |h| / (1 + |h|) < 0.02, then h = 0 and the IVV signal is 0. Any shorthand "|h| < 0.02" in team notes is superseded by this wording.

C3 (§09 step 5, missing inputs). After the warm-up, if any sector score or any required BETA52 (9 sectors and IVV) is missing in week t, the previous week's signals and target weights are carried forward unchanged and the book is rebalanced to those same targets; turnover from drift is therefore still charged. The event is logged with the week and the missing fields. Before the first fully valid week, the book is flat.

C4 (§09 step 3, sensitivity counts). In the k = 1 and k = 3 sensitivity runs, each selected long or short name receives core weight 0.5 / k, keeping the core dollar-neutral with gross exposure 1 before hedge scaling; k = 2 gives the pre-registered 0.25.

C5 (§10–§11, period boundary). The backtest is one continuous book from the first scored week to the data end. The OOS period does not restart from cash: its first trade is costed from the drifted In-Sample positions. Metrics, equity curves (rebased to 100) and behaviour statistics (turnover, holding periods) are computed separately for each period, following the course skeleton.

C6 (§05 step 1 vs Amendment 1). Amendment 1 supersedes §05 step 1 for ^VIX, DGS3MO, DGS10 and BAA10Y: in features dated Friday t, these series enter at their previous-session value, not their Friday value.

C7 (§06, naming). The weekly market-state frame stores the lagged VIX level in a column named VIX. VIX_Z denotes its in-fold standardisation inside the model pipeline and is used in the interaction VOL13 × VIX_Z.

Amendment 3 (2 Nov 2026): accounting corrections found by the independent ledger. Proposed by Mattia Cervelli; approved by Eliya Allam through the review of this pull request. No feature, score, signal or strategy result had been computed when it was committed; the engine had been run only on synthetic hand cases and the synthetic test market, and on seeded random weight books for In-Sample years 2005, 2012, 2016 and 2018.

C1 (§09 ledger, Level B). The engine uses dividend-adjusted opens, whose adjustment factor references the previous close; a cash ledger books dividends on the ex-date. Level B therefore passes if, every week, |ledger return − engine return − dividend-reinvestment term| ≤ 1e-6, where the term is computed from the dividend series and prices as documented in docs/methods.md. Measured on the In-Sample years 2005, 2012, 2016 and 2018 (10 seeded random weight books per year, no strategy signal; 2,090 book-weeks; zero cost): raw max weekly difference 5.86e-5, mean 1.46e-6; remainder max 5.11e-7. Level A (same price basis, no costs) keeps the 1e-6 tolerance unchanged.

C2 (§09 return formula). Drifted pre-trade weights divide by the book's value after costs and borrow: w_pre[t] = w[t−1]·(1+R_fwd[t−1]) / (1 + r_net[t−1]). The pre-registered denominator 1 + Σ w·R_fwd omitted costs and borrow; the difference was at most 2.31e-6 per week (mean 1.355e-6) against the shares-and-cash ledger at 10 bps and 2% borrow, on the same books. With the corrected formula the difference is at most 4.4e-16 on the same books and in all three cost scenarios.

Amendment 4 (2 Nov 2026): clarification of §06 (winsorising level).
Proposed by Eliya Allam; approved by Mattia Cervelli through the review of the pull request from branch
feat/2.2-features-m0. First committed as "Amendment 3, C8" (commit 80d822c), before any feature or model code existed
and before any feature had been computed. Renumbered as Amendment 4, C1, because the ledger corrections of pull request
#5 entered main first as Amendment 3 (decision S22-13); the clause text is unchanged. When it was renumbered, the
In-Sample features, market states, sizing betas and momentum variants had been built (weeks 1998-12-04 to 2019-12-27,
data/checksums_features.json); no label file, model score, signal, sizing or strategy result had been computed on real
data, and no Out-of-Sample value had been computed or seen.

C1 (§06, in-fold winsorising and standardisation). In each training fold, each continuous market state (MKT_VAR, VIX,
TERM and CREDIT; Amendment 2 C1) is winsorised at the 1st and 99th percentiles of its values over the distinct training
weeks (one value per week), then standardised with the mean and the sample standard deviation of the winsorised
training values. The same bounds, mean and standard deviation are applied unchanged to the weeks the fold scores. The
level is set in `config.yaml` as `features.winsor_quantiles: [0.01, 0.99]`. Reason: §06 requires "Scaling and winsorising
fitted inside each training fold" but states no level, which the implementation would otherwise choose.
