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
