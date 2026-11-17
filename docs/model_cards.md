# Model cards

All models use the same weekly decision clock, universe, labels, walk-forward folds, execution rule and baseline cost assumptions. In-Sample figures come from the walk-forward backtests (624 test weeks, 2008-01-04 to 2019-12-13; `docs/decisions.md` S37-9, S42-7, S44-3) and Out-of-Sample figures from the single run of record (355 weeks, first return realised 2019-12-30, data to 2026-10-16; S45-2). All figures are net of baseline costs (10 bps per trade, 2% a year borrow), with the headline Sharpe ratio using the weekly T-bill rate (Amendment 6 C1). P(uplift > 0) is the paired block bootstrap against M0 used by the gate (5,000 resamples, block 4). [prereg §05, §07, §09, §10]

## M0 — momentum hurdle

### Purpose and mechanism

M0 is the transparent momentum hurdle: relative sector winners are expected to keep winning because information diffuses slowly and capital rotates across industries. Precisely, M0 ranks sectors by `MOM26_1` and uses that score for the cross-sectional ranking. [prereg §02, §07]

### Inputs

`MOM26_1` is `ln TR(t−1w) − ln TR(t−26w)`, computed from adjusted-close total-return data and cross-sectionally z-scored on each Friday. No market-state input is used. [prereg §06; interfaces, contract 3]

### Preprocessing

The asset input is cross-sectionally z-scored using the nine sectors on each Friday. There are no model interactions and no fitted market-state transformation in M0. [prereg §06; interfaces, contract 3]

### Model and fixed grid

The model is a rank on `MOM26_1`; its fixed grid is empty. [prereg §07]

### Training schedule

M0 is scored on the same 12 yearly In-Sample test folds used for the candidates. The walk-forward process uses an expanding history, quarterly refits, purging and a one-week embargo; M0 itself has no fitted parameters. [prereg §07, §10; interfaces, contract 13]

### Role in selection

M0 is the hurdle against which every candidate is compared and is not itself in the candidate order. [prereg §07]

### Leakage controls and determinism

The signal is computed after Friday’s close and executed at the next session’s open; labels are available only after their realised forward return and fitted rows satisfy the purge and embargo rule. The fixed feature construction and tie-break rule are deterministic. [prereg §05, §09, §10; interfaces, contract 6, contract 13]

### Known limitations

M0 uses one momentum horizon, so it does not model other asset characteristics or regime interactions. Any weakness is assessed on the matched net-of-cost walk-forward results. [prereg §06, §07, §11]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −0.7714 | −47.98% | 0.40 | Reference | — | — | — |
| Out-of-Sample | −0.7662 | −42.50% | 0.39 | — | −0.1053 | −3.91% | −0.037 |

M0 is the hurdle, not a candidate. Its Out-of-Sample book is identical to M0\*'s, because M0\*'s frozen lookback is 26 weeks (S45-2).

## M1 — ridge multi-feature ranking

### Purpose and mechanism

M1 tests whether additive information beyond intermediate momentum improves the ranking. Precisely, it fits a ridge model to the six pre-registered asset features and scores each sector by the fitted relative-return model. [prereg §02, §07]

### Inputs

`MOM26_1`, `MOM52_4`, `REV1`, `VOL13`, `DD13` and `BETA52`. Their definitions are, respectively, intermediate momentum; 12–1 month momentum; one-week reversal/continuation; 13-week annualised daily-return volatility; 13-week drawdown; and 52-week daily beta to SPY. [prereg §06; interfaces, contract 3]

### Preprocessing

All six asset features are cross-sectionally z-scored on each Friday. In-fold winsorising and scaling are fitted on training data only; M1 has no interactions. [prereg §06, §07]

### Model and fixed grid

Ridge regression is evaluated with `λ ∈ {0.1, 1, 10}`. [prereg §07]

### Training schedule

Expanding training windows, quarterly refits, purged labels, a one-week embargo, and 12 yearly In-Sample test folds from 2008 through 2019 are used. [prereg §07, §10]

### Role in selection

M1 is the first candidate in the order `M1 → M2 → M3 → M5 → ENS`. It passes only if all three pre-registered gate tests pass. [prereg §07]

### Leakage controls and determinism

Training rows are restricted by `label_end` and the purge/embargo cutoff; scaling and winsorising are fitted within each training fold. The model grid and seed are fixed before scoring. [prereg §05, §06, §07, §10]

