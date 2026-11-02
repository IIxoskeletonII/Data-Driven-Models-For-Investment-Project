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

## Reviewer sign-offs

No result counts until its reviewer signs it here (protocol section 14).

| Date | Deliverable | Owner | Reviewer | Result |
| --- | --- | --- | --- | --- |

## Teaching-team check (protocol section 15)

To ask at the next in-class project session: (1) the continuously weighted IVV hedge carrying a discrete signal; (2) returns
reported without cash interest, with Sharpe under both conventions.

| Date | Question | Answer | Recorded by |
| --- | --- | --- | --- |
