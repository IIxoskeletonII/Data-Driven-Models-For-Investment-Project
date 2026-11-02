# Presentation outline — 10 slides / 600 seconds

All result values in the deck must come from committed outputs. Until the relevant gate has run, result labels are placeholders. [protocol §16; instructions, Presentation]

## Slide 1 — Hypothesis (45 seconds)

Headline: Sector momentum may persist because capital rotates slowly, but bear-market rebounds can make momentum crash. [prereg §02]

- Introduce the nine sector ETFs, IVV hedge and SPY context benchmark. [prereg §04]
- State the primary claim and the nulls for momentum and AI uplift. [prereg §02]
- Explain why regime-aware ranking is economically motivated. [prereg §02, §06]
- Flag that the study is retrospective evidence, not a live track record. [protocol §00, §10]

Figure/table: universe-and-hypothesis schematic; source table from `config.yaml` and `docs/preregistration.md` (no computed results). [prereg §04]

Presenter: `[owner placeholder]`. Course requirement: introduction/hypothesis. [instructions, Presentation]

## Slide 2 — Data and quality (50 seconds)

Headline: A fixed ETF universe, adjusted prices and lagged macro states provide a long weekly panel. [prereg §04, §06]

- Use adjusted OHLC data, VIX and FRED DGS3MO, DGS10 and BAA10Y. [prereg §04]
- Show warm-up through 2002, In-Sample through 27 December 2019 and OOS from 30 December 2019 to the data end. [prereg §10]
- Explain total-return adjustment, split/dividend QA and licensing boundaries. [protocol §04, §12]
- State that market states enter lagged one equity session. [Amendment 1; interfaces, contract 1, contract 4]

Figure/table: coverage, missingness and adjustment QA table from `02_validate_data.py` and `docs/qa_report.md`; no strategy results. [protocol §04, §12]

Presenter: `[owner placeholder]`. Course requirement: data and processing. [instructions, Presentation]

## Slide 3 — Information clock and validation boundary (45 seconds)

Headline: Friday-close information is executed at the next session open and evaluated at the following session open. [prereg §05]

- Decision after Friday close; execute at `O(t+1)`; realise `O(t+2)`. [prereg §05]
- Define the relative label and `label_end`. [prereg §05]
- Explain purging and the one-week embargo at every walk-forward boundary. [prereg §05, §10]
- Separate In-Sample selection from the single frozen OOS run. [prereg §10]

Figure/table: event-clock timeline and fold diagram from `05_train_walkforward.py` and `docs/interfaces.md`; no OOS result values. [interfaces, contract 6, contract 13]

Presenter: `[owner placeholder]`. Course requirement: execution timing and no lookahead. [instructions, Evaluation Framework]

## Slide 4 — System architecture and research lab (60 seconds)

Headline: The deterministic trading system is separated from the bounded agent lab by an In-Sample-only vault. [protocol §03, §08]

- Show data, features, labels, model ladder, signals, sizing, backtest and evaluation. [protocol §03]
- Show agent proposal, validator, skeptic, risk and human approval roles. [protocol §08]
- Explain the three information categories and what is audited versus disclosed. [protocol §08]
- State that agents never trade and never receive raw price series. [protocol §08]

Figure/table: architecture flow from `run_all.py`, `04_agent_lab.py` and vault access logs; exact candidate counts and costs only after committed lab outputs. [protocol §08]

Presenter: `[owner placeholder]`. Course requirement: methodology and pretrained-model leakage defence. [instructions, Evaluation Framework]

## Slide 5 — AI ladder and selection rule (80 seconds)

Headline: Each rung adds one pre-registered idea, and the simplest candidate clearing all three gates is selected. [prereg §07]

- Explain M0, M1, M2, M3, M5, ENS and fallback M0*. [prereg §07]
- State the fixed ridge grid, LightGBM grid and deterministic settings. [prereg §07]
- Explain expanding quarterly refits, 12 yearly test folds, purging and embargo. [prereg §07, §10]
- State the candidate order and the fallback rule. [prereg §07]
- Explain that the gate is governance, not proof. [prereg §07]

Figure/table: ladder table and Gate 3 scorecard from `05_train_walkforward.py`, `07_evaluate.py` and `docs/gate_scorecard.md`; values are `TBD (Gate 3)` until freeze. [prereg §07]