### Known limitations

An additive ridge model may miss nonlinear or regime-conditional effects, and `BETA52` is estimated from a finite rolling history. [prereg §06, §07]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −1.2856 | −58.46% | 1.19 | 0.100 | — | — | — |
| Out-of-Sample | −1.1740 | −40.12% | 1.21 | — | +0.0907 | −6.45% | +0.028 |

Gate (round 1): fails all three tests (S37-9). Frozen grid value λ = 10.

## M2 — ridge with pre-registered interactions

### Purpose and mechanism

M2 tests whether market regimes change the cross-sectional ordering rather than merely rescaling momentum. Precisely, it extends M1 with five fixed products between asset features and lagged market states. [prereg §06, §07]

### Inputs

M2 uses the six M1 asset features plus the five interactions `BETA52_x_BEAR24_x_MKT_VAR`, `BETA52_x_BEAR24`, `MOM26_1_x_BEAR24`, `MOM26_1_x_MKT_VAR` and `VOL13_x_VIX_Z`. The interactions use only `BEAR24`, `MKT_VAR` and `VIX_Z`; `TERM` and `CREDIT` enter no interaction. Their source observations are lagged one equity session. The stored market-state column is named `VIX`; `VIX_Z` is its in-fold standardisation inside the pipeline, and the states are not additional standalone M2 design columns. [prereg §06; Amendment 2 C1, C7; interfaces, contract 4–5]

### Preprocessing

Asset features are cross-sectionally z-scored. In-fold winsorising and standardisation apply only to the continuous market states `MKT_VAR`, `VIX`, `TERM` and `CREDIT`; `BEAR24` stays 0/1 and is never scaled. Interactions are built after that transformation. [prereg §06; Amendment 2 C1; interfaces, contract 4–5, open point P1]

### Model and fixed grid

Ridge regression is evaluated with `λ ∈ {0.1, 1, 10}`. No other interaction is searched. [prereg §06, §07]

### Training schedule

Expanding training windows, quarterly refits, purging and a one-week embargo are applied across the 12 yearly In-Sample test folds from 2008 through 2019. [prereg §07, §10]

### Role in selection

M2 is the second candidate in the order `M1 → M2 → M3 → M5 → ENS`; it also provides the pre-registered interaction test for H3. [prereg §02, §07]

### Leakage controls and determinism

Only timestamp-valid inputs and labels passing the cutoff are used. Market-state transformations and interactions are fit within folds, the interaction list and ridge grid are fixed, and the random state is fixed. [prereg §05, §06, §07, §10]

### Known limitations

`BEAR24` is expected to be active mainly around 2008–2010 and possibly never in OOS, so the primary crash interaction is estimated from few episodes. [prereg §06]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −0.9865 | −49.11% | 1.12 | 0.267 | — | — | — |
| Out-of-Sample | −1.3773 | −51.70% | 1.12 | — | −0.1799 | −7.94% | +0.020 |

Gate (round 1): passes the drawdown test only (S37-9). In-Sample it earned a headline Sharpe of +0.12 before costs and −0.99 after, at 1.12 turnover a week: the cost diagnosis behind round 2 (Amendment 9). Frozen grid value λ = 1.

## M3 — deterministic LightGBM

### Purpose and mechanism

M3 tests nonlinear combinations of the M2 inputs. Precisely, it fits LightGBM on the M2 design matrix: six asset features plus the five regime interactions. [prereg §06, §07; interfaces, contract 5]

### Inputs

M3 uses the M2 design: `MOM26_1`, `MOM52_4`, `REV1`, `VOL13`, `DD13`, `BETA52`, and the five named M2 interactions. The market states used inside those interactions are lagged one equity session. [prereg §06; Amendment 1; interfaces, contract 4–5]

### Preprocessing

Asset features are cross-sectionally z-scored. In-fold winsorising and standardisation apply only to continuous market states; `BEAR24` stays 0/1 and is never scaled. Interactions are constructed after that transformation. [prereg §06; Amendment 2 C1; interfaces, contract 3–5]

### Model and fixed grid

LightGBM uses depth `{2, 3}`, 200 trees, learning rate `0.03`, a fixed seed, deterministic execution and one thread. [prereg §07]

### Training schedule

The expanding, quarterly-refit, purged and one-week-embargo schedule is evaluated on the 12 yearly In-Sample folds from 2008 through 2019. [prereg §07, §10]

### Role in selection

