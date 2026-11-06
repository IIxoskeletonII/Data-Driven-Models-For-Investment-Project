# Decision log

Dated, append-only log of the team's decisions, deviations and reviewer sign-offs. Entries are never edited in place:
a later change is a new dated entry that refers to the earlier one. Section numbers refer to the DDMI Research Protocol v4.1.

## 2026-10-29 · Decision sheet (protocol section 18)

Eliya and Mattia agreed every item below on 29 October; Simone, Chiara and Giuseppe confirm by vote, and anything
Conditional gets an owner and a date in the notes.

| ID | Decision | Final proposal | Vote | Notes / owner |
| --- | --- | --- | --- | --- |
| D1 | Adopt v4.1 as the final protocol | v4.1 supersedes v4; v4 kept as the reviewed record |  |  |
| D2 | Strategy and universe | Regime-aware momentum on the 9 original sector SPDRs |  |  |
| D3 | Model comparison | M0–M3 and ENS; M4, country sleeve and forward log dropped on 29 Oct |  |  |
| D4 | Selection rule | Simplest candidate passing the gate; ENS is a candidate; fallback M0\* |  |  |
| D5 | OOS start | 2020-01-01, fixed before any In-Sample result |  | See G1-3 below |
| D6 | Sizing and hedge | Dollar-neutral core + IVV hedge, cap 50%, scaled to 100% gross |  |  |
| D7 | Return accounting | No cash interest; drifted-weight turnover; 10 bps + 2% borrow baseline; ledger reconciliation |  |  |
| D8 | Regime features | BEAR24 + 126-day MKT\_VAR; 5 pre-registered interactions |  |  |
| D9 | Agent lab | Committed; \~40 candidates; planted-signal test first; USD 5 cap |  |  |
| D10 | Bonus target | Market-neutral: \|β\| < 0.10, \|ρ\| < 0.20, positive down-week mean, consistency over time reported |  |  |
| D11 | Public repo licensing | No raw vendor data public; fetch scripts, checksums, derived outputs |  |  |
| D12 | Owners and calendar | Section 14 owners and contributions plan; pre-registration 30 Oct, freeze 5 Nov, OOS 6 Nov, deliver 10 Nov |  |  |

## 2026-10-29 · Additions on 29 October (protocol section 00)

| # | Change | Why |
| --- | --- | --- |
| 13 | Schedule re-baselined: pre-registration 30 Oct, freeze 5 Nov, OOS 6 Nov, delivery 10 Nov | No work had started; a 30 Oct freeze was unreachable |
| 14 | Extensions dropped: M4, country sleeve, forward log | The fixed cut order, applied to fit the schedule |
| 15 | Fourth market-neutral test: consistency of returns over time | The bonus text asks for "consistent relevant returns over time" |
| 16 | Contributions plan with owned, visible deliverables per member | The instructions allow different grades when contributions are clearly unbalanced |
| 17 | Data smoke test first; one archived snapshot; Stooq fallback; Bloomberg off the critical path | Yahoo access is the main data risk |
| 18 | Confirm two interpretive choices with the teaching team at an in-class session | Removes the risk of a grading disagreement on the IVV hedge and the cash convention |
| 19 | Submission named `group_7.zip` | Group number confirmed |

## 2026-10-29 · Gate 1 implementation notes

| ID | Kind | Note |
| --- | --- | --- |
| G1-1 | Ownership | 29 Oct: Eliya bootstrapped the Gate 1 pipeline to meet the deadline; workstream A ownership and sign-off remain with Simone (protocol §14). |
| G1-2 | Deviation | 04\_text\_signals.py removed (M4 dropped 29 Oct); scripts renumbered; run\_oos.py → 08\_run\_oos.py. The data smoke test is kept in the pipeline as `00_smoke_test_data.py`. |
| G1-3 | Clarification | D5's "2020-01-01" is shorthand for the In-Sample/OOS boundary of section 10: `in_sample_end: 2019-12-27` in `config.yaml`, and each return is assigned to IS or OOS by its realisation date, as in the skeleton. The first OOS-realised return is at the open of Monday 30 Dec 2019. This is a clarification, not a change. |
| G1-4 | Correction | The compliance matrix (section 01) lists `data/qa/qa_report.md`. The narrative QA report is `docs/qa_report.md` (as in section 13) and its CSV tables are in `data/qa/`. |
| G1-5 | Method | The QA gate thresholds are fixed in the `qa:` section of `config.yaml` before the data was downloaded. |
| G1-6 | Correction | 29 Oct: smoke test corrected. (1) Gap window built on the equity calendar; ^VIX publishes on US holidays (2026-05-25, 2026-09-07). (2) Report crash on failure fixed. Both were script bugs; no data issue. The equity calendar is the union of the session dates of the 11 tradables (9 sectors, IVV, SPY); each ticker is checked from its own first date, and a separate check requires a VIX value on every equity session. |

## 2026-11-02 · Session 2.0: Gate 1 close-out and interface contract

| ID | Kind | Note |
| --- | --- | --- |
| S2-1 | Owner, date | Second price source: owner Simone, due Wed 4 Nov 2026. The automatic Stooq download is blocked (HTML verification page, not bypassed), so the 11 CSV files are placed by hand in `data/raw/second_source/` (git-ignored). Format: `date,open,high,low,close,adj_close,volume`, ISO dates; investing.com exports accepted with the column mapping documented in `docs/qa_report.md`. Until the files exist, the QA gate reads `PENDING (owner: Simone)`. |
| S2-2 | Amendment | Market-state lag: Amendment 1 to `docs/preregistration.md` (commit `e4d688c`). ^VIX, DGS3MO, DGS10 and BAA10Y enter features lagged one equity session. Proposed by Eliya; approved by Eliya and Mattia on 2 Nov 2026; committed before any feature code existed. |
| S2-3 | Rule | Packaging: the files of `project/` in `group_7.zip` are exactly `git ls-files` + `data/raw/**` + `data/processed/**` + `outputs/**`, never a walk of the project folder. Local tool-settings files are refused even if tracked. Implemented in `make_submission.py: submission_files` with tests; Mattia owns the file from now on and adds the packaging at Gate 5. |
| S2-4 | CI | CI job `commit messages` (full history, `fetch-depth: 0`) fails if any commit message in the repository matches the forbidden attribution patterns of `tools/git-hooks/commit-msg`. |
| S2-5 | Data note | XLV 2000-01-10: adjusted close-to-close move of +10.2% (SPY +0.3%), listed in `data/qa/big_moves_close.csv`. It falls in the warm-up, before the longest feature window of the first scored week (104 weeks, from early January 2001), so no scored week is affected. Kept as is. |
| S2-6 | Schedule | Re-baselined after a 4-day pause: Gate 2 Tue 3 Nov (engine verified; features, labels, vault; M0 In-Sample walk-forward), Gate 3 Fri 6 Nov (M1–M3, ENS, agent lab, selection rule, `FROZEN.lock` signed), Gate 4 Sat 7 Nov (single OOS run), Gate 5 Wed 11 Nov (slides, docs, `group_7.zip`, clean runs on macOS and Windows). LUISS deadline unchanged: 16 Nov 2026, 23:59. Supersedes the calendar in D12 and item 13. |
| S2-7 | Ownership | Code workload split. Eliya: `src/features.py`, `src/labels.py`, `src/vault.py`, `src/models.py`, `src/stats.py`, `src/agents/`, `src/contracts.py`, `03_build_features.py`, `04_agent_lab.py`, `05_train_walkforward.py`, `08_run_oos.py`, `run_all.py`. Mattia: `src/sizing.py`, `src/backtest.py`, `src/ledger.py`, `src/metrics.py`, `src/plots.py`, `06_backtest.py`, `07_evaluate.py`, `make_submission.py`. Each owns the tests of their files; each reviews the other's pull requests. Shared files change only in small dedicated pull requests. |

## 2026-11-02 · Session 2.0b: Amendment 2 and the decision record

Format of the operating manual's evidence standard. Quotes are from the DDMI Research Protocol v4.1
(`DDMI_Research_Protocol_v4.1_Final.md`, whose sections the pre-registration copies verbatim) unless another source is named.
"Approved by" for S2-8 to S2-14 is completed by Mattia's approving review of the pull request that adds Amendment 2.

### S2-8 · BEAR24 is never scaled (Amendment 2, C1)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Is the 0/1 indicator BEAR24 winsorised and standardised in-fold like the other market states (interface contract open point P1)? |
| Options considered | (a) standardise every state, BEAR24 included; (b) keep BEAR24 raw 0/1 and scale only the continuous states |
| Decision | (b). BEAR24 is used as 0/1 everywhere; in-fold winsorising and standardisation apply only to MKT_VAR, VIX, TERM and CREDIT |
| Rationale | A standardised indicator is non-zero in normal weeks, so BETA52 × BEAR24 and BETA52 × BEAR24 × MKT_VAR would act outside the bear state, against the Daniel & Moskowitz (2016) mechanism the interactions encode |
| Evidence | §06 market states table: "BEAR24 \| 1 if SPY's cumulative total return over the prior 24 months (104 weeks) is negative, else 0"; heading "Market states (common to all assets; scaling fitted on training folds only)" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/interfaces.md`, `src/contracts.py` (`validate_market_states`), later `src/models.py` (pipeline) |
| Amendment | Yes: Amendment 2, C1 |

### S2-9 · Hedge dead-band on the final IVV weight (Amendment 2, C2)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Is the 2% dead-band applied to h or to the final IVV weight (open point P2)? |
| Options considered | (a) `\|h\| < 0.02` (shorthand in the team manual); (b) `\|h\| / (1 + \|h\|) < 0.02`, the final IVV weight as a share of capital |
| Decision | (b). If `\|h\| / (1 + \|h\|) < 0.02`, then h = 0 and the IVV signal is 0 |
| Rationale | Capital is the 100% gross book after scaling, so "2% of capital" is the scaled IVV weight; the shorthand (a) was an error (S2-15) |
| Evidence | §09 step 4: "0 if the hedge rounds to zero (below 2% of capital)" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/interfaces.md`, `src/contracts.py` (`validate_weights`), later `src/sizing.py` |
| Amendment | Yes: Amendment 2, C2 |

### S2-10 · Missing inputs carry the previous targets (Amendment 2, C3)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | What happens in a week with a missing sector score or BETA52 (open point P3)? |
| Options considered | (a) hold the drifted positions without trading; (b) carry the previous signals and target weights and rebalance to them; (c) keep the signals and re-size with fresh betas |
| Decision | (b). After the warm-up, if any sector score or any required BETA52 (9 sectors and IVV) is missing in week t, the previous week's signals and target weights are carried forward and the book is rebalanced to them (drift turnover charged); the event is logged with the week and the missing fields. Before the first fully valid week the book is flat |
| Rationale | Keeps every week on the same target-weight convention (Σ\|w\| = 1), so the engine and the validators need no special case; (c) would need the missing input |
| Evidence | §09 step 5: "If a required input is missing, last week's positions are kept and the event is logged." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/interfaces.md`, later `src/sizing.py`, `src/backtest.py` |
| Amendment | Yes: Amendment 2, C3 |

### S2-11 · Core weight 0.5 / k in the sensitivity runs (Amendment 2, C4)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How are the k = 1 and k = 3 sensitivity runs sized, given that 0.25 per name would give a core gross of 0.5 or 1.5 (open point P4)? |
| Options considered | (a) keep 0.25 per name; (b) 0.5 / k per name |
| Decision | (b). Each selected long or short name gets core weight 0.5 / k; k = 2 gives the pre-registered 0.25 |
| Rationale | Keeps the core dollar-neutral at gross 1 before hedge scaling, so the sensitivity runs differ from the baseline only in k |
| Evidence | §09 step 3: "The count of 2 is pre-registered; 1 and 3 are reported as sensitivity, never selected." and §09 sizing: "Core weights are 0.25 × signal" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/interfaces.md`, `src/contracts.py` (`validate_weights`, `validate_signals`), later `src/sizing.py` |
| Amendment | Yes: Amendment 2, C4 |

### S2-12 · One continuous book across the period boundary (Amendment 2, C5)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Does the OOS period start from cash, with a full entry cost on 30 Dec 2019 (open point P5)? |
| Options considered | (a) restart from cash at the OOS start; (b) one continuous book, metrics split by period |
| Decision | (b). One continuous book from the first scored week to the data end; the first OOS trade is costed from the drifted In-Sample positions. Metrics, equity curves (rebased to 100) and behaviour statistics are computed separately per period |
| Rationale | A live strategy would not liquidate on the boundary date; the skeleton restarts the statistics per period, not the positions |
| Evidence | §11: "Every series starts at 100 in each period"; skeleton `docs/metrics.md`: "turnover and holding periods restart at the first week of each period" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/interfaces.md`, later `src/backtest.py`, `src/metrics.py`, `08_run_oos.py` |
| Amendment | Yes: Amendment 2, C5 |

### S2-13 · Amendment 1 supersedes §05 step 1 for market series (Amendment 2, C6)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | §05 step 1 lists the Friday VIX close and FRED values as known on Friday; Amendment 1 lags them one session. Which governs? |
| Options considered | (a) Friday values (§05 step 1); (b) previous-session values (Amendment 1) |
| Decision | (b). In features dated Friday t, ^VIX, DGS3MO, DGS10 and BAA10Y enter at their previous-session value |
| Rationale | The later dated amendment governs; it was raised by the contract audit as a tension between the two texts |
| Evidence | §05 step 1: "Daily closes through Friday, VIX close, FRED values released by Friday…"; Amendment 1 (commit e4d688c) |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | later `src/features.py`; `docs/interfaces.md` (already states the one-session lag) |
| Amendment | Yes: Amendment 2, C6 |

### S2-14 · Market-state column VIX; VIX_Z only inside the pipeline (Amendment 2, C7)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | The interface contract named an unscaled column VIX_Z. What is the column called? |
| Options considered | (a) keep VIX_Z for the unscaled level; (b) VIX for the lagged level, VIX_Z for its in-fold standardisation |
| Decision | (b). The weekly market-state frame stores the lagged VIX level as VIX; VIX_Z exists only inside the model pipeline and in the interaction VOL13 × VIX_Z. `config.yaml` `features.states` lists VIX accordingly; the interaction keeps VIX_Z |
| Rationale | A column called VIX_Z that holds a raw level invites applying a second standardisation or none |
| Evidence | §06 table row "VIX_Z \| VIX level, z-scored"; the contract's market-state frame listed VIX_Z as unscaled (commit b505705) |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `config.yaml`, `docs/interfaces.md`, `src/contracts.py`, `src/features.py` (docstring), `tests/test_contracts.py` |
| Amendment | Yes: Amendment 2, C7 |

### S2-15 · Team manual corrected

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | The team operating manual (kept outside the repository by design) stated the dead-band as "\|h\| < 0.02". |
| Options considered | none: the manual ranks below the pre-registration |
| Decision | The shorthand was an error and the manual now matches §09 (S2-9). The manual also gained an evidence standard (every judgement call recorded here before code depends on it, with quoted evidence) and a contract-change rule (a change to `docs/interfaces.md` ships in the same pull request as the code, updates `src/contracts.py` and is approved by the other owner) |
| Rationale | Record the change here, because the manual itself is not versioned in the repository |
| Evidence | §09 step 4: "0 if the hedge rounds to zero (below 2% of capital)" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | none in the repository |
| Amendment | No |

### S2-16 · Second source in the licensing table

`docs/licensing.md` stays Simone's file: she adds investing.com as the second price source (S2-1) when she finalises it.

### S2-17 · Correction of the evidence reference in S2-14

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which commit introduced the unscaled `VIX_Z` market-state column that S2-14 corrects? |
| Options considered | (a) keep the reference to b505705; (b) cite the commits that added the text |
| Decision | (b). The evidence of S2-14 is commits 89a73eb (`docs/interfaces.md`, contract 4 lists `VIX_Z` as the unscaled lagged VIX level) and b24b727 (`src/contracts.py` and `tests/test_contracts.py` validate a market-state frame with a `VIX_Z` column). b505705 was the head of `main` that contained them but adds no `VIX_Z` line. S2-14 is not edited (this log is append-only); this entry supersedes its evidence reference |
| Rationale | Evidence references must point at the commit that introduced the text |
| Evidence | `git show 89a73eb`: "columns exactly `BEAR24`, `MKT_VAR`, `VIX_Z`, `TERM`, `CREDIT`"; `git show b505705` adds no line containing `VIX_Z` |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/decisions.md` |
| Amendment | No |

