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

## Reviewer sign-offs

No result counts until its reviewer signs it here (protocol section 14).

| Date | Deliverable | Owner | Reviewer | Result |
| --- | --- | --- | --- | --- |

## Teaching-team check (protocol section 15)

To ask at the next in-class project session: (1) the continuously weighted IVV hedge carrying a discrete signal; (2) returns
reported without cash interest, with Sharpe under both conventions.

| Date | Question | Answer | Recorded by |
| --- | --- | --- | --- |