M3 is the third candidate in the pre-registered candidate order. [prereg §07]

### Leakage controls and determinism

Label-end cutoffs, in-fold preprocessing, fixed hyperparameters, fixed seed, deterministic LightGBM, one thread and no file/network access in the model protocol constrain leakage and nondeterminism. [prereg §05, §06, §07; interfaces, contract 13–14]

### Known limitations

The model has nonlinear capacity but a small nine-sector cross-section, and regime interactions involving `BEAR24` have sparse activation. [prereg §06, §07]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −1.4169 | −61.34% | 1.19 | 0.028 | — | — | — |
| Out-of-Sample | −1.1943 | −46.97% | 1.19 | — | +0.0061 | −6.91% | +0.052 |

Gate (round 1): fails all three tests (S37-9). Frozen grid value: depth 3.

## M5 — best rung plus approved agent features

### Purpose and mechanism

M5 tests whether human-approved features proposed through the bounded research lab add value to the best preceding rung. Precisely, it extends the selected best rung with approved DSL features that use lagged inputs only. [prereg §06, §08]

### Inputs

M5 inherits the inputs of the best preceding rung and adds only approved agent features that are expressible in the feature DSL and pass leakage tests. No feature survived the lab, so M5 has no added features and is absent (S33-19). [prereg §06, §08]

### Preprocessing

Inherited asset features use cross-sectional z-scores; market states are lagged one session, in-fold winsorising and standardisation apply only to continuous states, and `BEAR24` stays 0/1 and is never scaled; added features follow the same lag and fold-fitting controls. [prereg §06, Amendment 1, Amendment 2 C1]

### Model and fixed grid

M5 inherits the fixed grid of the rung it extends. Agent proposals are bounded at approximately 40 candidates with a hard USD 5 lab budget; every trial is logged and counted. [prereg §07, §08]

### Training schedule

The model follows the same expanding quarterly refits, purging, one-week embargo and 12 yearly In-Sample test folds. [prereg §07, §10]

### Role in selection

M5 is the fourth candidate in the order `M1 → M2 → M3 → M5 → ENS`. [prereg §07]

### Leakage controls and determinism

The vault refuses OOS labels and metrics before the lock; agents see anonymised In-Sample summaries, never raw price series; proposals, accepted or rejected, are trial-counted and cached for replay. [prereg §08, §10]

### Known limitations

Agent background knowledge cannot be eliminated; it is disclosed, bounded to In-Sample access, and counted in DSR/PBO. Approval remains a human decision. [prereg §08, §10]

### Results

M5 is **absent**. The round-1 lab (DeepSeek, USD 0.16) proposed 40 features: 24 invalid, 4 redundant, 12 failed the Validator or the reviewers, 0 survived, so no feature reached the human gate (S33-19). Every proposal is a row of the trial log and counts in the deflated Sharpe ratio.

## ENS — equal-weight rank ensemble

### Purpose and mechanism

ENS tests whether combining model rankings is more robust than choosing one score. Precisely, it averages the cross-sectional rank scores of M1–M3, plus M5 if M5 exists. [prereg §07]

### Inputs

ENS consumes the rank scores produced by M1, M2 and M3, and M5 if it exists; it does not introduce a new raw feature set. [prereg §07]

### Preprocessing

Each component follows its own pre-registered in-fold preprocessing and interactions; ENS averages their cross-sectional rank scores with equal weights. [prereg §06, §07]

### Model and fixed grid

The ensemble has no additional grid. [prereg §07]

### Training schedule

Its component scores come from the same expanding quarterly walk-forward schedule, purged labels, one-week embargo and 12 yearly In-Sample folds. [prereg §07, §10]

### Role in selection

ENS is the fifth and final candidate in the pre-registered order. [prereg §07]

### Leakage controls and determinism

Only scores generated under the component models’ fold cutoffs are combined; the component order and equal weights are fixed. [prereg §07, §10]

### Known limitations

Equal weighting can dilute a genuinely stronger component and inherits the estimation limitations of its components. [prereg §07]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −1.1917 | −58.21% | 1.24 | 0.131 | — | — | — |
| Out-of-Sample | −1.5286 | −50.81% | 1.26 | — | −0.1609 | −8.43% | +0.063 |

Gate (round 1): fails all three tests (S37-9). ENS averages the ranks of M1, M2 and M3, since M5 is absent (Amendment 7 C3).

## M0* — optimised momentum fallback

