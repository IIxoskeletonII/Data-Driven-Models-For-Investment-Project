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

## Reviewer sign-offs

No result counts until its reviewer signs it here (protocol section 14).

| Date | Deliverable | Owner | Reviewer | Result |
| --- | --- | --- | --- | --- |

## Teaching-team check (protocol section 15)

To ask at the next in-class project session: (1) the continuously weighted IVV hedge carrying a discrete signal; (2) returns
reported without cash interest, with Sharpe under both conventions.

| Date | Question | Answer | Recorded by |
| --- | --- | --- | --- |
