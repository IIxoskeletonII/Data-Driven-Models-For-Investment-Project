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

## Reviewer sign-offs

No result counts until its reviewer signs it here (protocol section 14).

| Date | Deliverable | Owner | Reviewer | Result |
| --- | --- | --- | --- | --- |

## Teaching-team check (protocol section 15)

To ask at the next in-class project session: (1) the continuously weighted IVV hedge carrying a discrete signal; (2) returns
reported without cash interest, with Sharpe under both conventions.

| Date | Question | Answer | Recorded by |
| --- | --- | --- | --- |
