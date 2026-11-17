# Presentation outline — 10 slides / 600 seconds

Final structure of `presentation.pdf`, after the office hour of 13 November 2026 (recorded in `docs/decisions.md`,
Teaching-team check): the presentation focuses on **what we did and why**, and explains the results, above all why trading
costs were the problem and how round 2 cut them. Every figure comes from `docs/decisions.md` (S37-9, S42-7, S44-3,
S45-2) and the plots in `outputs/plots/`.

## Slide 1 — Hypothesis (45 seconds)

Do sector winners keep winning, after costs, without market risk? Nine Select Sector SPDR ETFs, weekly, 2003–2026;
dollar-neutral long/short with an IVV beta hedge; the goal is a rigorous framework, not beating the market. [prereg §02]

## Slide 2 — Data and quality (45 seconds)

Adjusted daily prices (Yahoo), VIX, FRED rates and credit spread, 1998–2026; QA gates, checksums, the 2016 and 2018 GICS
composition breaks; the second-source cross-check. Figure: QA gate table from `docs/qa_report.md`. [protocol §04]

## Slide 3 — How the strategy works (60 seconds)

The weekly five steps: score, rank, buy 2 / short 2 (+1/−1/0), hedge, hold. Execution: decide after Friday's close, trade at
the next open, earn the return to the following open; market states lagged one session; 10 bps per trade, 2% borrow, no
cash interest. "The models differ only in the score." [prereg §05, §09]

## Slide 4 — Validation framework (75 seconds)

Pre-registration and 9 dated amendments → walk-forward (12 yearly folds, 48 quarterly refits, 624 test weeks, purge plus
1-week embargo) → mechanical gate → freeze signed by all five (FROZEN.lock, 72 trials, 43 artefacts) → one Out-of-Sample
run, enforced by an access log in CI. [prereg §07, §10; S45-2]

## Slide 5 — The model ladder and the selection rule (75 seconds)

M0 to M9 in one sentence each, why each rung was chosen, the parameters optimised (ridge λ, tree depth, smoothing half-life,
M0\* lookback) and how (per refit, on the last 104 training weeks). Gate: Sharpe ≥ M0 + 0.15, drawdown ≤ 2 points worse,
bootstrap P ≥ 0.80 (0.90 in round 2). [prereg §07; Amendments 5, 9]

## Slide 6 — The multi-agent research lab (60 seconds)

Hypothesis → Coder → Validator → Skeptic/Risk → human approval; IS-only vault; planted-signal safety test. Round 1: 0 of 40
proposals survived. Round 2: the planted signal was vetoed by the turnover check on slow M7, and the rule was not changed
after the fact. [prereg §08; S33-19, S43-9]

## Slide 7 — In-Sample result and diagnosis (75 seconds)

No candidate passed; M0\* traded. Diagnosis: costs, not missing signal (M2 +0.12 Sharpe before costs, −0.99 after, at 1.12
turnover a week; placebo: M0 at the 100th percentile after costs, 22nd before). Figure: Gate 3 scorecard
(`docs/gate_scorecard.md`). [S37-9, S32-4]

## Slide 8 — Round 2: cutting the cost, and why (60 seconds)

Why we cut costs and how: a 4-week target, score smoothing, learning to rank (M6, M7, M8); turnover down 73%, net Sharpe up
from −0.99 to −0.65; still no positive edge before costs; disclosed as Amendment 9, stricter threshold, counted in the
deflated Sharpe. Figure: In-Sample equity of round 2 (`outputs/plots/round2_models_equity.png`). [Amendment 9; S42-7, S44-3]

## Slide 9 — Out-of-Sample results (75 seconds)

M0\* −3.9% a year (Sharpe −0.77, drawdown −42.5%) against SPY +15.4% (Sharpe 0.66); market-neutral (beta −0.04). The
explanation: the same cost structure In-Sample and Out-of-Sample (gross about −0.5%, costs 2%, borrow 1%), no overfitting
decay (In-Sample Sharpe −0.63). Figures: `outputs/plots/oos_M0_star_equity.png` and the two M0\* bridge plots. [S45-2]

## Slide 10 — Conclusion, weaknesses, contributions and AI tools (30 seconds)

What worked (the framework, the hedge, the diagnosis); what did not (no edge after costs); weaknesses (nine assets, weekly
noise, cost-sensitive design, the round-2 turnover check); the five pitfalls and their controls; contribution statement and
AI tools in one line each. [protocol §16]

## Coverage matrix

| Course requirement | Slide |
| --- | --- |
| Hypothesis | 1 |
| Data and processing | 2 |
| Methodology: model choice, parameters optimised and how, exact −1/0/+1 logic and thresholds | 3, 5 |
| Execution timing, costs, sizing, leverage | 3 |
| In-Sample / Out-of-Sample split, walk-forward, single OOS use | 4 |
| Results and equity curves, with benchmark and risk-free rate | 7, 8, 9 |
| Pitfalls: overfitting, look-ahead, survivorship, data snooping, pretrained-model leakage | 4, 6, 10 (backup slide in full) |
| Conclusion: what worked, what did not, weaknesses | 10 |
| Contribution statement and AI tools | 10 |

## Backup slides for Q&A

Every model Out-of-Sample (table); cost bridges of every model; the market-neutral bonus tests; the pitfall-to-control
table; M0\* drawdown; In-Sample equity of round 1; the deflated Sharpe ratio and PBO.