Presenter: `[owner placeholder]`. Course requirement: why the model/AI technique, optimisation and methodology. [instructions, Presentation]

## Slide 6 — Signals, sizing and costs (50 seconds)

Headline: The strategy selects the top two and bottom two sectors, then uses a capped IVV beta hedge with 100% gross exposure. [prereg §09]

- Sort scores descending and break exact ties alphabetically by ticker. [prereg §09]
- Assign `+1` to ranks 1–2, `−1` to the two lowest ranks and `0` otherwise. [prereg §09]
- Core weight is `0.25` per name; the beta hedge is `h = clip(−β_c/β̂_IVV, −0.5, 0.5)`. [prereg §09]
- The IVV signal is `0` when the final IVV weight is below 2% of capital, `|h|/(1+|h|) < 0.02`; all weights are divided by `(1+|h|)`. [Amendment 2 C2; prereg §09]
- The book is 100% gross with no leverage. [prereg §09]
- State baseline 10 bps trading cost, 2% annual borrow and the 5/20 bps and 1%/5% stress cases. [prereg §09]

Figure/table: signal-to-weight worked schematic and cost bridge from `06_backtest.py` and `07_evaluate.py`; exact result values are placeholders until outputs are committed. [prereg §09, §11]

Presenter: `[owner placeholder]`. Course requirement: precise −1/0/+1 logic, thresholds and position sizing. [instructions, Presentation]

## Slide 7 — Validation and pitfalls (70 seconds)

Headline: Walk-forward validation, a sealed OOS vault and targeted tests address the five required sources of bias. [protocol §10, §12]

- Show chronological expanding validation and the single OOS access rule. [prereg §10]
- Overfitting: fixed grids, simplest eligible candidate, PBO diagnostic. [protocol §12]
- Lookahead: event clock, lagged states, in-fold preprocessing and label assertions. [protocol §12]
- Survivorship: fixed universe and composition-break log; data snooping: trial ledger and DSR. [protocol §04, §12]
- Pretrained-model leakage: excluded trading models, vintage checks and disclosed agent knowledge. [protocol §07, §08, §12]

Figure/table: pitfall-to-test matrix from `tests/` and `docs/qa_report.md`; test outcomes are `TBD (Gate 3)` where not yet committed. [protocol §12]

Presenter: `[owner placeholder]`. Course requirement: pitfall analysis and evaluation rigour. [instructions, Evaluation Framework]

## Slide 8 — Results and evaluation (90 seconds)

Headline: The results compare the selected system with matched M0 and fixed benchmarks on identical period axes. [prereg §07, §11]

- Show In-Sample and OOS equity curves starting at 100 on shared dated log axes. [prereg §11]
- Report net-of-cost metrics, both Sharpe conventions, drawdown and rank IC. The risk-free rate is the weekly FRED 3-month T-bill (`DGS3MO`) with its period average, alongside the skeleton's constant 2%; no cash interest is credited. The skeleton convention (minus rf) is the headline Sharpe, with the zero-cost convention also shown. [prereg §09, §11]
- Compare with the T-bill as the primary benchmark for a hedged, dollar-neutral book, plus matched M0, equal-weight sectors and SPY context. Add the placebo benchmark: 1,000 random ±2/±2 portfolios, the same hedge rule and fixed seeds. [prereg §11]
- Show gross → after-costs → after-borrow decomposition. [prereg §11]

Figure/table: equity curves and metrics from `07_evaluate.py`; all numeric cells are `TBD (Gate 3)` or `TBD (Gate 4)` until committed outputs exist. [protocol §16]

Presenter: `[owner placeholder]`. Course requirement: results and evaluation, including equity curves. [instructions, Presentation]

## Slide 9 — Robustness, regimes and bonus (60 seconds)

Headline: Robustness is assessed through costs, regimes, selection-bias diagnostics and the pre-registered market-neutral tests. [prereg §11]