### S2-18 · Phase numbering of the module stubs

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which phase owns each remaining stub, and may this pull request touch the stub docstrings in `src/plots.py` (Mattia's file)? |
| Options considered | (a) keep the labels written in session 2.0 (stats 3.3, agents 3.2, plots 3.3); (b) renumber to the re-baselined plan |
| Decision | (b). 2.1 Mattia (engine); 2.2 Eliya (features, labels, folds, vault, M0); 2.3 both (integration); 3.1 Eliya (models and `src/stats.py`); 3.2 Mattia (`src/plots.py` and `07_evaluate.py`); 3.3 Eliya (agent lab). Moves: stats 3.3 → 3.1, agents 3.2 → 3.3, plots 3.3 → 3.2. The `src/plots.py` change touches only the module docstring and the stub error-message strings (no logic), and its owner approves it through his review of this pull request |
| Rationale | Stub labels must match who builds each module and when, so teammates do not plan against stale phases |
| Evidence | `git diff b505705..HEAD` (commit ae7360f): `docs/interfaces.md` lines 348–350, the contract 17 rows for `src/agents/` (3.2 → 3.3), `src/stats.py` (3.3 → 3.1) and `src/plots.py` (3.3 → 3.2, "with `07_evaluate.py`"); `tests/test_module_stubs.py` lines 21–22 (agents "3.2" → "3.3") and 24–25 (stats "3.3" → "3.1", plots "3.3" → "3.2"); `src/plots.py` line 3 (docstring "Phase 3.3 (Mattia)" → "Phase 3.2 (Mattia)") and lines 17, 22, 29 (`NotImplementedError("Phase 3.3, Mattia")` → `"Phase 3.2, Mattia"`). The same relabelling in Eliya's files: `src/stats.py` lines 4, 19, 26, 33, 40, 45, 56 and `src/agents/__init__.py` line 3, `graph.py` lines 5, 11, 18, `vault_server.py` lines 6, 14, 19, 24. Instruction: PROMPT_2.0b §2d.1, "The phase numbers in the stub table are correct: 2.1 Mattia (engine), 2.2 Eliya (features, labels, folds, vault, M0), 2.3 both (integration), 3.1 Eliya (ladder + `stats.py`), 3.2 Mattia (`plots.py` + `07_evaluate.py`), 3.3 Eliya (agent lab). Fix any that differ." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/interfaces.md`, `tests/test_module_stubs.py`, `src/plots.py`, `src/stats.py`, `src/agents/__init__.py`, `src/agents/graph.py`, `src/agents/vault_server.py` |
| Amendment | No: planning, not specification |

## 2026-11-02 · Session 2.1: engine, sizing, ledger and metrics

Each entry follows the operating manual §2a. "Approved by" lists the approvals given so far; Eliya approves through the
review of the 2.1 pull request.

### S21-1 · Amendment 2 C2–C5 in the engine

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How do the sizing and the engine implement Amendment 2 C2–C5? |
| Options considered | Implement from the amendment text (chosen); wait for the merge |
| Decision | C2: h = 0 (IVV signal 0) when the IVV weight \|h\|/(1+\|h\|) < `signal.hedge_deadband`. C3: see S21-2. C4: core weight 0.5/k from `src.contracts.core_weight_for(k)` (PR #3). C5: `run` is one continuous book over IS and OOS; `period_metrics` computes every metric, the equity rebased to 100 and the behaviour statistics per period |
| Rationale | The amendment settles open points P2–P5 of `docs/interfaces.md` |
| Evidence | Amendment 2 C2 "if \|h\| / (1 + \|h\|) < 0.02, then h = 0 and the IVV signal is 0"; C4 "each selected long or short name receives core weight 0.5 / k"; C5 "The backtest is one continuous book from the first scored week to the data end. The OOS period does not restart from cash" (commit 303152d, PR #3); §09 step 4 "0 if the hedge rounds to zero (below 2% of capital)"; skeleton `docs/metrics.md` "the equity curve restarts from 100 at the start of each period, and turnover and holding periods restart at the first week of each period". Test: h = −0.0203 is zeroed although \|h\| ≥ 0.02 |
| Proposed by | Eliya Allam (Amendment 2) |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam (amendment PR) |
| Files affected | `src/sizing.py`, `src/backtest.py`, `src/metrics.py` |
| Amendment | Amendment 2 itself |

### S21-2 · Missing inputs of §09 step 5 (Amendment 2 C3)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which missing inputs trigger the carry-forward, what is carried, and does a zero or non-finite IVV beta count as missing? |
| Options considered | What is carried: (a) last week's signals and target weights (chosen); (b) the signals, re-sized with the new betas. IVV beta: (c) a zero or non-finite β̂_IVV counts as missing (chosen); (d) only a NaN counts |
| Decision | Required: all 9 sector scores and all 10 BETA52 (the 9 sectors and IVV, whether held that week or not). A zero or non-finite IVV beta counts as missing: this is our interpretation, because the hedge h = clip(−β_c / β̂_IVV, −0.5, 0.5) is undefined there. A week missing any of them carries last week's sector signals, IVV signal, target weights, hedge, residual beta, net exposure and `cap_binds`; the engine rebalances from the drifted weights back to them; the event is logged (logger `src.sizing`, level WARNING) with the week and the missing fields, e.g. "2010-01-15: score XLI" or "2010-01-15: BETA52 IVV". Weeks before the first valid week have no row (flat), and the first row is entered from cash. A NaN beta after a column's warm-up breaks contract 10 and raises `ContractError` instead of being carried. The first implementation required only the betas of the held sectors and IVV; it was corrected to C3 before any commit, and the test that encoded it (`test_unheld_sector_without_beta_is_not_a_missing_input`) was replaced by `test_c3_every_beta_is_required_even_of_an_unheld_sector`, which is stricter, not looser: it requires more inputs before a week can trade |
| Rationale | (b) would change positions in a week whose inputs are incomplete, and C3 names the targets; (c) because a division by a zero or non-finite beta gives no hedge, so the week cannot be sized |
| Evidence | Amendment 2 C3: "After the warm-up, if any sector score or any required BETA52 (9 sectors and IVV) is missing in week t, the previous week's signals and target weights are carried forward unchanged and the book is rebalanced to those same targets; turnover from drift is therefore still charged. The event is logged with the week and the missing fields. Before the first fully valid week, the book is flat." (commit 303152d); §09 sizing: h = clip(−β_c / β̂_IVV, −0.5, 0.5); §09 step 5: "If a required input is missing, last week's positions are kept and the event is logged."; `docs/interfaces.md` contract 8: "A carried week also carries the previous `hedge`, `residual_beta`, `net_exposure` and `cap_binds`"; contract 10: "`NaN` in the warm-up only". Tests `test_c3_every_beta_is_required_even_of_an_unheld_sector`, `test_c3_unusable_beta_carries_signals_and_targets` (β̂_IVV = 0), `test_case_h_missing_score_keeps_last_signals` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam, 2 Nov 2026 (review of the 2.1 numbers) and PR review |
| Files affected | `src/sizing.py`, `tests/test_sizing.py` |
| Amendment | No (Amendment 2 C3) |

### S21-3 · Refined signatures of the Phase 2.1 stubs

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which stub signatures change in the phase PR? |
| Options considered | Keep the stubs exactly; refine them where the implementation needs it (chosen) |
| Decision | `signals_from_scores` returns the 9 sector columns (the TRADED signals with IVV come from `target_weights`). Optional keywords: `target_weights(..., missing=None)`, `run(..., core_weight=None)`. New helpers: `size_book`, `period_metrics`, `equity_curve`, `actual_prices`, `dividend_reinvestment_term`. `tbill_weekly_returns(dgs3mo, weeks, sessions)` gains a required `sessions` argument (`docs/interfaces.md` contract 16 updated in this PR). `run_ledger(weights, raw, initial_capital=100.0, *, mode, cost_bps, borrow_annual)` returns a DataFrame (`nav_start, ret, traded, costs, borrow, dividends, splits, nav_end`) |
| Rationale | The one-session lag needs the equity calendar; the ledger reports the components the reconciliation decomposes |
| Evidence | `docs/interfaces.md` header "Adding an optional keyword argument with a default that keeps the old behaviour is not a contract change."; contract 17 "a stub's exact argument list is a proposal that its owner may refine in the phase pull request, which the other author reviews"; stub docstring of `signals_from_scores` "columns = sectors" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/sizing.py`, `src/backtest.py`, `src/metrics.py`, `src/ledger.py`, `docs/interfaces.md` |
| Amendment | No |

### S21-4 · Weekly T-bill return

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How is the daily DGS3MO yield turned into a weekly risk-free return? |
| Options considered | rate/100 · 7/365 (chosen); rate/100/52; (1 + rate/100)^(1/52) − 1; actual days from O(t+1) to O(t+2) |
| Decision | rf_t = DGS3MO/100 · 7/365, simple; the rate of week t is the last observation dated on or before the session before the last session of week t |
| Rationale | Same day count as the pre-registered borrow charge; the lag follows Amendment 1 and contract 1 |
| Evidence | §09 "b·(7/365)·Σ_{w<0}\|w\|"; §11 "Weekly FRED 3-month T-bill (time-varying), with its period average stated on the results slide"; contract 1 "the last observation dated on or before the session before s" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/metrics.py` |
| Amendment | No |

### S21-5 · Risk-free rate inside Sharpe, Sortino and alpha

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which annual rf enters the skeleton formulas when rf is a weekly series? |
| Options considered | Compound annual return of the weekly rf over the same weeks (chosen); 52 × mean weekly rf |
| Decision | `sharpe_rf` and Sortino use (annualised return − rf_annual), rf_annual = (Π(1+rf))^(52/T) − 1 = `period_average_rf`; Jensen alpha uses the mean weekly rf, (r̄ − rf_w − β(m̄ − rf_w))·52, equal to the skeleton formula for a constant (rf_w = rf/52); `sharpe_zero_cost` = annualised return / volatility; `sharpe_textbook` = √52·mean/std, information only |
| Rationale | rf is annualised the same way as the strategy's compound return |
| Evidence | §09 "Sharpe is reported two ways: the skeleton convention, (annual return − rf) / volatility, which is conservative here and is the headline; and the zero-cost long/short convention, annual return / volatility."; skeleton `docs/metrics.md` Sharpe, Sortino and Jensen alpha rows |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/metrics.py` |
| Amendment | No |

### S21-6 · Behaviour statistics of a weighted book

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | What is N in the skeleton's behaviour metrics, and how are weights reported? |
| Options considered | N = 10 traded columns (chosen); N = 9 sectors |
| Decision | Skeleton signal metrics with N = 10 (9 sectors + IVV); weight-based net and gross exposure and target turnover Σ\|w_t − w_{t−1}\| reported alongside; the drifted-weight turnover stays in `BacktestResult.turnover` |
| Rationale | IVV is traded with its own discrete signal |
| Evidence | Skeleton `docs/metrics.md` "N: Number of stocks traded by the strategy"; operating manual §1 "The hedge is IVV (traded, with its own discrete signal)" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/metrics.py` |
| Amendment | No |

### S21-7 · Validating sensitivity books (k = 1, 3)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | `validate_backtest_result` checks sector sizes against `signal.core_weight` only; how are k = 1, 3 books validated? |
| Options considered | Local check in `run` until the contract has a `core_weight` keyword (chosen); skip validation |
| Decision | Until PR #3 merged, `run(..., core_weight=0.5/k)` called `validate_weights(core_weight=...)` and checked the contract-12 identities itself. PR #3 (commit 52b4a56) adds `k=` and `core_weight=` to `validate_backtest_result` and `core_weight_for` to `src/contracts.py`; the follow-up commit d3db20a "refactor: validate sensitivity books with the contract validator" removes the local check and `src.sizing.core_weight_for` and calls the contract functions instead. Tested before the merge on the PR #3 branch: 365 passed |
| Rationale | Never skip a validator; never edit the other owner's file |
| Evidence | `src/contracts.py: validate_backtest_result` at b505705 calls `validate_weights(result.weights)` with the default core weight; commit 52b4a56 "feat: accept a core-weight keyword when validating sensitivity books"; Amendment 2 C4 |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026 (deviation 3) |
| Files affected | `src/backtest.py` |
| Amendment | No |

### S21-8 · Ledger conventions

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How does the independent ledger book trades, costs, borrow and corporate actions? |
| Options considered | As below (chosen) |
| Decision | Execution at the first session after Friday t, valuation at the first session after Friday t + 7 days, found on the daily calendar; costs in cash on the traded value at execution; borrow at valuation on the short value at entry; dividends with ex-date in (execution, valuation] in cash (shorts pay); split factors multiply the shares; actual opens = Yahoo Open × product of later split factors; no interest on cash |
| Rationale | An independent path to the same quantities as the engine |
| Evidence | §09 "An independent position-and-cash ledger (shares, raw opens, dividend cash flows, splits, IVV) runs on three In-Sample years."; §05 clock |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/ledger.py` |
| Amendment | No |

### S21-9 · Drifted-weight denominator (Amendment 3 C2)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | With costs on, the engine and the ledger differ; which drifted-weight formula is right? |
| Options considered | (a) keep the pre-registered 1 + Σ w·R_fwd and document the gap; (b) divide by 1 + r_net (chosen) |
| Decision | w_pre[t] = w[t−1]·(1+R_fwd[t−1]) / (1 + r_net[t−1]); the engine loops over weeks for it |
| Rationale | The book's value after costs and borrow is 1 + r_net |
| Evidence | Real IS data, 2005/2012/2016/2018, 10 books per year, 10 bps + 2%: pre-registered denominator max \|ledger − engine\| 2.31e-6, mean 1.355e-6, residual after the term c·(turnover_ledger − turnover_engine) 3.7e-16; amended denominator max 3.7e-16 at 10 bps/2%, and at most 4.43e-16 over the three cost scenarios (5 bps/1% 4.10e-16, 10 bps/2% 3.68e-16, 20 bps/5% 4.43e-16; all nine bps × borrow combinations ≤ 4.93e-16). `tests/test_ledger.py: test_level_a_with_costs_matches_the_engine`, `test_level_a_with_every_cost_scenario` (≤ 1e-10) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/backtest.py`, `tests/test_backtest.py`, `tests/test_ledger.py`, `docs/preregistration.md` |
| Amendment | Yes: Amendment 3 C2 |

### S21-10 · Level B criterion (Amendment 3 C1)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Level B differs from the engine by more than the pre-registered 1e-6; what is the pass criterion? |
| Options considered | (a) \|ledger − engine − dividend-reinvestment term\| ≤ 1e-6 (chosen); (b) raw 1e-6 (fails); (c) cash-dividend accounting in the engine (rejected: larger change, departs from the skeleton's adjusted-price convention) |
| Decision | (a); the term is computed from the dividend series and prices with the formula of `docs/methods.md`, never back-solved; raw max and mean differences are reported in `docs/methods.md` and the PR |
| Rationale | The difference is the known reinvestment convention of the adjusted series |
| Evidence | Real IS data, 2,090 book-weeks, zero cost: raw max 5.86e-5, mean 1.46e-6; term max 5.88e-5; remainder max 5.11e-7 = max difference in weeks without a dividend (Yahoo Adj Close is float32). Synthetic market: remainder ≤ 1e-12. Hand case in `tests/test_ledger.py: test_reinvestment_term_hand_case` (term = 0.25·(1.03 − 1.0302) = −5e-5) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026 (conditional on these numbers); Eliya Allam: PR review |
| Files affected | `src/ledger.py`, `06_backtest.py`, `tests/test_ledger.py`, `docs/methods.md`, `docs/preregistration.md` |
| Amendment | Yes: Amendment 3 C1 |

### S21-11 · Ledger years and the XLF spin-off factor

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which In-Sample years does the real-data ledger check replay, and how is XLF 2016-09-19 handled? |
| Options considered | 2005, 2012, 2018 (prompt example); add 2016 (chosen) |
| Decision | Years 2005, 2012, 2016, 2018, 10 seeded random books each, in a new additive `ledger:` section of `config.yaml` with the tolerances (1e-6; 1e-10 with costs), read by `06_backtest.py: ledger_settings` (commit 0e12684), which refuses years reaching the OOS, a non-positive book count and any tolerance outside (0, 1e-6], so the pre-registered 1e-6 can never be loosened from the config; `--ledger-years` without years replays `ledger.years`. XLF 2016-09-19 is the real-estate (XLRE) spin-off, which Yahoo books as a 1.231 split factor; it is not a true split. The ledger treats it as a split, which preserves value like the adjusted series. The true 2:1 splits of December 2025 are Out-of-Sample and are not used (`06_backtest.py --ledger-years` refuses years reaching 2019-12-27) |
| Rationale | 2016 holds the only split factor of the In-Sample data |
| Evidence | `data/raw/yahoo/XLF.csv` Stock Splits = 1.231 on 2016-09-19 (no other split factor up to 2019-12-27 in the 11 tradables); remainder in the 5 held book-weeks ≤ 1.34e-7 |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026 (deviation 1); Eliya Allam: PR review |
| Files affected | `config.yaml`, `06_backtest.py`, `tests/test_backtest_script.py`, `docs/methods.md` |
| Amendment | No |

### S21-12 · Sections of `docs/methods.md`

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | `docs/methods.md` has no owner in the operating manual's table; who writes the engine and ledger methods? |
| Options considered | (a) each phase appends its own section in its phase pull request (chosen); (b) one owner for the whole file |
| Decision | (a). The Phase 2.1 pull request adds the section "Engine and ledger accounting" (ledger conventions, the dividend-reinvestment term of Amendment 3 C1 and the measured numbers); other phases append their own sections and do not edit earlier ones |
| Rationale | Each method is written by the person who implements it and reviewed by the other owner |
| Evidence | Operating manual §4 ownership table (no row for `docs/methods.md`); Eliya Allam, review of the 2.1 numbers, 2 Nov 2026: "docs/methods.md has no single owner. Each phase appends its own section; add 'Engine and ledger accounting' in this PR and record it as an S21 entry." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam, 2 Nov 2026; Mattia Cervelli |
| Files affected | `docs/methods.md` |
| Amendment | No |

### S21-13 · Turnover at the In-Sample/OOS boundary (Amendment 2 C5)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | In the first OOS week, which turnover is charged and which is reported? |
| Options considered | Charged: (a) from the drifted In-Sample book (chosen, C5); (b) from cash. Reported in the OOS behaviour statistics: (c) skeleton turnover restarting from flat (chosen); (d) continuing from the last In-Sample week |
| Decision | `src/backtest.py: run` is one book over both periods: the first OOS trade is costed from the drifted In-Sample positions (turnover Σ\|w_t − w_pre_t\|, never Σ\|w_t\|), and only the first week of the whole book is entered from cash. `src/metrics.py: period_metrics` computes `behaviour` on each period separately, so the reported OOS turnover per year and holding periods start from flat in the first OOS week (signal trades \|s_t − 0\|, target-weight trades \|w_t − 0\|), as in the skeleton. The cost actually charged that week stays in `BacktestResult.costs` and in the OOS net returns |
| Rationale | C5 fixes the cost; the skeleton fixes how the statistics restart; the two are different quantities and both are kept |
| Evidence | Amendment 2 C5: "The OOS period does not restart from cash: its first trade is costed from the drifted In-Sample positions. Metrics, equity curves (rebased to 100) and behaviour statistics (turnover, holding periods) are computed separately for each period, following the course skeleton." (commit 303152d); skeleton `docs/metrics.md`: "turnover and holding periods restart at the first week of each period". `06_backtest.py --synthetic` (synthetic market 2011–2020, is_end 2019-12-27, no real data): first OOS week (signal Friday 2019-12-20, realised 2019-12-30) engine turnover 1.380305, cost 0.001380, equal to the recomputed Σ\|w − w_pre\| (max difference over 512 weeks 4.4e-16); turnover 1.0 only in the first week of the book; behaviour counts that week from flat (Σ\|w\| = 1.0). Tests `tests/test_backtest.py` (C5 continuity) and `tests/test_metrics.py` (`period_metrics`) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `src/backtest.py`, `src/metrics.py` |
| Amendment | No (Amendment 2 C5) |

### S21-14 · No Out-of-Sample return in `06_backtest.py`

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How does `06_backtest.py` make sure that no forward return realised after 2019-12-27 is computed on real data, and does `FROZEN.lock` change that? |
| Options considered | (a) rely on the In-Sample cut of the raw files; (b) a guard on the realisation dates of every real-data path, independent of `FROZEN.lock` (chosen); (c) the same guard, lifted once `FROZEN.lock` exists |
| Decision | (b). `refuse_oos_returns(realised_on, is_end)` (commit 0b7226a) stops the run (SystemExit, nothing written) if any forward return on real data is realised after `split.in_sample_end`, before the ledger or the engine runs. It is called on the ledger path after `forward_returns`, behind the cut of the raw files at the In-Sample end and the refusal of `--ledger-years` reaching 2019-12-27; it stays on after `FROZEN.lock` exists, since the OOS run belongs to `08_run_oos.py`. Real-data backtests refuse to run until the vault exists (Phase 2.3). The synthetic mode is not restricted |
| Rationale | Defence in depth: a failure of the cut cannot leak an OOS return; (c) would be looser than contract 15 |
| Evidence | Operating manual rule 3: "Before Gate 3 (`FROZEN.lock` exists and is signed), no code may read, compute or print any label, return, metric or plot for a date after 2019-12-27"; `docs/interfaces.md` contract 15: "`OOSAccessError(PermissionError)`: raised for any request touching a date after `is_end` (2019-12-27) while `FROZEN.lock` does not exist, and even then except through the explicit unlock path of `08_run_oos.py`"; §09 "An independent position-and-cash ledger … runs on three In-Sample years". Tests `tests/test_backtest_script.py: test_oos_guard_refuses_a_return_realised_after_the_in_sample_end`, `test_ledger_check_stops_before_any_oos_return_even_with_frozen_lock` (the synthetic market extends to 2020-12-31, the cut is bypassed, a `FROZEN.lock` is present: the run stops before the ledger and writes nothing; the test fails with the guard disabled) |
| Proposed by | Eliya Allam (guard); Mattia Cervelli (independent of `FROZEN.lock`) |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py` |
| Amendment | No |

## 2026-11-02 · Session 2.2: features, labels, folds, vault and M0

Format of the operating manual's evidence standard. "Contract n" is `docs/interfaces.md`; "Instruction" quotes Eliya's
corrections to the session 2.2 prompt (2 Nov 2026). "Approved by" is completed by Mattia's approving review of the pull
request that implements Session 2.2.

### S22-1 · VOL13 uses daily simple returns

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Is VOL13 the standard deviation of daily log returns (contract 3) or of daily simple returns? |
| Options considered | (a) daily log returns, as contract 3 states; (b) daily simple returns |
| Decision | (b). VOL13 = sample standard deviation (`ddof=1`) of daily simple returns `TR(s) / TR(s−1) − 1` whose end session `s` lies in the 13 calendar weeks ending Friday t (S22-3), × √252. Contract 3 is corrected in the same pull request |
| Rationale | §06 does not say "log"; the contract's own convention reads unstated returns as simple; BETA52 and MKT_VAR, the other daily-return features, use simple returns, so all three share one return series |
| Evidence | §06 asset table: "VOL13 \| Std of daily returns over 13 weeks × √252"; §06 states table: "MKT\_VAR \| Variance of daily SPY returns over the prior 126 trading days"; contract 0 (commit 89a73eb): "Returns \| Simple returns unless "log" is said."; contract 3 (commit 89a73eb): "`VOL13` \| sample std (`ddof=1`) of daily log returns whose end session lies in weeks t−12 … t, × √252"; Instruction C: "protocol §06 says "Std of daily returns", not log returns. Use daily simple returns, consistent with BETA52 and MKT_VAR" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` §"Changes") |
| Files affected | `docs/interfaces.md` (contract 3, VOL13 row), `src/features.py`, `tests/test_features.py` |
| Amendment | No: the decision follows the pre-registered wording; the contract's "log" was the deviation |

### S22-2 · Market series at a session: last value published on or before the previous session

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How are ^VIX and the FRED series aligned to the equity calendar, in particular on bond-market holidays when equities trade (Columbus Day, Veterans Day)? |
| Options considered | (a) the value dated exactly on the previous session, NaN when it is missing; (b) the last non-missing observation dated on or before the previous session (carry the last published value forward, never a later one); (c) `data/processed/daily_market.csv` as written at Gate 1 (VIX of the same session, FRED lagged one calendar day) |
| Decision | (b). `lag_one_session(series, sessions)`: the value at session s is the last non-missing observation dated on or before the equity session before s; NaN at the first session and before the first observation. Each FRED series is lagged on its own, then TERM = DGS10 − DGS3MO. A feature dated Friday t takes the value at the last session of week t, i.e. the last observation dated on or before the session before it. Observations dated on non-sessions (VIX-only holidays, FRED values on Good Friday) are used only from the first session whose previous session is on or after their date. Features read the raw files `data/raw/yahoo/VIX.csv` (Close) and `data/raw/fred/<SERIES>.csv`, never `daily_market.csv`, which would lag FRED twice |
| Rationale | (a) would leave TERM and CREDIT missing after every bond holiday; (c) does not implement Amendment 1. (b) uses only values that were published by the decision time and is the contract 1 rule |
| Evidence | Amendment 1: "All market-state series (^VIX, DGS3MO, DGS10, BAA10Y) enter features lagged one equity session"; Amendment 2 C6: "in features dated Friday t, these series enter at their previous-session value, not their Friday value"; contract 1 (commit 89a73eb): "Contract value at session s (Amendment 1): **the last observation dated on or before the session before s**"; Instruction D: "On bond-market holidays when equities trade (e.g. Columbus Day, Veterans Day), carry the last published FRED value forward, never a later one". In the archived data, DGS10 has no value on Thursday 2004-11-11 and Thursday 2010-11-11 (equity sessions), so the Fridays 2004-11-12 and 2010-11-12 use Wednesday's value |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/features.py` (`lag_one_session`, `market_states`), `03_build_features.py`, `tests/test_features.py` (hand tests with a Thursday Veterans Day and a Columbus Day) |
| Amendment | No: applies Amendment 1 and C6 as contract 1 already states them; the bond-holiday case is recorded here |

### S22-3 · Window and lag conventions

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | What do "13 weeks", "52 weeks", "104 weeks", "126 trading days" and "TR(t − k w)" mean on the session calendar? |
| Options considered | (a) calendar weeks ending Friday t; (b) a fixed number of sessions (13 × 5, 52 × 5); (c) rows of the weekly index |
| Decision | (a), with fixed session counts only where the text gives them. With F the Friday `date_close` of week t: "the 13 (52) weeks ending t" are all equity sessions s with F − 91 days < s ≤ F (F − 364 days < s ≤ F). A daily return `TR(s) / TR(s−1) − 1` belongs to a window when its end session s does. `TR(t − k w)` is the close of the last session of the calendar week ending F − 7k days (Thursday when that Friday is a holiday); NaN if that week has no session. BEAR24 compares `TR_SPY(t)` with `TR_SPY(t − 104 w)` under the same rule. MKT_VAR uses exactly the 126 daily SPY returns whose end sessions are the last 126 sessions up to the last session of week t. `03_build_features.py` checks that the weekly index has no calendar week without a session, so (a) and (c) coincide on our data |
| Rationale | (a) follows the wording "over 13 weeks" and keeps holiday weeks consistent with the weekly panel (Thursday close after a Good Friday); (b) would cut windows in holiday weeks; MKT_VAR is defined in trading days, so it counts sessions |
| Evidence | §06: "MOM26\_1 \| log TR(t−1w) / TR(t−26w)", "VOL13 \| Std of daily returns over 13 weeks × √252", "DD13 \| TR(t) / max TR over 13 weeks − 1", "BETA52 \| cov(asset, SPY) / var(SPY), daily, 52 weeks", "BEAR24 \| 1 if SPY's cumulative total return over the prior 24 months (104 weeks) is negative", "MKT\_VAR \| Variance of daily SPY returns over the prior 126 trading days"; contract 0 (commit 89a73eb): "Its *last session* is Friday, or Thursday when Friday is a holiday" and "`t − k w` \| The value at the last session of the week k rows earlier in the weekly index"; Instruction E: ""13 weeks" and "52 weeks ending t" mean all equity sessions in the 13 (or 52) calendar weeks ending Friday t; BEAR24's 104 weeks are counted the same way. TR(t−kw) is the last session of week t−k (Thursday when Friday is a holiday). MKT_VAR uses exactly 126 sessions." The archived calendar has 1,100 weeks from 1998-12-04 to 2019-12-27 and none without a session |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/features.py`, `03_build_features.py`, `tests/test_features.py` |
| Amendment | No: implementation convention consistent with §06 and contract 0 |

### S22-4 · Warm-up: when a window is full

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | When is a feature value defined rather than NaN, and how are sectors with a missing raw value z-scored? |
| Options considered | (a) compute from whatever sessions are available; (b) NaN until every input of the window exists; z-score a week only when all 9 sectors have the raw value |
| Decision | (b). A window value is NaN unless every close it needs is present: for a return window, the closes of all its sessions and of the session before its first session; for `TR(t − k w)`, a session in that week with a close; for MKT_VAR, 127 closes. A cross-sectional z-score is computed per feature and week only when all 9 sectors have the raw value, else all 9 are NaN; with zero dispersion all 9 get 0 (contract 3). Scoring starts at the first week with `date_close` after `split.warmup_end` (2003-01-03) for every model, whatever the first complete week is |
| Rationale | Partial windows would make early values incomparable; a z-score over fewer than 9 sectors would change the scale of the score; contract 3 allows NaN only while a window is not full |
| Evidence | §06 constraints: "a 104-week warm-up applied identically to every model"; §10 table: "Warm-up \| Dec 1998 – Dec 2002 \| Feature windows only (104-week BEAR24, 52-week beta); no scoring"; contract 3 (commit 89a73eb): "`NaN` only while a window is not yet full (warm-up)" and "a week where every sector has the same raw value gets `z = 0`" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/features.py`, `tests/test_features.py` |
| Amendment | No |

### S22-5 · Features are built only through the In-Sample end until the freeze

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | May `03_build_features.py` build features for the full data range (session 2.2 prompt, §1) before `FROZEN.lock` exists? |
| Options considered | (a) build the full range, since features use no outcomes; (b) truncate every input at `split.in_sample_end` (2019-12-27) and refuse to write later rows unless `FROZEN.lock` exists and the caller is the explicit unlock path of `08_run_oos.py` |
| Decision | (b). `03_build_features.py` truncates the daily closes, ^VIX and FRED inputs at 2019-12-27 right after reading them and writes only rows with `date_close ≤ 2019-12-27`. Its writer raises `OOSAccessError` for any later row unless `FROZEN.lock` exists and `allow_oos=True` is passed, which only `08_run_oos.py` does (Gate 4). Features use only data up to t, so the In-Sample values are identical to a full-range build |
| Rationale | REV1, MOM26\_1 and the other features are past returns: computing them for dates after 2019-12-27 computes returns in the sealed period, which the manual forbids before Gate 3 even though no outcome is involved |
| Evidence | Operating manual §3.3: "Before Gate 3 (`FROZEN.lock` exists and is signed), no code may read, compute or print any label, return, metric or plot for a date after 2019-12-27, except raw data QA."; §10 vault protocol: "Until Gate 3, `src/vault.py` refuses to return any label or metric dated after the In-Sample end"; Instruction F: "until FROZEN.lock exists, 03_build_features.py builds only through 2019-12-27, by truncating its inputs at the In-Sample end … The full-range build happens only through 08_run_oos.py's unlock path." Supersedes the session 2.2 prompt §1, "builds features for the full date range" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `03_build_features.py`, `tests/test_build_features.py` |
| Amendment | No: stricter than §10 and consistent with it |

### S22-6 · In-fold scaling of the continuous states and the interaction columns

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | On which rows are the scaling parameters fitted, with which estimator, and how are the M2 interaction columns built? |
| Options considered | Fit on (a) the panel rows (each week repeated 9 times) or (b) the distinct training weeks; standard deviation with `ddof=0` or `ddof=1` |
| Decision | (b) with `ddof=1`. `fit_transform_train` takes the purged training rows; for each of MKT\_VAR, VIX, TERM and CREDIT it computes the lower and upper winsorising quantiles (level: S22-11) over the distinct training weeks, clips, then computes the mean and the sample standard deviation (`ddof=1`) of the clipped values over the same weeks; a state with zero training dispersion scales to 0. `transform_test` applies the stored parameters without refitting. BEAR24 is passed through as 0/1. VIX\_Z is the scaled VIX. The design matrix holds the six z-scored asset features and, with `interactions=True`, the five pre-registered products in `features.interactions` order: z-scored asset feature × raw BEAR24 × scaled MKT\_VAR or VIX\_Z (`BETA52_x_BEAR24_x_MKT_VAR`, `BETA52_x_BEAR24`, `MOM26_1_x_BEAR24`, `MOM26_1_x_MKT_VAR`, `VOL13_x_VIX_Z`). The states themselves are not columns of the design matrix (contract 5) |
| Rationale | A market state is one number per week; fitting on the panel rows would weight each week 9 times, which leaves the mean unchanged but shifts interpolated quantiles and the `ddof=1` standard deviation. `ddof=1` matches the z-scores of contract 3 |
| Evidence | §06: "Market states (common to all assets; scaling fitted on training folds only)"; §06 constraints: "Scaling and winsorising fitted inside each training fold"; Amendment 2 C1: "BEAR24 is an indicator and is used as 0/1 everywhere. It is never winsorised or standardised."; C7: "VIX_Z denotes its in-fold standardisation inside the model pipeline"; contract 5 (commit ae7360f): "`BEAR24` enters as its raw 0/1 value (Amendment 2 C1); `MKT_VAR` and `VIX_Z` (the in-fold standardised `VIX`, C7) enter scaled"; Instruction B: "Build the interactions after the transformation, from the scaled MKT_VAR and VIX_Z and the raw BEAR24. Test: when BEAR24 = 0, both BEAR24 interactions are exactly 0." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/models.py` (`fit_transform_train`, `transform_test`), `tests/test_models.py` |
| Amendment | No |

### S22-7 · Labels on weekly-index rows; label files at integration

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which week is "t+2" for `label_end`, and who writes the label file the vault reads? |
| Options considered | (a) `label_end` = first session of the row two places later in the weekly index; (b) first session of the calendar week starting `date_open + 14 days`; for the file: (c) built in this pull request; (d) built at integration (Phase 2.3) from `src/backtest.py: forward_returns` |
| Decision | (a) and (d). `make_labels(fwd, sessions)` uses rows, like `forward_returns` (contract 7), so `label_end` and `realised_on` refer to the same week; S22-3 shows (a) = (b) on our calendar. `03_build_features.py` writes no labels in this pull request: `forward_returns` is Mattia's and still a stub on `main`. The vault reads `data/processed/labels.csv` when it exists; Phase 2.3 writes it, truncated at the In-Sample end like the features (S22-5) |
| Rationale | Labels must be on the same weeks as the forward returns they come from; computing forward returns here would duplicate Mattia's engine code |
| Evidence | §05: "Each label has `label_end = O(t+2)`"; contract 6 (commit 89a73eb): "`label_end` (`datetime64`): the **actual session date of `O(t+2)`**, the first session of week t+2 (not the nominal Monday)"; contract 7: "`realised_on` … `date_open` of week t+2"; session 2.2 prompt §2.1: "`make_labels(fwd)` takes forward returns as an input (Mattia's engine computes them; no dependency)" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/labels.py`, `src/vault.py`, `tests/test_labels.py` |
| Amendment | No |

### S22-8 · Vault: data source, unlock path and trial rows

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Where does the vault read its data, how does `08_run_oos.py` unlock it, and what does `run_walkforward` write to the trial log before the engine is integrated? |
| Options considered | Trial metrics: (a) run the engine inside the vault; (b) an optional evaluator argument, metrics left empty without it |
| Decision | `Vault` gains optional keyword arguments with defaults that keep contract 15: `data_dir` (default `data/processed`, files `features.csv`, `market_states.csv`, `labels.csv`) or in-memory `frames`. Any `as_of` after `is_end`, and any spec asking for weeks after it, raises `OOSAccessError` and is logged as `refused`, unless `FROZEN.lock` exists and `unlock()` was called; `unlock()` itself raises when the lock is missing and is called only by `08_run_oos.py`. `run_walkforward(spec, evaluate=None)` scores the In-Sample folds of contract 13 and appends one trial row per call; `is_sharpe` and `is_mdd` are filled only when an evaluator (the engine, from Phase 2.3) is passed, and left empty otherwise. `spec_hash` is the SHA-256 of the spec as canonical JSON (sorted keys). No real-data walk-forward is run in this pull request, so `docs/trial_log.csv` gains no row |
| Rationale | (a) would make the vault depend on Mattia's engine before it exists; (b) keeps one trial row per evaluated configuration and lets Phase 2.3 attach the metrics |
| Evidence | Contract 15 (commit 89a73eb): "`run_walkforward(spec)` \| weekly scores (contract 8) of a model spec over the In-Sample folds (contract 13); appends one row to `docs/trial_log.csv`"; contract "Changes": "Adding an optional keyword argument with a default that keeps the old behaviour is not a contract change."; session 2.2 prompt: "Do NOT run M0 through the engine yet; that is Phase 2.3" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/vault.py`, `tests/test_vault.py` |
| Amendment | No |

### S22-9 · Checksums of the feature files

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Where are the checksums of the files written by `03_build_features.py` committed? |
| Options considered | (a) inside `data/checksums.json`, which `01_download_data.py` rewrites; (b) a separate `data/checksums_features.json` |
| Decision | (b). `03_build_features.py` writes `data/processed/features.csv`, `market_states.csv`, `sizing_betas.csv` and `momentum_variants.csv` (git-ignored) and records rows, date range, columns, size and SHA-256 of each in `data/checksums_features.json` (committed), plus `data/processed/features_config.yaml` for `check_used` |
| Rationale | (a) would be erased by every run of `01_download_data.py`; a hash, a date range and a row count disclose no price |
| Evidence | Operating manual §3.6: "Never commit raw vendor data … or any file holding a full daily or weekly price or return series per ticker. Summary tables, flags and metrics are fine."; session 2.2 prompt §1: "writes them to `data/processed/` (git-ignored, derived from licensed data) with `check_used`, and commits only checksums" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `03_build_features.py`, `data/checksums_features.json` |
| Amendment | No |

### S22-10 · Gate 2 scope and the re-baselined calendar

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Protocol §15 lists Gate 2 (2 Nov) as including "M0 In-Sample walk-forward reproduced by the reviewer; agent planted-signal test passes", with the hard stop "If Gate 2 slips past 3 November, cut M3 first". The team manual re-baselined the calendar on 2 Nov (S2-6). What do Gate 2 and the hard stop mean now? |
| Options considered | (a) apply §15 literally: the planted-signal test (agent lab, Phase 3.3) cannot pass by 3 Nov, so M3 is cut; (b) keep the 3 Nov trigger for Gate 2's core and move only the planted-signal test to Gate 3 |
| Decision | (b). Gate 2 core, by the end of Tue 3 Nov: engine hand cases and ledger reconciliation pass; features, labels, folds and vault done; M0 In-Sample walk-forward reproduced by the reviewer (Mattia). If the core slips past 3 Nov, the hard stop applies as written: cut M3 first, then reduce agent candidates from ~40 to ~20. The planted-signal test moves to Gate 3 (Fri 6 Nov) and is still never cut. Re-baselined calendar: Gate 3 Fri 6 Nov, Gate 4 Sat 7 Nov, Gate 5 Wed 11 Nov (protocol §15: 5, 6 and 10 Nov). The 16 Nov submission deadline is unchanged |
| Rationale | The hard stop protects the core, and its own text lists the validation protocol, the ledger reconciliation and the planted-signal test as never cut. The planted-signal test checks the agent lab, which M0 and Gate 2's other items do not depend on, so cutting M3 over its timing would shrink the AI ladder without protecting anything. The 3 Nov trigger is kept unchanged, so the pre-commitment stays binding |
| Evidence | Protocol §15 table: "\| 2 \| 2 Nov \| Engine matches hand-computed cases (long, short, hedge, costs, drift); ledger reconciliation passes; M0 In-Sample walk-forward reproduced by the reviewer; agent planted-signal test passes \|"; protocol §15 "Hard stops": "The extensions are already dropped. If Gate 2 slips past 3 November, cut M3 first, then reduce agent candidates from \~40 to \~20. The validation protocol, the ledger reconciliation and the agent planted-signal test are never cut. After Gate 4, no strategy changes."; team operating manual §8 (re-baselined 2 Nov): "\| 2 \| Tue 3 Nov \| Engine verified (hand cases + ledger reconciliation); features, labels and vault done; M0 runs In-Sample walk-forward \|", "\| 3 \| Fri 6 Nov \| M1–M3, ENS, agent lab done; selection rule applied; `FROZEN.lock` signed \|", "\| 4 \| Sat 7 Nov \| `08_run_oos.py` executed once \|", "\| 5 \| Wed 11 Nov \| Slides, docs and `group_7.zip`; clean runs on macOS and Windows; rehearsal \|". `docs/preregistration.md` contains neither the gate calendar nor the hard-stop rule; it names Gate 3 (§10 vault protocol) and Gate 4 (amendment policy) only by their content, which this entry does not change |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam and Mattia Cervelli (agreed 2 Nov 2026; confirmed through Mattia's review of this pull request) |
| Files affected | none (schedule) |
| Amendment | No: the gate calendar and the hard stops are in the protocol (§15), not in the pre-registration |

### S22-11 · Winsorising level of the continuous states (Amendment 3, C8)

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | §06 requires winsorising inside each training fold but states no level; neither the protocol nor `config.yaml` sets one. Which level does the pipeline use? |
| Options considered | (a) Amendment 3 fixing the 1st/99th percentiles, with the key `features.winsor_quantiles` in `config.yaml` (separate shared pull request); (b) leave the pipeline unimplemented until Phase 3.1; (c) implement 1st/99th from the session prompt without an amendment |
| Decision | (a). Amendment 3, C8: bounds at the 1st and 99th percentiles of the distinct training weeks, then standardisation with the mean and `ddof=1` standard deviation of the winsorised training values (S22-6). Percentiles use NumPy's default linear interpolation (`numpy.nanquantile`). `config.yaml` gains `features.winsor_quantiles: [0.01, 0.99]` in its own small pull request; `src/models.py` reads it and fails with a clear message if it is missing |
| Rationale | (c) would add a threshold that is not pre-registered (manual rule 4); (b) would delay M1–M3, which reuse the pipeline. A 1/99 clip limits the influence of the 2008 and 2020 variance spikes on a fold's scaling without changing the ranking within the bulk of the distribution |
| Evidence | §06 constraints: "Scaling and winsorising fitted inside each training fold"; operating manual §3.4: "Features, thresholds, grids, costs, the split and the selection rule come from `docs/preregistration.md` via `config.yaml`. Don't add, remove or retune anything that isn't pre-registered."; session 2.2 prompt §4.1: "winsorise (1st/99th percentile) and standardise the market states using the training rows only"; `grep -i winsor` over the protocol v4.1 finds only line 251 (the §06 constraint), with no level |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (chose option (a), 2 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `docs/preregistration.md` (Amendment 3), `config.yaml` (`features.winsor_quantiles`), `src/models.py`, `tests/test_models.py` |
| Amendment | Yes: Amendment 3, C8 |

### S22-12 · Calendar-start rule for every window; vault hardening after the audit

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | The session 2.2 audit found four judgement calls not stated in S22-4 or S22-8: (1) does the "calendar starts before the window" condition apply to DD13, which needs no prior close? (2) may a `Vault` be built with an `is_end` later than `split.in_sample_end`? (3) are failures other than seal refusals (missing file, failed validation, unknown feature) logged? (4) what happens to spec keys other than those listed in S22-8? |
| Options considered | (1) apply the calendar-start condition (a) to return windows only or (b) to every window; (2) (a) accept any `is_end` or (b) refuse one after `split.in_sample_end`; (3) (a) log only seal refusals or (b) log every failed call as `refused`; (4) (a) ignore unknown keys or (b) refuse them |
| Decision | (1b): a 13- or 52-week window is defined only when the session calendar has a session dated on or before F − 91 (F − 364) days, for DD13 as for the return windows; it affects only warm-up weeks of 1999. (2b): `Vault(is_end)` raises `OOSAccessError` (logged) when `is_end` is after `split.in_sample_end`; Out-of-Sample dates open only through `unlock()`. (3b): every public vault call writes exactly one access-log line, `ok` or `refused`, whatever the failure. (4b): a spec may hold only `rung`, `feature`, `author`, `kind`, `notes`, `as_of`, `end`; any other key raises `ValueError` and is logged as `refused`, with no trial row |
| Rationale | (1b) treats every window alike: a window the calendar does not cover is not full, whatever the statistic. (2b) the seal would otherwise depend on an argument any caller can set. (3b) contract 15 says every call is logged. (4b) a key the vault does not read (for example a start date) would be silently ignored instead of checked against the seal |
| Evidence | S22-4: "A window value is NaN unless every close it needs is present"; contract 3 (commit 89a73eb): "`NaN` only while a window is not yet full (warm-up)"; contract 15 (commit 89a73eb): "Every call appends one JSON line to the access log … result (`ok` or `refused`)" and "raised for any request touching a date after `is_end` (2019-12-27) while `FROZEN.lock` does not exist"; S22-8: "any spec asking for weeks after it, raises `OOSAccessError`" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/features.py` (docstring states the rule), `src/vault.py`, `tests/test_vault.py`, `docs/interfaces.md` (contract 15) |
| Amendment | No |

### S22-13 · The winsorising amendment is Amendment 4, clause C1

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Two pull requests each appended an "Amendment 3" to `docs/preregistration.md` on 2 Nov: Mattia's ledger corrections (pull request #5, merged first, clauses C1 and C2) and the winsorising level of this pull request (commit 80d822c, clause numbered C8). Which number does the winsorising amendment take? |
| Options considered | (a) keep two amendments numbered 3; (b) renumber the unmerged one as Amendment 4, with its clause numbered C1 as in the merged Amendment 3 |
| Decision | (b). The winsorising amendment becomes "Amendment 4 … C1 (§06, in-fold winsorising and standardisation)"; its clause text is unchanged, its header now records the first commit, the renumbering and what had been computed at each point (In-Sample features built; no label, score, signal or strategy result on real data), and it is placed after Mattia's Amendment 3. Every reference "Amendment 3, C8" or "Amendment 3 C8" in S22-6, S22-11, `src/models.py`, `tests/test_models.py` and the `config.yaml` comment of the separate configuration pull request now reads "Amendment 4 C1". S22-6 and S22-11 are not edited (this log is append-only); this entry supersedes their amendment references |
| Rationale | Amendments are numbered in the order they enter `main`; two amendments with the same number would make every citation ambiguous. The renumbering happens before the winsorising amendment is merged, so no merged text changes |
| Evidence | `git show ce9bfa7:docs/preregistration.md`: "Amendment 3 (2 Nov 2026): accounting corrections found by the independent ledger. Proposed by Mattia Cervelli"; commit 80d822c: "Amendment 3 (2 Nov 2026): clarification of §06 (winsorising level)"; pre-registration, amendment policy: "A later change to anything pre-registered above is added at the end, as a dated amendment" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/preregistration.md`, `docs/decisions.md`, `src/models.py`, `tests/test_models.py`, `config.yaml` (comment, separate pull request) |
| Amendment | No new amendment: renumbering of an unmerged one |

## 2026-11-02 · Session 2.3a: In-Sample labels and the M0 walk-forward

Format of the operating manual's evidence standard. "Session 2.3a instructions" quotes the task list Eliya set for the session (2 Nov 2026), with its additions agreed with Mattia.
"Approved by" is completed by Mattia's approving review of the pull request that implements Session 2.3a.

### S23-1 · Labels from the truncated adjusted opens

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which inputs build `data/processed/labels.csv`, how is it kept In-Sample, and which settings guard it through `check_used`? |
| Options considered | Source: (a) `data/processed/weekly_open.csv` (full range, written by `01_download_data.py`), filtered afterwards; (b) `data/processed/daily_open.csv` truncated at `split.in_sample_end` right after reading, weekly opens rebuilt from the truncated daily opens and closes. Settings: (c) keep `{data, features, in_sample_end}`; (d) add `execution`, since `execution.type` determines the labels |
| Decision | (b) and (d). `03_build_features.py` reads the fully adjusted daily opens, truncates them at 2019-12-27 like the closes (S22-5), builds the weekly opens with `src.data.weekly_panel` from the truncated opens and closes, and calls `src.backtest.forward_returns(weekly_open, is_end)` (Mattia's function, imported and unchanged) and `src.labels.make_labels(fwd, sessions)` with the truncated session calendar. It keeps the rows with `label_end ≤ 2019-12-27` and checks that the label weeks lie on the weekly index of the features. Because the opens end on 2019-12-27, the weeks ending 2019-12-20 and 2019-12-27 have no O(t+2) and therefore no forward return and no label: the last label is the week ending 2019-12-13 (`label_end` 2019-12-23), and no open after 2019-12-27 enters any computation. `write_tables` also refuses a labels table with a `label_end` after the In-Sample end unless `FROZEN.lock` exists and `allow_oos=True` (only `08_run_oos.py`). `labels.csv` gets an entry in `data/checksums_features.json` (rows, date range, columns, size, SHA-256). `features_config.yaml` is written from the new `src.features.features_settings(cfg)` = `{data, features, execution, in_sample_end}` |
| Rationale | (a) would bring Out-of-Sample opens into the computation and rely on a filter to drop them; (b) applies the S22-5 rule to the opens. A change to `execution.type` changes every label, so it must invalidate the built files |
| Evidence | §05: "Following session open O(t+2). Exit or rebalance. The week's return is realised here, and only now may it enter a training label." and "Each label has `label_end = O(t+2)`"; contract 7 (commit 89a73eb): "the last In-Sample signal week is the one ending 2019-12-13"; S22-5 (truncation at the In-Sample end); S22-7: "Phase 2.3 writes it, truncated at the In-Sample end like the features"; `01_download_data.py` docstring: "`data/processed/daily_{open,high,low,close}.csv` fully adjusted prices of the tradables on the equity calendar"; Session 2.3a instructions §2: "write data/processed/labels.csv from src.backtest.forward_returns (Mattia's function, imported, not edited) and src.labels.make_labels, using adjusted opens from the same truncated inputs. Keep only rows with label_end ≤ 2019-12-27. Add its entry to data/checksums_features.json" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `03_build_features.py`, `src/features.py` (`features_settings`), `tests/test_build_labels.py`, `data/checksums_features.json`, `docs/interfaces.md` (contract 6) |
| Amendment | No |

### S23-2 · One trial-log row per distinct model specification

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | When `run_walkforward` is called again with an identical spec (a determinism check, or a rerun after a rebuild), does each call append a row to `docs/trial_log.csv`? |
| Options considered | (a) every call appends a row; (b) a row is appended only when the trial log has no row with the same `spec_hash`; (c) a caller option that skips the trial log |
| Decision | (b). `run_walkforward` computes, validates and returns the scores and logs the call as `ok` as before, but appends a trial row only for a `spec_hash` not yet in the trial log. A spec that differs in any key (rung, feature, author, kind, notes, dates) is a different configuration and gets its own row. Open points for both humans: (1) how In-Sample metrics are attached to an existing row once the engine evaluates the scores (Phase 2.3b); (2) the hash covers the spec only, not the config sections that drive the scores, so a rerun after an amended `config.yaml` with the same spec adds no row. Settings are pre-registered and change only by a dated amendment (manual §3.4), but before Phase 3.1 adds grids the team should decide whether the trial key also covers `walkforward_settings(cfg)` |
| Rationale | The deflated Sharpe ratio counts configurations tried; (a) would count a rerun of the same configuration as a second trial and inflate N; (c) would allow an In-Sample evaluation without a row, against manual rule 5 |
| Evidence | Operating manual §3.5: "Every model configuration evaluated on In-Sample data, by a human or an agent, gets a row in `docs/trial_log.csv`. The deflated Sharpe ratio uses that count."; §10: "Deflated Sharpe Ratio with N = every human and agent trial in the ledger"; contract 15 (commit 89a73eb): "Every configuration evaluated on In-Sample data, by a human or an agent, is one row"; Session 2.3a instructions §3: "Append one row to docs/trial_log.csv. The script must be deterministic: two runs give identical files." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contract 15) |
| Files affected | `src/vault.py`, `tests/test_vault.py`, `docs/interfaces.md` (contract 15) |
| Amendment | No |

### S23-3 · Outputs of `05_train_walkforward.py` and the M0 trial spec

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | What exactly do `05_train_walkforward.py --model M0` and its outputs contain, and which spec is logged? |
| Options considered | Summary: (a) with a run timestamp; (b) without any time or machine-dependent field, so that two runs give identical bytes. Spot values: chosen before the run, fixed in the script |
| Decision | (b). The script accepts only `--model M0` until Phase 3.1. It checks `data/processed/features_config.yaml` against `features_settings(cfg)` (`check_used`), builds `Vault(split.in_sample_end)` and calls `run_walkforward` with the spec `{"rung": "M0", "feature": "MOM26_1" (models.M0.feature), "author": "Eliya Allam", "kind": "human", "notes": "M0 In-Sample walk-forward (Phase 2.3a)"}`; every fit asserts the purge (S22-8). It writes to `outputs/walkforward/M0/` (git-ignored): `scores.csv` (contract 8, `%.17g`), `used.yaml` (content: S23-5), which later scripts check with `check_used`, and `summary.json` (sorted keys, LF): `rung`, `spec_hash`, `refits` (folds of contract 13 recomputed through the vault), `rows` (data rows of `scores.csv` = weeks), `weeks`, `values` (non-missing scores), `nan_count`, `first_week` and `last_week` (`date_close`), `column_sums` (per sector), `min`, `max`, five spot values fixed before the run (2008-01-04 XLB, 2008-10-10 XLF, 2012-06-01 XLK, 2016-02-12 XLE, 2019-12-13 XLY) and `scores_sha256`. No timestamp. It computes no performance metric (Phase 2.3b) |
| Rationale | A summary without timestamps lets the reviewer reproduce the run byte for byte from the archived data; the spot values are fixed in advance so they cannot be picked after seeing the scores |
| Evidence | Session 2.3a instructions §3: "Output: the scores frame of contract 8 for the 624 test weeks, 2008-01-04 to 2019-12-13, written to outputs/walkforward/M0/scores.csv, plus used.yaml (check_used) and summary.json (rows, weeks, first/last week, column sums, min, max, and 5 fixed spot values)… The script must be deterministic: two runs give identical files."; §4: "Compute no performance metrics here"; operating manual §6: "Scripts use the skeleton's `check_used` pattern to refuse outputs built with a different config"; manual §3.6 (the scores are a weekly series per ticker derived from prices: they stay under the git-ignored `outputs/`, and only summary values appear in the pull request) |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `05_train_walkforward.py`, `tests/test_walkforward_script.py`, `docs/interfaces.md`, `docs/trial_log.csv` |
| Amendment | No |

### S23-4 · The vault serves the sizing betas

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | How does `06_backtest.py` (Phase 2.3b) obtain the raw BETA52 of contract 10 for sizing, given that all model and research data access goes through the vault? |
| Options considered | (a) 06 reads `data/processed/sizing_betas.csv` directly; (b) a vault method serving it like the other tables |
| Decision | (b). `Vault.sizing_betas(as_of)` returns the rows of `sizing_betas.csv` (weekly index, columns the 9 sectors and IVV, float64) with `date_close ≤ as_of`. The table is in `FRAME_NAMES`, read with the weekly index, validated with `validate_betas` on first use, sealed at the In-Sample end like every table (a later `as_of` raises `OOSAccessError` unless `FROZEN.lock` exists and `unlock()` was called) and every call writes one access-log line, `ok` or `refused`. In-memory `frames` may hold it under the key `sizing_betas` |
| Rationale | One sealed path for every input of the backtest; (a) would bypass the seal and the access log |
| Evidence | Operating manual §3.3: "All model and research data access goes through `src/vault.py`."; contract 10: "raw (not z-scored) `BETA52` of each sector and of IVV against SPY, known after Friday close t, used to size the positions taken at `O(t+1)`"; Session 2.3a instructions, addition 1 (agreed with Mattia for 06): "Vault.sizing_betas(as_of): serve data/processed/sizing_betas.csv … the same way as the other tables: add it to FRAME_NAMES, validate it with validate_betas, seal it at the In-Sample end, and log each access." |
| Proposed by | Eliya Allam and Mattia Cervelli (agreed for Phase 2.3b) |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contract 15) |
| Files affected | `src/vault.py`, `tests/test_vault.py`, `docs/interfaces.md` (contract 15) |
| Amendment | No |

### S23-5 · Config sections in the walk-forward `used.yaml`

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Which settings does `outputs/walkforward/<rung>/used.yaml` hold, given that `06_backtest.py` compares against it with `check_used`? |
| Options considered | (a) `features_settings(cfg)` plus `split` and the rung's `models` entry (first draft of S23-3, never committed); (b) exactly the whole config sections `{seed, data, split, features, models}`, the set agreed with Mattia for 06 |
| Decision | (b). `src.models.walkforward_settings(cfg)` returns `{key: cfg[key] for key in ("seed", "data", "split", "features", "models")}`; `05_train_walkforward.py` saves it with `save_used`. `execution` is not in the set: the labels the scores are trained on are guarded by `data/processed/features_config.yaml` (which holds `execution`, S23-1), checked by 05 before it scores. Open point for Phase 3.1: if `execution` changes and only `03_build_features.py` is rerun, 06's check of this file would still pass with scores trained on the old labels; M0 is not affected (its scores do not use labels) |
| Rationale | Both sides must compare the same set; whole sections are simpler to reproduce in 06 than a derived dictionary |
| Evidence | Session 2.3a instructions, addition 2: "05_train_walkforward.py writes outputs/walkforward/M0/used.yaml with save_used, containing exactly the config sections {seed, data, split, features, models}. Mattia's 06 check_used compares against exactly that set."; operating manual §6: "Scripts use the skeleton's `check_used` pattern to refuse outputs built with a different config" |
| Proposed by | Eliya Allam and Mattia Cervelli (agreed for Phase 2.3b) |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/models.py` (`walkforward_settings`), `05_train_walkforward.py`, `tests/test_walkforward_script.py`, `docs/interfaces.md` (contract 15) |
| Amendment | No |

### S23-6 · Trial identity covers the config; `execution` in `used.yaml`; trial metrics; a display incident

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | (1) Should a trial's `spec_hash` also cover the config that determines the scores (open point (2) of S23-2)? (2) Should the walk-forward `used.yaml` hold `execution` (open point of S23-5)? (3) When are `is_sharpe` and `is_mdd` of the trial log filled (open point (1) of S23-2)? (4) How is the display of raw prices dated after the In-Sample end during this session recorded? |
| Options considered | (1) (a) hash of the spec only (S22-8, S23-2); (b) hash of the spec and the config sections `walkforward_settings(cfg)`. (2) (c) keep `{seed, data, split, features, models}` (S23-5); (d) add `execution`. (3) (e) fill them in Phase 2.3b from `06_backtest.py`; (f) leave them empty until the selection step of Phase 3.1 |
| Decision | (1b), (2d), (3f). (1) `spec_hash(spec, cfg)` is the SHA-256 of the canonical JSON (sorted keys, no spaces) of `{"config": walkforward_settings(cfg), "spec": spec}`; `params_json` stays the spec's canonical JSON. The same spec under a changed walk-forward config section is a new trial and gets its own row; a rerun under the same config still adds none (S23-2). This supersedes the hash definition of S22-8 and S23-2. The M0 row of `docs/trial_log.csv`, not yet on `main`, was recomputed with the new hash (`6ce1693e…420c`, previously `dc69863a…806c`) by resetting the log to its header and rerunning `05_train_walkforward.py --model M0`; the scores are unchanged (`scores_sha256` `7078b900…96a8`). (2) `walkforward_settings(cfg)` = exactly `{seed, data, split, execution, features, models}`, saved as `used.yaml` and compared by `06_backtest.py` with `check_used`; this supersedes the set of S23-5 and closes its open point. (3) `is_sharpe` and `is_mdd` stay empty until Phase 3.1, where the selection step fills them from the outputs of `06_backtest.py`. (4) Incident: during a format check of `data/processed/daily_open.csv` in this session, its last two rows (adjusted opens of 2026-10-15 and 2026-10-16) were displayed. No label, return, metric or plot was computed from them and nothing was written; rule 3 of the operating manual (which covers labels, returns, metrics and plots) was not engaged. Later format checks print only In-Sample rows or metadata |
| Rationale | (1) The deflated Sharpe ratio must count every configuration evaluated; a config change, even through a dated amendment, is a different configuration, so counting it keeps N conservative. (2) `execution.type` determines the labels the scores are trained on from Phase 3.1, so a change must invalidate the walk-forward outputs, not only the label files. (3) The metrics come from 06; the selection step reads them anyway, so filling the rows there avoids a second write path into the trial log. (4) The record must state what was seen even when no rule was broken |
| Evidence | Operating manual §3.5: "Every model configuration evaluated on In-Sample data, by a human or an agent, gets a row in `docs/trial_log.csv`. The deflated Sharpe ratio uses that count."; §3.3: "no code may read, compute or print any label, return, metric or plot for a date after 2019-12-27, except raw data QA"; §10: "Deflated Sharpe Ratio with N = every human and agent trial in the ledger"; S23-1 (labels depend on `execution.type`); Session 2.3a instructions, final addition: "Trial identity: the trial's spec_hash also covers the config sections that determine the scores (walkforward_settings(cfg)), so a changed config is a new trial and the DSR count stays conservative. Recompute the M0 row in docs/trial_log.csv with the new hash; the row is not on main yet." and "used.yaml: add the execution section, so it holds {seed, data, split, execution, features, models}." and "is_sharpe/is_mdd of the trial log stay empty until Phase 3.1, where the selection step fills them from 06's outputs" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contract 15) |
| Files affected | `src/vault.py` (`spec_hash`, `run_walkforward`), `src/models.py` (`walkforward_settings`), `05_train_walkforward.py`, `tests/test_vault.py`, `tests/test_walkforward_script.py`, `docs/trial_log.csv`, `docs/interfaces.md` (contract 15) |
| Amendment | No |

## 2026-11-03 · Session 2.3b: In-Sample backtest of M0

Each entry follows the operating manual §2a. "Instruction" quotes the session 2.3b prompt (2 Nov 2026; restated 3 Nov
2026). "Approved by" lists the approvals given so far; Eliya approves through the review of the 2.3b pull request.

Numbering: these entries were drafted on 2 Nov 2026 as S23-1 to S23-6 on the unmerged 2.3b branch while Eliya's 2.3a
pull request (#8) used the same numbers; they were never committed and are renumbered S23-7 to S23-10 after #8 merged; S23-11 records the diagnostic of the first real-data result.
Two drafts are dropped because S23-4 to S23-6 decide the same points: the betas are read through `Vault.sizing_betas`
(S23-4), and the walk-forward `used.yaml` is checked against `src.models.walkforward_settings(cfg)`, exactly the whole
sections {seed, data, split, execution, features, models} (S23-5, S23-6). `06_backtest.py` imports that function and
`src.features.features_settings` (S23-1) instead of copying them, so the check cannot drift from what 03 and 05 save.

### S23-7 · The three cost scenarios pair `costs.bps` and `costs.borrow` by position

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | `config.yaml` lists the trading costs and the borrow rates as two lists. Which pairs are the baseline and the two stress scenarios? |
| Options considered | (a) pair by position: 5 bps with 1%, 10 bps with 2%, 20 bps with 5% (chosen); (b) all nine combinations |
| Decision | (a). `06_backtest.py: cost_scenarios` zips the two lists, refuses lists of different length or a baseline (`bps_baseline`, `borrow_baseline`) that is not one of the pairs, and labels each scenario `<bps>bps_<borrow %>pct` (`5bps_1pct`, `10bps_2pct`, `20bps_5pct`). The baseline is reported as the headline; the other two are the stress scenarios |
| Rationale | The §09 table defines three named scenarios, each a row with one cost and one borrow rate; (b) would report six combinations that were not pre-registered |
| Evidence | §09 cost table: "Optimistic \| 5 bps \| 1%", "Baseline (reported) \| 10 bps \| 2%", "Adverse \| 20 bps \| 5%"; `config.yaml` `costs: bps: [5, 10, 20]`, `borrow: [0.01, 0.02, 0.05]`. Test `test_cost_scenarios_pair_costs_and_borrow_by_position` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py` |
| Amendment | No |

### S23-8 · Prices, risk-free rate and benchmark of the model backtest

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | The vault serves model inputs, not prices or the T-bill yield. Where does `--model` read them, and which risk-free rate and benchmark enter the metrics? |
| Options considered | Prices and DGS3MO: (a) read the raw files in `06`, cut at the In-Sample end right after reading, behind `refuse_oos_returns` (chosen, as on the ledger path, S21-14); (b) wait for vault accessors for prices and rates |
| Decision | (a). The raw Yahoo files of the 11 tradables and `data/raw/fred/DGS3MO.csv` (`metrics.risk_free_series`) are cut at `split.in_sample_end` right after reading; forward returns come from `src.backtest.forward_returns` on adjusted weekly opens, and `refuse_oos_returns` stops the run, before the engine and before anything is written, if any return is realised after 2019-12-27. Headline rf: `tbill_weekly_returns` (DGS3MO lagged one session, Amendment 1; S21-4), with its compound annual average reported as `rf_tbill_annual`; the constant `metrics.risk_free_constant` (2%) alongside. Benchmark: SPY's forward return on the same weeks (`data.benchmark`, never traded). `period_metrics` is computed for the IS period only; a non-IS week stops the run |
| Rationale | Prices and the T-bill rate are accounting inputs of the engine, not model inputs; they carry no label or score, and the cut plus the guard are the same defence as on the ledger path. (b) would add vault methods that are not needed to keep the seal |
| Evidence | Instruction §1: "computes forward returns with refuse_oos_returns … rf = tbill_weekly_returns (lagged DGS3MO) as the headline and the constant 2% alongside, benchmark SPY"; §11: "Weekly FRED 3-month T-bill (time-varying), with its period average stated on the results slide; the skeleton's constant 2% is shown alongside for comparability"; S21-14 (b). Tests `test_model_backtest_stops_before_any_oos_return` (raw files not cut: the run stops and the engine is never called), `test_model_backtest_writes_the_four_outputs` (Sharpe recomputed from `weekly.csv`) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py` |
| Amendment | No |

### S23-9 · The model backtest writes no trial row

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | Does `06_backtest.py --model` append a row to `docs/trial_log.csv` for each cost scenario or risk-free convention? |
| Options considered | (a) no: the model configuration's row is appended once by `Vault.run_walkforward` when `05` scores it (chosen); (b) one row per scenario |
| Decision | (a). The scenarios and the two rf conventions report one configuration under the pre-registered costs; they are not candidates and are never selected. `06_backtest.py` writes nothing to `docs/trial_log.csv` and is not passed to `run_walkforward` as an evaluator: as S23-6 (3) decided, `is_sharpe` and `is_mdd` stay empty until the selection step of Phase 3.1 fills them from the outputs of `06_backtest.py` (`summary.json`: baseline `net_sharpe_rf_tbill` and `max_drawdown`, S23-10) |
| Rationale | (b) would inflate the trial count that feeds the Deflated Sharpe Ratio with rows that are not separate configurations |
| Evidence | Operating manual §3.5: "Every model configuration evaluated on In-Sample data, by a human or an agent, gets a row in `docs/trial_log.csv`"; contract 15: "`run_walkforward(spec)` … appends one row to `docs/trial_log.csv`"; S23-2 (one row per distinct configuration); S23-6 (3): "`is_sharpe` and `is_mdd` stay empty until Phase 3.1, where the selection step fills them from the outputs of `06_backtest.py`"; §09 table "Baseline (reported)" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py` (no trial-log write) |
| Amendment | No |

### S23-10 · Outputs of `outputs/backtests/<model>/`

| Field | Content |
| --- | --- |
| Date | 2026-11-02 |
| Question | What exactly do `weekly.csv`, `metrics.csv` and `summary.json` hold? |
| Options considered | As below (chosen) |
| Decision | Backtested weeks: the consecutive scored weeks with a realised In-Sample forward return for every traded column (contract 12), entered from cash in the first. `weekly.csv` (weekly index): `realised_on`, `period`, the baseline `gross`, `net`, `turnover` (drifted-weight), `costs`, `borrow`, `residual_beta`, `net_exposure`, `hedge`, plus `cap_binds`, `rf` (weekly T-bill) and `net_<scenario>` of the two stress scenarios; no per-ticker price or return series. `metrics.csv`: one row per (scenario, rf ∈ {`tbill`, `constant`}), every `period_metrics` metric of the IS period. `summary.json`: model, period, baseline label, weeks, `first_week`/`last_week` (`date_close` of the signal weeks), `first_realised_on`/`last_realised_on`; for the baseline `net_sharpe_rf_tbill` (headline), `net_sharpe_rf_constant`, `net_sharpe_zero_cost`, `max_drawdown`, `mean_turnover` (mean weekly drifted-weight turnover, the first week's 1.0 included); `mean_abs_residual_beta` (all weeks, dead-band weeks included), `cap_binding_weeks` (count of `cap_binds`), `missing_input_weeks` (weeks with an Amendment 2 C3 missing input, S21-2), `rf_tbill_annual`, `rf_constant`, `benchmark`, and the same Sharpe, return, drawdown and turnover figures per scenario. `used.yaml`: `used_settings` (`seed`, `split`, `execution`, `signal`, `costs`, `metrics`) ∪ `src.models.walkforward_settings` (S23-6) ∪ {`model`}. All of `outputs/` is git-ignored |
| Rationale | The instruction's list of summary fields, with each definition stated so that `07_evaluate.py` and the reviewer read them the same way |
| Evidence | Instruction §1: "summary.json (weeks, first/last week, net Sharpe under both conventions, max drawdown, mean turnover, mean \|residual beta\|, cap-binding weeks). Everything is git-ignored."; operating manual §3.6; `.gitignore` `outputs/*`. Tests `test_model_backtest_writes_the_four_outputs` (Sharpe, rf average, turnover, residual beta and cap-binding count recomputed from `weekly.csv`), `test_model_backtest_counts_a_missing_score_week` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 2 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py` |
| Amendment | No |

### S23-11 · Diagnostic of the M0 In-Sample result

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | The first real-data run of `06_backtest.py --model M0` (3 Nov 2026) gave a baseline net Sharpe of −0.77 (T-bill) and a max drawdown of −48% over 624 In-Sample weeks, although the score sums favour XLK and XLY and penalise XLE. Is this an accounting, sign or timing error, or the result of the pre-registered rule? How is the check recorded? |
| Options considered | (a) report the result as computed, after a read-only diagnostic of the same configuration, recorded here (chosen); (b) report it without a check; (c) change a setting, feature or the code because of the result (excluded: operating manual §3.4 and §3.8) |
| Decision | (a). One script outside the repository read the same inputs through the functions of `06_backtest.py` (`read_scores`, `read_betas` through the sealed vault, `in_sample_market` with `refuse_oos_returns`), ran `size_book` and `run` at zero cost, and checked: (1) the signals of `size_book` against an independent top-2 / bottom-2 ranking of the scores with alphabetical ties: identical in all 624 weeks; (2) timing: the first forward return of the week ending 1998-12-04 is realised on 1998-12-14, the open of week t+2 (contract 7); (3) the legs, annualised weekly means: core (0.25·s) −2.18%, of which long legs +3.72% and short legs +5.90%; IVV hedge leg +0.12%; gross −1.48%; (4) the mean weekly cross-sectional rank IC of the MOM26_1 score against the forward returns: 0.0045 (t = 0.25); (5) a one-week-shift look-ahead check, the scores of week t+1 against the returns of week t: IC 0.0106, larger than at t, as expected when no future information enters at t. The positions agree with the score sums (XLK long 162 weeks, short 59; XLE long 131, short 258). Net −4.7% a year = gross −1.5% minus about 2.1% of trading costs (mean turnover 0.40 a week × 10 bps × 52) and the borrow charge. No accounting, sign or timing error was found: the result is the pre-registered rule's. No code, setting, feature, threshold, grid or score was changed because of the result; the outputs of `outputs/backtests/M0/` are those of the first run. The diagnostic evaluated no new configuration, so it adds no trial row (S23-2); the M0 row's `is_sharpe` and `is_mdd` stay empty (S23-6 (3)) |
| Rationale | A result far from expectation must be checked for errors before it is reported, and the record must show that the check could not have changed the result |
| Evidence | `outputs/backtests/M0/summary.json` (3 Nov 2026): `net_sharpe_rf_tbill` −0.7714, `max_drawdown` −0.4798, `mean_turnover` 0.4004; `outputs/walkforward/M0/summary.json`: `scores_sha256` `7078b900…96a8`, as recorded in S23-6; operating manual §3.4: "Don't add, remove or retune anything that isn't pre-registered", §3.8: "Never weaken a test or a threshold to make it pass", §6: "the one-week-shift test must not improve results" (here it is a look-ahead check on the scores: a higher IC with future scores shows that week t's scores hold no future information) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026 ("Investigating a bad result is fine; changing anything because of it is not"); Eliya Allam: PR review |
| Files affected | `docs/decisions.md` only |
| Amendment | No |

## 2026-11-03 · Session 3.2: backtests of every model, In-Sample evaluation, shift check, placebo and plots

Each entry follows the operating manual §2a. "Instruction" quotes the session 3.2 prompt (3 Nov 2026); "Answer" quotes
Mattia's answers to the two questions asked during the session (3 Nov 2026). "Approved by" lists the approvals given so
far; Eliya approves through the review of the 3.2 pull request.

### S32-1 · `--model` accepts any walk-forward folder; `--all`

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which names does `06_backtest.py --model` accept, now that the walk-forward writes fixed variants (e.g. `M3_d2`, `M0_L13`) besides the rungs? |
| Options considered | (a) keep the closed list `M0`, `M0_star` and `models.candidate_order` of S23-10; (b) any folder of `outputs/walkforward/` that holds a `scores.csv` (chosen) |
| Decision | (b). `walkforward_models()` lists the folders of `outputs/walkforward/` with a `scores.csv` whose name matches `[A-Za-z0-9][A-Za-z0-9_]*`; `check_model` refuses any other name (no path separators, no `..`) and a name without scores. `--all` checks every score file (`check_used` of `walkforward_settings`, no week after the In-Sample end) before any real-data input is read, then reads the vault betas, the market cut at the In-Sample end and the T-bill once (`InSampleInputs`) and backtests every folder. The checks, the vault access and the OOS guard are those of S23-4 to S23-10, unchanged. The test `test_model_backtest_refuses_an_unknown_model` (closed list) is replaced by `test_model_backtest_refuses_a_model_without_walkforward_scores`, which still refuses `M9` and also refuses `../M0`, `M0/..`, `M-0` and the empty name |
| Rationale | A fixed variant is a separate configuration with its own walk-forward output and trial row; the folder, not a list in the code, says what exists |
| Evidence | Instruction §1: "06_backtest.py --model NAME for any directory under outputs/walkforward/ (rungs and fixed variants, e.g. M1, M3_d2, M0_L13), and --all. Same check_used, vault access and OOS guard as M0." Tests `test_walkforward_models_lists_folders_with_scores`, `test_a_fixed_variant_folder_is_backtested`, `test_all_backtests_every_folder_with_one_vault_read`, `test_diagnostics_stop_before_any_oos_return[--all]` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py` |
| Amendment | No |

### S32-2 · Exposure columns of `weekly.csv`

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | The exposure plot needs the long and short legs, which `weekly.csv` (S23-10) does not hold. Are they added, and does it change the rule that no per-ticker series is written? |
| Options considered | (a) add `long_exposure` = Σ w⁺ and `short_exposure` = Σ w⁻ of the baseline book, IVV included (chosen); (b) write the 10 weight columns; (c) re-run the engine in `07_evaluate.py` |
| Decision | (a). `weekly.csv` gains the two columns; every column of S23-10 is unchanged (on real data, `summary.json` of M0 is byte-identical to the 2.3b run and the old columns of `weekly.csv` are equal). Σ|w| = 1 gives `long_exposure − short_exposure` = 1, and Σw = `net_exposure` (the IVV weight, because the core is dollar-neutral); both are tested. Still no per-ticker price, return or weight series |
| Rationale | Two aggregate columns are enough for the §11 exposure chart; (b) and (c) add data or a second engine run that the chart does not need |
| Evidence | §11: "Added: … weekly residual beta and net dollar exposure"; S23-10: "no per-ticker price or return series"; test `test_weekly_exposures_add_up`; real-data comparison with the 2.3b outputs (session log, 3 Nov 2026: "summary.json identical"; "new columns: ['long_exposure', 'short_exposure'] \| old columns identical: True") |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py` |
| Amendment | No |

### S32-3 · The §12 one-week-shift check: definition, verdict rule and the `src/stats.py` hooks

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | (1) What is "M0 with its signals delayed one extra week"? (2) What counts as "outperforming"? (3) How are the rank IC and the paired bootstrap computed while `src/stats.py` is a Phase 3.1 stub? |
| Options considered | (1) (a) delay the scores one row of the weekly index and re-size the hedge from week t's BETA52 (chosen); (b) delay the whole book, hedge included. (2) (c) any higher net Sharpe fails; (d) fail only if the delayed book has the higher net Sharpe and the paired bootstrap gives P(delayed > base) ≥ 0.80 (chosen). (3) (e) hooks that call `src.stats` and report "pending" while it raises `NotImplementedError` (chosen); (f) a local implementation in Mattia's files |
| Decision | (1a): `delayed_scores` gives week t the scores of week t − 1 on the full weekly index (a week whose previous week has no score is a missing input, Amendment 2 C3); the first scored week has no delayed score, so the two books are compared on their common weeks (623 for M0), with baseline costs and the weekly T-bill. (2d): `shift_verdict` returns FAIL only if the delayed net Sharpe (T-bill) is higher and P(delayed > base) ≥ `selection.bootstrap_prob`; PENDING if it is higher and the bootstrap is not available; PASS otherwise. The bootstrap uses `selection.bootstrap_resamples`, `selection.bootstrap_block` and `seed`, on the paired weekly net returns (delayed as candidate, base as baseline). A FAIL is investigated, never fixed by a change of settings. Reported side by side: net Sharpe (both conventions), gross Sharpe, return, drawdown, turnover, mean rank IC and P. (3e): `stats_hook(name, …)` returns `None` while `src.stats.<name>` raises `NotImplementedError`. The keys read are `p_uplift_positive` (`BOOTSTRAP_P_KEY`) and `mean` (`RANK_IC_MEAN_KEY`); contract 16 does not name the keys, so Eliya confirms or renames them in the review of this pull request, and a bootstrap result without the key stops the run. `shift_check(cfg, model)` runs on any walk-forward folder (`--shift-check M1 M2 …`), so the same check runs on every candidate at Gate 3 |
| Rationale | (1a) moves only the signal timing; the hedge rule stays identical. (2d) M0's rank IC is about zero (0.0045, S23-11), so a delayed book can beat it by noise; the bootstrap threshold of the selection rule separates noise from a real timing gain. (3e) keeps one implementation of each statistic, in its owner's file |
| Evidence | Instruction §3: "Leakage check (§12): M0 with its signals delayed one extra week must not outperform M0. Report both."; protocol §12 table, lookahead row: "One-week-shift test must not improve results"; Answer 2: "Option 1. Report M0 and M0-delayed side by side: net Sharpe, mean rank IC and the paired bootstrap P(delayed > M0). M0 has almost no signal (IC 0.0045), so the delayed version can beat it by noise. Treat the check as failed only if the delayed version is better with bootstrap P ≥ 0.80, and investigate it then. Make the function generic, so the same check runs on every candidate rung in Phase 3.2/Gate 3. Record the rule as an S32 decision."; `config.yaml` `selection.bootstrap_prob: 0.80`. Planted test `test_shift_check_flags_scores_that_are_one_week_early` (scores equal to the next week's forward return: the delayed book wins and, with P = 1, the verdict is FAIL); `test_shift_verdict`, `test_delayed_scores_hand_case` |
| Proposed by | Mattia Cervelli (definition and hooks); Mattia Cervelli, Answer 2 (verdict rule) |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review (including the two key names) |
| Files affected | `06_backtest.py`, `07_evaluate.py`, `tests/test_backtest_script.py`, `tests/test_evaluate_script.py` |
| Amendment | No: applies §12; the verdict rule reuses the pre-registered bootstrap threshold |

### S32-4 · The §11 placebo: count, seeds, weeks and percentile

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How are the "1,000 random ±2/±2 portfolios with the same hedge rule, fixed seeds" built, where do the count and the seeds live, and how is a model's percentile defined? |
| Options considered | Count: (a) a separate `config.yaml` pull request; (b) a new additive `placebo:` section in this pull request (chosen); (c) a constant in `06_backtest.py`. Seeds: seed + offset + i (chosen); a `SeedSequence` spawn |
| Decision | `config.yaml` gains `placebo: {books: 1000, seed_offset: 1000000}`, an additive section like `ledger:` (S21-11), flagged in the pull request body; it is not part of any `used.yaml` checked by the backtests (the M0 outputs stay valid). Book i (0-based) draws standard normal sector scores with `numpy.random.default_rng(seed + seed_offset + i)` (`random_scores`), seeds 1000042 to 1001041, disjoint from the ledger books (seed + 100·year + book, at most 201951). Each book goes through the same `size_book` (top 2 / bottom 2, alphabetical ties, BETA52 hedge through the vault, cap, dead-band, scaling) and `run` with the baseline costs, on the scored weeks of a reference model (`--placebo` defaults to M0; 624 weeks, 2008-01-04 to 2019-12-13). Statistic: net Sharpe with the weekly T-bill. Percentile of a model: 100 · (#{placebo < model} + ½ #{placebo = model}) / n, computed by `07_evaluate.py` for every model on the same weeks. Because random books are redrawn every week, their turnover is far above a model's; the percentile of the gross zero-cost Sharpe is reported alongside as information only |
| Rationale | The count is pre-registered, so it comes from `config.yaml` like every setting; an offset keeps the placebo seeds apart from the ledger seeds; the same sizing and costs make the placebo differ from the model only in the scores |
| Evidence | §11 comparator table: "1,000 random ±2/±2 portfolios with the same hedge rule, fixed seeds \| How much is luck? \| Placebo (skeleton's random baseline)"; skeleton `docs/metrics.md` robustness table: "Random baseline \| Compare with random signals \| A good strategy should clearly beat random signals"; operating manual §3.4; Answer 1: "Option 2: add placebo: {books: 1000, seed_offset: ...} as a new additive section, flagged in the PR body under the S21 shared-file exception. Seed rule: book i uses config.seed + offset + i; record it as an S32 decision." Tests `test_placebo_seeds_follow_the_config`, `test_placebo_settings_refuse_bad_values`, `test_placebo_percentile_hand_case`, `test_placebo_books_are_seeded_and_on_the_reference_weeks` (two runs give the same summary) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026 (Answer 1); Eliya Allam: PR review (shared file) |
| Files affected | `config.yaml`, `06_backtest.py`, `07_evaluate.py`, `tests/test_backtest_script.py`, `tests/test_evaluate_script.py` |
| Amendment | No: implements the pre-registered placebo |

### S32-5 · The shift check and the placebo are not trials

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Do the delayed book and the 1,000 placebo books get rows in `docs/trial_log.csv`? |
| Options considered | (a) no row (chosen); (b) one row each |
| Decision | (a). They are diagnostics of a configuration that already has its trial row: they are not candidates, are never selected and their scores do not come from a model. `06_backtest.py` writes nothing to the trial log in any mode (S23-9) |
| Rationale | The Deflated Sharpe Ratio counts the configurations among which the winner was chosen; 1,001 diagnostic rows would inflate N with books that could never be chosen |
| Evidence | Operating manual §3.5: "Every model configuration evaluated on In-Sample data, by a human or an agent, gets a row in `docs/trial_log.csv`. The deflated Sharpe ratio uses that count."; §11: "Selection bias \| Deflated Sharpe Ratio, N = all human and agent trials \| Is the winner more than the luckiest of N?"; S23-9 |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | none (no trial-log write) |
| Amendment | No |

### S32-6 · Plot conventions and the refined `src/plots.py` signatures

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How are the §11 charts dated, coloured and written, and which arguments do the stubs of contract 17 take? |
| Options considered | As below (chosen); keep the stub argument lists `equity_curves(returns, period, path)`, `exposures(result, path)` |
| Decision | Each chart writes `path.html` (plotly; `plotly.min.js` written once into the folder, so the files open offline) and `path.png` (matplotlib, `Figure` objects, no display backend). Equity and drawdown points are dated by `realised_on` (the open of week t + 2), and each period starts at 100 on the execution date of its first week (the open of week t + 1), as in the skeleton's `plots.equity_curves`; equity on a log axis. Signatures: `equity_curves(returns, period, realised_on, path, *, title)`, `drawdowns(returns, period, realised_on, path, *, title)` (`realised_on` added: the weekly index alone does not give the realisation dates), `exposures(result, path, *, title)` with `result` a `BacktestResult` or a frame with `long_exposure`, `short_exposure`, `net_exposure`, `residual_beta` (07 reads `weekly.csv`, not a `BacktestResult`); residual beta in its own panel (another unit). New: `cost_bridge(weekly, path)`, the waterfall gross → −costs → −borrow → net of the mean weekly returns × 52 (arithmetic, so the steps add up exactly; the compound net return is in the tables), and `placebo_histogram(sharpes, marks, path)`. Colours follow the entity: fixed categorical slots per rung (M0 blue, M1 orange, M2 aqua, M3 yellow, M5 magenta, ENS green, M0_star violet), a variant `<rung>_<x>` its rung's colour dashed; benchmarks grey, the T-bill dotted. The equal-weight basket is the skeleton's: 1/9 of each sector's forward return, rebalanced weekly, no cost. `docs/interfaces.md` contract 17 is updated in this pull request; `tests/test_module_stubs.py` moves `src.plots` from the stub list to the implemented list (its row only) |
| Rationale | Contract 17 lets the owner refine a stub's argument list in the phase pull request; the dating follows the skeleton the graders know |
| Evidence | §11: "Every series starts at 100 in each period, on a shared dated axis, log scale." and "Added: … a gross → after-costs → after-borrow bridge"; Amendment 2 C5; skeleton `src/plots.py: equity_curves` ("Equity curve of every series, starting at 100 in each period, dated when each return is realized"); skeleton `docs/metrics.md`: "Equal weight \| (1/N) Σ R^fwd_{t,i}"; contract 17: "a stub's exact argument list is a proposal that its owner may refine in the phase pull request, which the other author reviews"; tests `tests/test_plots.py` (hand cases: 100 → 110 → 55 → 66 dated by realisation; drawdown 0, 0, −50%, −40%; restart at 100 per period; the bridge adds up; HTML and PNG written) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review (contract 17, `tests/test_module_stubs.py`) |
| Files affected | `src/plots.py`, `tests/test_plots.py`, `tests/test_module_stubs.py`, `docs/interfaces.md` |
| Amendment | No |

### S32-7 · `07_evaluate.py`: In-Sample only, inputs and outputs

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | What does `07_evaluate.py` read and write, and how does it make sure that it shows nothing after 2019-12-27? |
| Options considered | As below (chosen) |
| Decision | Reads every `outputs/backtests/<model>/` (not `synthetic`) after `check_used` of its `used.yaml` (`backtest_used`: `used_settings` ∪ `walkforward_settings` ∪ {model}), and the shift checks and the placebo after `check_used`; stops (nothing written) if any weekly row has a period other than IS, a signal week after `split.in_sample_end` or a return realised after it. SPY and the equal-weight basket come from `06_backtest.py: in_sample_market` (raw files cut at the In-Sample end, `refuse_oos_returns`), the T-bill from `weekly.csv`. Writes `outputs/metrics/is_models.csv` (one row per model, baseline costs: net Sharpe with the T-bill and with the constant 2%, zero-cost and gross Sharpe, return, volatility, Sortino, drawdown, Calmar, hit rate, turnover, holding period, the bridge terms, beta, correlation, alpha, residual beta, cap and missing-input weeks, the stress Sharpes, `rank_ic_mean` through the hook of S32-3, `placebo_percentile`), `is_benchmarks.csv` (T-bill, SPY, equal weight on M0's weeks), `shift_check.csv`, `placebo.csv`, `used.yaml`, and the plots of S32-6 in `outputs/plots/` (`<model>_equity`, `_drawdown`, `_exposure`, `_bridge`, `all_models_equity` for the models on M0's weeks, `placebo_sharpe`). The §07 selection gate is not applied here (Phase 3.1, `src.stats.selection_gate`) |
| Rationale | One table the selection step and the slides read; the IS check is a second guard behind the one in 06 |
| Evidence | Instruction §2: "07_evaluate.py, In-Sample only: one table of every model's IS metrics (net Sharpe under both conventions, MDD, turnover, rank IC hook) plus src/plots.py: equity curves rebased to 100 (strategy vs T-bill vs SPY vs equal weight, log scale, IS only), drawdowns, exposures, and the gross → costs → borrow bridge."; operating manual §3.3; tests `tests/test_evaluate_script.py` (a week labelled OOS and a return realised on 2019-12-30 are refused before anything is written; a backtest or placebo built with another config is refused) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `07_evaluate.py`, `tests/test_evaluate_script.py` |
| Amendment | No |

### S32-8 · First real-data results of the shift check and the placebo (M0)

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | What did the first runs give, and how are they read? |
| Options considered | Report as computed (chosen); change anything because of them (excluded: operating manual §3.4, §3.8) |
| Decision | Shift check (`06_backtest.py --shift-check M0`, 623 common weeks 2008-01-11 to 2019-12-13, 10 bps / 2%): net Sharpe (T-bill) M0 −0.7767, delayed −0.8039; zero-cost −0.6897 / −0.7152; gross zero-cost −0.2564 / −0.2727; max drawdown −47.98% / −47.39%; mean turnover 0.3994 / 0.4004. The delayed book is not better, so the verdict is PASS whatever the bootstrap gives; P and the rank IC are pending `src/stats.py`. Placebo (`--placebo`, 1,000 books on M0's 624 weeks): net Sharpe mean −1.819, sd 0.280, 5% −2.286, median −1.828, 95% −1.364, mean turnover 1.555 a week; M0 −0.771, percentile 100.0. Before costs, M0's gross zero-cost Sharpe −0.249 against a placebo median of −0.025: percentile 22.1. M0 beats every random book after costs because it trades about a quarter as much (0.40 against 1.56 a week), not because its ranking is better than random; this is how the placebo result is reported. Benchmarks on the same weeks: SPY Sharpe 0.487, equal weight 0.476, T-bill average 0.60% a year. M0's numbers equal those of S23-11 (`summary.json` byte-identical). No code, setting or score was changed because of these results |
| Rationale | The placebo's net comparison mixes skill and trading frequency; stating both percentiles keeps the reading honest |
| Evidence | `outputs/metrics/shift_check.csv`, `outputs/metrics/placebo.csv`, `outputs/metrics/is_benchmarks.csv` (3 Nov 2026); `outputs/diagnostics/placebo/summary.json`; S23-11 |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `docs/decisions.md` only |
| Amendment | No |

## 2026-11-03 · Session 3.1: model ladder and inference statistics

Format of the operating manual's evidence standard. "Session 3.1 instructions" quotes the task list Eliya set for the
session (3 Nov 2026). "Approved by" is completed by Mattia's approving review of the pull request from branch
`feat/3.1-ladder`, which also carries Amendment 5 (commit a510085, committed alone before any code of this session).

### S31-1 · Forward returns file and `Vault.forward_returns`

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | In which format does `03_build_features.py` write the forward returns that the inner Sharpe of Amendment 5 C1 needs, and what does `Vault.forward_returns(as_of)` return? |
| Options considered | File: (a) only the rows with a realised return; (b) the full truncated weekly index of contract 7, whose last two rows (weeks ending 2019-12-20 and 2019-12-27) are `NaN`/`NaT` because the opens end on 2019-12-27. Vault slice: (c) rows with `date_close ≤ as_of`; (d) rows with `realised_on ≤ as_of` |
| Decision | (b) and (d). `03_build_features.py: build_forward_returns(daily_open, daily_close, is_end)` truncates both inputs at `split.in_sample_end`, calls `src.backtest.forward_returns` (Mattia's, imported, unchanged) and refuses (`OOSAccessError`) any `realised_on` after the In-Sample end; `build_labels` now starts from it, so labels and forward returns come from one computation. `data/processed/forward_returns.csv` (git-ignored) holds the weekly index, the 11 tradables of contract 7, `realised_on` and `period`; it passes `validate_forward_returns` as a whole, every `realised_on` is ≤ 2019-12-27 or `NaT`, every `period` is `IS` or missing, and its checksum entry is added to `data/checksums_features.json`. `write_tables` refuses a `realised_on` after the In-Sample end like a late `label_end`. `Vault.forward_returns(as_of)` returns `(fwd, realised_on, period)` on the rows with `realised_on ≤ as_of`, i.e. returns already realised at `as_of`, like `labels(as_of)`; it is sealed (an `as_of` after `is_end` raises `OOSAccessError` unless `FROZEN.lock` exists and `unlock()` was called), validated as a whole on first read and logged `ok` or `refused` like every vault call. A slice does not pass the "last two rows NaN" rule of `validate_forward_returns`, which applies to the full table |
| Rationale | (b) keeps one validated file in the exact contract-7 shape; (d) uses the knowledge date of a return, which is the only safe slice for a training window (c would hand out returns realised after `as_of`) |
| Evidence | Session 3.1 instructions §2: "03_build_features.py also writes data/processed/forward_returns.csv (contract 7, only rows realised ≤ 2019-12-27), and the vault serves it as Vault.forward_returns(as_of): sealed, logged, refusal tested. The inner Sharpe of C1 needs it, together with Vault.sizing_betas."; contract 7: "`realised_on` … `date_open` of week t+2 … `NaT` on the last two rows"; S23-1 (labels from the truncated opens); manual §3.3 "All model and research data access goes through `src/vault.py`" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contracts 7 and 15) |
| Files affected | `03_build_features.py`, `src/vault.py`, `tests/test_build_labels.py`, `tests/test_vault.py`, `data/checksums_features.json`, `docs/interfaces.md` |
| Amendment | No |

### S31-2 · Trial specs of the ladder; tuning settings in the spec, not in `walkforward_settings`

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How does a spec name a rung run with the Amendment 5 C1 rule, a fixed grid value or ENS, and how do the settings that drive the C1 choice (inner window, costs, sizing, tie order) enter the trial identity of S23-6? |
| Options considered | (a) add `signal`, `costs`, `metrics` and a new tuning section to `walkforward_settings(cfg)`; (b) keep `walkforward_settings(cfg)` = `{seed, data, split, execution, features, models}` and put the C1 settings into the spec of every tuned run, built from `config.yaml` |
| Decision | (b). The vault accepts three new spec keys (`SPEC_KEYS` gains `params`, `tuning`, `members`; every other unknown key is still refused, S22-12). Forms: M0 `{"rung": "M0", "feature": F}` (unchanged); fixed grid value `{"rung": "M1"\|"M2", "params": {"alpha": a}}` or `{"rung": "M3", "params": {"max_depth": d}}`, the value taken from the `config.yaml` grid (any other value is refused); C1 rung `{"rung": "M1"\|"M2"\|"M3"\|"M0_star", "tuning": T}`; ENS `{"rung": "ENS", "members": ["M1", "M2", "M3"], "tuning": T}`. `T = src.models.tuning_spec(cfg)` = `{"rule": "Amendment 5 C1", "tuning": cfg["tuning"], "cost_bps": costs.bps_baseline, "borrow_annual": costs.borrow_baseline, "sharpe": "zero_cost", "signal": cfg["signal"], "periods_per_year": metrics.periods_per_year}`; the vault refuses a `tuning` that differs from it. A rung with a grid must state exactly one of `params` or `tuning`. New additive config sections, flagged in the pull request: `tuning` (`inner_validation_weeks: 104`, `tie_order` per rung, S31-3) and `inference` (`pbo_blocks: 16`, `confidence: 0.95`, S31-8, S31-9) |
| Rationale | (a) would change the `spec_hash` of the M0 trial already on `main` (a second M0 row for an identical configuration) and the `used.yaml` set agreed with Mattia for `06_backtest.py` (S23-5, S23-6); (b) still makes every setting that determines a tuned run's scores part of its `spec_hash` (the spec is hashed with the config), so a changed cost or window is a new trial, and leaves M0 and 06 untouched |
| Evidence | S23-6: "`spec_hash(spec, cfg)` is the SHA-256 of the canonical JSON … of `{"config": walkforward_settings(cfg), "spec": spec}`" and its rationale "The deflated Sharpe ratio must count every configuration evaluated"; S23-5: "Mattia's 06 check_used compares against exactly that set"; Amendment 5 C1 (inner window 104 weeks, baseline costs, §09 sizing, ties); Session 3.1 instructions §6: "Any new settings (e.g. pbo_blocks: 16) go in a new additive config section, flagged in the PR." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contract 15; shared file `config.yaml`) |
| Files affected | `config.yaml`, `src/models.py`, `src/vault.py`, `05_train_walkforward.py`, `tests/test_vault.py`, `docs/interfaces.md` |
| Amendment | No |

### S31-3 · Implementation of the Amendment 5 C1 choice

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How exactly are the inner split, the inner backtest, the Sharpe and the ties of Amendment 5 C1 computed? |
| Options considered | As below (chosen); the alternatives were a tolerance-free tie test and a fresh state scaling only at the outer fit |
| Decision | For a refit record `f` (contract 13): the training weeks are the weeks with `date_close` in `[f.train_start, f.train_end]` that have a label; the validation weeks are the last `tuning.inner_validation_weeks` (104) of them, from `V` (their first `date_close`) to `f.train_end`; the inner purge limit is `V − 7 × split.embargo_weeks` days and the inner training weeks are the training weeks with `label_end` at most that limit. `src.models.inner_fold` returns this split as a `WalkForwardFold` that keeps the outer `test_year` and `refit` (used in messages only; it is not passed to `validate_folds`, whose same-year rule fits outer folds only). Every inner fit calls `assert_purged` with the inner limit, every outer fit with `f.purge_end`, and every validation week must have `realised_on ≤ f.purge_end` (so no return realised after the cutoff enters the choice). For each grid value the rung is fitted on the inner training rows (the market-state scaling of S22-6 is refitted on the inner training weeks), scores the validation weeks, and the book is built with `src.sizing.size_book` (the §09 sizing from `signal.*`) and `src.backtest.run` at `costs.bps_baseline` and `costs.borrow_baseline` (both Mattia's, imported, unchanged), entered from cash in the first validation week. The inner Sharpe is `src.metrics.annualized_return(net) / src.metrics.annualized_volatility(net)` (zero-cost convention). The highest Sharpe wins; values within 1e-12 of the best are ties and go to the first of `tuning.tie_order` (M1 and M2 `[10, 1, 0.1]`, M3 `[2, 3]`, M0\* `[26, 13, 52]`); a `NaN` Sharpe never wins unless all are `NaN`, when the first of the tie order is taken. Then the rung is refitted with the chosen value on all training rows of `f` and scores `f.test_start … f.test_end`. Open point for Phase 4: §07 says the refits continue during OOS but "tuning does not"; whether OOS refits keep the last In-Sample choice or apply C1 again must be settled before `08_run_oos.py` is written |
| Rationale | The 1e-12 tolerance matters: two values often give the same ranking every week, hence bit-identical books and Sharpes, and the tie rule then decides. For M0\*, Amendment 5 names only the 26-week lookback; between 13 and 52 the order takes the lookback nearer to 26 (13) |
| Evidence | Amendment 5 C1: "Each value is fitted on the window minus its last 104 weeks (inner training, with labels purged and a one-week embargo before the inner validation start) and scored on those 104 weeks. The value with the highest net Sharpe of the hedged book (zero-cost convention, annualised return / volatility) at baseline costs (10 bps, 2% borrow), with the §09 sizing, is chosen, and the rung is refitted with it on the full training window. Ties go to the simpler value: the larger λ, the smaller depth, the 26-week lookback."; §07 "The same refits continue during OOS on newly realised labels; tuning does not."; §06 "Scaling and winsorising fitted inside each training fold"; Session 3.1 instructions §3: "One shared helper implements C1 for every grid, calling src.sizing.size_book and src.backtest.run (Mattia's, imported, never edited). Every refit asserts the purge for both the inner and the full fit." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/models.py`, `config.yaml` (`tuning`), `tests/test_ladder.py` |
| Amendment | No (applies Amendment 5 C1) |

### S31-4 · Ridge (M1, M2) and LightGBM (M3) settings

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which estimator settings, beyond the pre-registered grid values, do M1–M3 use, and how are missing inputs handled? |
| Options considered | Library defaults except where §07 or determinism requires a value (chosen); tuning further parameters (refused: not pre-registered) |
| Decision | M1: `sklearn.linear_model.Ridge(alpha=λ)` on the six z-scored asset features (the design of `fit_transform_train(..., interactions=False)`), target `y` of contract 6, library defaults otherwise (`fit_intercept=True`, `solver="auto"`). M2: the same on the design with the five interactions (`fit_transform_train` / `transform_test`, `interactions=True`). M3: `lightgbm.LGBMRegressor` on the M2 design with `max_depth` from the grid, `n_estimators=models.M3.n_estimators` (200), `learning_rate=models.M3.learning_rate` (0.03), `num_threads=models.M3.num_threads` (1), `deterministic=True`, `random_state=config.seed` (42); the other parameters set are `force_row_wise=True` (LightGBM's documentation asks for `force_row_wise` or `force_col_wise` with `deterministic=True`) and `verbose=-1` (no console output). Everything else is the library default: L2 objective, `num_leaves=31` (above 2^3, so the depth grid alone limits tree size), `min_child_samples=20`, no row or column subsampling, no regularisation. `fit` refuses a non-finite input or label (after the warm-up every training input is finite); `score` gives `NaN` to a row with any missing input, which the sizing treats as a missing score (Amendment 2 C3) |
| Rationale | Only the pre-registered values and what determinism needs are set, so no unregistered tuning enters |
| Evidence | §07 table: "M1 \| Ridge on 6 asset features \| … \| λ ∈ {0.1, 1, 10}", "M3 \| LightGBM on M2 inputs \| … \| depth ∈ {2, 3}; 200 trees; learning rate 0.03; fixed seed; deterministic; 1 thread"; contract 14 "LightGBM with `deterministic=True`, `num_threads=1`, `seed`"; Session 3.1 instructions §3: "M3: LightGBM regressor on the M2 design: max_depth from the grid, n_estimators 200, learning_rate 0.03, num_threads 1, deterministic=True, seed from config. Record every other parameter you set as a decision."; LightGBM parameter documentation, `deterministic`: "to avoid potential instability due to numerical issues, please set force_col_wise=true or force_row_wise=true when setting deterministic=true" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/models.py`, `tests/test_ladder.py` |
| Amendment | No |

### S31-5 · ENS

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which member scores does ENS average, how are they ranked, and what happens in a week with a missing member score? |
| Options considered | Members: (a) the C1 rungs M1, M2, M3; (b) fixed grid values. Missing: (c) average the members present; (d) the whole week missing |
| Decision | (a) and (d). Each week, each member's 9 scores are ranked cross-sectionally (1 = lowest, ties get their average rank) and the ENS score is the equal-weight mean of the member ranks. A week where any member lacks any sector score is `NaN` for every sector, so the sizing carries the previous book (Amendment 2 C3). ENS has no fit and no grid; each member's week-t score comes from that member's own refit, so ENS uses no information after the cutoff. Equal ENS scores are broken alphabetically by the §09 rule in `signals_from_scores`. M5 joins the members in Phase 3.3 (the spec's `members` changes, so it is a new trial) |
| Rationale | §07 defines ENS on the rungs, not on grid values; averaging the members present would change the scale and the meaning of the score from week to week |
| Evidence | §07 table: "ENS \| Equal-weight average of the cross-sectional rank scores of M1–M3 (+ M5 if it exists)"; §09 step 2 "break exact ties alphabetically by ticker"; Session 3.1 instructions §3: "ENS: each week, the equal-weight average of the cross-sectional ranks of M1, M2 and M3 (M5 added in Phase 3.3)." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/models.py`, `tests/test_ladder.py` |
| Amendment | No |

### S31-6 · M0\* and the fixed lookbacks

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which momentum columns do M0\* and the fixed runs `M0_L13`, `M0_L26`, `M0_L52` use, and is `M0_L26` a new trial? |
| Options considered | `M0_L26`: (a) a new spec on the variant `MOM26_1`; (b) the M0 trial itself |
| Decision | M0\* scores `MOM{L}_1` of `momentum_variants.csv` (contract 3) with L chosen per S31-3; its `fit` is a no-op, so the inner "fit" only scores the validation weeks. `M0_L13` and `M0_L52` are M0 specs with `feature` `MOM13_1` and `MOM52_1`. (b): `M0_L26` runs exactly the M0 spec of trial 1, so it has the same `spec_hash` and adds no row (S23-2); its outputs are written under `outputs/walkforward/M0_L26/` for the PBO matrix |
| Rationale | The variant `MOM26_1` equals the feature `MOM26_1` on the built data (maximum absolute difference 0.0 over all rows), so `M0_L26` and M0 are one configuration; a second row would count it twice in N |
| Evidence | §07 table: "M0\* (fallback) \| M0 with lookback chosen at each refit from {13, 26, 52} weeks"; contract 3: "M0\* variants … `MOM13_1`, `MOM26_1`, `MOM52_1` = `ln TR(t − 1w) − ln TR(t − L w)`"; S23-2 "a rerun of the same configuration" adds no row; Session 3.1 instructions §4: "--fixed for each grid value (… M0_L13/26/52)" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `05_train_walkforward.py`, `src/models.py`, `src/vault.py` |
| Amendment | No |

### S31-7 · Trial counting rule

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | What is N for the Deflated Sharpe Ratio and which configurations form the PBO matrix? |
| Options considered | (a) N = rows of `docs/trial_log.csv`; (b) N = distinct rungs only |
| Decision | (a). Each tuned rung (M1, M2, M3, M0\*, ENS, each with its C1 rule) and each fixed grid value (M1 and M2 at λ = 0.1, 1, 10; M3 at depth 2 and 3; M0 at 13 and 52 weeks) is one row, keyed by `spec_hash` as in S23-6; `M0_L26` is the existing M0 row (S31-6). After this session the log holds 16 rows (M0 plus 15). N for the DSR is the number of rows of the trial log when the DSR is computed, including M5, the agent trials and any re-keyed configuration of Phase 3.3 and later. The PBO matrix has one column per trial-log row with an In-Sample weekly net return series from `06_backtest.py` (rungs, fixed values, M0 once, agent candidates); it never chooses the model |
| Rationale | Counting every row, including a tuned rung on top of its fixed values, keeps N conservative, as Amendment 5 C2 requires |
| Evidence | Amendment 5 C2: "These fixed runs enter the PBO matrix and the trial log, and the Deflated Sharpe Ratio counts every rung and every fixed configuration."; §10: "Deflated Sharpe Ratio with N = every human and agent trial in the ledger"; "PBO by CSCV. Run on the In-Sample weekly return matrix of every candidate configuration (rungs × grid values × agent candidates)"; Session 3.1 instructions §5: "one row per configuration (each rung with its C1 rule, each fixed value), keyed as in S23-6. Record the counting rule as an S31 decision." |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `docs/trial_log.csv`, `src/stats.py` |
| Amendment | No (applies Amendment 5 C2) |

### S31-8 · Bootstrap statistic and the selection gate's Sharpe convention

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | (1) What does "P(uplift > 0)" measure in the paired block bootstrap? (2) Which Sharpe convention does the gate use? (3) What if a candidate (M5) does not exist? |
| Options considered | (1) (a) the Sharpe uplift on each paired resample; (b) the mean weekly difference. (2) skeleton convention (annual return − rf) / volatility or zero-cost; fixed now or at the gate. (3) skip silently, or require it to be named |
| Decision | (1) (a), with (b) reported alongside. `paired_block_bootstrap` draws one set of stationary-bootstrap indices (Politis and Romano 1994; geometric blocks with mean `block` weeks, circular wrap, `numpy.random.default_rng(seed)`) and applies it to both series (and to a weekly rf series when one is given). It returns the observed Sharpe uplift, the percentile interval at `inference.confidence` (0.95), P(uplift > 0) as the share of resamples with uplift strictly above 0, and the mean weekly difference with its interval. Sharpe is the formula of `src.metrics.sharpe_ratio`; rf = 0 gives the zero-cost convention. The gate runs it with `selection.bootstrap_block` (4) and reports `selection.bootstrap_block_sensitivity` (8) as information. (2) Not fixed in code: `selection_gate(..., *, rf)` has no default, so the caller must pass rf = 0.0 (zero-cost) or the weekly T-bill series (skeleton headline); open point for both humans before the gate is run in Phase 3.3. (3) A candidate of `models.candidate_order` missing from the results raises `ValueError` unless it is named in `absent=` (e.g. M5 when no agent feature is approved); absent candidates are reported as such |
| Rationale | (1) The stub docstring and the gate's first criterion are in Sharpe units; resampling paired weeks is the bootstrap of weekly differences of H2. (2) §09 names the skeleton convention the headline, while Amendment 5 C1 uses zero-cost for the inner choice; the choice changes the gate and belongs to the humans |
| Evidence | §07 step 3: "net Sharpe ≥ M0 + 0.15; max drawdown at most 2 percentage points worse than M0; paired block bootstrap P(uplift > 0) ≥ 0.80"; §11 inference table: "Uplift vs M0 \| Paired stationary block bootstrap, 5,000 resamples, 4-week mean block (8-week sensitivity) \| H2 interval and P(uplift > 0)"; H2: "Paired block bootstrap of weekly differences"; §09: "the skeleton convention, (annual return − rf) / volatility, which is conservative here and is the headline; and the zero-cost long/short convention"; `src/stats.py` stub (commit ae7360f): "Returns the Sharpe uplift, its interval and P(uplift > 0)"; §07 "M5 \| Best rung + approved agent features"; "ENS … (+ M5 if it exists)" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/stats.py`, `config.yaml` (`inference.confidence`), `tests/test_stats.py` |
| Amendment | No |

### S31-9 · Rank IC, HAC, Ledoit–Wolf, DSR and PBO conventions

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which estimators and conventions do the remaining §11 procedures use? |
| Options considered | As below (chosen) |
| Decision | Rank IC: per week, the Spearman correlation (Pearson correlation of average ranks) of the 9 sector scores of week t with their forward returns of contract 7 (realised at O(t+2)); weeks without all 9 pairs finite, or with constant scores or returns, are skipped. Its mean has a Newey–West (Bartlett) HAC standard error with lag rule L = ⌊4 (T/100)^(2/9)⌋ (Newey and West 1994), T the number of weekly ICs; t = mean / se. Ledoit–Wolf (2008): Sharpe per period μ/σ with σ² = E[r²] − μ², delta method on (μ_a, μ_b, E[r_a²], E[r_b²]), HAC covariance with the T/(T − 4) small-sample factor, quadratic-spectral kernel with the Andrews (1991) AR(1) plug-in bandwidth (equal weights), no prewhitening; two-sided normal p-value (a Bartlett kernel with an explicit bandwidth is available for checks). DSR: Bailey and López de Prado (2014) with per-period (weekly) Sharpe mean/std (`ddof=1`), sample skewness and Pearson kurtosis (population moments), SR₀ = √V[SR] · ((1 − γ) Φ⁻¹(1 − 1/N) + γ Φ⁻¹(1 − 1/(N e))), γ the Euler–Mascheroni constant, V[SR] the sample variance (`ddof=1`) of the trials' weekly Sharpes, N from S31-7; N = 1 gives SR₀ = 0 (the probabilistic Sharpe ratio). PBO (Bailey, Borwein, López de Prado and Zhu 2017): `inference.pbo_blocks` (16) contiguous equal blocks after dropping the oldest T mod 16 weeks; all C(16, 8) = 12,870 splits; per split the In-Sample winner (highest mean/std, first column on ties) gets the relative rank ω = rank / (N + 1) of its OOS Sharpe (average ranks, `NaN` lowest), λ = ln(ω / (1 − ω)), and PBO = share of splits with λ ≤ 0 |
| Rationale | Standard published forms; the lag rule and the kernel are recorded because the texts allow several. Prewhitening is omitted to keep the estimator simple with 300–600 weekly observations |
| Evidence | §11 inference table (procedures named); Session 3.1 instructions §6: "rank_ic: weekly Spearman, HAC (Newey-West) mean and t-statistic; record the lag rule", "deflated_sharpe_ratio: Bailey and López de Prado (2014), N = trial count", "pbo_cscv: 16 blocks", "sharpe_difference_test: Ledoit–Wolf (2008), HAC"; protocol references: "Ledoit & Wolf (2008), Robust Performance Hypothesis Testing with the Sharpe Ratio", "Bailey & López de Prado (2014), The Deflated Sharpe Ratio" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/stats.py`, `config.yaml` (`inference.pbo_blocks`), `tests/test_stats.py` |
| Amendment | No |

### S31-10 · Outputs of the ladder runs and refined Phase 3.1 names

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | What do the ladder runs of `05_train_walkforward.py` write, and which stub names of contract 17 change? |
| Options considered | As below (chosen) |
| Decision | `--model {M0, M1, M2, M3, ENS, M0_star}` or `--fixed NAME` with the names built from the grids (`M1_a0.1`, `M1_a1`, `M1_a10`, `M2_a0.1`, `M2_a1`, `M2_a10`, `M3_d2`, `M3_d3`, `M0_L13`, `M0_L26`, `M0_L52`). Each run writes `outputs/walkforward/<name>/scores.csv`, `used.yaml` (`walkforward_settings(cfg)`, unchanged, S31-2) and `summary.json` (S23-3, plus `name`); tuned rungs with a grid (M1, M2, M3, M0\*) also write `selection.csv`, one row per refit: `test_year`, `refit`, `test_start`, `train_start`, `train_end`, `purge_end`, `inner_train_end`, `inner_purge_end`, `inner_val_start`, `inner_val_end`, `inner_val_weeks`, one `sharpe_<value>` column per grid value in config order, and `chosen`. Contract 17: `select_m0_star_lookback(net_returns, cutoff)` is replaced by the shared C1 helpers `inner_fold`, `inner_sharpe`, `choose_grid_value` and `walkforward_rung` (M0\* uses them like every grid); `tuning_spec`, `LadderData` and `to_weekly` (moved from the vault's private `_weekly_scores`) are added; `Vault.last_selection` holds the selection table of the last tuned `run_walkforward` call; `src/stats.py` adds the helpers `stationary_bootstrap_indices`, `newey_west_lags`, `hac_variance_of_mean`, `weekly_rank_ic`, `expected_max_sharpe`, `probabilistic_sharpe_ratio`, `cscv_logits`; `selection_gate` returns a dictionary (selected name and per-candidate details) instead of a name |
| Rationale | The selection table lets the reviewer check every choice; the stub refinements follow the implementation |
| Evidence | Session 3.1 instructions §4: "Each run writes outputs/walkforward/<name>/ scores.csv, used.yaml and summary.json, as for M0. Rungs with a grid also write selection.csv: per refit, the inner Sharpe of each value and the value chosen."; contract 17: "a stub's exact argument list is a proposal that its owner may refine in the phase pull request, which the other author reviews" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contracts 15 to 17) |
| Files affected | `05_train_walkforward.py`, `src/models.py`, `src/vault.py`, `src/stats.py`, `tests/test_module_stubs.py`, `docs/interfaces.md` |
| Amendment | No |

### S31-11 · Gate 2 sign-off

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Is Gate 2 passed, with the scope fixed by S22-10, by its trigger date of Tue 3 Nov 2026, so that the hard stop ("cut M3 first") does not apply? |
| Options considered | (a) Gate 2 passed on 3 Nov with the S22-10 scope; (b) Gate 2 not passed, hard stop applies (cut M3, then reduce agent candidates to ~20) |
| Decision | (a). Every item of the Gate 2 core of S22-10 is met on 3 Nov 2026: (1) engine hand cases and ledger reconciliation (pull request #5; S21-9 to S21-11); (2) features, labels, folds and vault (pull requests #6, #7, #8); (3) M0 In-Sample walk-forward reproduced by the reviewer on Mattia's machine with byte-identical scores (`scores_sha256` `7078b900…96a8`, `spec_hash` `6ce1693e…420c`; pull request #9; S23-6). The M0 In-Sample baseline that the §07 gate will use as the hurdle is recorded: net Sharpe −0.771 (skeleton convention, weekly T-bill rf), maximum drawdown −48.0% (pull request #9). The planted-signal test of the agent lab is not part of Gate 2: it moved to Gate 3 (Fri 6 Nov) and is never cut (S22-10). The hard stop is not triggered, so M3 stays in the ladder and the agent lab keeps ~40 candidates |
| Rationale | The trigger date is kept unchanged by S22-10, so the pre-commitment is binding; recording the M0 baseline now fixes the hurdle before any M1–M3, ENS or M0\* result exists |
| Evidence | S22-10: "Gate 2 core, by the end of Tue 3 Nov: engine hand cases and ledger reconciliation pass; features, labels, folds and vault done; M0 In-Sample walk-forward reproduced by the reviewer (Mattia). If the core slips past 3 Nov, the hard stop applies as written: cut M3 first, then reduce agent candidates from ~40 to ~20. The planted-signal test moves to Gate 3 (Fri 6 Nov) and is still never cut."; S21-9, S21-10, S21-11 (engine and ledger, pull request #5); S23-6: "the scores are unchanged (`scores_sha256` `7078b900…96a8`)" and the M0 row "`6ce1693e…420c`"; pull request #9 (Phase 2.3b, Mattia): reproduction of the M0 scores and the In-Sample backtest, net Sharpe −0.771 with the T-bill rf, maximum drawdown −48.0%; Session 3.1 instructions, addition: "Add one more decision entry to this PR, S31-n 'Gate 2 sign-off' in the full §2a format … Scope per S22-10 (the planted-signal test moves to Gate 3). Approved by Eliya Allam and Mattia Cervelli through this PR's review." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam and Mattia Cervelli (review of the pull request from branch `feat/3.1-ladder`) |
| Files affected | none (gate record) |
| Amendment | No |

### S31-12 · Interface names agreed with Phase 3.2 and fixes from the session audit

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | (1) Which keyword names and result keys of `src/stats.py` does Mattia's Phase 3.2 code read? (2) May a spec give a grid value with another type (`{"alpha": 1.0}` or `{"alpha": true}` for the grid value 1)? (3) In which units does `deflated_sharpe_ratio` take the trial Sharpes? (4) Must a weekly rf series given to the bootstrap cover exactly the weeks of the returns? |
| Options considered | (1) keep the key `p_uplift` or use `p_uplift_positive`; (2) accept any value equal to a grid value, or require the grid value with its type; (3) weekly Sharpes only, or also the trial return matrix; (4) exact index, or the weeks of the returns as in `src.metrics` |
| Decision | (1) `paired_block_bootstrap(candidate, baseline, n_resamples=..., block=..., seed=..., *, rf=None, confidence=None)` returns the probability under the key `p_uplift_positive` (not `p_uplift`); the gate's per-candidate keys are `p_uplift_positive` and `p_uplift_positive_sensitivity`; `rank_ic(...)` returns `mean`. Every signature and result key is listed in contract 17. (2) The value must equal a grid value and have its type (int 1, float 0.1); `bool` is refused. Otherwise one configuration could be logged under several `spec_hash` values, inflating N and duplicating PBO columns. (3) The trial Sharpes are per week (mean/std, `ddof=1`). `deflated_sharpe_ratio(..., *, trial_returns=None)` also accepts the weekly return matrix and computes them; the annualised `is_sharpe` of the trial log must never be passed. (4) The rf series is reindexed to the weeks of the returns, as `src.metrics.sharpe_ratio` does; a missing week raises `ValueError`. Also: the vault checks the forward-returns table against its own `cfg`; two tests added (the inner fits ignore the labels of the inner validation weeks; a label moved into (inner purge_end, outer purge_end] trips the inner purge check) |
| Rationale | (1) Mattia's hooks are already written against these names; the contract follows them rather than the reverse. (2)–(4) Findings of the session's independent audit; (2) and the two tests close gaps that a mutation of the code would otherwise pass |
| Evidence | Session 3.1 instructions, interface note: "his hooks call paired_block_bootstrap(a, b, n_resamples=..., block=..., seed=...) and read result["p_uplift_positive"], and rank_ic(...) and read result["mean"]. Use exactly these keyword names and result keys in src/stats.py, and document every function's signature and result keys in contract 17 of docs/interfaces.md."; audit findings 1, 2, 3 and 5 and the notes on the rf index and the vault configuration; S23-2 ("one row per distinct configuration"); §10 "Deflated Sharpe Ratio with N = every human and agent trial" |
| Proposed by | Eliya Allam (2–4); Mattia Cervelli (1, names used by Phase 3.2) |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contracts 16 and 17) |
| Files affected | `src/stats.py`, `src/vault.py`, `tests/test_stats.py`, `tests/test_vault.py`, `tests/test_ladder.py`, `docs/interfaces.md` |
| Amendment | No |

### S31-13 · Gate Sharpe convention (Amendment 6 C1)

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which Sharpe convention does the §07 gate use for "net Sharpe ≥ M0 + 0.15" and for the bootstrap P(uplift > 0) (open point (2) of S31-8)? |
| Options considered | (a) the §09 headline (annualised net return − rf) / annualised volatility with the weekly T-bill rf; (b) the zero-cost convention, as inside the Amendment 5 C1 training windows |
| Decision | (a), by Amendment 6 C1. The gate is called with `rf` = the weekly FRED 3-month T-bill returns of `src.metrics.tbill_weekly_returns` (Mattia's) over the same weeks; `selection_gate` keeps `rf` as a required keyword (no default), reindexes the series to the weeks of the returns and applies the same rf to the Sharpe criterion and to both bootstraps (blocks 4 and 8). Per candidate it also reports the zero-cost Sharpe alongside, under the new keys `sharpe_zero_cost` and `sharpe_m0_zero_cost` (information only; no criterion uses them). This closes open point (2) of S31-8 |
| Rationale | The gate must use the Sharpe the slides report; the zero-cost convention stays where only the ranking of grid values matters (Amendment 5 C1) |
| Evidence | Amendment 6 C1: "The gate's 'net Sharpe' is the headline convention of §09: (annualised net return − rf) / annualised volatility, with rf the weekly FRED 3-month T-bill over the same weeks; the zero-cost Sharpe is reported alongside."; §09: "the skeleton convention, (annual return − rf) / volatility, which is conservative here and is the headline"; §11: "Weekly FRED 3-month T-bill (time-varying)"; S21-4, S21-5 (weekly T-bill return and its annualisation) |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (review of the pull request from branch `feat/3.1-ladder`) |
| Files affected | `src/stats.py`, `tests/test_stats.py`, `docs/interfaces.md` (contract 17) |
| Amendment | Yes: Amendment 6 C1 |

### S31-14 · Out-of-Sample refits keep the last In-Sample grid value (Amendment 6 C2)

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Do the Out-of-Sample refits keep the last In-Sample grid value of each rung or apply Amendment 5 C1 again (open point of S31-3)? |
| Options considered | (a) keep the value chosen at the last In-Sample refit (the 2019 Q4 row of each `selection.csv`), refitting only the model parameters on newly realised labels; (b) apply C1 again at every OOS refit |
| Decision | (a), by Amendment 6 C2. In `08_run_oos.py` (Gate 4), each tuned rung (M1, M2, M3, M0\*) runs as the fixed configuration of its last In-Sample choice: ridge and LightGBM coefficients are refitted at every quarterly OOS refit on the labels realised by then, M0\* keeps its lookback; ENS ranks the members so refitted. The chosen values are recorded in `FROZEN.lock` with the other artefacts. No code changes in this pull request; `08_run_oos.py` implements it. This closes the open point of S31-3 |
| Rationale | Re-choosing a grid value with Out-of-Sample data is tuning, which §07 forbids after the freeze |
| Evidence | Amendment 6 C2: "Out-of-Sample refits keep, for each rung, the grid value chosen at the last In-Sample refit, and refit only the model's parameters on newly realised labels."; §07 "The same refits continue during OOS on newly realised labels; tuning does not."; §10 table: "Out-of-Sample \| … \| One run of the frozen system; scheduled quarterly refits allowed, tuning forbidden"; §10 vault protocol: "`FROZEN.lock` records the config hash, code commit, trial-log hash and model artefacts" |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (review of the pull request from branch `feat/3.1-ladder`) |
| Files affected | later `08_run_oos.py`, `FROZEN.lock` |
| Amendment | Yes: Amendment 6 C2 |

## 2026-11-03 · Session 3.2 follow-up: `06_backtest.py` aligned with `src/stats.py`

"Instruction" quotes Mattia's follow-up prompt of 3 Nov 2026, run on the branch `feat/3.1-ladder` after Eliya merged
`main` (with the 3.2 pull request) into it.

### S32-9 · Dotted model names, and the shift-check bootstrap on the gate's Sharpe

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | (1) The `--fixed` names of `05_train_walkforward.py` hold the grid value (`M1_a0.1`, `M2_a0.1`; S31-10), which the S32-1 pattern `[A-Za-z0-9][A-Za-z0-9_]*` refuses. Which names does `06_backtest.py` accept now? (2) Which Sharpe convention does the shift check's paired bootstrap use, now that `src.stats.paired_block_bootstrap` exists and takes `rf`? |
| Options considered | (1) (a) letters, digits and underscores with single dots between them, `[A-Za-z0-9][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*` (chosen); (b) any character but `/`, `\` and `..`; (c) the closed list of `fixed_names(cfg)`. (2) (d) the §09 headline with the weekly T-bill over the common weeks, as the gate (chosen); (e) the zero-cost convention (`rf` None, the S32-3 call) |
| Decision | (1a). `MODEL_NAME` accepts `M1_a0.1`, `M2_a0.1`, `M1_a10`, `M3_d2`, `M0_L13`; it refuses `..`, `.`, any `/` or `\`, `:`, a space, `-`, the empty name, two dots in a row, and a leading or trailing dot (Windows drops a trailing dot from a folder name, so `M1.` would open `M1`). `walkforward_models` and `check_model` use the same pattern, so `--model`, `--all` and `--shift-check` agree. (2d). `shift_check` passes `rf` = `inputs.rf_weekly` on the common weeks to `paired_block_bootstrap`; its observed uplift equals the reported `sharpe_difference_delayed_minus_base` of the T-bill Sharpes (tested). Settings unchanged: `selection.bootstrap_resamples`, `selection.bootstrap_block`, `seed`, delayed as candidate, base as baseline. The keys `p_uplift_positive` and `mean` of S32-3 are those of `src/stats.py` (S31-8, S31-9). The tests that asserted the Phase 3.1 stub now assert real values: `p_delayed_better` a float in [0, 1], `rank_ic_mean` finite |
| Rationale | (1a) is the smallest change that admits every name 05 writes and still cannot leave `outputs/walkforward/`; (c) would tie 06 to the grids of 05. (2d) the §12 verdict reuses the gate's bootstrap threshold (S32-3), so it must use the gate's Sharpe |
| Evidence | Instruction: "06_backtest.py: allow '.' in model folder names (e.g. M1_a0.1, M2_a0.1), while still refusing path-like names ('..', '/', '\\'). Add tests for both."; "The shift check's bootstrap uses the headline Sharpe with the T-bill rf (Amendment 6 C1), for consistency with the gate."; Amendment 6 C1: "The gate's 'net Sharpe' is the headline convention of §09 … with rf the weekly FRED 3-month T-bill over the same weeks"; `05_train_walkforward.py` `FIXED_PREFIX` ("--fixed names: M1_a0.1, M3_d2, M0_L13 (S31-10)"); S31-13. Tests `test_a_model_name_may_hold_single_inner_dots`, `test_a_path_like_model_name_is_refused`, `test_a_dotted_variant_folder_is_backtested`, `test_shift_check_writes_both_books_on_common_weeks` |
| Proposed by | Mattia Cervelli (instruction) |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py`, `tests/test_evaluate_script.py` |
| Amendment | No: applies Amendment 6 C1; the name pattern is an implementation detail of S32-1 |

## 2026-11-03 · Session 3.1, continued: LightGBM on macOS

### S31-15 · LightGBM's macOS wheel needs Homebrew's libomp

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | The macOS CI job of pull request #11 fails when LightGBM (M3) is imported. How do CI and the team's macOS machines get the OpenMP runtime it needs? |
| Options considered | (a) install Homebrew's `libomp` in the macOS CI job and state it as a macOS prerequisite in the README; (b) drop or skip LightGBM on macOS (refused: M3 is pre-registered and must run on macOS and Windows, Gate 5); (c) pin or build another LightGBM wheel (a dependency change outside this pull request) |
| Decision | (a). `.github/workflows/ci.yml`: in the `test` job, right after `astral-sh/setup-uv`, the step "OpenMP runtime for LightGBM (macOS)" runs `brew install libomp` when `runner.os == 'macOS'`. `README.md` (Quick start) states: "macOS: run `brew install libomp` once (LightGBM needs the OpenMP runtime)." The same pull request corrects the README's `05_train_walkforward.py` line to `uv run python 05_train_walkforward.py --model M0`, since the script requires `--model` |
| Rationale | LightGBM's macOS wheel links the OpenMP runtime dynamically and does not ship it; installing it is an environment prerequisite that changes no setting, model or result |
| Evidence | macOS CI log on pull request #11, as reported by Eliya Allam (3 Nov 2026): "Library not loaded: @rpath/libomp.dylib"; operating manual §8, Gate 5: "clean runs on macOS and Windows"; `05_train_walkforward.py` on `main`: `parser.add_argument("--model", required=True, ...)` (with pull request #11, one of `--model` and `--fixed` is required) |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (review of the pull request from branch `ci/macos-libomp`) |
| Files affected | `.github/workflows/ci.yml`, `README.md` |
| Amendment | No |

## 2026-11-03 · Session 3.2b: backtests of every model and the reproduction of the walk-forwards

"Instruction" quotes the session 3.2b prompt (3 Nov 2026). "Approved by" lists the approvals given so far; Eliya
approves through the review of the 3.2b pull request.

### S32-10 · `06_backtest.py` refuses stale walk-forward scores by `spec_hash`

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | `check_used` compares `used.yaml` with `walkforward_settings(cfg)` only, but a trial's identity (`spec_hash`, S23-6) also holds the spec, and the spec of a tuned rung holds `tuning_spec(cfg)` (the `tuning:` section, the baseline costs, `signal`, `metrics.periods_per_year`; S31-2). A change there leaves `used.yaml` valid while the scores are stale. How does 06 detect it? |
| Options considered | (a) recompute the spec_hash of the folder's name from the current `config.yaml` with 05's own `spec_for` and `src.vault.spec_hash`, and refuse the scores unless it equals `summary.json["spec_hash"]` (chosen); (b) add the tuning sections to the `used.yaml` check (changes the `walkforward_settings` contract, Eliya's file); (c) compare `summary.json` with the trial log only (a row of an old config stays in the log, so it cannot show staleness) |
| Decision | (a). `read_scores`, used by `--model`, `--all`, `--shift-check` and `--placebo`, calls `check_spec_hash(model, cfg)` right after the `used.yaml` check and before any real-data input is read or any output written. `expected_spec_hash(model, cfg)` = `spec_hash(spec_for(model, cfg), cfg)`, with `05_train_walkforward.py` loaded by path from the script folder, read only (Eliya's file, unchanged). The run stops (`SystemExit`) when `summary.json` is missing, has no or an empty `spec_hash`, holds another hash ("stale scores", both hashes shown, rerun 05), or when 05 has no spec for the folder name (a folder outside the 17 names of S31-10 cannot be checked, so it is refused; the M5 and agent folders of Phase 3.3 need their spec in 05 first). The folder name, not `summary.json`, selects the spec, so a summary copied from another folder is refused. The backtest `summary.json` gains `spec_hash`, which links each backtest to its trial-log row (the PBO matrix of S31-7). `--all` checks every folder before reading any input, as in S32-1 |
| Rationale | The spec_hash is the identity the trial log, the DSR and the PBO matrix use, so it is the right staleness key; recomputing it with 05's own `spec_for` keeps one definition of every spec |
| Evidence | Instruction §1: "06_backtest.py: before backtesting a model, recompute its spec_hash from the current config.yaml and refuse it if it differs from summary.json["spec_hash"] (stale scores after a config change). Add tests and an S32 decision."; S23-6 (spec_hash over `walkforward_settings` and the spec); S31-2 (`tuning_spec` in the spec); S31-10 (`summary.json` of every run holds `spec_hash`). Tests `test_model_backtest_refuses_stale_scores`, `test_a_tuning_change_makes_the_scores_stale_although_used_yaml_still_matches` (a `tuning.inner_validation_weeks` change: `used.yaml` still matches, M1 is refused, M0 is not, `--all` writes nothing), `test_a_fixed_value_folder_holding_another_names_scores_is_refused`, `test_model_backtest_needs_the_spec_hash_of_05`, `test_a_folder_05_has_no_spec_for_is_refused`, `test_diagnostics_refuse_stale_scores`, `test_the_backtest_summary_records_the_spec_hash`, and `test_expected_spec_hash_is_the_trial_log_hash_of_05s_spec` (the 17 names give 16 hashes, all rows of `docs/trial_log.csv`). With the check removed, eight of these tests fail |
| Proposed by | Mattia Cervelli (instruction) |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `06_backtest.py`, `tests/test_backtest_script.py`, `tests/test_evaluate_script.py` |
| Amendment | No |

### S32-11 · Reproduction of the walk-forwards and the In-Sample results of every model

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Do the walk-forwards reproduce on Mattia's machine, and what do the In-Sample backtests and shift checks of every model give? |
| Options considered | Report as computed (chosen); change anything because of them (excluded: operating manual §3.4, §3.8) |
| Decision | Environment: Windows 11, Python 3.12.14, lightgbm 4.7.0, scikit-learn 1.9.1, numpy 2.5.4, pandas 3.1.0. `03_build_features.py` reproduces `data/checksums_features.json` byte for byte (no diff). The 17 runs of `05_train_walkforward.py` (6 rungs, 11 fixed values) end without error and add no row to `docs/trial_log.csv`, so every spec_hash equals a logged one; M0's `scores_sha256` is `7078b900…96a8`, as in S31-11, and `M0_L26` equals it (S31-6). The other 16 `scores_sha256` are compared with Eliya's table in the review of this pull request (M3 above all). In-Sample, 624 weeks 2008-01-04 to 2019-12-13, 10 bps / 2%, headline net Sharpe (weekly T-bill) and zero-cost net Sharpe: M0 −0.771 / −0.684, M1 −1.286 / −1.183, M2 −0.986 / −0.887, M3 −1.417 / −1.311, ENS −1.192 / −1.095, M0\* −0.634 / −0.545; max drawdown −48.0%, −58.5%, −49.1%, −61.3%, −58.2%, −40.1%; turnover a week 0.400, 1.190, 1.121, 1.185, 1.244, 0.397; mean rank IC 0.0045, −0.0037, −0.0001, 0.0160, 0.0078, 0.0158. Among M1–M3 the highest headline net Sharpe is M2's. The fitted rungs lose 1.11 to 1.22 of zero-cost Sharpe to costs and borrow (gross zero-cost M1 0.005, M2 0.223, M3 −0.096, ENS 0.074), against 0.43 for M0 and M0\*, because they trade about three times as much. Shift check (623 common weeks, bootstrap with the T-bill Sharpe, S32-9): every rung PASSes; P(delayed > base) is M0 0.410, M1 0.278, M2 0.071, M3 0.093, ENS 0.065. For M0\* the delayed book is better (−0.563 against −0.639; rank IC 0.0186 against 0.0156) with P = 0.755, below the 0.80 of S32-3, so it PASSes; it is the closest to the threshold and is reported as such. M0's placebo is unchanged from S32-8. The §07 gate (`src.stats.selection_gate`) was not run in this session. No code, setting or score was changed because of these results |
| Rationale | The results feed the agent lab (it builds on the best of M1–M3) and the Gate 3 scorecard; stating the M0\* margin keeps the shift-check reading honest |
| Evidence | `outputs/metrics/is_models.csv`, `outputs/metrics/shift_check.csv`, `outputs/diagnostics/shift/M0_star/summary.json` (uplift 0.076, 95% interval −0.136 to 0.288), `outputs/walkforward/*/summary.json` (3 Nov 2026); S31-11; S32-8 |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 3 Nov 2026; Eliya Allam: PR review |
| Files affected | `docs/decisions.md` only |
| Amendment | No |

## 2026-11-03 · Session 3.3: multi-agent research lab and M5

Format of the operating manual's evidence standard. "Session 3.3 instructions" quotes the task list Eliya set for the
session (3 Nov 2026); "Answer" quotes Eliya's answers to the four questions asked at its start (3 Nov 2026). "Approved
by" is completed by Mattia's approving review of the pull request from branch `feat/3.3-agent-lab`, which also carries
Amendment 7 (committed alone, before any code of this session).

### S33-1 · Model id, prices and the budget meter

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Is the §08 model available, at what price, and how does the code compute the USD 5 hard stop? |
| Options considered | Prices: (a) peak rates whatever the time of day; (b) time-of-day rates. Mode: (c) thinking (the API default); (d) non-thinking. Tokens: (e) price every prompt token at the cache-miss rate; (f) use the cache-hit discount |
| Decision | DeepSeek's `/models` endpoint (3 Nov 2026) lists `deepseek-flash` and `deepseek-v4-pro`; `deepseek-flash` (model version DeepSeek-V4.1-Flash-1017) is used. (a), (d), (e). The meter charges each live call `prompt_tokens` × USD 0.30 / 1M + `completion_tokens` × USD 1.20 / 1M (the peak cache-miss input and peak output rates), from the `usage` the API returns. Before each live call the lab adds a worst-case bound of that call (prompt characters as tokens, plus `max_tokens` output tokens) to everything already spent, summed over every committed cache file under `agent_lab/cache/`; if the total would exceed `agent_lab.budget_usd` (5), the call is not made and the run stops. Calls use `extra_body={"thinking": {"type": "disabled"}}`, `response_format={"type": "json_object"}` and `max_tokens` 1,500; temperature is not sent (ignored by the API). Live calls are allowed for the planted-signal test only; Eliya is asked again before the real In-Sample run |
| Rationale | (a) and (e) can only over-count, so the stop is never late; (d) is cheaper, and replay makes the run reproducible whatever the sampling |
| Evidence | `/models` response (3 Nov 2026): `['deepseek-flash', 'deepseek-v4-pro']`; DeepSeek pricing page (https://api-docs.deepseek.com/quick_start/pricing, read 3 Nov 2026), deepseek-flash: "1M INPUT TOKENS (CACHE HIT)" off-peak "$0.003", peak "$0.006"; "1M INPUT TOKENS (CACHE MISS)" off-peak "$0.15", peak "$0.3"; "1M OUTPUT TOKENS" off-peak "$0.6", peak "$1.2"; "Off-peak rates are half of the peak rates. Peak hours are 01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday"; thinking-mode guide: "Thinking mode is enabled by default", "Thinking mode does not support the `temperature` … parameters"; §08 "DeepSeek V4.1 Flash (`deepseek-flash`) … with a hard stop in code at USD 5"; `config.yaml` `agent_lab.budget_usd: 5`; Answer 4: "Live calls allowed now for the planted-signal test only, with the meter at peak prices (the conservative option). Ask me again before the real In-Sample run." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (Answer 4, 3 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/llm.py`, `tests/test_agents_llm.py` |
| Amendment | No |

### S33-2 · Two vault spec gaps from the session 3.1 audit

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | (1) A spec's `as_of` or `end` is checked against the seal and then ignored by the walk-forward. (2) An M0 spec accepts any column of `features.asset` (e.g. `BETA52`) and any `MOM{L}_1` variant in the file. Should these be refused? |
| Options considered | (1) (a) keep the keys; (b) refuse any spec carrying them. (2) (c) keep; (d) accept only `models.M0.feature` and `MOM{L}_1` for L in `models.M0_star.lookback_weeks` |
| Decision | (1b): `as_of` and `end` leave the allowed spec keys. A spec carrying either raises `OOSAccessError` when the date is after `is_end` (the seal, as before) and `ValueError` otherwise; both are logged `refused` and add no trial row. (2d): an M0 spec's `feature` must be `MOM26_1` (models.M0.feature) or `MOM13_1`, `MOM26_1`, `MOM52_1` (the M0\* grid), read from `config.yaml`; any other name raises `ValueError` |
| Rationale | (1) a key the walk-forward does not use must not look as if it restricted the dates (S22-12 (4b) refused unknown keys for the same reason). (2) M0 on another column is not a pre-registered configuration and would add an unregistered trial |
| Evidence | Session 3.3 instructions §1: "specs carrying as_of/end are refused (not silently ignored), and M0 specs accept only MOM26_1 and the MOM{13,26,52}_1 variants"; S22-12 (4b); §07 table rows M0 and M0\*; `src/vault.py` at commit 2e2a4f7: `SPEC_KEYS = (...) + SPEC_DATE_KEYS` and `_feature_column` accepting `cfg["features"]["asset"]` |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contract 15) |
| Files affected | `src/vault.py`, `tests/test_vault.py`, `docs/interfaces.md` |
| Amendment | No |

### S33-3 · The feature DSL

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | What exactly can an agent feature express, and how is it evaluated without look-ahead? |
| Options considered | (a) a JSON expression tree on weekly samples with a closed list of operations (chosen); (b) daily-resolution operations; (c) raw Python (excluded by §08) |
| Decision | A spec is JSON `{"name": str, "expr": node}`. Leaves: `{"input": "close"}` (the asset's adjusted close) and `{"input": "spy"}` (SPY's, the same value for every sector), each sampled at the last session on or before Friday t (TR(t) of S22-3; NaN when the week has no session). Operations: `lag` (n weeks), `rolling` with `stat` in mean, std (ddof = 1), sum, min, max over the n weekly values ending at t, `diff` (x(t) − x(t − n)), `log`, `ratio` (a / b), `cs_rank` and `cs_z` (across the 9 sectors each Friday; `cs_z` is `src.features.cross_sectional_zscore`, `cs_rank` the average rank mapped linearly to [−1, 1]) and `mul_state` with `state` one or two of BEAR24, MKT_VAR, VIX, TERM, CREDIT. n is an integer, 1 ≤ n ≤ 104 for `lag` and `diff`, 2 ≤ n ≤ 104 for `rolling`. Root rule (Amendment 7 C2): the root is `cs_rank` or `cs_z`, or `mul_state` whose child is `cs_rank` or `cs_z`; `mul_state` appears only at the root, and the evaluator returns the cross-sectional asset part, the product being formed in-fold by the model pipeline. A window value is NaN unless all n inputs are finite; `log` of a non-positive value and a ratio with a zero or non-finite denominator give NaN. Each window is computed on its own n values (`numpy.lib.stride_tricks.sliding_window_view`), so nothing after t can change a value at t. Limits: at most 25 nodes and depth 10; unknown keys or operations raise `DSLError`. Output: float64 on the (date_close, ticker) index of contract 3, known after Friday close t |
| Rationale | Weekly samples make every window end at t by construction; the root rule follows §06 (a market state alone cannot reorder the ranking) and Amendment 7 C2 |
| Evidence | Session 3.3 instructions §2: "Inputs: daily adjusted closes of the asset and SPY, and the lagged market states. Operations: lag, rolling mean/std/sum/min/max over ≤ 104 weeks ending at t, diff, log, ratio, cross-sectional rank and z-score, and product with a market state. Output: a weekly feature (contract 3), known after Friday close t. The evaluator refuses any window past t."; §08 Coder "Turns the spec into DSL operations (lag, rolling, rank, ratio); no raw Python"; §06 "Why a market state alone cannot reorder a ranking"; Amendment 7 C2 |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/agents/dsl.py`, `tests/test_dsl.py` |
| Amendment | Amendment 7 C2 |

### S33-4 · Agent features in the vault and the model pipeline

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How does the vault evaluate a DSL feature and add it to the base rung, and how is the headline Sharpe computed without reading data outside the vault? |
| Options considered | (a) new sealed vault tables for the daily closes and the T-bill yield (chosen); (b) read the raw files in the lab, as `06_backtest.py` does |
| Decision | New spec key `agent_features` (a list of DSL specs), allowed only with rung M1, M2 or M3 and either `params` or `tuning`. New sealed, logged vault methods: `Vault.daily_closes(as_of)` (adjusted daily closes of the 9 sectors and SPY from `data/processed/daily_close.csv`, cut at `is_end` right after reading, then at `as_of`) and `Vault.tbill_weekly(as_of)` (the weekly T-bill return of Mattia's `src.metrics.tbill_weekly_returns`, DGS3MO lagged one session, from `data/raw/fred/DGS3MO.csv` cut at `is_end` right after reading, on the weeks of the forward returns realised by `as_of`). In-memory `frames` may hold them under `daily_close` and `dgs3mo`. The vault evaluates each DSL spec on the In-Sample closes (column `AG<k>`, k = 1, 2, … in list order) and adds it to the features; `src.models` builds the design as the base rung's design plus `AG<k>` and, for `mul_state`, the product `AG<k>_x_<state>` with the in-fold scaled state (VIX as VIX_Z), formed like the pre-registered interactions. A row with a missing agent value gets a NaN score (Amendment 2 C3). `run_walkforward(spec, evaluate)` may return a third value from `evaluate`, the trial row's notes (default: the spec's notes) |
| Rationale | (a) keeps every model and research input behind the seal and the access log (manual §3.3); (b) would put a second data path in the lab |
| Evidence | Manual §3.3 "All model and research data access goes through `src/vault.py`"; S23-4 (sizing betas through the vault); S23-8 (DGS3MO cut at the In-Sample end right after reading); Amendment 6 C1 (gate Sharpe with the weekly T-bill); Amendment 7 C2 |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review; contract change, `docs/interfaces.md` contracts 14, 15 and 17) |
| Files affected | `src/vault.py`, `src/models.py`, `tests/test_vault.py`, `tests/test_ladder.py`, `docs/interfaces.md` |
| Amendment | Amendment 7 C2 |

### S33-5 · The `ddmi-vault` MCP server

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | What do the three tools return, how are the sectors anonymised, and how are refusals recorded? |
| Options considered | As below (chosen) |
| Decision | `src/agents/vault_server.py` builds an MCP server named `ddmi-vault` (`mcp.server.mcpserver.MCPServer`, mcp 2.3) with three tools; the graph calls them in process through the server's `call_tool`, and `python -m src.agents.vault_server` serves them over stdio. `IN_SAMPLE_END = "2019-12-27"` is a constant; the server refuses to start if `split.in_sample_end` differs, and any tool argument dated after it is refused. Anonymisation: sector `universe(cfg).sectors[i]` gets code `A<j+1>` with j its position in `numpy.random.default_rng(seed).permutation(9)`; the mapping never leaves the server. `get_features(as_of)`: per code, the six z-scored asset features at the last week ≤ `as_of` and their mean and standard deviation over the 104 weeks ending there, the market states of that week, and the pooled correlation matrix of the six features over those weeks, rounded to 3 decimals; no price, return or series. `run_walkforward(spec)`: validates the DSL spec, runs the Validator checks of S33-6, adds the feature to the base rung (S33-10) and returns `checks`, `net_sharpe` (headline, Amendment 6 C1), `net_sharpe_zero_cost`, `uplift` and `max_drawdown_change` against the base rung on the same weeks, `p_uplift_positive` (paired block bootstrap, `selection.bootstrap_resamples`, `selection.bootstrap_block`, `seed`), `rank_ic_mean` and `rank_ic_t` (`src.stats.rank_ic`), `mean_turnover`, `mean_abs_residual_beta`, the adverse-cost (20 bps, 5%) net Sharpe and uplift, and `passed_gate`. `get_trial_history()`: every trial-log row without `params_json` of human rows; agent rows keep their DSL spec. Every call, refused or not, writes one line to the server log (`<run>/vault_server_log.jsonl`: tool, argument hash, ok or refused, reason) besides the vault's own access log |
| Rationale | §08 fixes the three tools, the hard-coded end, the logging and the anonymised summaries; a seeded permutation hides the alphabetical order |
| Evidence | §08: "One MCP server (`ddmi-vault`) is the agents' only path to data, with three tools: `get_features(as_of)`, `run_walkforward(spec)`, `get_trial_history()`. The In-Sample end date is hard-coded; any request touching OOS dates raises an error and is logged. Agents see anonymised codes (A1…A9) and summary metrics, never raw price series."; Session 3.3 instructions §3 |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/agents/vault_server.py`, `tests/test_vault_server.py` |
| Amendment | No |

### S33-6 · The Validator: checks and the pass rule

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which deterministic checks does a candidate pass before Skeptic and Risk see it? |
| Options considered | Walk-forward rule: (a) the §07 gate thresholds against the base rung; (b) P(uplift > 0) ≥ 0.80 only; (c) no threshold |
| Decision | In order, stopping at the first failure: (1) the spec parses (S33-3); (2) leakage: for the cutoffs 2006-06-30, 2012-06-29 and 2017-06-30 (in a run whose data end earlier, the cutoffs inside its In-Sample weeks), every close after the cutoff is multiplied by `exp(N(0, 0.05²))` (`numpy.random.default_rng(seed)`), and the feature on every week ≤ the cutoff must be bit-identical (NaN equal to NaN); (3) warm-up: no missing value on any (week, sector) row from the first week after `split.warmup_end` to the In-Sample end where the six asset features are all finite; (4) redundancy: the pooled Pearson correlation over those rows with each of the six asset features and with the asset part of every candidate that has survived so far must satisfy \|corr\| < 0.9; (5) walk-forward (a): against the base rung on the same backtested weeks at baseline costs, uplift ≥ `selection.sharpe_uplift` (0.15), max drawdown no more than `selection.mdd_tolerance` (2 points) worse, P(uplift > 0) ≥ `selection.bootstrap_prob` (0.80) |
| Rationale | (a): H5 asks that agent features "survive the same gate as human features"; (b) would pass about one noise feature in five |
| Evidence | Answer 1: "§07 gate vs base (Recommended)"; Session 3.3 instructions §4: "Validator: deterministic tool; leakage test, warm-up, \|corr\| < 0.9 with existing features, walk-forward."; H5 "Agent-proposed features survive the same gate as human features after trial-count deflation"; §07 step 3 thresholds; `config.yaml` `selection.*` |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (Answer 1, 3 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/vault_server.py`, `src/agents/graph.py`, `tests/test_vault_server.py` |
| Amendment | No: lab procedure (§08 is not part of the pre-registration); the thresholds are the pre-registered ones |

### S33-7 · Graph, LLM roles, cache, replay and limits

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How do the roles of §08 interact, and how are calls cached, replayed and limited? |
| Options considered | (a) LangGraph `StateGraph` (chosen); (b) the plain-Python fallback |
| Decision | Per candidate: Orchestrator (deterministic: candidate cap, budget, routing) → Hypothesis (LLM: mechanism, rationale and a feature idea, given the DSL grammar, `get_features` at the In-Sample end and `get_trial_history`) → Coder (LLM: the DSL JSON only) → Validator (S33-6, through `run_walkforward`) → Skeptic (LLM: veto on overfitting, redundancy, economic plausibility) → Risk (LLM, given the tool's turnover, residual beta and adverse-cost figures: veto on turnover, beta and cost sensitivity) → record. Skeptic and Risk run only on candidates that pass the Validator. A candidate survives if it passes the Validator and neither LLM vetoes. An unparseable LLM answer counts as a veto (Skeptic, Risk) or an invalid spec (Coder); there are no retries. Cache: every LLM call is one line of `agent_lab/cache/<run>.jsonl` (committed): `key` = SHA-256 of the canonical JSON of the request (model, messages, parameters), the request, the response text, `usage` and `cost_usd`; no time and no credential. A request whose key is in any cache file is answered from it at zero cost; in replay mode a missing key raises and no client or key is needed. Prompts hold no time or machine-dependent field, so a replay recomputes the same prompts and reproduces the run. Limits: `agent_lab.max_candidates` (40) proposals in the real run; USD 5 (S33-1). The run writes `<run>/candidates.jsonl` (one line per proposal: spec, checks, metrics, verdicts, cost) |
| Rationale | §08 names LangGraph with a plain loop as fallback; the hashed cache makes the lab replay offline at zero cost |
| Evidence | §08 roles table; "Prompts, responses and tool results are cached as hashed JSONL, so the lab replays offline at zero cost"; "Framework. LangGraph 1.0 for the graph and state, MCP for the vault; a plain Python loop is the fallback"; Session 3.3 instructions §4 |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/agents/graph.py`, `src/agents/llm.py`, `src/agents/prompts.py`, `04_agent_lab.py`, tests |
| Amendment | No |

### S33-8 · The planted-signal test

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | How are the planted effect, the noise and PASS defined? |
| Options considered | (a) the planted spec and fixed noise specs injected at the Validator, plus the LLM loop on the same market (chosen); (b) the LLM must discover the effect unaided |
| Decision | `src/agents/planted.py` builds a deterministic synthetic market (seed `config.seed`) with the 11 tradables, VIX and FRED, weeks from 2011 to 2019, no momentum, and one planted effect: each sector's expected log return in week t + 1 is κ times its cross-sectional z-score in week t of the DSL feature P = `cs_z(ratio(rolling std 4 of diff(log close, 1), rolling std 26 of diff(log close, 1)))`, a short-to-long volatility ratio. Its tables go through `03_build_features.py` into a separate folder, with the split of the synthetic ladder tests (warm-up to 2012, initial training 2013–2014, test years 2015–2019, 52 inner validation weeks). The lab runs on it with its own trial log (`agent_lab/planted/trial_log.csv`), never `docs/trial_log.csv`: 6 LLM candidates, then the planted spec and 4 fixed noise specs injected at the Validator, and every candidate that passes goes through Skeptic and Risk. PASS: P survives, and every candidate whose asset part has \|corr\| < 0.5 with P's is rejected. Reported separately, as information and not part of PASS/FAIL: whether Hypothesis and Coder proposed P, or a feature with \|corr\| ≥ 0.9 to it, unaided. κ is set on the synthetic market before any real-data lab run |
| Rationale | (b) could fail by chance in a few proposals although every component works; injecting tests the Validator, Skeptic and Risk on a known answer, while the LLM candidates supply realistic noise |
| Evidence | Answer 2: "Option 1, plus: report separately whether the Hypothesis/Coder agents proposed the planted feature (or one with \|corr\| ≥ 0.9 to it) unaided, as information. It is not part of PASS/FAIL. State this in the decision and in the report."; §08 "On synthetic data with one planted effect and pure noise elsewhere, the lab must find the planted effect and reject the noise"; Session 3.3 instructions §5; S22-10 (never cut) |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (Answer 2, 3 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/planted.py`, `04_agent_lab.py`, `tests/test_planted_signal.py`, `agent_lab/` |
| Amendment | No |

### S33-9 · Trial rows of agent proposals

| Field | Content |
| --- | --- |
| Date | 2026-11-03 |
| Question | Which proposals get a trial row, with which fields? |
| Options considered | (a) every proposal, evaluated or not (chosen); (b) only proposals that reach the walk-forward |
| Decision | Every proposal is one row with `kind` "agent", `author` "agent lab", `rung` the base rung, `spec_hash` of the candidate spec (`{"rung", "tuning", "agent_features", "author", "kind", "notes": "agent lab candidate"}` with the config, S23-6; an unparseable proposal is hashed as `{"invalid_dsl": <proposal>}`), and `notes` a compact JSON with the candidate number, the stage reached, uplift, P(uplift > 0), rank IC, turnover, mean \|residual beta\| and the USD cost of the calls that produced the proposal (Hypothesis and Coder); `is_sharpe` and `is_mdd` hold the candidate's headline net Sharpe and max drawdown when the walk-forward ran. The vault writes the row when it evaluates the spec; the server writes it for a proposal refused before. A repeated spec adds no row (S23-2). Skeptic and Risk verdicts and their cost are in `candidates.jsonl` and `agent_lab/review.md` |
| Rationale | Manual §3.5 and §10 count every configuration; counting proposals that failed a check keeps N conservative |
| Evidence | Session 3.3 instructions §6: "Every proposal, accepted or rejected, is a trial-log row (kind "agent") with spec hash, metrics and cost."; §08 "every proposal, accepted or rejected, is a row in `trial_log.csv` with spec hash, metrics and cost"; S23-2, S23-6, S31-7 |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/vault.py`, `src/agents/vault_server.py`, `docs/trial_log.csv` |
| Amendment | No |

### S33-11 · Fixes from the audit of the vault, DSL and model-pipeline changes

S33-10 is reserved for the base rung (S33-5), recorded once the In-Sample backtests of M1–M3 exist.

| Field | Content |
| --- | --- |
| Date | 2026-11-04 |
| Question | The session's independent audit of the S33-2 to S33-4 code (no look-ahead or seal breach found) raised: (1) a pre-built `FeatureSpec` skipped DSL validation; (2) one configuration could get several `spec_hash` values (a state as `"VIX"` or `["VIX"]`, two states in either order, a renamed feature, the same feature twice); (3) `unlock()` kept tables cut at `is_end` while sealed; (4) lag, diff and rolling count the rows of the weekly grid, not calendar weeks; (5) an agent value missing in a training row refuses the whole run; (6) smaller points. How is each settled? |
| Options considered | (2): (a) refuse non-canonical forms; (b) hash a canonical form (chosen) |
| Decision | (1) `parse` validates a `FeatureSpec` again from its name and expression; the vault accepts agent features only as JSON objects. (2b) `src.agents.dsl.canonical(spec)` = `{"expr": …}` with a root `mul_state`'s states as a list in the order of `STATES` (BEAR24, MKT_VAR, VIX, TERM, CREDIT; the product commutes) and without the name, which never reaches the design; `spec_hash` hashes each agent feature in that form (the trial row's `params_json` keeps the spec as given), `FeatureSpec.states` and the design column names follow the same order, and the same feature twice in one spec is refused. This refines S33-3 ("in the given order") and S33-9 (the hash). (3) `unlock()` clears the cached tables, and `tbill_weekly` cuts the yield at `as_of`. (4) Weeks are the rows of `src.features.weekly_index` (calendar weeks with at least one session), so `n` counts those rows; a week without any session is absent rather than NaN, which corrects the wording of S33-3. It only ever reaches further back. (5) Kept: `fit` refuses a non-finite training input (S31-4), so a mid-sample gap refuses the run, logged `refused`; the Validator's warm-up check (S33-6 (3)) rejects such a feature first. A gap in a week that only scores gives a NaN score that week (Amendment 2 C3). (6) Non-string operations, inputs, statistics or states raise `DSLError`; `evaluate` must return two or three values. Tests: `tests/test_dsl.py` and `tests/test_agent_vault.py` (the S33-4 tests are in this new file, not in `tests/test_ladder.py` as S33-4 listed) |
| Rationale | One configuration must have one hash, or the trial count of the Deflated Sharpe Ratio grows with renamings (S31-12) |
| Evidence | Audit report of 4 Nov 2026 (findings M1–M3, L1–L5); S31-12 "Otherwise one configuration could be logged under several `spec_hash` values, inflating N"; S23-2; S31-4 |
| Proposed by | Eliya Allam |
| Approved by | Mattia Cervelli (pull request review) |
| Files affected | `src/agents/dsl.py`, `src/vault.py`, `tests/test_dsl.py`, `tests/test_agent_vault.py`, `docs/interfaces.md` |
| Amendment | No |

### S33-12 · The planted market spans the real split; κ = 0.002; the gate's power in short samples

| Field | Content |
| --- | --- |
| Date | 2026-11-04 |
| Question | S33-8 placed the planted market on 2011–2019 with the synthetic ladder tests' split (test years 2015–2019, 52 inner validation weeks) and left κ open ("κ is set on the synthetic market before any real-data lab run"). Calibration on that market showed noise passing the Validator. Which window and κ does the planted-signal test use? |
| Options considered | (a) the real run's split on a market from 1999, κ = 0.002 (chosen); (b) the short window with κ = 0.004; (c) the short window with κ = 0.002 |
| Decision | (a). `src/agents/planted.py` generates the market from 1999-01-04 to the In-Sample end, and the planted run uses `config.yaml` unchanged: warm-up to 2002, initial training 2003–2007, 12 yearly test folds 2008–2019 with quarterly refits, 104 inner validation weeks, the base rung chosen by Amendment 7 C1. κ = 0.002. Everything else in S33-8 (planted spec, noise specs, injection, PASS rule, the separate trial log, the unaided-discovery report) is unchanged. Calibration record, synthetic data only, no LLM call, no spend, the base rung M3 in every run. The first draft of `planted.py` used κ = 0.004. Short window, κ = 0.004: planted uplift 3.10 (P 1.00); the four noise specs failed (uplift −0.93 to −0.26). Short window, κ = 0.002: planted uplift 1.66 (P 1.00); two noise specs passed the gate (uplift 0.37, P 0.90; uplift 0.52, P 0.96) and two failed. Real split, κ = 0.002: planted uplift 1.39 (P 1.00); the four noise specs failed (uplift −0.33 to −0.10, P ≤ 0.29). Finding, reported and not hidden: on a 5-year test window, the §07 gate against a weak base rung passed 2 of 4 pure-noise features. The gate's power and its false-pass rate depend on the sample length, and the real In-Sample run has the 12-year window. Every agent trial is still counted in the Deflated Sharpe Ratio, and the human gate reviews every survivor |
| Rationale | The test must have the same statistical power as the real run, which uses the same split; κ = 0.002 is the weaker of the two values tried, so the planted effect is not trivially strong; (b) would choose κ by which value makes noise fail |
| Evidence | Calibration runs of 4 Nov 2026 (scratchpad script, synthetic data, `VaultServer.run_walkforward` on each spec), figures above; S33-8; Eliya's answer (4 Nov 2026): "Option 1. … only the window changes, to match the real run's split, refit schedule and inner window; the 5-year result (2 of 4 noise specs passing at κ = 0.002) is reported as a finding on the gate's power in short samples, not hidden." (Eliya also wrote that κ = 0.002 was "unchanged from S33-8 (chosen before this calibration)"; S33-8 left κ open and the first draft used 0.004, so this entry records the sequence as it happened) |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (answer of 4 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/planted.py`, `04_agent_lab.py`, `tests/test_planted_signal.py` |
| Amendment | No |

### S33-13 · Planted-signal attempts 1 and 2: both FAIL (Risk vetoes the planted feature); two pipeline fixes

| Field | Content |
| --- | --- |
| Date | 2026-11-04 |
| Question | What happened in the planted-signal runs, what was changed between them, and what does the record keep? |
| Options considered | (a) keep every attempt on record with its spend, fix the pipeline bugs the first exposed, rerun once and stop on a second failure (chosen, Eliya's conditions); (b) discard a failed attempt |
| Decision | Both attempts use the S33-12 design unchanged (market from 1999, the real split, κ = 0.002, the four noise specs, the gate thresholds); the base rung is M3 in both (In-Sample headline net Sharpe on the planted market: M1 −1.105, M2 −1.178, M3 −1.077; Amendment 7 C1). **Attempt 1, FAIL.** An unintended live run: it was meant as a dry run with a fake client, but the fake was patched in after `LLM` had bound the real client factory as its dataclass default. It made 14 live `deepseek-flash` calls (6 Hypothesis, 6 Coder, 1 Skeptic, 1 Risk; 24,454 prompt and 3,431 completion tokens; USD 0.011453, inside the planted-test authorisation of S33-1); they are kept in `agent_lab/cache/planted_attempt1.jsonl`, so the meter counts them, and in `agent_lab/planted/attempt1/`. Decisions by agent: the Validator rejected the 4 noise specs and 1 LLM proposal at the gate (5 more LLM proposals were invalid specs) and passed the planted feature (uplift 1.39, P 1.00); the Skeptic accepted the planted feature; Risk vetoed it. Invalid-proposal rate of the LLM agents: 5 of 6, 4 of them complete specs followed by surplus closing braces that strict JSON parsing rejected, 1 a genuinely invalid spec (`mul_state` below the root). **Fixes before attempt 2** (diffs shown to and approved by Eliya; nothing else changed): (1) `src.agents.llm.parse_json` takes the first complete JSON object when strict parsing fails, only if nothing precedes it and nothing but whitespace or surplus `}`/`]` follows; the DSL validation stays strict (tests: unknown operation, extra keys and the root rule are still refused after a lenient parse). (2) The Risk prompt's adverse-cost clause "Veto if the uplift disappears or turns negative under adverse costs" became "Veto if the uplift over the base rung (candidate minus base rung) disappears or turns negative under adverse costs"; no other wording changed. **Attempt 2, FAIL.** 14 calls in all: 9 live (4 Hypothesis, 4 Coder, 1 Risk; 17,513 prompt and 2,126 completion tokens; USD 0.007805) and 5 answered from attempt 1's cache (identical requests, zero cost: Hypothesis and Coder of candidates 1 and 2, and the Skeptic of the planted feature); `agent_lab/cache/planted_attempt2.jsonl`, `agent_lab/planted/attempt2/`. Decisions by agent: the Validator rejected the 4 noise specs and 3 LLM proposals at the gate (uplift −0.56, −0.13, −0.14), 2 LLM proposals at the warm-up check, and 1 LLM proposal as an invalid spec (`cs_z` given an extra key), and passed the planted feature (uplift 1.39, P 1.00); the Skeptic accepted it (cached answer of attempt 1); Risk vetoed it again, reading the adverse-cost uplift (+1.37) as "a raw/uplift figure not a net adverse-cost comparison" and vetoing on the candidate's absolute adverse-cost Sharpe (−0.96). Invalid-proposal rate after the parser fix: 1 of 6. Unaided discovery (information only): no LLM proposal had \|corr\| ≥ 0.9 with the planted feature in either attempt (all ≤ 0.03). Total spend of both attempts: 23 live calls, USD 0.019258. Per Eliya's condition, no attempt 3 is run without Eliya's approval; attempt 3 is S33-14 |
| Rationale | The planted test exists to expose pipeline faults; the record keeps every attempt and its cost, and no threshold was weakened |
| Evidence | `agent_lab/planted/attempt1/candidates.jsonl` (attempt 1 Risk: "Under the stated veto rule (veto if the uplift disappears or turns negative under adverse costs), the positive edge is erased and the strategy turns negative. VETO.", `adverse_uplift` 1.3704); `agent_lab/planted/attempt2/candidates.jsonl` (attempt 2 Risk: "The reported Sharpe uplift is positive (1.37), but that is a raw/uplift figure not a net adverse-cost comparison; on a net-of-adverse-costs basis the candidate loses money (-0.96), so the uplift over the base rung does not survive. Veto per the adverse-cost criterion."); cache files (calls, tokens, cost); Eliya's conditions (4 Nov 2026): "Nothing changes except the two fixes", "If attempt 2 fails, STOP and report. No attempt 3 without my approval.", "S33-13 reports both attempts: calls, cost, which agent decided what, and the LLM's invalid-proposal rate before and after the parser fix. Both attempts' caches are committed."; manual §3.8 |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (conditions of 4 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/llm.py`, `src/agents/prompts.py`, `tests/test_agents_llm.py`, `agent_lab/cache/`, `agent_lab/planted/` |
| Amendment | No |

### S33-14 · Risk's three numeric checks run in the tool; the Risk LLM vetoes only for a named concern (attempt 3, final)

| Field | Content |
| --- | --- |
| Date | 2026-11-04 |
| Question | Attempts 1 and 2 (S33-13) failed because the Risk LLM vetoed the planted feature on its absolute adverse-cost Sharpe, which is not a Risk criterion. How should Risk apply its checks? |
| Options considered | (a) give the LLM the base rung's adverse-cost Sharpe as well and label the uplift as net of adverse costs (prompt only); (b) run the three numeric checks deterministically in the tool and keep an LLM veto on top, for a named concern only (chosen); (c) accept the result and leave the planted-signal test failed |
| Decision | (b), as attempt 3, the final attempt. **Tool checks** (`src.agents.vault_server.risk_checks`, on the unrounded figures of `run_walkforward`, returned with its result as `risk_checks`): (1) turnover: the candidate's mean weekly turnover is at most 1.5 times the base rung's (the "more than half again" of the attempt 1 and 2 prompt); (2) residual beta: the candidate's mean absolute residual beta is at most 0.10 (the same prompt; D10's market-neutral bound); (3) cost sensitivity: the Sharpe uplift over the base rung under the adverse costs (20 bps, 5% borrow; both books on their common weeks) is above 0 (the prompt's "disappears or turns negative"). Thresholds are unchanged. Any failed check is a Risk veto and the LLM is not called. Absolute performance is not a Risk criterion; it belongs to the Validator's §07 gate. **LLM veto** (only when all three checks pass): the Risk LLM sees the spec, the three checks with their figures (candidate and base turnover, residual beta, adverse-cost uplift) and the rank IC; it sees no absolute Sharpe. It answers `{"veto": bool, "concern": "concentration" \| "mechanism" \| "instability" \| null, "notes": str}`. A veto counts only if `concern` names one of the three; a veto with any other `concern`, or whose notes cite a Sharpe ratio or costs (the case-insensitive words `sharpe`, `cost`, `costs`, `borrow`), is recorded as an invalid veto (`invalid_veto` with the reason, the LLM's answer kept) and does not count. An unparseable answer or a non-boolean `veto` still counts as a veto (S33-7). **Attempt 3** runs `04_agent_lab.py --planted` live with everything else unchanged (κ, the window, the gate thresholds, the noise specs, the Hypothesis, Coder and Skeptic prompts; their identical requests are answered from the cache of attempts 1 and 2 at zero cost). Attempt 2's files move to `agent_lab/cache/planted_attempt2.jsonl` and `agent_lab/planted/attempt2/`; attempt 3 wrote `agent_lab/cache/planted.jsonl` and `agent_lab/planted/`, moved to `agent_lab/cache/planted_attempt3.jsonl` and `agent_lab/planted/attempt3/` by S33-15. Attempts 1 and 2 stay on record as FAIL with their cost (S33-13). If attempt 3 fails, the planted-signal test of Gate 3 stays failed and Eliya and Mattia decide the next step together; there is no attempt 4. **Result: attempt 3 PASS** (base rung M3): proposed 11, validated 1 (the planted feature), vetoed 0, surviving 1; the tool checks passed the planted feature (turnover ratio 0.93, mean absolute residual beta 0.0007, adverse-cost uplift +1.37) and failed every other walk-forward candidate on cost sensitivity; the Skeptic accepted (cached answer); the Risk LLM did not veto (`concern` null). Unaided discovery (information only): no. 14 calls: 1 live (Risk; USD 0.000445) and 13 from the cache; total spend of all attempts USD 0.019704 over 24 live calls. **Superseded by S33-15**: the Skeptic saw the planted spec's origin, so this PASS does not count |
| Rationale | An absolute adverse-cost test would veto every real candidate: the base rung on the real data is M2 (the best of M1–M3 by In-Sample headline net Sharpe, Amendment 7 C1), whose headline net Sharpe is −0.986 at baseline costs (S32-11), so no candidate that improves it by a realistic margin has a positive absolute Sharpe, under adverse costs even less. Each Risk check is relative to the base rung (or a fixed exposure bound), so it cannot duplicate the gate. §08 defines Risk as "LLM + tool": the tool part is the deterministic arithmetic of the three thresholds, which an LLM reading figures can misapply (S33-13), and the LLM part is the judgement the arithmetic cannot make (concentration, a flawed mechanism, instability). Recording invalid vetoes keeps every LLM answer on record without letting it override the pre-set criteria |
| Evidence | Protocol §08 roles table (Risk: "LLM + tool"); S32-11 (on `main`, PR #13): "M2 −0.986 / −0.887 … Among M1–M3 the highest headline net Sharpe is M2's"; S33-13 (attempt 2 Risk: "on a net-of-adverse-costs basis the candidate loses money (-0.96) … Veto per the adverse-cost criterion"); D10 (\|β\| < 0.10); Eliya's instruction (4 Nov 2026): "Risk's three numeric checks (turnover, beta, cost sensitivity) run deterministically in the tool, each measured relative to the base rung as already specified; thresholds unchanged. Absolute performance is not a Risk criterion: it belongs to the Validator's gate.", "The Risk LLM keeps a veto only on top of the tool's checks, and must name a concrete concern (concentration, a mechanism flaw, instability). A veto that cites absolute Sharpe or absolute cost is recorded as invalid and does not count.", "If it fails, STOP and report." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 4 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/vault_server.py`, `src/agents/graph.py`, `src/agents/prompts.py`, `04_agent_lab.py`, tests, `agent_lab/cache/`, `agent_lab/planted/` |
| Amendment | No: S33-7 is refined within §08's "LLM + tool"; no pre-registered threshold, feature or rule changes |

### S33-15 · Attempt 3 superseded (the Skeptic saw the planted label); neutral labels, five audit fixes, attempt 4

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | The audit of the lab code found that the Skeptic's prompt names an injected spec's origin, and five further faults. What happens to attempt 3, what is fixed, and how is the planted-signal test rerun? |
| Options considered | (a) keep attempt 3's PASS with a disclosure; (b) supersede it, fix the label and the five audit items, rerun once as attempt 4 (chosen, Eliya's instruction) |
| Decision | **Attempt 3 is superseded, not deleted.** `Lab.inject` set an injected spec's hypothesis to `{"injected": "<source>"}` and the Skeptic prompt prints the hypothesis, so the Skeptic request of the planted feature began `Hypothesis: {"injected":"injected:planted"}` (attempt 1's request; attempts 2 and 3 reused its cached answer). Attempts 1 and 2 carry the same flaw; no noise spec reached the Skeptic. Attempt 3's PASS does not count; its files move to `agent_lab/cache/planted_attempt3.jsonl` and `agent_lab/planted/attempt3/` and stay committed. **Neutral labels:** an injected spec (planted or noise) reaches the LLMs as its DSL spec and the hypothesis `{"feature_idea": <the spec's name>}`; its origin stays in `candidates.jsonl` (`source`), which no prompt includes. The spec names describe their construction and contain no origin word. A test asserts that no prompt sent to any LLM in the planted run contains `planted`, `injected` or `noise` (case-insensitive) or an injected spec's source. **Audit fixes:** (1) a Coder answer whose `spec` is not a JSON object becomes `{"unparsed": <answer>}` (an invalid spec, S33-9), the MCP tool accepts any JSON value as `spec`, and any exception after the spec parses (a refusal of the vault included) is caught by the server, written as a trial row with stage `refused` and the error, and returned as a rejected proposal; the graph also records a failed tool call as a rejected proposal, so the lab never stops on a proposal. (2) The words that invalidate a Risk veto (S33-14) are matched with letters, not word characters, as boundaries, so snake_case names (`net_sharpe`, `cost_sensitivity`) match; `costly` and `borrowed` still do not. The Risk prompt also asks that the notes not cite Sharpe ratios, costs or the tool's figures, since a veto whose notes restate them would not count. (3) A cached answer records the cost its live call had (`recorded_cost_usd`), which goes into the proposal's trial notes and `candidates.jsonl` (S33-9); the budget meter still charges a cached answer nothing and sums each cached call once. `04_agent_lab.py --replay` needs `--out`, and a replay refuses to write into `agent_lab/` (the committed run folders). (4) Each Hypothesis round calls `get_trial_history` through the MCP server and receives every logged trial in summary (trial id, kind, rung, headline Sharpe and max drawdown rounded to 2 decimals; for agent rows the feature name and expression and the stage reached), besides this run's earlier candidates with their verdicts (S33-7). (5) The new tests found two faults, fixed in the code: `anonymise` gave sector i the code `A<perm[i]+1>`, not S33-5's `A<j+1>` with j the position of i in the permutation (now as S33-5 states; attempts 1 to 3 used the earlier mapping), and `planted_verdict` compared a signed correlation with the \|corr\| thresholds of S33-8 (now `abs`; the run already passed absolute values, so no result changes). (6) `tests/test_vault_server.py` (S33-5, S33-6, S33-9, S33-14, S33-15) and `tests/test_planted_signal.py` (S33-8: the planted run replayed from the committed cache must PASS and reproduce `agent_lab/planted/summary.json`, with no prompt naming an origin) are written. **Attempt 4** runs `04_agent_lab.py --planted` live with κ, the window, the gate thresholds, the noise specs, the base-rung rule and the PASS rule unchanged. The Hypothesis prompt (trial history), the Skeptic's input for injected specs (neutral hypothesis) and the Risk prompt (notes) change, so their calls are new and made live under the meter. If attempt 4 fails, it stops and is reported; Gate 3's planted-signal test then stays failed. **Run of attempt 4.** The first invocation stopped after 12 live calls (6 Hypothesis, 6 Coder; USD 0.012038) when the Skeptic's API call failed with a network error (`openai.APITimeoutError`: TLS handshake timed out, after the client's 2 retries), before any verdict. The same command was run again: its requests are identical, so the 12 cached answers replayed at zero cost and the run continued live from the Skeptic (2 live calls, Skeptic and Risk; USD 0.000875). This resumes attempt 4 and is not a new attempt: no setting, prompt or answer differs from an uninterrupted run. **Result: attempt 4 PASS** (base rung M3): proposed 11, validated 1 (the planted feature: uplift 1.39, P 1.00), vetoed 0, surviving 1. The Skeptic saw the hypothesis `{"feature_idea": "short-to-long volatility ratio"}` and accepted; the Risk tool checks passed it (turnover ratio 0.93, mean absolute residual beta 0.0007, adverse-cost uplift +1.37) and the Risk LLM did not veto (`concern` null). The 4 noise specs and the 2 LLM proposals that reached the walk-forward failed the gate (uplift −0.44 to −0.10) and the cost-sensitivity check; 1 LLM proposal failed redundancy; 3 were invalid specs, each a `mul_state` below the root (Amendment 7 C2), so the invalid-proposal rate is 3 of 6, all grammar violations and none a parsing failure. Unaided discovery (information only): no. Attempt 4: 14 live calls, USD 0.012913. All attempts: 38 live calls, USD 0.032617. **Origin test.** Literally applied, "no prompt contains `noise`" fails on attempt 4 only because the Hypothesis LLM wrote "does add noise to cross-sectional ranking" and the Coder prompt quotes that hypothesis. The test therefore exempts exactly the string values longer than 20 characters of the LLMs' own cached answers that contain a forbidden word, and checks all other prompt text strictly; it still flags attempt 1's `{"injected":"injected:planted"}`, and an injected spec's source may not appear anywhere |
| Rationale | A Skeptic told which candidate is the planted one cannot test the Skeptic; the test must see the injected specs exactly as it sees any proposal. The audit items stop a malformed answer from ending a run without a trial row (manual §3.5), close the forbidden-word gap that the Risk prompt's own key names opened, make the trial notes state what each proposal cost, keep the committed record from being overwritten, and give Hypothesis the trial history S33-7 promised |
| Evidence | Attempt 1 cache `agent_lab/cache/planted_attempt1.jsonl` (Skeptic request: `Hypothesis: {"injected":"injected:planted"}`); audit of 5 Nov 2026 (graph.py `inject`, prompts.py `skeptic_messages`; graph.py `coder`; vault_server.py `run_walkforward` re-raise; the regex `\b(sharpe\|costs?\|borrow)\b`; llm.py cached `cost_usd` 0.0; `04_agent_lab.py` replay into `agent_lab/planted/`; graph.py `hypothesis` without `get_trial_history`; missing test files cited by S33-5, S33-6, S33-8); Eliya's instruction (5 Nov 2026): "attempt 3's PASS is contaminated (the Skeptic saw "injected:planted"). Record it in S33-15 (attempt 3 superseded, not deleted).", "Give every injected spec (planted and noise) a neutral, non-identifying label.", "Run planted attempt 4 live … If it fails, STOP and report." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/graph.py`, `src/agents/prompts.py`, `src/agents/llm.py`, `src/agents/vault_server.py`, `04_agent_lab.py`, `tests/test_vault_server.py`, `tests/test_planted_signal.py`, `agent_lab/` |
| Amendment | No |

### S33-10 · The base rung of the agent lab and M5 is M2

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | Which rung do agent features extend (Amendment 7 C1)? |
| Options considered | M1, M2, M3 by In-Sample headline net Sharpe (the rule of Amendment 7 C1; no other option) |
| Decision | M2. In-Sample headline net Sharpe (weekly T-bill, 10 bps / 2%, 624 weeks 2008-01-04 to 2019-12-13): M1 −1.2856, M2 −0.9865, M3 −1.4169; M2 is the highest. The lab's server rebuilds M2's book from the vault and gets the same headline Sharpe as `06_backtest.py` (−0.986488 against −0.986488, difference 0.0), with the trial log unchanged (M2's spec hash is already logged) |
| Rationale | Amendment 7 C1 fixes the rule; this entry records its outcome and the local reproduction |
| Evidence | S32-11 (Mattia, 3 Nov 2026): "M1 −1.286 / −1.183, M2 −0.986 / −0.887, M3 −1.417 / −1.311 … Among M1–M3 the highest headline net Sharpe is M2's"; local `06_backtest.py --all` on main `e88f940` (5 Nov 2026), `outputs/backtests/M2/summary.json` `net_sharpe_rf_tbill` −0.986487564971885 (M1 −1.285581, M3 −1.416857; M0, ENS and M0\* also equal S32-11); `src.agents.vault_server.real_server("M2").base()["net_sharpe"]` −0.986487564971885 |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `04_agent_lab.py`, `agent_lab/run/` |
| Amendment | No (Amendment 7 C1 applied) |

### S33-16 · The real In-Sample run: trial-log snapshot, limits, cache and resume

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | How does the real In-Sample run see the trial history so that a replay reproduces it, and what are its limits? |
| Options considered | (a) Hypothesis reads the live `docs/trial_log.csv` (rejected: a replay sees the run's own rows and later rows, so its prompts differ, S33-15 audit); (b) a snapshot at the start plus this run's own trials (chosen, Eliya's instruction) |
| Decision | `04_agent_lab.py --insample` copies `docs/trial_log.csv` at its start to `agent_lab/run/trial_log_snapshot.csv`. `get_trial_history` then returns the snapshot's rows plus the rows of the trial log whose spec hash this run's server wrote or evaluated, in trial-log order; it never shows a row written by anyone else after the snapshot. Every proposal of the run (accepted, rejected or invalid) is a row of `docs/trial_log.csv` (S33-9: spec hash, metrics, cost). A replay (`--insample --replay --out <folder outside agent_lab/>`) copies the committed snapshot to `<folder>/trial_log.csv` and writes there, never to `docs/trial_log.csv`, so its history and prompts equal the live run's. Limits: 40 LLM candidates (`agent_lab.max_candidates`), no injected specs, base rung M2 (S33-10); the budget is USD 5 minus the spend already in `agent_lab/cache/` (the planted runs, USD 0.032617), so the lab's total stays under the hard stop; the meter keeps the peak prices of S33-1. Every LLM call is cached in `agent_lab/run/cache/insample.jsonl`. The run writes `agent_lab/run/candidates.jsonl`, `summary.json`, `vault_server_log.jsonl` and the snapshot. If a call fails (network or API error), the same command is run again: identical requests are answered from the cache at zero cost and the run continues live; each resumption is recorded. No prompt, threshold or setting changes during the run |
| Rationale | The snapshot fixes what Hypothesis can see at every round, so a replay rebuilds identical requests; writing every proposal to the real trial log keeps the deflated Sharpe's trial count complete (manual §3.5); counting the planted spend keeps the whole lab under USD 5 |
| Evidence | Eliya's instruction (5 Nov 2026): "the run snapshots docs/trial_log.csv at its start into agent_lab/run/; Hypothesis reads only that snapshot plus this run's own trials, so a replay sees the same history", "at most 40 candidates, under the $5 hard stop, with the meter at peak prices", "every LLM call is cached under agent_lab/run/cache/", "if a call fails, resume from the cache as you did in attempt 4, and record it", "no prompt, threshold or setting changes during the run"; audit of 5 Nov 2026 (S2); S33-1; S33-7; S33-9; S33-15 |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction and spend approval of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `src/agents/vault_server.py`, `04_agent_lab.py`, tests, `agent_lab/run/`, `docs/trial_log.csv` |
| Amendment | No |

### S33-17 · The recognition probe

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | How is the residual risk measured that the model recognises the sectors behind the anonymised codes A1 … A9? |
| Options considered | (a) one call per code: the model sees that code's anonymised summary from `get_features` and names the ETF (chosen); (b) one call with all nine codes (rejected: the answers would be a joint assignment, not nine independent guesses) |
| Decision | After the run, 9 calls of the lab's model, one per code, each with the code's six features at the In-Sample end (value, 104-week mean and standard deviation, exactly as `get_features("2019-12-27")` gives them) and the list of the 9 sector ETFs with their sector names; the model answers `{"ticker": one of the 9, "reason": str}`. A hit is the code's true ticker; an unparseable or unlisted answer is a miss. The hit rate (hits / 9, against 1/9 by chance) is reported as a measured residual of the anonymisation, with each code's answer; it changes nothing in the run. The calls are cached in `agent_lab/run/cache/probe.jsonl`, under the same meter and budget; the mapping itself is used only to score the answers and is written only as hit or miss per code |
| Rationale | Independent calls measure what a single proposal's context could reveal; the result shows how much the anonymisation protects against the model's memory of sector behaviour |
| Evidence | Session 3.3 instructions §6 ("Recognition probe"); Eliya's instruction (5 Nov 2026): "run the recognition probe (one call per code A1…A9; report the hit rate as a measured residual)"; S33-5 (anonymisation) |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `04_agent_lab.py`, `src/agents/prompts.py`, `agent_lab/run/` |
| Amendment | No |

### S33-18 · Results of the In-Sample agent run and the recognition probe

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | What did the real In-Sample lab run and the recognition probe give? |
| Options considered | Report as computed (chosen); change anything because of them (excluded: manual §3.4, §3.8) |
| Decision | **Run** (`04_agent_lab.py --insample`, code `13aa688`, base rung M2 at −0.986488, S33-10): one invocation, no failed call, no resumption. 40 proposals, every one a `docs/trial_log.csv` row of kind "agent" (16 rows before, 56 after). 24 invalid specs: 13 `mul_state` below the root (Amendment 7 C2), 4 Coder answers whose JSON braces do not balance (the largest answer used 932 of the 1,500 output tokens, so none was cut off), 2 unknown operation `abs`, 2 `cs_z` with an extra key, 1 unknown operation `close`, 1 `ratio` without `a`, 1 `lag` with n 0. 4 stopped at redundancy (3 with REV1, \|corr\| 0.961 to 1.000; 1 with MOM26_1, 0.977). 12 reached the walk-forward and all failed the §07 gate against M2: the largest uplift was +0.146 with P(uplift > 0) 0.755 (candidate 4, `rel_mom_26_4_credit`), the largest P 0.857 (candidate 22, uplift +0.126; candidate 33, uplift +0.133), and the other uplifts ran from −0.176 to +0.090. No candidate reached the Skeptic or Risk; validated 0, vetoed 0, surviving 0, so `agent_lab/run/review.md` lists no feature for approval. Spend: 80 live calls (40 Hypothesis, 40 Coder), USD 0.127144. A replay into a folder outside `agent_lab/` made 0 live calls, left `docs/trial_log.csv` unchanged, and reproduced `candidates.jsonl` byte for byte and `summary.json` field for field. The first replay differed only in the summary's spend and call count, because these summed every cache file, including `probe.jsonl` written after the run; they now count the run's own cache file, and the live values (USD 0.127144, 80 calls) are unchanged. `review.md` prints uplift and P with 3 decimals, so candidate 4's +0.146 does not read as the 0.15 threshold. **Probe** (S33-17): 9 live calls, USD 0.002564; 3 hits of 9 (hit rate 0.33 against 0.11 by chance): A5 named XLK, A6 XLU and A7 XLE, all correct. The model answered XLE five times, XLU three times and XLK once, so the hits are the three codes with the most distinctive profiles (strong momentum and high beta; the lowest beta and volatility; deep negative momentum with high volatility). This is the measured residual of the anonymisation; every Hypothesis prompt holds all nine codes' summaries, so it applies to the run. It changes nothing in the run. The probe prompt dates the summary to the end of December 2019 (the In-Sample end), which may have helped recognition. `probe.json` keeps each answer and hit as S33-17 asks, so the three hits show their tickers; the true ticker of a miss is not written. **Lab total** (planted runs, In-Sample run, probe): 127 live calls, USD 0.162325, under the USD 5 stop. **Open for Eliya and Mattia:** Amendment 7 C3 defines M5 as the base rung plus the human-approved agent features; with no survivor there is no feature to approve, so whether M5 is built (and what it would be) needs their decision. Nothing about M5 was started |
| Rationale | The record states the outcome, including the failures and the probe residual, so the deflated Sharpe's trial count (56 rows) and the Gate 3 scorecard rest on the logged run |
| Evidence | `agent_lab/run/summary.json`, `candidates.jsonl`, `review.md`, `probe.json`, `run_log.jsonl` (one live invocation), `cache/insample.jsonl` (80 entries, cost sum USD 0.127144), `cache/probe.jsonl` (9 entries, USD 0.002564), `agent_lab/cache/` (38 entries, USD 0.032617); `docs/trial_log.csv` (rows 17 to 56); Eliya's spend approval (5 Nov 2026) |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam; Mattia Cervelli (pull request review) |
| Files affected | `docs/decisions.md`; `04_agent_lab.py` (summary spend and call fields; `review.md` prints uplift and P with 3 decimals) |
| Amendment | No |

### S33-19 · M5 is absent; the gate evaluates M1, M2, M3 and ENS; H5 result

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | What happens to M5 and ENS when no agent feature is approved? |
| Options considered | (a) M5 is absent, ENS stays M1–M3 (chosen); (b) a re-run of the lab to look for a feature (rejected: every trial is already logged, and a re-run until something passes would be a search the deflated Sharpe has to pay for, with no pre-registered basis) |
| Decision | M5 does not exist: no candidate of the In-Sample run survived (S33-18), so there is no agent feature to approve and the base rung plus approved agent features cannot be formed. The selection rule evaluates M1, M2, M3 and ENS in that order, with M5 marked absent (`src.stats.selection_gate(..., absent=("M5",))`). ENS stays the equal-weight rank average of M1–M3. **H5 result:** no agent-proposed feature survived the gate, so H0 (DSR below threshold) is not rejected; all 40 agent trials stay in `docs/trial_log.csv` and count in the trial number of the deflated Sharpe. Reported as limitations: the invalid-spec rate of the run (24 of 40 proposals, mostly `mul_state` below the root and unbalanced JSON) and the recognition-probe hit rate (3 of 9 against 1 of 9 by chance, S33-17). There is no re-run |
| Rationale | The pre-registration names M5 conditionally ("+ M5 if it exists") and builds it from approved features only; with none, the ladder runs without it, and the agent trials still count against the result |
| Evidence | Pre-registration §07 table: M5 "Best rung + approved agent features", "Research-lab output (H5)"; ENS "Equal-weight average of the cross-sectional rank scores of M1–M3 (+ M5 if it exists)"; §02 H5 "Agent-proposed features survive the same gate as human features after trial-count deflation", "H0: DSR below threshold. Every trial reported"; S33-18 (validated 0, surviving 0; invalid 24 of 40; probe 3 of 9); `src/stats.py` `selection_gate(..., absent=...)` ("e.g. M5 without approved agent features"); Eliya's decision (5 Nov 2026): "no candidate survived, so M5 does not exist", "No re-run." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (decision of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `docs/decisions.md` only; the selection step (`07_evaluate.py`, Mattia's) passes `absent=("M5",)` |
| Amendment | No: the pre-registration anticipates a missing M5 |

## 2026-11-05 · Session 3.4: OOS run script, freeze tooling and OOS evaluation

"Instruction" quotes the session 3.4 prompt (5 Nov 2026) and its addition of the same day. Everything in this session
is built and tested on the synthetic market of contract 18 (sessions to 2020-12-31) only: no part of it was run on real
data, no Out-of-Sample value was computed or seen, and no `FROZEN.lock` was created in the repository. "Approved by"
lists the approvals given so far; Eliya approves through the review of the 3.4 pull request.

### S34-1 · Ownership of `08_run_oos.py` moves to Mattia

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | `08_run_oos.py` is Eliya's file (S2-7). Who builds it before Gate 3, while Eliya carries the agent lab, M5 and the gate? |
| Options considered | (a) Eliya after the agent lab; (b) Mattia for this phase, calling only Eliya's public functions and never editing his files (chosen) |
| Decision | (b). Mattia owns `08_run_oos.py` and its test file `tests/test_run_oos_script.py` from this phase. It imports Eliya's public functions (`03_build_features.py`: `load_inputs`, `load_opens`, `build_tables`, `build_labels`, `build_forward_returns`, `write_tables`; `05_train_walkforward.py`: `spec_for`; `src.vault`: `Vault`, `Vault.unlock`, `spec_hash`, `logged_spec_hashes`; `src.labels`: `walk_forward_folds`, `label_end_by_week`; `src.models`: `LadderData`, `walkforward_rung`, `ensemble_scores`, `grid`, `walkforward_settings`) and edits none of his files. Hooks that are missing are listed in the pull request (S34-5) instead of being added to his code |
| Rationale | Gate 3 needs the freeze tooling and the run script tested before `FROZEN.lock` is signed; Eliya's remaining work before Gate 3 is on the critical path |
| Evidence | Instruction §1: "Decision S34-1: ownership of 08_run_oos.py moves from Eliya to Mattia for this phase. Reason: Eliya carries the agent lab, M5 and the gate before Gate 3. Approved by Eliya through this PR's review. 08 only calls Eliya's public functions and never edits his files. If a hook is missing, list it in the PR rather than editing his code."; S2-7 (ownership table) |
| Proposed by | Eliya Allam and Mattia Cervelli (session 3.4 instruction) |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `tests/test_run_oos_script.py` |
| Amendment | No: ownership, not specification |

### S34-2 · Cross-machine reproduction of the In-Sample walk-forward

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | The 17 walk-forward outputs of S32-11 were rerun on Mattia's machine and compared with Eliya's. Eight `scores_sha256` differ. Is the walk-forward reproduced, and how is reproduction judged from now on? |
| Options considered | (a) require byte-identical score files (`scores_sha256`); (b) judge by numeric tolerance and identity of the ±1 signals (chosen) |
| Decision | (b). Reproduction is judged by numeric tolerance and signal identity, not by file hashes. On Mattia's machine (Windows 11, Python 3.12.14, lightgbm 4.7.0, scikit-learn 1.9.1, numpy 2.5.4, pandas 3.1.0) all 17 outputs reproduce Eliya's: 9 are byte-identical (`scores_sha256` equal): M0, M0_L13, M0_L26, M0_L52, M0_star, M3, M3_d2, M3_d3, ENS. The 8 ridge runs (M1, M1_a0.1, M1_a1, M1_a10, M2, M2_a0.1, M2_a1, M2_a10) differ only at floating-point level, max \|difference\| 3.47e-17, with identical weekly ranks and identical ±1 signals in all 624 weeks, so their backtests and metrics are identical. The cause is a different summation order in the linear-algebra library on another CPU. All 17 `spec_hash` values matched the trial log, so no trial row was added. The same rule applies to the reproduction check of `08_run_oos.py` (S34-6). It does not apply to the SHA-256 values of `FROZEN.lock` (S34-3): they test that the files on the machine that runs the OOS are those frozen, not that two machines agree |
| Rationale | Floating-point summation order is not part of the method; ranks and signals are what the strategy trades |
| Evidence | Operating manual §6: "Numeric comparisons use tolerances, never file hashes."; addition to the session 3.4 instruction (5 Nov 2026): "9 are byte-identical (scores_sha256 equal): M0, M0_L13, M0_L26, M0_L52, M0_star, M3, M3_d2, M3_d3, ENS. The 8 ridge runs (M1, M1_a0.1, M1_a1, M1_a10, M2, M2_a0.1, M2_a1, M2_a10) differ only at floating-point level: max \|difference\| 3.47e-17, with identical weekly ranks and identical ±1 signals in all 624 weeks"; S32-11 ("The other 16 `scores_sha256` are compared with Eliya's table in the review of this pull request") |
| Proposed by | Mattia Cervelli |
| Approved by | Eliya Allam and Mattia Cervelli (review of this pull request) |
| Files affected | `docs/decisions.md`; `08_run_oos.py` (reproduction check, S34-6) |
| Amendment | No |

### S34-3 · `08_run_oos.py --freeze`: content of `FROZEN.lock`

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | What does `--freeze` record, from which inputs, and what may change in the repository between the freeze and the run? |
| Options considered | Gate output: (a) the JSON of `src.stats.selection_gate` at `outputs/metrics/selection_gate.json` (chosen); (b) a name typed on the command line. Post-freeze changes: (c) none; (d) only `FROZEN.lock` and `docs/decisions.md` (the signatures, chosen); (e) any documentation |
| Decision | `--freeze` refuses (nothing written) when `git status --porcelain` is not empty (untracked files count; git-ignored ones do not), when `FROZEN.lock` already exists, when `outputs/oos_access_log.json` has an entry, when the gate file is missing or malformed, or when any artefact below is missing, built with another config (`check_used`) or stale (its `summary.json` `spec_hash` differs from `spec_hash(spec_for(name), cfg)`, or is not in the trial log). It writes `FROZEN.lock` (JSON, sorted keys, LF): `format` 1, `created_utc`, `code_commit` (HEAD), `config_sha256` (`config.yaml`), `trial_log_sha256` and `trial_count` (`docs/trial_log.csv`), `in_sample_end`, `data_end`, `gate_file`, `selected`, `models` (S34-6), `frozen_values` (the grid value chosen at the last In-Sample refit of M1, M2, M3 and M0\*, from the last row of each `selection.csv`, with its `test_year` and `refit`; Amendment 6 C2), `allowed_after_freeze` = [`FROZEN.lock`, `docs/decisions.md`] and `artefacts`: path → SHA-256 of `data/processed/{features, market_states, labels, momentum_variants, sizing_betas, forward_returns}.csv`, `features_config.yaml`, the gate file, and `outputs/walkforward/<name>/{scores.csv, used.yaml, summary.json, selection.csv}` of every model in `models`. The gate file holds at least `selected` (a name of `models.candidate_order` or `M0_star`) and `candidates` (each with `name` and `status` `evaluated` or `absent`), as `selection_gate` returns them; it is written by the gate step, which does not exist yet (missing hook, S34-5). The five signatures go into `docs/decisions.md` by hand at Gate 3; `FROZEN.lock` and that entry are then committed. Text files are hashed with CRLF read as LF, so a checkout's line endings cannot change a hash; data files are hashed byte for byte. The artefacts must be on the machine that runs the OOS; if the freeze and the run are on different machines, the frozen files are copied, not rebuilt (S34-2) |
| Rationale | §10 step 2 lists what the lock records; (d) leaves room only for the signatures, so the code, config, trial log and artefacts of the run are exactly those frozen |
| Evidence | §10 vault protocol step 2: "Freeze: `FROZEN.lock` records the config hash, code commit, trial-log hash and model artefacts; all five members sign it in `docs/decisions.md`."; Amendment 6 C2; S31-14: "The chosen values are recorded in `FROZEN.lock` with the other artefacts."; S32-10 (staleness by `spec_hash`); Instruction §2: "writes FROZEN.lock with the config hash, code commit, trial-log hash, the selected model (from the selection gate's output) and the SHA-256 of every model artefact and walk-forward output it depends on (prereg §10 step 2). It refuses to run with a dirty tree. The five signatures go into docs/decisions.md by hand at Gate 3."; `.gitattributes` ("Text files are stored with LF") |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `tests/test_run_oos_script.py` |
| Amendment | No |

### S34-4 · The single run and `outputs/oos_access_log.json`

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | What does the run check before it touches Out-of-Sample data, when is the access entry written, and how can CI see the log, given that `outputs/` is git-ignored? |
| Options considered | Entry: (a) after a successful run; (b) after every check passes and before the vault is unlocked (chosen). CI: (c) a `.gitignore` exception (shared file); (d) the human adds the log with `git add -f` after the run; a test reads the working-tree file and every version in the available git history (chosen) |
| Decision | The run refuses, with nothing written, unless `FROZEN.lock` exists and parses; the working tree is clean; `code_commit` is an ancestor of HEAD and `git diff --name-only code_commit HEAD` lists only paths of `allowed_after_freeze`; `config.yaml`, `docs/trial_log.csv` and every artefact hash as recorded; and `outputs/oos_access_log.json` is missing or an empty list. It then writes the log as a JSON list with exactly one entry (`utc`, `code_commit`, `head_commit`, `lock_sha256`, `selected`, `data_end`, `script` `08_run_oos.py`) before `Vault.unlock()`, so every access to Out-of-Sample data is logged even if a later step fails. A second run is refused. After Gate 4 the log is committed with `git add -f outputs/oos_access_log.json`; `tests/test_oos_access_log.py` (run by CI) fails if the file in the working tree, or any version of it in the git history available to the job, holds more than one entry or is malformed. Open point for both humans (not resolved here): §10 step 4 ("A bug found afterwards is fixed in a new commit and rerun, and both runs are shown") requires a second run, which step 3 and this test refuse; how a rerun is logged must be decided by an amendment before any rerun |
| Rationale | (b) records the access itself, which is what the vault protocol protects; (d) needs no change to a shared file |
| Evidence | §10 vault protocol step 3: "One command, `run_oos.py`, checks the lock, runs once, and appends a timestamped entry to `oos_access_log.json`. CI fails if the log ever has more than one entry."; step 4: "A bug found afterwards is fixed in a new commit and rerun, and both runs are shown with the reason. No retuning, ever."; contract 15: "This access log is separate from `oos_access_log.json`, the single-entry log written only by `08_run_oos.py` (§10), which CI checks."; Instruction §3: "refuses unless FROZEN.lock exists and its hashes match the current tree; refuses if outputs/oos_access_log.json already has an entry; it appends exactly one timestamped entry … Add a CI test that fails if oos_access_log.json ever holds more than one entry."; `.gitignore` `outputs/*` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `tests/test_run_oos_script.py`, `tests/test_oos_access_log.py` |
| Amendment | No (the step 3 / step 4 tension is left open for an amendment) |

### S34-5 · Full-range tables through 03's unlock path; missing hooks

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | How does the run rebuild the tables to the data end without overwriting the frozen In-Sample tables, and which of Eliya's functions lack a hook it needs? |
| Options considered | Output folder: (a) overwrite `data/processed/` (would change hashed artefacts); (b) `data/processed/oos/` (git-ignored, chosen) |
| Decision | (b). After the access entry, the run calls 03's `load_inputs` and `load_opens` with `end` = `data.end`, `build_tables`, `build_labels(…, data.end)` and `build_forward_returns(…, data.end)`, and writes them with `write_tables(…, allow_oos=True)` and the lock path, the unlock path of S22-5. Missing hooks, listed in the pull request and worked around without editing Eliya's files: (1) `build_forward_returns` uses one date for the truncation and the period boundary, so at `data.end` every period reads `IS`; the run re-assigns `period` from `realised_on` against `split.in_sample_end` (contract 7) and checks it with `validate_forward_returns`. (2) The vault refuses any `forward_returns` table with a return realised after `split.in_sample_end`, even when unlocked (`_validate_frame`); the run does not need it (the grid values are frozen, so no inner Sharpe is computed; the engine's forward returns come from the raw prices, as in 06, S23-8). (3) The vault has no public `momentum_variants(as_of)`; the run calls it if it exists, otherwise the vault's own sealed and logged reader `_rows_until("momentum_variants", …)`. (4) No script writes the gate file of S34-3 yet. Model inputs (features, market states, labels, sizing betas, momentum variants) are read through `Vault(…, data_dir=data/processed/oos)` after `unlock()` |
| Rationale | The frozen In-Sample tables stay byte-identical, so the lock still verifies after the run; every model input still goes through the vault |
| Evidence | S22-5: "Its writer raises `OOSAccessError` for any later row unless `FROZEN.lock` exists and `allow_oos=True` is passed, which only `08_run_oos.py` does (Gate 4)"; contract 7; S31-1; operating manual §3.3 "All model and research data access goes through `src/vault.py`."; Instruction §3: "rebuilds the full-range tables through 03's unlock path"; S34-1 ("If a hook is missing, list it in the PR rather than editing his code") |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review (the four hooks) |
| Files affected | `08_run_oos.py` |
| Amendment | No |

### S34-6 · Out-of-Sample refits: folds, models and frozen values

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | Which refits score the Out-of-Sample weeks, which models are run, and which scores do the two December 2019 weeks (signal weeks 2019-12-20 and 2019-12-27, realised Out-of-Sample) get? |
| Options considered | Folds: (a) `src.labels.walk_forward_folds` with `split.in_sample_end` = `data.end` and `split.test_years` = [last In-Sample test year, year of `data.end`] (chosen); (b) a new fold builder in 08. December weeks: (c) scored by the 2019 Q4 refit, whose window extends to the next quarterly refit (chosen); (d) an extra refit at 2019-12-20; (e) left unscored (the book would carry its last targets) |
| Decision | (a) and (c). The run keeps the folds of (a) whose `test_end` is after the last In-Sample scored week (2019-12-13): the 2019 Q4 refit, now scoring 2019-10-04 to 2019-12-27, then one refit per calendar quarter to the last week with a realised label (2026-10-02 on the real calendar, §05). Every fit asserts the purge (`walkforward_rung`). Models (`FROZEN.lock` `models`): the selected model, every candidate the gate evaluated, M0 (the hurdle) and M0\* (the fallback), in `models.candidate_order`, then M0, M0_star; ENS adds its members. Values (Amendment 6 C2): M1, M2, M3 at their frozen value (`walkforward_rung(rung, …, value=v)`, parameters refitted each quarter); M0\* as M0 on `MOM{L}_1` with its frozen L (S31-6); M0 on `models.M0.feature`; ENS = `ensemble_scores` of the members' Out-of-Sample scores. The scores of the In-Sample weeks are the frozen `scores.csv`; the refits supply only the weeks after 2019-12-13. Reproduction check (S34-2): the 2019 Q4 refit's In-Sample weeks are compared with the frozen scores, and `run.json` reports the max \|difference\| and whether the ±1 signals are identical; a difference is reported, not a reason to stop (the In-Sample book uses the frozen scores either way) |
| Rationale | (a) applies Eliya's own fold rule unchanged, as contract 13 requires ("with the same rule"); (c) is that rule: a refit scores the weeks up to the next quarterly refit, and the 2019 Q4 window was cut only because the In-Sample period ended. (e) would hold stale positions for two weeks for no reason in the method |
| Evidence | §07 "The same refits continue during OOS on newly realised labels; tuning does not."; §07 step 6 "Every candidate, eligible or not, appears in the OOS scorecard."; Amendment 6 C2; contract 13: "OOS refits (§07, "the same refits continue during OOS") are produced by `08_run_oos.py` after the freeze with the same rule, never before."; contract 7: "the last In-Sample signal week is the one ending 2019-12-13"; S31-14 ("ENS ranks the members so refitted"); Instruction §3: "continues the quarterly refits into OOS with each rung's last In-Sample grid value frozen (Amendment 6 C2), for the selected model AND every candidate" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `tests/test_run_oos_script.py` |
| Amendment | No: applies §07, §10, contract 13 and Amendment 6 C2 |

### S34-7 · The continuous book and the run's outputs

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | How is each model backtested across 2019-12-27, and what is written? |
| Options considered | As below (chosen) |
| Decision | One book per model from its first scored week to the last week with every forward return realised (Amendment 2 C5): the frozen In-Sample scores followed by the Out-of-Sample scores, `size_book` with the sizing betas of the unlocked vault, and `run` in the three cost scenarios of S23-7. Prices and DGS3MO are read from the raw files cut at `data.end` (`06_backtest.py: read_market`, `read_risk_free`; the In-Sample paths of 06 keep `refuse_oos_returns`); `period` follows `realised_on` (contract 7). Check: the baseline net returns of the In-Sample weeks equal those of the frozen `outputs/backtests/<name>/weekly.csv` when it exists (max \|difference\| reported in `run.json`). Outputs under `outputs/oos/` (git-ignored): per model `scores.csv` (Out-of-Sample weeks only), `weekly.csv` (the columns of S23-10 and S32-2 over both periods), `metrics.csv` (`period_metrics` per scenario, rf and period), `summary.json`, `used.yaml`; and `run.json` (lock hash, folds, frozen values, the two reproduction checks, the rebuilt tables' rows and SHA-256) |
| Rationale | The book a live strategy would have held; the In-Sample equality check shows the boundary does not restart the book |
| Evidence | Amendment 2 C5: "The backtest is one continuous book from the first scored week to the data end. The OOS period does not restart from cash: its first trade is costed from the drifted In-Sample positions."; S21-13; S23-7, S23-8, S23-10, S32-2; Instruction §3: "backtests one continuous book across 2019-12-27 (Amendment 2 C5)" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `06_backtest.py` (`read_market`, optional `root` and `end` arguments that keep the old behaviour), `tests/test_run_oos_script.py`, `tests/test_backtest_script.py` |
| Amendment | No |

### S34-8 · `07_evaluate.py --period OOS`

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | What does the Out-of-Sample evaluation read and write, and when may it run? |
| Options considered | As below (chosen) |
| Decision | `--period IS` (the default) is the evaluation of S32-7, unchanged. `--period OOS` refuses unless `FROZEN.lock` exists and `outputs/oos_access_log.json` holds exactly one entry whose `lock_sha256` is that of the lock, and checks every `outputs/oos/<model>/used.yaml`. It writes `outputs/metrics/oos_models.csv` (one row per model and period, baseline costs, the metrics of S32-7 per period, the rank IC per period), `oos_benchmarks.csv` (T-bill, SPY, equal weight per period on the reference model's weeks), `oos_bonus.csv` (S34-9 for every model; the claim is made only for the selected model), `oos_secondary.csv` (S34-10), `oos_inference.csv` (S34-11), `oos_used.yaml`, and the plots `oos_<model>_{equity, drawdown, exposure, bridge}` and `oos_all_models_equity`, each period rebased to 100 on a shared dated log axis (S32-6). Every Out-of-Sample statistic of 07 is built and tested on the synthetic market only in this session |
| Rationale | Evaluation is possible only after the single run; the IS mode stays the Gate 3 input and is not touched |
| Evidence | §11: "computed separately for In-Sample and OOS"; "Every series starts at 100 in each period, on a shared dated axis, log scale."; S32-7; Instruction §4: "07_evaluate.py --period OOS (built and tested on synthetic): metrics per period, with IS and OOS equity curves each rebased to 100" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `07_evaluate.py`, `tests/test_evaluate_script.py` |
| Amendment | No |

### S34-9 · Conventions of the market-neutral bonus tests (§11)

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | §11 fixes the thresholds of the four market-neutral tests but not the estimators. Which are used? |
| Options considered | Beta interval: (a) Newey–West (Bartlett) HAC standard error of the OLS slope with the lag rule of S31-9 (chosen); (b) OLS standard error. Down-market interval: (c) a stationary block bootstrap of the whole paired series, the mean taken over the resampled down weeks (chosen); (d) an i.i.d. bootstrap of the down weeks only. Months: (e) calendar months of `realised_on`, compounded (chosen); (f) blocks of four weeks |
| Decision | On the Out-of-Sample weeks of each book, baseline costs, against SPY's forward return on the same weeks (never traded): (1) β = OLS slope of the weekly net return on SPY's (with intercept; `cov/var` as `src.metrics.market`), HAC variance Σ_j k_j Γ_j of the moment x̃_t u_t, Bartlett weights 1 − j/(L+1), L = `src.stats.newey_west_lags(T)`, normal interval at `inference.confidence` (0.95); passes if \|β\| < `metrics.market_neutral.beta_abs_max` (0.10) and the interval contains 0. (2) ρ = Pearson correlation of the same weekly series; passes if \|ρ\| < `corr_abs_max` (0.20). (3) Down weeks: SPY forward return < 0; mean weekly net return over them; percentile interval (`inference.confidence`) from `selection.bootstrap_resamples` stationary-bootstrap resamples (`src.stats.stationary_bootstrap_indices`, mean block `selection.bootstrap_block` = 4 weeks, seed `seed`) of the paired series; passes if the mean > 0 (the interval is reported). Down months: weeks grouped by the calendar month of `realised_on`, returns compounded, SPY < 0; the same bootstrap on the monthly series with a mean block of 1 month (≈ 4 weeks); passes if the mean > 0. (4) Consistency: Out-of-Sample mean weekly net return (passes if > 0), the share of the T − 51 rolling 52-week windows whose compounded return is positive, and the compounded return of each calendar year of `realised_on` (2019 holds only the week realised on 2019-12-30, reported as such). The bonus is met only if all four pass; it is claimed for the selected model only |
| Rationale | (a), (c) and (e) keep the time dependence of weekly returns and use the conventions already fixed for §11 (S31-8, S31-9) |
| Evidence | §11 bonus: "OOS beta of the full book (including IVV) to SPY: \|β\| < 0.10, with a 95% HAC interval containing 0"; "OOS correlation with SPY: \|ρ\| < 0.20"; "Mean weekly return in SPY-down weeks > 0, with a bootstrap interval; the same for down months"; "OOS mean weekly return > 0, plus the share of rolling 52-week windows with a positive return and the return in each calendar year of the OOS, all reported"; `config.yaml` `metrics.market_neutral: { beta_abs_max: 0.10, corr_abs_max: 0.20 }`; S31-8, S31-9 |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review (contract change, `docs/interfaces.md` contracts 16 and 17) |
| Files affected | `src/metrics.py` (`hac_beta`, `monthly_returns`, `rolling_positive_share`, `calendar_year_returns`), `07_evaluate.py`, `tests/test_metrics.py`, `tests/test_evaluate_script.py`, `docs/interfaces.md` (contracts 16 and 17: the four new public names) |
| Amendment | No: estimators for pre-registered thresholds |

### S34-10 · Secondary bonus: Sharpe and drawdown against SPY

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | How is the alternative bonus ("higher Sharpe and lower max drawdown than SPY, with a significance test") computed? |
| Options considered | As below (chosen) |
| Decision | Out-of-Sample weeks of each book, baseline costs: the book's headline Sharpe (weekly T-bill, §09) and max drawdown against SPY's on the same weeks (SPY held, no cost); significance by `src.stats.sharpe_difference_test(book, SPY)` (Ledoit–Wolf, S31-9), whose per-week Sharpe is μ/σ of the raw returns. Reported: both Sharpes, both drawdowns, the test's difference, z and p-value, and `meets` = higher Sharpe and smaller drawdown. Reported as a secondary result; at most one bonus is claimed |
| Rationale | One procedure, fixed in §11's inference table |
| Evidence | §11: "The alternative bonus (higher Sharpe and lower max drawdown than SPY, with a significance test) is reported as a secondary result. Only one bonus point exists, and we claim at most one."; §11 inference table: "Sharpe difference vs SPY \| Ledoit–Wolf (2008) HAC test \| Secondary bonus significance" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `07_evaluate.py`, `tests/test_evaluate_script.py` |
| Amendment | No |

### S34-11 · DSR and PBO in the Out-of-Sample report

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | On which returns are the Deflated Sharpe Ratio and PBO computed in the final report? |
| Options considered | DSR: (a) on the selected model's In-Sample walk-forward returns (chosen, headline), with the Out-of-Sample value as information; (b) Out-of-Sample only. PBO: In-Sample only (pre-registered) |
| Decision | The trial matrix is the In-Sample baseline net returns of `outputs/backtests/<name>/weekly.csv`, one column per distinct `spec_hash` of the trial log (a backtest whose `spec_hash` is not in the log is refused; `M0_L26` and `M0` share a column), on their common weeks. N = the number of rows of `docs/trial_log.csv` (S31-7). DSR = `src.stats.deflated_sharpe_ratio(selected In-Sample net, N, trial_returns=matrix)`; the same with the selected model's Out-of-Sample net returns is reported as information. PBO = `src.stats.pbo_cscv(matrix, inference.pbo_blocks)`. Reported with N, the number of columns and weeks |
| Rationale | DSR answers whether the In-Sample winner is more than the luckiest of N, which is a question about the selection; PBO is defined on the In-Sample matrix |
| Evidence | §10: "Auxiliary: PBO by CSCV. Run on the In-Sample weekly return matrix of every candidate configuration"; "Deflated Sharpe Ratio with N = every human and agent trial in the ledger"; §11 inference table; S31-7; S31-9; S32-10 (the backtest `summary.json` holds `spec_hash`) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `07_evaluate.py`, `tests/test_evaluate_script.py` |
| Amendment | No |

## 2026-11-05 · Session 3.5: submission packaging

"Instruction" quotes the session 3.5 prompt (5 Nov 2026); "Answer" quotes Mattia's answers of the same day to the two
questions the session asked before any code was written. "Course instructions" quotes `Mid-Term Project
Instructions.pdf` (DDMI 2026-27, the reference folder outside the repository), pages 3, 4 and 6. "Approved by" lists the
approvals given so far; Eliya approves through the review of the 3.5 pull request.

### S35-1 · What the course requires of the zip; the session prompt's refusal of raw data was wrong

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | The session 3.5 prompt asked `make_submission.py` to refuse "raw vendor data (data/raw/)", "any full price or return series" and "outputs that are not committed". S2-3 and `docs/licensing.md` ship `data/raw/**`, `data/processed/**` and `outputs/**` in the zip. Which governs? |
| Options considered | (a) the course instructions and S2-3: the zip ships the raw data, the processed data and the outputs (chosen); (b) the prompt literally: no raw data, no price series, no uncommitted output; (c) wait for a joint decision |
| Decision | (a). The course instructions rank above the session prompt (operating manual §2), and they require the raw data, the processed data and the results in `project/`, with results reproducible without downloading. The prompt's refusal of `data/raw/` and of full price or return series was wrong for the zip: it applies to the git repository only, where the pre-commit hook and `tests/test_hooks_policy.py` already enforce it (operating manual §3.6). "Outputs that are not committed" is replaced by S35-3: every output ships, synthetic wiring outputs are left out, and a stale output stops the build. The conflict was reported before any code was written |
| Rationale | A zip without data could not reproduce a single result, which the course instructions require and grade ("Code & Presentation Quality … reproducibility") |
| Evidence | Course instructions, Deliverables (p. 3): "You will submit a single file group_<group-number>.zip (e.g., group_4.zip) containing: project/: The code repository of your project; presentation.pdf (or .pptx): The slides used to present your project". Project code (p. 4): "the repository includes the data and the outputs of every step (e.g., in data/): raw data (including data from licensed sources such as Bloomberg), processed data, and final results. The results must be reproducible without downloading any data;"; "random seeds are fixed for all stochastic components, paths are relative to the repository root, and no API keys or credentials are included in the code;"; "it includes a way to recreate the environment (e.g., requirements.txt or pyproject.toml with a lock file such as uv.lock, or environment.yml) and specifies the Python version;"; "it includes a README.md with all the information needed to set up the environment, and the commands required to run the code (scripts or notebooks), in order."; "All results must be reproducible starting from the contents of the code repository. All steps will be reproduced by running the code, except for costly or non-deterministic steps (e.g., LLM or paid API calls): their saved outputs will be used as the starting point." Submission Method (p. 6): "A dedicated submission section will be created on the my.luiss platform where you will upload your single .zip file." S2-3: "the files of `project/` in `group_7.zip` are exactly `git ls-files` + `data/raw/**` + `data/processed/**` + `outputs/**`"; `docs/licensing.md`: "It stays local in `data/raw/` (git-ignored) and ships only in the LUISS submission zip, as the instructions require."; Answer 1: "ship the data, as the course PDF requires; S2-3. Note in S35 that the 3.5 prompt's refusal of data/raw/ and of price series was wrong for the zip; it applies to the git repository only, which CI already enforces." |
| Proposed by | Mattia Cervelli (Answer 1) |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `make_submission.py`, `tests/test_make_submission.py` |
| Amendment | No: packaging, not specification |

### S35-2 · Contents of `group_7.zip` and what the build refuses

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | Which files enter the zip, which are left out, and when does the build stop? |
| Options considered | Assistant and tool files: (a) left out of the list, as S2-3 does, and reported (chosen); (b) stop the build. Secrets: (c) stop the build (chosen); (d) leave the file out |
| Decision | `project/` holds `submission_files()` of S2-3, unchanged in rule (`git ls-files` + `data/raw/**` + `data/processed/**` + `outputs/**`, never a walk of the folder), minus: assistant and tool settings files at any depth (the local settings folder and instruction files of operating manual §3.2, matched by `make_submission.py: FORBIDDEN`; S2-3 covered four of them, this session adds `AGENTS.md` and `.codex/`), which are left out and listed in the output; and synthetic outputs, any path under `outputs/` with a folder named `synthetic` (S35-3). The build stops, writing nothing, when: (1) a file in the list is a `.env` file (`.env`, `.env.*`) at any depth; (2) any file in the list contains a key-like string: `sk-` followed by 20 or more key characters (DeepSeek and similar keys), an AWS access key id, a GitHub token, a Slack token, a Google API key, a PEM private-key header, an assignment of a name ending in `API_KEY`, `SECRET`, `TOKEN` or `PASSWORD` to a 16-character value holding a digit, or the value of the environment variable `DEEPSEEK_API_KEY` of the lab (S33-1) when it is set; the only exception is an exact match of `ALLOWED_FAKE_KEYS`, which holds one string, the fake sentinel key of `tests/test_agents_llm.py` (`sk-test-SENTINEL-…`, used to test that the lab never logs its key), found by the first dry run on the repository; (3) a tracked file has uncommitted changes (`git status --porcelain --untracked-files=no`), so `project/` is a committed state; (4) `README.md`, `pyproject.toml`, `uv.lock` or `config.yaml` is missing; (5) the presentation file is missing or is neither `.pdf` nor `.pptx`; (6) an output is stale (S35-3). The scan reads every file as bytes, data files included |
| Rationale | Tool files are local and harmless to omit, as S2-3 already does; a secret in any file means a leak that a human must fix, so the build cannot pass over it |
| Evidence | Instruction §2: "It refuses: … .env files, the API key or any key-like string; assistant or tool settings files (… AGENTS.md, .codex/, .mcp.json)" (the first two names omitted here, as in every committed file); course instructions (p. 4): "no API keys or credentials are included in the code", "it includes a way to recreate the environment … and specifies the Python version", "it includes a README.md"; operating manual §3.2; S2-3; S33-1 and `src/agents/llm.py` (`API_KEY_ENV = "DEEPSEEK_API_KEY"`) |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `make_submission.py`, `tests/test_make_submission.py` |
| Amendment | No |

### S35-3 · Every output ships; synthetic outputs are left out; a stale output stops the build

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | Which of `outputs/` ships (it is git-ignored, so almost nothing in it is committed), and how is a stale result kept out? |
| Options considered | (a) all of `outputs/`, minus synthetic wiring outputs, and a `check_used` of every settings file against the current `config.yaml` (chosen); (b) a fixed allow-list of folders; (c) only tracked files |
| Decision | (a). Every `used.yaml` (and `oos_used.yaml`) under `outputs/`, and `data/processed/config.yaml` and `features_config.yaml`, is checked with `src.config.check_used` against the settings its writer saves, taken from the writer's own function: `data/processed/config.yaml` `data_settings`; `features_config.yaml` `features_settings`; `outputs/walkforward/<name>/` `walkforward_settings`; `outputs/backtests/<name>/` and `outputs/diagnostics/shift/<name>/` `06_backtest.py: backtest_used(cfg, name)`; `outputs/diagnostics/placebo/` `placebo_used(cfg, reference)` with the reference of its `summary.json`; `outputs/ledger/` `ledger_used`; `outputs/metrics/used.yaml` `07_evaluate.py: metrics_used`; `outputs/metrics/oos_used.yaml` `oos_metrics_used`; `outputs/oos/<name>/` `08_run_oos.py: oos_used(cfg, name)`. A settings file in any other place stops the build, since it cannot be checked. Every failure is listed and nothing is written. `06_backtest.py: ledger_used` and `07_evaluate.py: metrics_used`, `oos_metrics_used` are the expressions those scripts already saved, moved into functions (no change in content) |
| Rationale | The zip must hold results of the submitted code and config; one writer function per settings file means the check cannot drift from what the scripts save |
| Evidence | Answer 2: "all of outputs/, with two safeguards: (a) exclude synthetic wiring outputs (outputs/backtests/synthetic/ and any other synthetic-only folder); (b) refuse to build if any output folder with a used.yaml fails check_used against the current config.yaml, so no stale result can enter the zip. The manifest lists every file with its SHA-256 and size, and the zip's total size."; operating manual §6 ("Scripts use the skeleton's `check_used` pattern to refuse outputs built with a different config"); S23-10, S32-4, S32-7, S34-7, S34-8 (the settings each writer saves) |
| Proposed by | Mattia Cervelli (Answer 2) |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `make_submission.py`, `06_backtest.py`, `07_evaluate.py`, `tests/test_make_submission.py` |
| Amendment | No |

### S35-4 · Zip layout, determinism and the manifest

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | How is the zip laid out and described? |
| Options considered | As below (chosen) |
| Decision | `group_7.zip` holds `project/<path>` for every file of S35-2 and the presentation at the root as `presentation.pdf` (or `presentation.pptx`), nothing else. Entries are sorted, deflated, with a fixed timestamp (1980-01-01) and mode 0644, so the same files give the same zip bytes. Defaults: output `group_7.zip` in the project folder (git-ignored by `*.zip`), presentation `presentation.pdf` in the project folder; both can be given on the command line (`--out`, `--presentation`). The manifest, printed and optionally written with `--manifest PATH`, lists every entry with its SHA-256 and size in bytes, then the number of files, the total uncompressed size, the zip's size and the zip's SHA-256 |
| Rationale | A reproducible archive and a manifest let the reviewer and the teaching team check what was submitted |
| Evidence | Course instructions (p. 3), quoted in S35-1; Instruction §2: "It prints a manifest with SHA-256s."; Answer 2 (manifest with SHA-256, size and the zip's total size); decision sheet item 19: "Submission named `group_7.zip`" |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `make_submission.py`, `tests/test_make_submission.py` |
| Amendment | No |

### S35-5 · The presentation is a PDF only; the course sets no size limit

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | (1) Which presentation formats does the build accept? S35-2 and S35-4 accepted `.pdf` or `.pptx`. (2) Do the course instructions set a size limit for the zip? |
| Options considered | (1) (a) `.pdf` or `.pptx`, as the course allows (S35-2); (b) a PDF only, stored as `presentation.pdf` (chosen). (2) (c) enforce a limit; (d) none, since the instructions state none; the manifest keeps reporting the zip's size (chosen) |
| Decision | (1b). The build refuses any presentation whose name does not end in `.pdf` (`.pptx` included, whatever the case of the suffix) and any `.pdf` whose content does not start with the PDF header `%PDF-`; the file given with `--presentation` is stored at the zip root as `presentation.pdf`, whatever its name. This supersedes the `.pptx` clauses of S35-2 (refusal 5) and S35-4. The course instructions accept `.pptx` too ("presentation.pdf (or .pptx)"), so a PDF only is the team's stricter choice within them, not a course requirement. (2d). Searched over the six pages of the instructions ("MB", "GB", "size", "limit", "upload", ".zip"): the only rules on the file are its name and that it is a single zip uploaded to my.luiss, with no size limit; the build therefore enforces none |
| Rationale | One fixed format and name the graders can open without office software; a renamed slide deck is caught by its header, not only its suffix |
| Evidence | Course instructions, Deliverables (p. 3): "You will submit a single file group_<group-number>.zip (e.g., group_4.zip) containing: project/: The code repository of your project; presentation.pdf (or .pptx): The slides used to present your project"; Submission Method (p. 6): "A dedicated submission section will be created on the my.luiss platform where you will upload your single .zip file."; instruction of 5 Nov 2026: "the presentation must be a PDF named presentation.pdf at the zip root … Refuse .pptx and any other format, with a test. Also confirm from the PDF's quoted pages whether there is a size limit for the zip; if there is one, the build refuses to exceed it." Tests `test_refuses_any_presentation_that_is_not_a_pdf`, `test_refuses_a_pdf_name_without_pdf_content`, `test_the_presentation_is_stored_as_presentation_pdf_whatever_its_name` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026; Eliya Allam: PR review |
| Files affected | `make_submission.py`, `tests/test_make_submission.py` |
| Amendment | No |

## 2026-11-05 · Session 3.6: Amendment 8 (the Out-of-Sample run of record and the bug-fix rerun)

"Instruction" quotes the session 3.6 prompt (5 Nov 2026). "Answer" quotes the options Mattia chose that day for the two
questions the session asked before any code was written. Amendment 8 was committed alone (commit `acff27f`) before this
entry and before any code it affects. When this entry was written, no Out-of-Sample value had been computed or seen,
`FROZEN.lock` did not exist and `outputs/oos_access_log.json` had no entry. Everything below is built and tested on the
synthetic market of `tests/test_run_oos_script.py` only. "Approved by" lists the approvals given so far; Eliya approves
through the review of the 3.6 pull request.

### S36-1 · Implementing Amendment 8: the rerun decision, the checks of `--rerun`, the log rule and the rerun's folders

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | Amendment 8 C1 allows a rerun of `08_run_oos.py` only to correct a bug found after the run of record, recorded first in a decision. How does the script recognise that decision, what does it check before any Out-of-Sample access, which files may have changed since the freeze, how is the rerun logged, where does it write, and how does CI count the log's entries? |
| Options considered | Decision format: (a) three dedicated fields `Bug`, `Fix commit` and `Fix files` in the usual table (chosen); (b) the existing `Files affected` field, which every decision has, so it cannot mark a rerun decision. Files allowed to change since the freeze: (c) exactly `FROZEN.lock`, `docs/decisions.md` and the decision's files, as the instruction says; (d) (c) plus `outputs/oos_access_log.json` and the `Fix files` of the decisions named by earlier rerun entries (chosen, Answer 1); (e) (c) plus the log only. Outputs: (f) separate folders per rerun decision (chosen, Answer 2); (g) overwrite `outputs/oos/` and `data/processed/oos/` |
| Decision | (a), (d) and (f). (1) **Rerun decision.** An entry `### <ID> · <title>` of `docs/decisions.md` whose table has the fields `Bug` (not empty), `Fix commit` (exactly one commit hash in backticks, 7 to 40 hexadecimal characters) and `Fix files` (one or more repository paths, each in backticks); the other fields are those of every decision. Its ID must head exactly one entry. (2) **`08_run_oos.py --rerun ID`** (it cannot be combined with `--freeze`) refuses, writing nothing, unless all of these hold: ID is a word of letters, digits, `.`, `_` and `-`; `FROZEN.lock` exists and parses; the log holds the run of record (a first entry naming no decision, written for the current lock) and is valid under (4); no entry names ID yet, so each decision gives at most one rerun; the decision ID exists with the three fields; the fix commit resolves, comes after the freeze (the frozen `code_commit` is its ancestor and differs from it) and is an ancestor of HEAD; the files it changes (`git diff --name-only <fix>^1 <fix>`, which for a GitHub merge commit is the whole pull request; `docs/decisions.md` aside) are exactly `Fix files`; `Fix files` names none of `config.yaml`, `docs/trial_log.csv`, `FROZEN.lock` or an artefact of the lock (the fix changes no setting, threshold, grid, feature, model, cost or selected model). Every check of the run of record (S34-4) then applies unchanged: a clean tree, the frozen commit an ancestor of HEAD, and the config, trial-log and artefact hashes as recorded. The only difference is that the files changed since the freeze may be `allowed_after_freeze`, `outputs/oos_access_log.json`, this decision's `Fix files` and the `Fix files` of the decisions named by earlier rerun entries. (3) **Entry and folders.** The rerun appends exactly one entry, with the fields of S34-4 plus `rerun_decision` (ID) and `fix_commit` (the full hash), before `Vault.unlock()`. It writes its full-range tables to `data/processed/oos_reruns/<ID>/` and its outputs to `outputs/oos_reruns/<ID>/`, in the layout of `outputs/oos/`; its `run.json` also holds the decision, the bug and the fix commit. The run of record's `outputs/oos/` and `data/processed/oos/` are never overwritten, so both runs can be shown. Run without `--rerun`, the script refuses as before once the log has an entry, and the message names `--rerun`. (4) **CI** (`tests/test_oos_access_log.py`, `check_oos_log_text`). A log fails if it is malformed; if it holds more than 1 + K entries, where K is the number of rerun decisions recorded in `docs/decisions.md` in the same state (the working tree for the working-tree log, the same commit for each committed version); if its first entry names a decision; if a later entry names no decision or one not recorded; or if two entries name the same decision. (5) **Not in this pull request.** After a rerun, `07_evaluate.py --period OOS` still requires exactly one entry and reads only `outputs/oos/`, and `make_submission.py` stops on settings files under `outputs/oos_reruns/` (no known writer, S35-3). Both refuse, so nothing is reported or shipped wrongly. Both get adapted, with tests, if a rerun ever happens, before its results are reported |
| Rationale | (a) makes a rerun decision checkable by the script without changing any other decision. (d): the procedure of S34-4 commits the log after Gate 4, so (c) would refuse every rerun once the log was committed. A second bug's rerun would also be refused, because the first fix's files changed after the freeze even though they are recorded and logged. (f): "both runs are shown" needs the first run's outputs kept. A clean tree and committed decision mean the decision is recorded before the rerun, as C1 requires |
| Evidence | Amendment 8 C1: "Before the rerun, a decision entry records the bug, the fix commit and the files it changes; the fix changes no setting, threshold, grid, feature, model, cost or selected model. Each such rerun appends exactly one entry to outputs/oos_access_log.json naming that decision, and CI fails if the log holds more than one entry plus one per recorded rerun decision. Every run's results are reported, with the reason."; §10 step 4: "both runs are shown with the reason"; S34-4: "After Gate 4 the log is committed with `git add -f outputs/oos_access_log.json`"; S34-3 (`allowed_after_freeze`); Instruction §2: "08_run_oos.py --rerun DECISION_ID checks that the decision exists with those fields, and that only the files it names (plus FROZEN.lock and docs/decisions.md) changed since the freeze. Update tests/test_oos_access_log.py to the C1 rule. Add tests, including that a rerun naming no valid decision is refused."; Answer 1: "Widen it: Allowed = FROZEN.lock, docs/decisions.md, the decision's Fix files, outputs/oos_access_log.json, plus the Fix files of decisions already named by earlier rerun entries. Recorded as a deviation from the prompt in S36-1."; Answer 2: "Separate folders: outputs/oos_reruns/<ID>/ and data/processed/oos_reruns/<ID>/, so the run of record's outputs stay untouched and 'both runs are shown'." |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 5 Nov 2026 (Answers 1 and 2); Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `tests/test_run_oos_script.py`, `tests/test_oos_access_log.py` |
| Amendment | No new amendment: implements Amendment 8 (commit `acff27f`); (d) deviates from the instruction's wording, not from the pre-registration |

## 2026-11-05 · Session 3.7: selection gate, selection-bias diagnostics and the pre-freeze hooks

Format of the operating manual's evidence standard. "Instruction" quotes the session 3.7 task list Eliya set (5 Nov
2026). Everything here is In-Sample: the vault stays sealed, no `FROZEN.lock` exists, and no Out-of-Sample value is
computed or seen. "Approved by" is completed by Mattia's approving review of the pull request from branch
`feat/3.7-gate`. Amendment 8 is not on `main` when this session starts (the last amendment is Amendment 7).

### S37-1 · Correction to S33-19: where the selection step runs

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | S33-19 ("Files affected") says the selection step that passes `absent=("M5",)` is in `07_evaluate.py`. Is that right? |
| Options considered | (a) leave S33-19 as written; (b) record the correction in a new entry, since entries are never edited in place (chosen) |
| Decision | (b). S33-19 is wrong on this point: `07_evaluate.py` does not call `src.stats.selection_gate`, and before this session no module ran it (the only calls were in `tests/test_stats.py`). The selection step is `05_train_walkforward.py --select`, added in this session (S37-4), and that is where `absent=("M5",)` is applied. Everything else in S33-19 stands (M5 absent, ENS = M1–M3, the H5 result) |
| Rationale | The decision log must say where the binding rule is applied, because `08_run_oos.py` reads its output (S34-3) |
| Evidence | S33-19, Files affected: "the selection step (`07_evaluate.py`, Mattia's) passes `absent=("M5",)`"; `grep -rn "selection_gate(" --include=*.py` on `main` `df5bf6e`: the definition in `src/stats.py` and 12 calls in `tests/test_stats.py`, none elsewhere; S32-7: "The §07 selection gate is not applied here (Phase 3.1, `src.stats.selection_gate`)"; Instruction: "S33-19 says the selection step is in 07_evaluate.py; it is not. No module ran selection_gate before this session. 05_train_walkforward.py --select (this session) is where absent=("M5",) is applied." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `docs/decisions.md` only |
| Amendment | No |

### S37-2 · `build_forward_returns` takes a truncation date separate from the In-Sample end (S34-5 hook 1)

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | `03_build_features.py: build_forward_returns(daily_open, daily_close, is_end)` uses one date both to truncate the opens and as the period boundary, so 08's call at `data.end` labels every week `IS` (S34-5, hook 1). How is the truncation separated? |
| Options considered | (a) a keyword `truncate_at` (default: `is_end`), with `is_end` kept as the period boundary; a truncation after `is_end` needs an existing `FROZEN.lock` passed as `lock_path`, as `write_tables(..., allow_oos=True)` does (chosen); (b) the same keyword without a lock check; (c) a second function for the Out-of-Sample run |
| Decision | (a). Signature `build_forward_returns(daily_open, daily_close, is_end, truncate_at=None, lock_path=None)`. Both inputs are cut at `truncate_at` (`is_end` when `None`), and `period` is "IS" if `realised_on ≤ is_end`, "OOS" if after, missing where `realised_on` is `NaT`, by `src.backtest.forward_returns(weekly_open, is_end=is_end)` (Mattia's, unchanged). If `truncate_at` is after `is_end`, the function raises `OOSAccessError` unless `lock_path` is given and exists; without that, a `realised_on` after `is_end` still raises `OOSAccessError`, as before. With `truncate_at=None` the output is identical to the current function's (default behaviour unchanged; `build_labels` and `main` keep calling it with three arguments). A `truncate_at` before `is_end` is refused (`ValueError`) |
| Rationale | (a) gives 08 the period labels of contract 7 straight from the builder, and keeps the seal: the builder itself cannot compute an Out-of-Sample return before the freeze. (b) would let any caller compute Out-of-Sample returns before Gate 3 |
| Evidence | S34-5 (hook 1): "`build_forward_returns` uses one date for the truncation and the period boundary, so at `data.end` every period reads `IS`; the run re-assigns `period` from `realised_on` against `split.in_sample_end`"; contract 7 (`period`); S22-5 ("Its writer raises `OOSAccessError` for any later row unless `FROZEN.lock` exists and `allow_oos=True` is passed"); operating manual §3.3; Instruction §1(a): "build_forward_returns takes an optional truncation date separate from the In-Sample end, with the default behaviour unchanged" |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review; contract 7) |
| Files affected | `03_build_features.py`, its tests, `docs/interfaces.md` (contract 7) |
| Amendment | No |

### S37-3 · Public `Vault.momentum_variants(as_of)` (S34-5 hook 3)

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | 08 reads the M0\* momentum variants through the vault's private `_rows_until` because there is no public reader (S34-5, hook 3). What does the public reader do? |
| Options considered | (a) `momentum_variants(as_of)` with the same seal, slice and log as `features`, `market_states` and `sizing_betas` (chosen); (b) leave the private call in 08 |
| Decision | (a). `Vault.momentum_variants(as_of)` returns the rows of `momentum_variants.csv` (contract 3: `MOM13_1`, `MOM26_1`, `MOM52_1`, index `(date_close, ticker)`) with `date_close ≤ as_of`, known after Friday close `as_of`. An `as_of` after `is_end` raises `OOSAccessError` unless `FROZEN.lock` exists and `unlock()` was called; every call is logged `ok` or `refused` under the method name `momentum_variants`, exactly like the other table readers (it is `_rows_until("momentum_variants", "momentum_variants", as_of)`). 08's `vault_momentum` already prefers a public `momentum_variants` when it exists, so 08 needs no change |
| Rationale | One public, tested path per table; 08 should not depend on a private method of another owner's file |
| Evidence | S34-5 (hook 3): "The vault has no public `momentum_variants(as_of)`; the run calls it if it exists, otherwise the vault's own sealed and logged reader `_rows_until("momentum_variants", …)`"; `08_run_oos.py: vault_momentum` (`getattr(vault, "momentum_variants", None)`); contract 15; Instruction §1(c): "a public Vault.momentum_variants(as_of), sealed and logged like the other readers" |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review; contract 15) |
| Files affected | `src/vault.py`, its tests, `docs/interfaces.md` (contract 15) |
| Amendment | No |

### S37-4 · The §07 gate: `05_train_walkforward.py --select` and `outputs/metrics/selection_gate.json`

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | Which inputs does the selection step read, how does it refuse stale ones, which rf does it pass, and what does it write for `08_run_oos.py --freeze` (S34-3, S34-5 hook 4)? |
| Options considered | Inputs: (a) the In-Sample baseline weekly net returns of `outputs/backtests/<name>/weekly.csv` for M0, M1, M2, M3 and ENS (chosen); (b) re-run the engine in 05. rf: (c) the `rf` column of M0's `weekly.csv`, the weekly T-bill return 06 wrote (chosen); (d) recompute it from DGS3MO in 05 |
| Decision | (a) and (c). `--select` is a new option of `05_train_walkforward.py`, exclusive with `--model` and `--fixed`. For each of M0, M1, M2, M3 and ENS it stops (`SystemExit`, nothing written) when: `outputs/backtests/<name>/used.yaml` fails `check_used` against `06_backtest.py: backtest_used(cfg, name)` (06 loaded by path, read only); `outputs/walkforward/<name>/summary.json` or `outputs/backtests/<name>/summary.json` has a `spec_hash` other than `spec_hash(spec_for(name, cfg), cfg)` (the S32-10 rule of 06); that hash is not a row of `docs/trial_log.csv`; the backtest summary's `period` is not `IS` or its `baseline` is not the configured baseline scenario; any row of `weekly.csv` is not In-Sample (`period` other than `IS`, or a `date_close` or `realised_on` after `split.in_sample_end`); `net` or `rf` is missing or not finite; a candidate's weekly index differs from M0's; or the `rf` columns of the five files differ by more than 1e-12. It then calls `src.stats.selection_gate({M1, M2, M3, ENS}, M0, cfg, rf=rf, absent=("M5",))` with rf the weekly T-bill (Amendment 6 C1, S31-13) and writes `outputs/metrics/selection_gate.json` (JSON, sorted keys, LF, no timestamp): the gate's `selected` and `candidates` unchanged (every row: Sharpe, zero-cost Sharpe, MDD, P(uplift > 0) at blocks 4 and 8, the uplift interval, the three test verdicts, `passes`), plus `absent`, `m0` (headline and zero-cost Sharpe, MDD), `thresholds` (the `selection` section), `seed`, `weeks`, `first_week`, `last_week`, `first_realised_on`, `last_realised_on`, `rf_source`, `rf_tbill_annual` (M0's summary), `inputs` (per model: `spec_hash` and SHA-256 of `weekly.csv`), `fallback` (true when M0\* is selected) and `statement`. When no candidate passes, `statement` reads "No candidate passed the §07 gate, so M0* is traded: the ML models failed to beat the baseline (pre-registration §07 step 5)." `--select` also fills the trial log (S37-5) and writes the diagnostics (S37-7); every check of the three steps runs before any of the three files is written |
| Rationale | The gate must use the backtests the slides report, and refuse them exactly when 06 would; reading rf from M0's file keeps one T-bill series (06's) for every Sharpe |
| Evidence | §07 steps 1 to 5; Amendment 6 C1; S31-8, S31-13; S32-10; S23-10 (`weekly.csv` holds `rf`, the weekly T-bill); S33-19 and S37-1 (M5 absent); S34-3 ("The gate file holds at least `selected` … and `candidates` (each with `name` and `status` …), as `selection_gate` returns them"); Instruction §2: "05_train_walkforward.py --select reads the In-Sample weekly net returns of M0, M1, M2, M3 and ENS from outputs/backtests/<name>/weekly.csv. It refuses stale outputs, checking spec_hash against the trial log as 06 does. It takes the weekly T-bill rf, calls src.stats.selection_gate(results, m0, cfg, rf=..., absent=("M5",)) (Amendment 6 C1 headline Sharpe), and writes outputs/metrics/selection_gate.json, the file 08 reads, with every candidate's row and the selected model." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review; contract 15) |
| Files affected | `05_train_walkforward.py`, its tests, `docs/interfaces.md` (contract 15) |
| Amendment | No: applies §07 and Amendment 6 C1 |

### S37-5 · `is_sharpe` and `is_mdd` of the human trial rows

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | S23-6 (3) left `is_sharpe` and `is_mdd` empty for the selection step to fill from the outputs of 06. Which values, in which format, and what if a cell is already filled? |
| Options considered | Value: (a) the baseline headline Sharpe `net_sharpe_rf_tbill` and `max_drawdown` of `outputs/backtests/<name>/summary.json` (chosen; the agent rows hold the same two figures, S33-9); (b) the zero-cost Sharpe. Filled cell: (c) overwrite; (d) keep it if it equals the value, stop if it differs (chosen) |
| Decision | (a) and (d). In `--select`, each human row is matched to the backtest folders whose `summary.json` holds its `spec_hash`, among the 17 names of S31-10, each checked as in S37-4 (`used.yaml`, current spec hash, In-Sample only). Every human row must match at least one folder; `M0` and `M0_L26` share trial 1 and must give equal values. The values are written as Python's shortest float text (`repr`), the format of the agent rows. An empty cell is filled; a filled cell equal to the value is kept; a filled cell that differs stops the run (the trial log or the backtest is stale). Agent rows keep their recorded metrics. The file is rewritten with the `csv` writer of `src.vault.append_trial` (LF), so every other cell and every agent row stay byte-identical |
| Rationale | One Sharpe convention in the trial log, the gate's (Amendment 6 C1); refusing a silent overwrite keeps the log append-only in spirit |
| Evidence | S23-6 (3): "`is_sharpe` and `is_mdd` stay empty until Phase 3.1, where the selection step fills them from the outputs of `06_backtest.py`"; S23-9 ("baseline `net_sharpe_rf_tbill` and `max_drawdown`, S23-10"); S33-9; S31-6 (`M0_L26` is trial 1); Instruction §3: "Fill is_sharpe and is_mdd for every human trial row of docs/trial_log.csv from the 06 outputs (S23-6). Agent rows keep their recorded metrics." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `05_train_walkforward.py`, its tests, `docs/trial_log.csv` |
| Amendment | No |

### S37-6 · Weekly In-Sample returns of the agent candidates that reached the walk-forward (`--agent-returns`)

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | PBO (§10) runs on the weekly In-Sample returns of every candidate configuration, agent candidates included, but the lab run kept only summary metrics of the 12 candidates that reached the walk-forward (S33-18). How are their weekly returns obtained? |
| Options considered | (a) re-score each one through the sealed vault from the spec in its trial row and book it with the lab's own engine path, checking the result against the row's recorded figures (chosen); (b) leave the agent candidates out of the PBO matrix; (c) re-run the lab (refused: S33-19, no re-run) |
| Decision | (a). `05_train_walkforward.py --agent-returns` takes every agent row of `docs/trial_log.csv` whose `notes` record the stage `walk_forward`, rebuilds its spec from `params_json`, and stops unless `spec_hash(spec, cfg)` equals the row's `spec_hash` (otherwise the config changed and the row is stale). It scores the spec with `Vault.run_walkforward` on the sealed vault of `src.agents.vault_server.real_server` (base rung from `agent_lab/run/summary.json`, M2, S33-10) and books it with that server's `book` (§09 sizing and Mattia's engine at baseline costs, the vault's forward returns and T-bill), the computation that produced the row. A logged spec adds no trial row (S23-2); the run checks that `docs/trial_log.csv` is byte-identical afterwards and stops otherwise. Reproduction: the headline Sharpe and the max drawdown must equal the row's `is_sharpe` and `is_mdd` within 1e-9 (S34-2: tolerances, not hashes), else the run stops and reports both. Outputs (git-ignored): `outputs/agent_lab/walkforward/agent_c<candidate, 2 digits>/weekly.csv` (weekly index, `realised_on`, `period`, `net`, `rf`; every week In-Sample) and `summary.json` (`trial_id`, `candidate`, `spec_hash`, `net_sharpe_rf_tbill`, `max_drawdown`, `weeks`, `first_week`, `last_week`). No `used.yaml` is written (S35-3 checks only the settings files it knows); `--select` checks each folder's staleness through the spec hash instead (summary hash = row hash = `spec_hash(params_json, cfg)`). Feasibility, 5 Nov 2026, before this entry: trial 17 re-scored in 9.5 s, Sharpe and MDD differences 0.0, trial log unchanged |
| Rationale | (b) would drop 12 of the configurations the selection process could have picked from, and §10 names agent candidates in the matrix; re-scoring a logged spec on In-Sample data is a reproduction, not a new trial |
| Evidence | §10: "PBO by CSCV. Run on the In-Sample weekly return matrix of every candidate configuration (rungs × grid values × agent candidates)"; S31-7 ("agent candidates"); S33-9, S33-16, S33-18 (12 candidates reached the walk-forward); S23-2; S34-2; Instruction §4: "PBO by CSCV with inference.pbo_blocks (16) over every configuration that has weekly In-Sample returns (rungs, fixed grid values, agent candidates that reached the walk-forward); list what is included." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `05_train_walkforward.py`, its tests |
| Amendment | No |

### S37-7 · Selection-bias diagnostics: DSR and PBO in `outputs/metrics/selection_bias.json`

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | On which matrix and with which N are the Deflated Sharpe Ratio and PBO of the In-Sample selection computed, and how does this relate to S34-11? |
| Options considered | Matrix: (a) one column per distinct `spec_hash` with weekly In-Sample returns: the 17 backtest folders (`M0_L26` and `M0` one column) and the agent folders of S37-6 (chosen); (b) the backtest folders only, as S34-11 does for the Out-of-Sample report |
| Decision | (a). In `--select`, after the gate: every backtest folder is checked as in S37-4 and every agent folder as in S37-6; a walk-forward agent row without its folder stops the run (run `--agent-returns` first). The matrix holds the baseline weekly net returns on the weeks common to all columns. PBO = `src.stats.pbo_cscv(matrix, inference.pbo_blocks)` (16 blocks, C(16, 8) = 12,870 splits, S31-9). DSR = `src.stats.deflated_sharpe_ratio(selected In-Sample net, N, trial_returns=matrix)`, N = the number of rows of `docs/trial_log.csv` (human and agent, S31-7), the selected model being the gate's (its `outputs/backtests/<name>/weekly.csv`); Sharpes per week, mean/std of the net returns (S31-9, S31-12). `selection_bias.json` (sorted keys, LF, no timestamp) holds: `selected`; `dsr` (value, N, human and agent counts, the selected model's weekly and annualised Sharpe, weeks, the trial-Sharpe variance, SR₀ weekly); `pbo` (value, blocks, splits, block length, weeks dropped, median logit); `matrix` (weeks, first and last week, and every column with its name, kind, rung, `spec_hash`, trial ids, source folder); `excluded` (every trial row without weekly returns, with its trial id, kind and stage). Relation to S34-11: `07_evaluate.py --period OOS` builds its In-Sample matrix from `outputs/backtests/` only, so it would hold 16 columns, not 28, and its In-Sample DSR and PBO would differ from these; it is Mattia's file, so this is an open point for him (read the agent folders or `selection_bias.json`), not changed here |
| Rationale | The DSR asks whether the winner beats the luckiest of every configuration tried; leaving the agent trials out of the variance and of PBO would understate the search |
| Evidence | §10 validation hierarchy items 2 and 3; §11 inference table ("Selection bias \| Deflated Sharpe Ratio, N = all human and agent trials", "Selection-process overfitting \| PBO by CSCV, 16 blocks"); S31-7, S31-9, S31-12; S34-11; Instruction §4: "the Deflated Sharpe Ratio of the selected model, with N = every trial-log row (human and agent); PBO by CSCV with inference.pbo_blocks (16) over every configuration that has weekly In-Sample returns (rungs, fixed grid values, agent candidates that reached the walk-forward); list what is included." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instruction of 5 Nov 2026); Mattia Cervelli (pull request review) |
| Files affected | `05_train_walkforward.py`, its tests |
| Amendment | No: applies §10 and §11 |

### S37-8 · Fixes from the session audit, and two open points for `08_run_oos.py`

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | The independent audit of the session's code (before any code commit) found no blocker and three should-fix points and several nits. Which are fixed, and what is left open? |
| Options considered | Fix in Eliya's files now (chosen for 2 to 6); change `08_run_oos.py` (refused: Mattia's file, S34-1) |
| Decision | (1) **Open for Mattia, not fixed here:** S37-2's rationale ("the builder itself cannot compute an Out-of-Sample return before the freeze") holds only for `truncate_at`. The three-argument call with a late `is_end`, which 08's `rebuild_tables` still makes (`build_forward_returns(daily_open, daily_close, end)`), computes every return to `data.end` with no lock check in the builder and labels them `IS`. Nothing leaks today: 08 runs that call only after its lock and tree checks, and `write_tables(..., allow_oos=True)` needs the lock. Refusing a late `is_end` in the builder would break 08's current call at Gate 4, so 08 should move to `build_forward_returns(daily_open, daily_close, is_end, truncate_at=end, lock_path=<FROZEN.lock>)` and drop its period re-assignment. (2) `--select` and `--agent-returns` stop when `FROZEN.lock` exists (`refuse_after_freeze`): the gate file and the trial log are hashed by the lock (S34-3), so a rerun after the freeze would change a frozen artefact. (3) `select` writes the three texts to `<target>.tmp` files and then moves each onto its target with `os.replace`; a failed write leaves the old files in place and no temporary file. (4) `trial_rows` refuses a row with more or fewer fields than the header, so a rewrite cannot drop a field. (5) `_gate_frames` refuses a `models.candidate_order` whose non-absent names, after M0, differ from `GATE_MODELS` (M0, M1, M2, M3, ENS). (6) PBO is taken from the same CSCV logits as the median logit (one CSCV pass, same value as `pbo_cscv`). Not changed: `agent_returns` writes each candidate's folder as soon as it reproduces (a later failure leaves valid earlier folders); `selection_gate.json` carries a `rule` key (a one-line citation of §07, Amendment 6 C1, S33-19, S37-1) beyond the S37-4 list; the `--agent-returns` command line branch is run on real data, not in a unit test. Observation for the write-up: `M1_a0.1` and `M1_a1` have identical weekly net returns (their scores differ by at most 5.3e-6 but rank the sectors the same every week), so the PBO matrix holds two equal columns |
| Rationale | The fixes protect frozen artefacts and the trial log; the 08 change belongs to its owner |
| Evidence | Session audit (5 Nov 2026), should-fix 1 to 3 and nits 4 to 11; S34-1 ("If a hook is missing, list it in the PR rather than editing his code"); S34-3 (`trial_log_sha256`, the gate file among the artefacts); `08_run_oos.py: rebuild_tables` (`s03.build_forward_returns(daily_open, daily_close, end)`); tests added: `test_select_refuses_once_frozen_lock_exists`, `test_agent_returns_refuses_once_frozen_lock_exists`, `test_select_leaves_no_temporary_file`, `test_trial_rows_refuse_a_row_with_an_extra_field`, `test_gate_frames_refuse_a_candidate_order_other_than_the_decision` |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam; Mattia Cervelli (pull request review; point 1 is his to act on) |
| Files affected | `05_train_walkforward.py`, `tests/test_select.py`; later `08_run_oos.py` (Mattia) |
| Amendment | No |

### S37-9 · Results of the §07 gate, the trial metrics and the selection-bias diagnostics

| Field | Content |
| --- | --- |
| Date | 2026-11-05 |
| Question | What did `--agent-returns` and `--select` give on the real In-Sample outputs? |
| Options considered | Report as computed (chosen); change anything because of them (excluded: manual §3.4, §3.8; §07 is binding) |
| Decision | **Agent returns** (`--agent-returns`): the 12 agent candidates that reached the walk-forward (trials 17, 18, 20, 26, 38, 45, 47, 48, 49, 50, 53, 55; candidates 1, 2, 4, 10, 22, 29, 31, 32, 33, 34, 37, 39) were re-scored through the sealed vault in 2 min 15 s; every headline Sharpe and max drawdown equals its trial row (all 12 within 1e-9; trial 17 to 0.0 in the feasibility check), 624 weeks each, and `docs/trial_log.csv` was byte-identical before and after (SHA-256 `11fb3cd0…007a`). **Gate** (`--select`; 624 weeks, signal weeks 2008-01-04 to 2019-12-13, realised 2008-01-14 to 2019-12-23; baseline 10 bps / 2%; headline Sharpe with the weekly T-bill, average 0.60% a year; thresholds Sharpe ≥ M0 + 0.15, MDD ≥ M0 − 0.02, P ≥ 0.80; 5,000 resamples, block 4, seed 42). Hurdle M0: Sharpe −0.771, MDD −47.98%. M1: Sharpe −1.286 (fail), MDD −58.46% (fail), P(uplift > 0) 0.100 (fail; block 8: 0.095). M2: −0.986 (fail), −49.11% (pass), P 0.267 (fail; 0.268). M3: −1.417 (fail), −61.34% (fail), P 0.028 (fail; 0.024). M5: absent (S33-19). ENS: −1.192 (fail), −58.21% (fail), P 0.131 (fail; 0.137). Uplift 95% intervals: M1 −1.318 to 0.288, M2 −0.917 to 0.505, M3 −1.370 to 0.011, ENS −1.215 to 0.365. **Selected: M0\* (`M0_star`).** No candidate passed the §07 gate, so M0\* is traded: the ML models failed to beat the baseline (pre-registration §07 step 5); M2 passed only the drawdown test. `08_run_oos.py: read_gate` accepts the file; `run_models` gives M1, M2, M3, ENS, M0, M0_star. **Trial metrics:** 32 cells filled (16 human rows × `is_sharpe`, `is_mdd`), e.g. M0 −0.7714198666898625 / −0.47979956694425874, M0\* −0.633948093579576 / −0.4005343760888368; agent rows unchanged; trial log SHA-256 after `8313875d…936a`. **DSR** of M0\* In-Sample: 3.1e-5, with N = 56 (16 human, 40 agent), the trial Sharpes of 28 columns (weekly variance 0.001208), SR₀ 0.0806 a week (0.581 annualised) against M0\*'s −0.0722 a week (−0.521 annualised, zero rf), 624 weeks. **PBO**: 0.293 (16 blocks of 39 weeks, none dropped, 12,870 splits, median logit 0.799) over 28 configurations on 624 common weeks: M0 (trial 1, with `M0_L26`), M1, M2, M3, ENS, M0\*, the 10 other fixed grid values and the 12 agent candidates; excluded: 28 agent rows without weekly returns (24 `invalid_spec`, 4 `redundancy`). A second `--select` filled 0 cells and wrote byte-identical files (`selection_gate.json` `ac7d305b…c2ba`, `selection_bias.json` `6740f1e4…56a5`). Reading: H2 is not supported In-Sample (no candidate beats M0); the DSR says M0\*'s In-Sample Sharpe is far below what the best of 56 unskilled trials would show; PBO 0.29 says that in 29% of the CSCV splits the In-Sample winner fell to or below the median Out-of-Sample (a diagnostic only, it chooses nothing). No code, setting, threshold or score was changed because of these results |
| Rationale | The record fixes the gate outcome before the freeze, so `FROZEN.lock` and the slides rest on one logged result |
| Evidence | `outputs/metrics/selection_gate.json`, `outputs/metrics/selection_bias.json`, `outputs/agent_lab/walkforward/agent_c*/summary.json` (5 Nov 2026, code `afd7b4d`); `docs/trial_log.csv` (commit `7d1ce3b`); S32-11 (the same Sharpes and drawdowns of the six models); §07 step 5: "If none passes, M0\* is traded, so the trading system still contains an optimisation method. The report states plainly that the ML models failed to beat the baseline." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam; Mattia Cervelli (pull request review) |
| Files affected | `docs/decisions.md` only |
| Amendment | No |

## 2026-11-06 · Session 3.8: follow-ups from Session 3.7 and a flaky test

Evidence-standard format. "Instruction" quotes the session 3.8 prompt (6 Nov 2026). Everything below is built and tested
on the synthetic markets of `tests/test_run_oos_script.py` and `tests/test_evaluate_script.py` only. When this entry was
written, `FROZEN.lock` did not exist, `outputs/oos_access_log.json` had no entry, and no Out-of-Sample value had been
computed or seen. "Approved by" lists the approvals given so far; Eliya approves through the review of the pull request
from branch `feat/3.8-oos-followups`.

### S38-1 · `08_run_oos.py` builds the forward returns with the truncation date and the lock (S37-2, S37-8 point 1)

| Field | Content |
| --- | --- |
| Date | 2026-11-06 |
| Question | S37-8 (1) found that 08's `rebuild_tables` calls `build_forward_returns(daily_open, daily_close, end)` with a late `is_end`. That call bypasses the builder's own lock check and labels every week `IS`, which 08 then re-labels. How does 08 call the builder now? |
| Options considered | (a) `build_forward_returns(daily_open, daily_close, is_end, truncate_at=data.end, lock_path=<root>/FROZEN.lock)`, with 08's period re-assignment dropped (chosen); (b) keep the three-argument call and the re-assignment |
| Decision | (a). `rebuild_tables` passes `split.in_sample_end` as `is_end` (the period boundary), `data.end` as `truncate_at` and the project's `FROZEN.lock` as `lock_path`. The builder labels `period` from `realised_on` (contract 7, through `src.backtest.forward_returns`, the rule 08 applied before), and 08 still checks the table with `validate_forward_returns`. The forward returns are now built first, before `build_tables` and `build_labels`, so without `FROZEN.lock` the builder raises `OOSAccessError` before any other table is computed and nothing is written. The values, `realised_on` and `period` are those of the previous code. Open point for Eliya, not changed here (his file, S34-1): `build_labels(daily_open, daily_close, is_end)` has no `truncate_at`, so 08 still calls it with `data.end` as `is_end`, and inside it `build_forward_returns` runs with a late `is_end` and no lock check. In 08 that call now runs only after the guarded call above has passed |
| Rationale | The builder's own check now protects the Out-of-Sample path, as S37-2 intended, and 08 keeps no second copy of the period rule |
| Evidence | S37-8 (1): "08 should move to `build_forward_returns(daily_open, daily_close, is_end, truncate_at=end, lock_path=<FROZEN.lock>)` and drop its period re-assignment."; S37-2 (signature and lock rule); contract 7; Instruction (a): "08_run_oos.py: call build_forward_returns(..., is_end, truncate_at=end, lock_path=FROZEN.lock) as S37-2 provides, so the function's own lock check protects the OOS path. Tests."; tests `test_rebuild_tables_passes_the_truncation_and_the_lock_to_the_builder`, `test_rebuild_tables_is_refused_by_the_builder_without_the_lock`, `test_the_full_range_tables_reach_the_data_end_with_periods_by_realisation` (unchanged, passes) |
| Proposed by | Mattia Cervelli (instruction of 6 Nov 2026) |
| Approved by | Mattia Cervelli, 6 Nov 2026; Eliya Allam: PR review |
| Files affected | `08_run_oos.py`, `tests/test_run_oos_script.py` |
| Amendment | No |

### S38-2 · `07_evaluate.py --period OOS` takes its DSR and PBO matrix from `selection_bias.json` (supersedes the matrix of S34-11)

| Field | Content |
| --- | --- |
| Date | 2026-11-06 |
| Question | S37-7 found that 07's Out-of-Sample report built its In-Sample trial matrix from `outputs/backtests/` only. That gives 16 columns instead of the 28 of `selection_bias.json` (S37-9), so its In-Sample DSR and PBO would differ from the recorded ones. Which matrix does 07 use? |
| Options considered | (a) rebuild the matrix from the columns that `outputs/metrics/selection_bias.json` declares (contract 15: `name`, `kind`, `spec_hash`, `source`, in its order), and check the In-Sample DSR and PBO against the file's values (chosen); (b) import 05's `trial_matrix` (a function of Eliya's file that is not in the contract); (c) copy the file's values without recomputing them |
| Decision | (a). `07_evaluate.py: trial_matrix` reads `selection_bias.json` and stops (`SystemExit`) in these cases: the file is missing; its columns and `excluded` rows do not cover each `spec_hash` of `docs/trial_log.csv` exactly once; its `dsr.n_trials` is not the trial log's row count; a column's `source` is not a `weekly.csv` under `outputs/backtests/` or `outputs/agent_lab/walkforward/`; the `summary.json` next to that source does not hold the column's `spec_hash`; any week is not In-Sample; or the inner join of the columns does not give exactly the file's `matrix.weeks` complete weeks. The column order is the file's, so CSCV breaks ties as 05 does (S37-8: `M1_a0.1` and `M1_a1` are equal columns). The new `in_sample_inference` stops unless the file's `selected` is the run's selected model. It computes the selected model's In-Sample DSR (`src.stats.deflated_sharpe_ratio`, N = trial-log rows) and PBO (`src.stats.pbo_cscv`, `inference.pbo_blocks`), and stops unless each is within 1e-12 of the file's `dsr.value` and `pbo.value`. It reads In-Sample outputs only, so it can be run before the freeze. `inference_row` adds the Out-of-Sample DSR against the same trial Sharpes, as information (S34-11). `oos_inference.csv` gains `matrix_columns_agent` and keeps its other columns. On the real outputs this means the 28 columns and the In-Sample DSR 3.1e-5 and PBO 0.293 of S37-9. They were not recomputed on this machine, which holds neither `selection_bias.json` nor `outputs/agent_lab/`. The synthetic test writes the file with 05's own `selection_bias` and checks the match |
| Rationale | One matrix for the selection-bias numbers in every report. (a) depends only on a file format the contract declares, not on another owner's private code. Recomputing and comparing catches a stale file or a changed column, where (c) would not |
| Evidence | S37-7: "`07_evaluate.py --period OOS` builds its In-Sample matrix from `outputs/backtests/` only, so it would hold 16 columns, not 28, and its In-Sample DSR and PBO would differ from these; it is Mattia's file, so this is an open point for him (read the agent folders or `selection_bias.json`)"; S37-9 (DSR 3.1e-5, N = 56, PBO 0.293 over 28 configurations); S34-11; `docs/interfaces.md` contract 15 (`selection_bias.json`: `matrix` "one entry per column: `name`, `kind`, `rung`, `spec_hash`, `trial_ids`, `aliases`, `source`" and `excluded`); §10 validation hierarchy items 2 and 3; Instruction (b): "07_evaluate.py --period OOS (S34-11): build the DSR/PBO matrix from the same configurations as outputs/metrics/selection_bias.json (including the 12 agent candidates' weekly returns that 05 --agent-returns re-scores), so its In-Sample DSR and PBO match S37-9. Tests."; tests `test_oos_inference_uses_the_matrix_of_selection_bias`, `test_oos_inference_needs_selection_bias`, `test_oos_inference_refuses_a_selection_bias_that_does_not_match` (6 cases), `test_oos_inference_refuses_a_stale_or_changed_column` |
| Proposed by | Mattia Cervelli |
| Approved by | Mattia Cervelli, 6 Nov 2026; Eliya Allam: PR review |
| Files affected | `07_evaluate.py`, `tests/test_evaluate_script.py` |
| Amendment | No: applies §10 and §11 with the matrix of S37-7 |

### S38-3 · The temporary git repositories of `tests/test_run_oos_script.py` are copied without git's lock files

| Field | Content |
| --- | --- |
| Date | 2026-11-06 |
| Question | On macOS CI (PR #19) the fixture that copies the temporary git repository failed with `shutil.Error` on `.git/objects/maintenance.lock`. Git's background auto-maintenance, started by a commit, deleted the file during `copytree`. How is the copy made reliable? |
| Options considered | (a) turn git's automatic housekeeping off in the fixture's repository (`gc.auto 0`, `maintenance.auto false`, set after `git init` and before the first commit) and copy with an ignore of `*.lock` inside `.git/` only (chosen); (b) `shutil.ignore_patterns("*.lock")`, which applies at every depth and would drop the committed `FROZEN.lock` that the frozen and run copies need; (c) `git clone`, which would not copy the git-ignored `data/` and `outputs/` the tests need |
| Decision | (a). `init_repo` runs `git init` and sets both settings in `.git/config`, so every copy inherits them. `copy_repo` replaces every `shutil.copytree` of the file (five places) and skips names ending in `.lock` under `.git/` only. `FROZEN.lock` and any other file outside `.git/` are copied. No test assertion changed |
| Rationale | Turning maintenance off removes the cause. The ignore keeps the copy safe from any lock git still creates. Restricting the ignore to `.git/` keeps the frozen projects intact |
| Evidence | Instruction (c): "tests/test_run_oos_script.py: the fixture that copies its temporary git repository is flaky on macOS (shutil.Error on .git/objects/maintenance.lock, CI log of PR #19): git's background auto-maintenance deletes a lock file during copytree. In the fixture's repo, set gc.auto 0 and maintenance.auto false, and copy with an ignore for *.lock (or use git clone instead of copytree)."; tests `test_copy_repo_skips_git_lock_files_and_keeps_frozen_lock`, `test_project_copies_keep_automatic_git_housekeeping_off` |
| Proposed by | Mattia Cervelli (instruction of 6 Nov 2026) |
| Approved by | Mattia Cervelli, 6 Nov 2026; Eliya Allam: PR review |
| Files affected | `tests/test_run_oos_script.py` |
| Amendment | No: test infrastructure |

## 2026-11-06 · Session 4.0: attribution policy, then Amendment 9

"Instruction" quotes Eliya's instruction of 6 Nov 2026. It came after the commit of the Amendment 9 draft was refused by
the pre-commit hook: the draft names the vendor and model of the round-2 agent lab's LLM, and check (b) of
`tools/git-hooks/pre-commit` refused that name in every file but `docs/ai_tools_used.md` and `uv.lock`. The Amendment 9
draft is paused. This entry and the hook change go in first, as their own pull request from branch
`policy/research-vendor-scope`. No setting, threshold, model, score or result changes here, and no Out-of-Sample value
is computed or seen.

### S40-0 · Authorship and attribution policy; naming the agent lab's model

| Field | Content |
| --- | --- |
| Date | 2026-11-06 |
| Question | Given operating manual hard rule 1, may the repository name the vendor of the agent lab's model? |
| Options considered | (a) Keep check (b) as it is. The round-2 lab could then not record its model id, its prices or its client in the repository. (b) Allow the vendor and model name only in the files where that model is the research object, and keep every authorship rule unchanged (chosen). (c) Drop the vendor check entirely; refused, because it would weaken the authorship guard everywhere. (d) Use a different provider for round 2; not chosen, because the team has API credits for the chosen model. (e) Commit with the hook bypassed; refused (manual §3.8; a policy is changed by a decision, not skipped) |
| Decision | (b). **(a) Authorship is unchanged and applies everywhere.** Commits are authored by team members under their own identity. No file and no commit message holds a co-author trailer, a "generated with" line, a session link or an assistant settings file. No commit message names a vendor or an assistant. **(b) Disclosure.** The AI tools the team used are disclosed in `docs/ai_tools_used.md`. **(c) Research object.** The vendor and model name of the agent lab's LLM may appear only where that model is the research object: `docs/preregistration.md`, `docs/decisions.md`, `docs/ai_tools_used.md`, `config.yaml`, `src/agents/`, `agent_lab/`, `tests/test_agents*.py`, `tests/test_vault_server.py` and `tests/test_planted_signal.py`, plus `pyproject.toml` and `uv.lock` if a dependency is ever needed. **Implementation.** `tools/git-hooks/pre-commit`, check (b): a co-author trailer is refused in every scanned file. The vendor words are refused in added lines unless the file matches `allow_re`, the list of (c) as an anchored pattern (`src/agents/` and `agent_lab/` with anything below them; `tests/test_agents` followed by any name ending in `.py` directly under `tests/`). `docs/ai_tools_used.md` and `uv.lock` stay exempt from the scan, as before. Checks (a) (assistant settings files, refused at any path) and (c) (`data/raw/`) are unchanged. `tools/git-hooks/commit-msg` is unchanged (point (a)). **CI.** The `commit-messages` job of `.github/workflows/ci.yml` already enforces point (a) on every commit message and is unchanged. `tests/test_hooks_policy.py`, which the `test` job runs on all three systems, now holds `ALLOWED_RE`. A test checks that it is character for character the hook's `allow_re`, so the hook and CI apply one list. A new backstop scans every tracked file: no co-author trailer anywhere, and the vendor words only in files matching (c), with the same two exempt files. Tests run both hooks on a temporary repository: the vendor name passes in each allowed path, and fails in other paths (including look-alikes such as `src/agents.py`, `agent_labx/`, `tests/sub/test_agents.py` and `docs/decisions.md.bak`); a co-author trailer fails even in an allowed path; assistant settings files are refused everywhere, also under `src/agents/` and `agent_lab/`; `data/raw/` is still refused; and commit messages with a vendor name, a co-author trailer, a "generated with" line or a session link still fail. Hooks are not versioned, so each member runs `uv run python tools/install_hooks.py` once after this pull request is merged. The operating manuals themselves are not edited |
| Rationale | Rule 1 exists to keep authorship with the team. Naming a model that the research studies is disclosure, as for DeepSeek in round 1: S33-1 records its model id and prices, and `src/agents/llm.py` reads `DEEPSEEK_API_KEY`. That vendor was never on the hook's word list, so the team already read rule 1 as an authorship rule. The scope keeps the name out of every other file, and every authorship check is unchanged |
| Evidence | Operating manual §2: "A later dated amendment or decision overrides earlier text, including this file."; operating manual §3, hard rule 1: "Commits are made by the human running the session, under their own git identity. No commit message, file, comment, docstring, config or workflow may contain co-author trailers, "generated with" lines, session links, or any mention of an AI assistant, tool or vendor. The only exception is `docs/ai_tools_used.md`, which humans fill in by hand."; `tools/git-hooks/pre-commit` on `main` `30ebd5c`, check (b): "an added line contains a forbidden attribution word (docs/ai_tools_used.md and uv.lock are exempt)"; S33-1 (model id, prices and the budget meter of round 1); `src/agents/llm.py`: `API_KEY_ENV = "DEEPSEEK_API_KEY"`; `git grep` of the tracked files on `30ebd5c`: no file holds the vendor words or a co-author trailer, so the new backstop passes on the current tree; Instruction: "… (we have free API credits), so the repository policy is narrowed properly first, through a recorded decision." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam and Mattia Cervelli, through the review of the pull request from branch `policy/research-vendor-scope` |
| Files affected | `tools/git-hooks/pre-commit`, `tests/test_hooks_policy.py`, `docs/decisions.md` |
| Amendment | No: repository policy, not part of the pre-registration. Amendment 9 follows in its own pull request |

### S40-1 · Amendment 9 in config.yaml: the round2: section, the spec_hash trap and three corrections to the draft

| Field | Content |
| --- | --- |
| Date | 2026-11-06 |
| Question | Where do the round-2 settings of Amendment 9 go in `config.yaml` without changing any round-1 identity? Which corrections were made to the instructed amendment text before it was committed (commit `c8999b0`)? |
| Options considered | Placement: (a) add M6, M7, M8 and M9 to `models:`, extend `models.candidate_order` and set a second `bootstrap_prob` in `selection:`; (b) a new top-level section `round2:`, with every existing section left byte-identical (chosen). Gate thresholds: (c) copy `sharpe_uplift` and `mdd_tolerance` into `round2:`; (d) set only `round2.selection.bootstrap_prob` and read the other thresholds from `selection:` (chosen) |
| Decision | (b) and (d). **The trap.** `src.models.walkforward_settings(cfg)` is exactly the sections {seed, data, split, execution, features, models}. It is part of every trial's `spec_hash` (`src.vault.spec_hash`, S23-6) and is saved as each `outputs/walkforward/<name>/used.yaml` and in each `outputs/backtests/<name>/used.yaml` (06 `backtest_used`). Option (a) would change every one of the 56 trial-log hashes and stale all 34 round-1 `used.yaml` files. `08_run_oos.py --freeze` and `05 --select` would then refuse the round-1 outputs, against C4 ("no round-1 spec_hash changes"). `round2:` is in neither identity. **Section content.** `test_weeks` 624; `label` (4-week horizon, cross-sectional demeaning, `label_end` at O(t+5)); `smoothing` (half-lives [2, 4] weeks, k = 0 … 3H); `models` M6 (ridge, λ [0.1, 1, 10]), M7 (M6 + smoothing, λ × H), M8 (LambdaRank, relevance = the within-week rank of y4 on 9 levels, linear gain, 9 positions, depth [2, 3], 200 trees, learning rate 0.03, 1 thread, deterministic, H [2, 4]), M9 (M7 + agent features approved by name); `tie_order` (λ [10, 1, 0.1], depth [2, 3], H [4, 2]) and `tie_precedence` [alpha, max_depth, half_life_weeks]; `candidate_order` [M6, M7, M8, M9], appended after `models.candidate_order`; `selection.bootstrap_prob` 0.90; `agent_lab` (base rung M7, 40 candidates, 1 Coder repair, USD 10 stop, `api_key_env` `DDMI_ANTHROPIC_API_KEY`, planted-signal test and recognition probe repeated). The model id and prices are not in the config: C2 records them in a decision before the run. **Corrections to the instructed text, before the commit.** (1) The instructed diagnosis "M2: Sharpe +0.22 before costs, −0.99 after" mixed two conventions: +0.22 is the gross Sharpe with rf = 0, and −0.99 is the headline net Sharpe with the weekly T-bill (Amendment 6 C1). In the headline convention, M2's figures are +0.12 before costs and −0.99 after, at 1.12 turnover a week, and Amendment 9 states those. (2) The tie rule "the larger λ, the smaller depth, the larger H" did not say which parameter decides when two tied grid points differ in both, for example (λ 10, H 2) against (λ 1, H 4). C1 adds "λ or depth decides first, then H". (3) C2's model sentence names the vendor of the lab's model, and the first commit attempt was refused by pre-commit check (b). The commit was paused, S40-0 scoped the check (pull request #21, merged as `a47b574`), and C2 was then committed with the sentence exactly as instructed. **Key variable.** The round-2 lab reads its API key only from the environment variable `DDMI_ANTHROPIC_API_KEY`, never from `ANTHROPIC_API_KEY`, as instructed. This is a setting of the lab, not of the pre-registration, so it lives in `round2.agent_lab.api_key_env` and here, not in Amendment 9. **Test.** `tests/test_round2_config.py` (9 tests) checks the following. Every trial-log row's `spec_hash` reproduces from its `params_json` under the current config (56 rows). `walkforward_settings(cfg)`, 06's `used_settings(cfg)` and every section other than `round2` hash to the SHA-256 values pinned from `config.yaml` at `30ebd5c` (unchanged on `main` through `a47b574`). `round2` is outside both identities. Its values are those above, except that `api_key_env` is checked only for its `DDMI_` prefix and `_API_KEY` suffix: the test file is outside the files of S40-0 (c), so the exact name is tested with the round-2 lab code under `tests/test_agents*.py`. Adding M6 to `models:` would change every round-1 hash (the trap). Every existing `outputs/<stage>/<name>/used.yaml` passes `check_used`; this test skips where outputs/ is absent, as in CI, and passed locally on all 34 files. Mutation checks before the commit: changing an M1 λ failed four tests, and changing `placebo.books` failed the round-1 digest test |
| Rationale | One source of truth per setting (operating manual §6). The gate thresholds that C3 keeps from round 1 are read from `selection:`, so the two rounds cannot drift apart. The trap test makes C4 mechanical: any later edit of a round-1 section fails CI |
| Evidence | Amendment 9 C1 to C4 (commit `c8999b0`), C4: "Round-2 settings live in a new config section, and no round-1 spec_hash changes."; `src/models.py`: `WALKFORWARD_SECTIONS = ("seed", "data", "split", "execution", "features", "models")`; `src/vault.py: spec_hash` (S23-6); `06_backtest.py: used_settings`, `backtest_used` (S23-10); `outputs/backtests/M2/weekly.csv` and `src.metrics.sharpe_ratio` (6 Nov 2026): gross 0.2227 (rf 0) and 0.1225 (T-bill), net −0.8867 (rf 0) and −0.9865 (T-bill), mean turnover 1.1205; S37-9 (M2 −0.986); S40-0; Eliya's answers of 6 Nov 2026: "T-bill headline only"; tie rule: "Add to amendment"; "The lab reads the key from the environment variable DDMI_ANTHROPIC_API_KEY, never ANTHROPIC_API_KEY. Record all three corrections in S40-1."; "The key-variable rule goes in config and S40-1 only." |
| Proposed by | Eliya Allam |
| Approved by | Eliya Allam (instructions of 6 Nov 2026); Mattia Cervelli, through the review of the pull request from branch `docs/amendment-9` |
| Files affected | `config.yaml` (new `round2:` section only), `tests/test_round2_config.py`, `docs/decisions.md` |
| Amendment | Implements Amendment 9 (commit `c8999b0`). No further amendment |

## Reviewer sign-offs

No result counts until its reviewer signs it here (protocol section 14).

| Date | Deliverable | Owner | Reviewer | Result |
| --- | --- | --- | --- | --- |
| 2026-11-03 | Gate 2 core (S22-10): engine hand cases and ledger reconciliation (PR #5); features, labels, folds and vault (PRs #6, #7, #8); M0 In-Sample walk-forward reproduced with byte-identical scores (`scores_sha256` `7078b900…96a8`, PR #9); M0 baseline net Sharpe −0.771 (T-bill rf), max drawdown −48.0% | Eliya Allam, Mattia Cervelli | Mattia Cervelli (M0 reproduction); Eliya Allam and Mattia Cervelli (sign-off) | Passed on 3 Nov 2026; hard stop not triggered (S31-11) |

## Teaching-team check (protocol section 15)

To ask at the next in-class project session: (1) the continuously weighted IVV hedge carrying a discrete signal; (2) returns
reported without cash interest, with Sharpe under both conventions.

| Date | Question | Answer | Recorded by |
| --- | --- | --- | --- |