### Purpose and mechanism

M0* preserves the transparent momentum mechanism while adding a walk-forward choice of lookback, so the system still contains an optimisation method if no AI candidate clears the gate. Precisely, it chooses among `MOM13_1`, `MOM26_1` and `MOM52_1` at each refit using In-Sample walk-forward Sharpe. [prereg §07; interfaces, contract 3]

### Inputs

The variants are `MOM13_1 = ln TR(t−1w) − ln TR(t−13w)`, `MOM26_1 = ln TR(t−1w) − ln TR(t−26w)` and `MOM52_1 = ln TR(t−1w) − ln TR(t−52w)`. [interfaces, contract 3]

### Preprocessing

Each momentum variant uses the same cross-sectional z-scoring and warm-up discipline as the asset features. No market-state interaction is added. [prereg §06, §07; interfaces, contract 3]

### Model and fixed grid

The fixed lookback grid is `{13, 26, 52}` weeks, selected by walk-forward In-Sample Sharpe at each refit. [prereg §07]

### Training schedule

The lookback choice is made within the expanding quarterly walk-forward schedule with purging, a one-week embargo and the 12 yearly In-Sample folds. [prereg §07, §10]

### Role in selection

M0* is the fallback traded when no candidate in `M1 → M2 → M3 → M5 → ENS → M6 → M7 → M8 → M9` passes its gate (Amendment 9 C3). [prereg §07]

### Leakage controls and determinism

Only earlier In-Sample information is eligible for each lookback choice; OOS is frozen and run once after the lock. The candidate grid and tie handling are fixed. [prereg §07, §10]

### Known limitations

M0* can adapt the horizon but cannot use the additional asset features, interactions or nonlinear structure of later rungs. [prereg §06, §07]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −0.6339 | −40.05% | 0.40 | — | — | — | — |
| Out-of-Sample | −0.7662 | −42.50% | 0.39 | — | −0.1053 | −3.91% | −0.037 |

**Traded model** (S37-9, S44-3): no candidate of either round passed its gate. Frozen lookback: 26 weeks (chosen at the last In-Sample refit). Out-of-Sample against SPY: SPY returned 15.43% a year (Sharpe 0.6625, maximum drawdown −31.79%); M0\* returned −3.91% a year (volatility 9.01%), from 100 to 76.15; costs took 2.01% a year and borrow 1.02%. Market-neutrality tests: beta −0.037 and correlation −0.078 pass; mean return in SPY's down weeks −0.09% a week fails, so no bonus is claimed. Deflated Sharpe ratio (N = 72 trials): 1.96e-5 In-Sample, 0.0046 Out-of-Sample; PBO 0.459 (S44-3, S45-2).

## M6 — ridge on the 4-week target (round 2)

### Purpose and mechanism

Round 2 (Amendment 9) responds to the round-1 diagnosis that trading costs, not missing signal, sank the candidates. M6 keeps M2's inputs but trains on a smoother target, the 4-week excess return, so its scores change more slowly. [Amendment 9 C1]

### Inputs

M2's inputs: the six asset features, the market states and the five pre-registered interactions. Label `y4 = R4 − mean`, with `R4 = O(t+5)/O(t+1) − 1` and `label_end` at the session of `O(t+5)`. [Amendment 9 C1]

### Preprocessing

As M2: in-fold winsorising and standardisation of the continuous market states; BEAR24 stays 0/1. [Amendment 2 C1, Amendment 4 C1]

### Model and fixed grid

Ridge regression, λ ∈ {0.1, 1, 10}, chosen at each refit on the last 104 weeks of the training window (Amendment 5 C1); ties go to the larger λ. Every grid value was also run fixed as a trial. Frozen value: λ = 10. [Amendment 9 C1]

### Training schedule

Round 1's 48 quarterly refits and 624 test weeks; each fit is purged by the 4-week `label_end`. [Amendment 9 C1; S41-2]

### Role in selection

First round-2 candidate; round-2 candidates need P(uplift > 0) ≥ 0.90. [Amendment 9 C3]

### Leakage controls and determinism

Purge on the 4-week `label_end`, asserted on every fit; the same vault and determinism controls as round 1. [S41-2]

### Known limitations

A longer target smooths scores but does not by itself cut turnover enough; M6 still traded 0.76 of the book a week. [S42-7]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −0.9651 | −47.04% | 0.76 | 0.263 | −0.0314 | — | — |
| Out-of-Sample | −0.9002 | −40.08% | 0.76 | — | +0.0524 | −4.47% | +0.019 |