- Show optimistic, baseline and adverse cost/borrow scenarios. [prereg §09]
- Show bull/bear, VIX, rates and crisis-window cuts. [prereg §11]
- Report DSR with the full trial count, PBO as an auxiliary diagnostic and the paired bootstrap. [prereg §10, §11]
- Market-neutral bonus thresholds: `|β| < 0.10` with a 95% HAC interval containing 0; `|ρ| < 0.20`; mean return in SPY-down weeks > 0 with a bootstrap interval, and the same for down months; and consistency measured by OOS mean weekly return > 0, the share of positive rolling 52-week windows and the return in each OOS year. [prereg §11]
- Secondary bonus: higher Sharpe and lower max drawdown than SPY, tested with Ledoit–Wolf (2008). We claim at most one bonus point; market-neutral is the primary target. [prereg §11]

Figure/table: regime and cost panels, DSR/PBO summary and bonus-test table from `07_evaluate.py`, `src/stats.py` and `docs/trial_log.csv`; result cells are placeholders until Gate 4. [prereg §11]

Presenter: `[owner placeholder]`. Course requirement: robustness, weaknesses and optional market-neutral bonus. [instructions, Bonus Point]

## Slide 10 — Conclusion, weaknesses, contributions and AI tools (50 seconds)

Headline: We report what survived the frozen test, what failed, and what the evidence cannot establish. [protocol §16; instructions, Presentation]

- State whether the selected candidate beat M0 under the registered gate; if not, state that M0* was traded. [prereg §07]
- Summarise the strongest and weakest result without changing the committed rules. [prereg §11]
- State limitations: sparse bear episodes, nine correlated ETFs, retrospective knowledge and the dropped M4 extension. [prereg §06, §07, §10]
- Show each member’s contribution and the AI tools used, based on committed documentation. [protocol §14; instructions, Presentation]

Figure/table: one conclusion table from `07_evaluate.py`, `docs/contribution_statement.md` and `docs/ai_tools_used.md`; result values are `TBD (Gate 4)` until OOS is run. [protocol §16]

Presenter: `[owner placeholder]`. Course requirement: conclusion, weaknesses, contribution statement and AI tools used. [instructions, Presentation]

## Coverage matrix

| Course requirement | Slide |
|---|---:|
| Introduction and hypothesis | 1 |
| Data and processing | 2 |
| Methodology: why the model/AI technique | 5 |
| Methodology: what was optimised and how | 5 |
| Methodology: exact `−1/0/+1` logic and thresholds | 6 |
| Results and equity curves | 8 |
| Conclusion and weaknesses | 10 |
| Contribution statement | 10 |
| AI tools used | 10 |
| Overfitting | 7 |
| Lookahead bias | 3, 7 |
| Survivorship bias | 2, 7 |
| Data snooping | 7, 9 |
| Pretrained-model leakage | 4, 7 |
| Market-neutral bonus: beta, correlation, down-market returns | 9 |
| Superior risk-adjusted-performance bonus alternative | 9 |

## Appendix and backup slides for Q&A

- Formula sheet: label, forward return, hedge, weights, turnover, costs and borrow. [prereg §05, §09]
- Cost bridge: gross, after trading costs, after borrow, with stress cases. [prereg §09, §11]
- Regime cuts: bull/bear, VIX, rates and crisis windows. [prereg §11]
- Agent-lab trial log: proposals, approvals, rejections, hashes, budget and DSR count. [protocol §08; interfaces, contract 15]
- Leakage audit: timestamp checks, lag tests, purge assertions, vault refusal and OOS access log. [protocol §10, §12]
- Parameter neighbourhood: fixed ridge and LightGBM grids, M0* lookbacks and sensitivity settings. [prereg §07, §09]
- Q&A prompts: momentum persistence; ranking versus scale; sparse BEAR24; IVV versus SPY; no collateral interest; dropped news; agent knowledge; trial count; dollar-neutral versus market-neutral; failure to beat M0; effective sample size; T-bill benchmark. [protocol §16]

## Design notes

- Use one message per slide and a consistent chart style; keep axes, colours and benchmark labels identical across periods. [protocol §16]
- Use numbers in slides only from committed outputs and identify whether they are In-Sample or OOS. [protocol §16; prereg §10]
- Keep formulas and audit detail in backup slides so the 600-second main story remains readable. [protocol §16]
- State the retrospective nature of the evidence and the limits of the OOS vault’s protection against human hindsight. [protocol §10]
