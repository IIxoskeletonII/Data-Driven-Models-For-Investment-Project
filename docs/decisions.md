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

## Reviewer sign-offs

No result counts until its reviewer signs it here (protocol section 14).

| Date | Deliverable | Owner | Reviewer | Result |
| --- | --- | --- | --- | --- |

## Teaching-team check (protocol section 15)

To ask at the next in-class project session: (1) the continuously weighted IVV hedge carrying a discrete signal; (2) returns
reported without cash interest, with Sharpe under both conventions.

| Date | Question | Answer | Recorded by |
| --- | --- | --- | --- |
