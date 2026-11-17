# Gate 3 selection scorecard

This scorecard applies the pre-registered governance rule to matched In-Sample walk-forward results. [prereg §07; Amendment 9 C3]

Source of every figure: `outputs/metrics/selection_gate.json` and `docs/decisions.md` S37-9 (round 1) and S44-3 (both rounds). All candidates were scored on the same 624 test weeks (2008-01-04 to 2019-12-13), at baseline costs (10 bps per trade, 2% a year borrow), with the headline Sharpe ratio using the weekly T-bill rate (Amendment 6 C1).

## Gate tests

1. Net Sharpe must be at least the M0 net Sharpe plus `0.15`. [prereg §07]
2. Maximum drawdown may be no more than `2` percentage points worse than M0. [prereg §07]
3. The paired stationary block bootstrap probability of uplift greater than zero must be at least `0.80` for round-1 candidates and `0.90` for round-2 candidates, using `5,000` resamples and block length `4` weeks; the pre-registered `8`-week block-length sensitivity is reported. [prereg §07; Amendment 9 C3; protocol §11]

These are governance rules for selecting one pre-registered candidate; they are not proof of superiority. [prereg §07; protocol §11]

**Hurdle (M0):** net Sharpe −0.7714, maximum drawdown −47.98%. **Bars:** Sharpe ≥ −0.6214; drawdown no worse than −49.98%.

## Candidate scorecard

### Round 1 (primary pre-registered result; P ≥ 0.80)

| Candidate | Net Sharpe | Sharpe test | MDD | MDD test | P(uplift > 0), block 4 | Block 8 (sensitivity) | Bootstrap test | Overall |
|---|---:|---|---:|---|---:|---:|---|---|
| M0 | −0.7714 | Reference | −47.98% | Reference | — | — | Reference | Hurdle |
| M1 | −1.2856 | Fail | −58.46% | Fail | 0.100 | 0.095 | Fail | Fail |
| M2 | −0.9865 | Fail | −49.11% | Pass | 0.267 | 0.268 | Fail | Fail |
| M3 | −1.4169 | Fail | −61.34% | Fail | 0.028 | 0.024 | Fail | Fail |
| M5 | Absent | — | — | — | — | — | — | Absent: no agent feature survived the lab (S33-19) |
| ENS | −1.1917 | Fail | −58.21% | Fail | 0.131 | 0.137 | Fail | Fail |

### Round 2 (Amendment 9; P ≥ 0.90)

| Candidate | Net Sharpe | Sharpe test | MDD | MDD test | P(uplift > 0), block 4 | Block 8 (sensitivity) | Bootstrap test | Overall |
|---|---:|---|---:|---|---:|---:|---|---|
| M6 | −0.9651 | Fail | −47.04% | Pass | 0.263 | 0.281 | Fail | Fail |
| M7 | −0.6527 | Fail (0.031 below the bar) | −36.66% | Pass | 0.635 | 0.637 | Fail | Fail |
| M8 | −0.8236 | Fail | −49.83% | Pass | 0.436 | 0.438 | Fail | Fail |
| M9 | Absent | — | — | — | — | — | — | Absent: the round-2 planted-signal test failed, so the lab never read real data (S43-9) |

**Result:** no candidate of either round passed its gate, so the fallback **M0\*** is traded (In-Sample net Sharpe −0.6339, maximum drawdown −40.05%; lookback chosen walk-forward from {13, 26, 52} weeks, 26 weeks at the last refit). Round 1's verdict, M0\*, is the primary pre-registered result. [S37-9, S44-3]

## Selection procedure

1. Score M0 on the 12 yearly In-Sample walk-forward test folds. [prereg §07, §10]
2. Score candidates in this fixed order: M1, M2, M3, M5, ENS, then M6, M7, M8, M9. [prereg §07; Amendment 9 C3]
3. For every candidate, compare net Sharpe, maximum drawdown and paired weekly uplift against the matched M0 result using the three tests above. [prereg §07; protocol §11]
4. Mark a candidate eligible only when all three tests pass. [prereg §07]
5. Select the first eligible candidate in the fixed order; do not choose by inspecting OOS results. [prereg §07, §10]
6. If none is eligible, trade M0\*, whose lookback is selected walk-forward from `{13, 26, 52}` weeks. [prereg §07]
7. Record the winner and the applied rule in `docs/decisions.md`; every candidate remains in the OOS scorecard. [prereg §07, §10]

## Gate 3 freeze checklist

- [x] All candidates were scored on the same weeks and costs. [prereg §07, §10; S44-3]
- [x] The trial log is complete, including human and agent trials (72 rows: 32 human, 40 agent). [prereg §08, §10; S44-2]
- [x] No OOS label, return, metric or plot was accessed before the lock. [prereg §10; interfaces, contract 15; S45-1, S45-2]
- [x] The selection rule was applied mechanically in the registered order. [prereg §07; S44-1]
- [x] The winner was recorded in `docs/decisions.md`. [prereg §10; S37-9, S44-3]
- [x] `FROZEN.lock` records the config hash, code commit (`9931631450e8`), trial-log hash and 43 model artefacts, and all five members signed it. [prereg §10; S45-2]

Signatures at Gate 3 (each a comment by full name on [PR #30](https://github.com/IIxoskeletonII/Data-Driven-Models-For-Investment-Project/pull/30); recorded in S45-2):

| Member | Signature | Date |
|---|---|---|
| Eliya Allam | "I, Eliya Allam, sign the Gate 3 freeze." | 11 Nov 2026 |
| Chiara Baldoni | "I, Chiara Baldoni, sign the Gate 3 freeze." | 11 Nov 2026 |
| Simone Cavallaro | "I, Simone Cavallaro, sign the Gate 3 freeze." | 11 Nov 2026 |
| Giuseppe Catrambone | "I, Giuseppe Catrambone, sign the Gate 3 freeze." | 11 Nov 2026 |
| Mattia Cervelli | "I, Mattia Cervelli, sign the Gate 3 freeze." | 12 Nov 2026 |