Gate (round 2): passes the drawdown test only (S44-3).

## M7 — M6 with score smoothing (round 2)

### Purpose and mechanism

M7 adds exponential smoothing of past scores to M6, so the ranking changes only when evidence accumulates, cutting turnover directly. [Amendment 9 C1]

### Inputs

As M6, plus its own lagged scores. [Amendment 9 C1]

### Preprocessing

As M6. Smoothing weights 2^(−k/H), k = 0…3H, over scores already known at t. [Amendment 9 C1]

### Model and fixed grid

Ridge; grid λ ∈ {0.1, 1, 10} × half-life H ∈ {2, 4} weeks, chosen per refit (λ decides first, then H; ties to the larger λ and larger H). Frozen value: λ = 10, H = 2. [Amendment 9 C1; S41-7]

### Training schedule

As M6. [S41-2]

### Role in selection

Second round-2 candidate, and the base rung of the round-2 agent lab. [Amendment 9 C2, C3]

### Leakage controls and determinism

As M6; the smoothing uses only scores known at t, including across the In-Sample/Out-of-Sample boundary (tested in S42-8). [S42-8]

### Known limitations

The closest candidate: it missed the Sharpe bar by 0.031 and the bootstrap test (P 0.635 against 0.90). Its slow book also made the lab's relative turnover check veto any informative feature (S43-7). [S44-3]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −0.6527 | −36.66% | 0.30 | 0.635 | −0.1251 | — | — |
| Out-of-Sample | −0.7802 | −30.92% | 0.34 | — | −0.0520 | −3.17% | +0.016 |

Gate (round 2): passes the drawdown test only (S44-3).

## M8 — LightGBM LambdaRank on the 4-week target (round 2)

### Purpose and mechanism

M8 learns the weekly ranking directly (learning to rank) on M2's inputs and the 4-week target, with the same score smoothing as M7. [Amendment 9 C1]

### Inputs

As M6. Relevance = the within-week rank 0–8 of the 4-week return; linear gain over 9 positions. [Amendment 9 C1]

### Preprocessing

As M6. [Amendment 9 C1]

### Model and fixed grid

LightGBM LambdaRank, 200 trees, learning rate 0.03, deterministic, one thread; depth ∈ {2, 3} × H ∈ {2, 4}, chosen per refit (depth decides first; ties to the smaller depth and larger H). Frozen value: depth 3, H = 4. [Amendment 9 C1; S41-7]

### Training schedule

As M6. [S41-2]

### Role in selection

Third round-2 candidate. [Amendment 9 C3]

### Leakage controls and determinism

As M6; LightGBM with `deterministic=True`, one thread and a fixed seed. [Amendment 9 C1]

### Known limitations

Low turnover, but its gross ranking signal was negative In-Sample. The one-week shift check gave a slightly higher delayed Sharpe (+0.059, P 0.729, a PASS under S32-3), reported as such (S42-6). [S42-7]

### Results

| Period | Net Sharpe | Max drawdown | Turnover / week | P(uplift > 0) vs M0 | Gross Sharpe (no costs) | Return / year | Beta to SPY |
|---|---:|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | −0.8236 | −49.83% | 0.30 | 0.436 | −0.3074 | — | — |
| Out-of-Sample | −0.8692 | −26.97% | 0.28 | — | −0.1513 | −3.62% | +0.015 |

Gate (round 2): passes the drawdown test only (S44-3).

## M9 — M7 plus approved agent features (round 2)

M9 = M7 plus the agent features Eliya and Mattia approve by name (Amendment 9 C2). The round-2 lab used the round-2 lab model recorded in S43-1, chosen as the most capable model of its provider available at run time. Before touching real data, the lab must pass the planted-signal test. Attempt 5 **failed**: the planted feature passed the Validator (uplift +0.79, P 0.997) and the Skeptic, but Risk's turnover check vetoed it (ratio 1.63 against the 1.5 limit), because M7's book is so slow. The failure was predicted offline in S43-7 before the live run. Changing the check after seeing it fail was refused. So the lab never read real data, and **M9 is absent** (S43-9). Round-2 lab spend: USD 1.39 of the USD 10 budget.

## M4 — dropped extension

M4 was dropped on 29 October 2026 and is documented as a planned extension, not part of this submission. [prereg §07; protocol §00, §02]