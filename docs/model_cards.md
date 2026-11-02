# Model cards

All models use the same weekly decision clock, universe, labels, walk-forward folds, execution rule and baseline cost assumptions. Results are intentionally blank until the relevant gate has run. [prereg §05, §07, §09, §10]

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

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

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

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

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

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

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

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

## M5 — best rung plus approved agent features

### Purpose and mechanism

M5 tests whether human-approved features proposed through the bounded research lab add value to the best preceding rung. Precisely, it extends the selected best rung with approved DSL features that use lagged inputs only. [prereg §06, §08]

### Inputs

M5 inherits the inputs of the best preceding rung and adds only approved agent features that are expressible in the feature DSL and pass leakage tests. The exact final feature names are `TBD (Gate 3)` because no trial result is recorded in this template. [prereg §06, §08]

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

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

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

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

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

M0* is the fallback traded when no candidate in `M1 → M2 → M3 → M5 → ENS` passes every gate test. [prereg §07]

### Leakage controls and determinism

Only earlier In-Sample information is eligible for each lookback choice; OOS is frozen and run once after the lock. The candidate grid and tie handling are fixed. [prereg §07, §10]

### Known limitations

M0* can adapt the horizon but cannot use the additional asset features, interactions or nonlinear structure of later rungs. [prereg §06, §07]

### Results

| Period | Net Sharpe (skeleton convention) | Net Sharpe (zero-cost convention) | Max drawdown | P(uplift > 0) | Rank IC | DSR |
|---|---:|---:|---:|---:|---:|---:|
| In-Sample walk-forward | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` | `TBD (Gate 3)` |
| OOS | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` | `TBD (Gate 4)` |

## M4 — dropped extension

M4 was dropped on 29 October 2026 and is documented as a planned extension, not part of this submission. [prereg §07; protocol §00, §02]
