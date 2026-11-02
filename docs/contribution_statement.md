# Contribution statement

Drafted from the git log and `docs/decisions.md`, and agreed by all five members before submission (protocol section 14).
Every deliverable is reviewed by someone who did not build it.

## Owners and reviewers (protocol section 14)

| Workstream | Visible deliverables (in git and `decisions.md`) | Owner | Reviewer |
| --- | --- | --- | --- |
| A · Data and provenance | Smoke-test run, archived snapshot with checksums, QA report, Stooq reconciliation, composition-break register, licensing table | Simone | Giuseppe |
| B · Engine verification | Hand-computed test cases (long, short, hedge, costs, drift), ledger reconciliation sign-off, metrics checked against the skeleton's definitions | Mattia | Eliya |
| C · Models and selection | Model cards for M0–M3, ENS and M0\*; gate scorecard; application of the selection rule; parameter-neighbourhood plots | Chiara | Mattia |
| D · Robustness and primer | Regime cuts, placebo portfolios, cost and sensitivity grids, bonus tests, `docs/primer.md` | Giuseppe | Simone |
| E · Integration, agent lab, infrastructure | Pipeline code, vault and agent lab, CI on 3 OS, repo, packaging of `group_7.zip` | Eliya | Mattia |

## Code ownership (decided 2 Nov 2026, `docs/decisions.md` S2-7)

The workstream deliverables above are unchanged. The code is split between two authors, who review each other's pull
requests; each author also owns the tests of their files.

| Author | Files | Reviewer |
| --- | --- | --- |
| Eliya | `src/features.py`, `src/labels.py`, `src/vault.py`, `src/models.py`, `src/stats.py`, `src/agents/`, `src/contracts.py`, `03_build_features.py`, `04_agent_lab.py`, `05_train_walkforward.py`, `08_run_oos.py`, `run_all.py` | Mattia |
| Mattia | `src/sizing.py`, `src/backtest.py`, `src/ledger.py`, `src/metrics.py`, `src/plots.py`, `06_backtest.py`, `07_evaluate.py`, `make_submission.py` | Eliya |
| Shared (small dedicated pull requests) | `config.yaml`, `pyproject.toml`, `uv.lock`, `README.md`, `docs/decisions.md` (append-only), `.github/` | both |

## Statement

To be written from the git log and `docs/decisions.md`, and agreed by all five before submission.

| Member | Role | Contributions | Agreed (date) |
| --- | --- | --- | --- |
| Eliya |  |  |  |
| Simone |  |  |  |
| Chiara |  |  |  |
| Mattia |  |  |  |
| Giuseppe |  |  |  |
