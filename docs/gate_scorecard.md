# Gate 3 selection scorecard

This scorecard applies the pre-registered governance rule to matched In-Sample walk-forward results. [prereg §07]

## Gate tests

1. Net Sharpe must be at least the M0 net Sharpe plus `0.15`. [prereg §07]
2. Maximum drawdown may be no more than `2` percentage points worse than M0. [prereg §07]
3. The paired stationary block bootstrap probability of uplift greater than zero must be at least `0.80`, using `5,000` resamples and block length `4` weeks; report the pre-registered `8`-week block-length sensitivity. [prereg §07; protocol §11]

These are governance rules for selecting one pre-registered candidate; they are not proof of superiority. [prereg §07; protocol §11]

## Candidate scorecard

All cells remain blank until the candidate has been scored on the same In-Sample weeks, costs and inference procedure as M0. [prereg §07, §10]

| Candidate | Net Sharpe | Sharpe test | MDD | MDD test | P(uplift > 0) | Bootstrap test | Overall |
|---|---:|---|---:|---|---:|---|---|
| M0 | `TBD` | `Reference` | `TBD` | `Reference` | `—` | `Reference` | `TBD` |
| M1 | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| M2 | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| M3 | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| M5 | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |
| ENS | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |

## Selection procedure

1. Score M0 on the 12 yearly In-Sample walk-forward test folds. [prereg §07, §10]
2. Score candidates in this fixed order: M1, M2, M3, M5, ENS. [prereg §07]
3. For every candidate, compare net Sharpe, maximum drawdown and paired weekly uplift against the matched M0 result using the three tests above. [prereg §07; protocol §11]
4. Mark a candidate eligible only when all three tests pass. [prereg §07]
5. Select the first eligible candidate in the fixed order; do not choose by inspecting OOS results. [prereg §07, §10]
6. If none is eligible, trade M0*, whose lookback is selected walk-forward from `{13, 26, 52}` weeks. [prereg §07]
7. Record the winner and the applied rule in `docs/decisions.md`; every candidate remains in the OOS scorecard. [prereg §07, §10]

## Gate 3 freeze checklist

- [ ] All candidates were scored on the same weeks and costs. [prereg §07, §10]
- [ ] The trial log is complete, including human and agent trials. [prereg §08, §10]
- [ ] No OOS label, return, metric or plot was accessed before the lock. [prereg §10; interfaces, contract 15]
- [ ] The selection rule was applied mechanically in the registered order. [prereg §07]
- [ ] The winner was recorded in `docs/decisions.md`. [prereg §10]
- [ ] `FROZEN.lock` records the config hash, code commit, trial-log hash and model artefacts, and all five members sign it in `docs/decisions.md`. [prereg §10]

Signatures at Gate 3:

| Member | Signature | Date |
|---|---|---|
| Eliya | ____________________ | __________ |
| Simone | ____________________ | __________ |
| Chiara | ____________________ | __________ |
| Mattia | ____________________ | __________ |
| Giuseppe | ____________________ | __________ |
