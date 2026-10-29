# Regime-aware sector momentum with a beta hedge

[![CI](https://github.com/IIxoskeletonII/Data-Driven-Models-For-Investment-Project/actions/workflows/ci.yml/badge.svg)](https://github.com/IIxoskeletonII/Data-Driven-Models-For-Investment-Project/actions/workflows/ci.yml)

Group 7 project for *Data-Driven Models for Investment* (LUISS, 2026–27).

Each Friday after the close, the system ranks the nine original Select Sector SPDR ETFs and gives each one a discrete signal:
+1 for the two highest scores, −1 for the two lowest, 0 for the rest. The signals are executed at the next session's open.
The long and short legs form a dollar-neutral core, an IVV leg hedges the core's estimated market beta, and the whole book is
scaled to 100% gross exposure with no leverage. The score comes from an AI ladder (ridge, regime interactions, gradient
boosting, an ensemble and agent-proposed features). Each rung is tested against a matched momentum rule with a single
pre-registered selection gate, using walk-forward validation inside the In-Sample period and one Out-of-Sample run.
The hypotheses, the split, the benchmarks, the gate and the tests are pre-registered in
[docs/preregistration.md](docs/preregistration.md) before any strategy result.

## Quick start

Install [uv](https://docs.astral.sh/uv/), then from the project folder:

```bash
uv sync                                    # Python 3.12 and every dependency, pinned by uv.lock
uv run python 00_smoke_test_data.py        # check that every data series is available (saves nothing)
uv run python 01_download_data.py          # download once, archive with checksums, build the weekly panel
uv run python 02_validate_data.py          # QA gates -> docs/qa_report.md and data/qa/
uv run python 03_build_features.py         # features and market states            (Gate 2)
uv run python 04_agent_lab.py              # research lab, replayed from data/cache/ (Gate 2)
uv run python 05_train_walkforward.py      # AI ladder, walk-forward In-Sample      (Gate 2)
uv run python 06_backtest.py               # sizing, hedge, costs                   (Gate 2)
uv run python 07_evaluate.py               # metrics, selection gate, plots         (Gate 3)
uv run python 08_run_oos.py                # single Out-of-Sample run               (Gate 4)
uv run pytest                              # tests on a synthetic fixture
```

Scripts marked with a gate are implemented in that gate of the calendar and stop with `NotImplementedError` until then.
All settings are in [config.yaml](config.yaml); each script refuses outputs built with a different configuration.

Contributors install the repository's git hooks once after cloning: `uv run python tools/install_hooks.py`.

## Reproduction

- **LUISS submission zip.** It contains the raw data in `data/raw/`, so every step reproduces offline:
  `01_download_data.py` finds the archived files, verifies their SHA-256 and does not download anything.
- **Public repository.** Raw vendor data (Yahoo, Cboe, FRED/Moody's, Stooq) is licensed and is not redistributed here.
  `01_download_data.py` fetches it again and compares it with `data/checksums.json`; any vendor revision is reported, not hidden.
  See [docs/licensing.md](docs/licensing.md).
- **CI.** Lint and tests run on Windows, macOS and Linux with a synthetic fixture only: no network, no licensed data.

## Repository map

| Path | Content |
| --- | --- |
| `config.yaml` | Every setting: universe, dates, split, grids, gate, costs, QA thresholds, seed |
| `00_…08_*.py`, `run_all.py`, `make_submission.py` | Pipeline stages, in order |
| `src/` | Shared code: config, data, validation, features, labels, models, sizing, backtest, ledger, metrics, stats, plots, vault, agents |
| `tests/` | Unit tests on a deterministic synthetic fixture |
| `data/raw/` | Raw vendor data: local and in the LUISS zip only |
| `data/processed/` | Daily and weekly tables derived from the raw data: local and in the LUISS zip only |
| `data/qa/` | QA tables (returns and counts, no price levels) |
| `data/checksums.json` | SHA-256 and metadata of every raw and processed file |
| `outputs/` | Models, signals, backtests, metrics and plots (later gates) |
| `docs/` | Pre-registration, decisions, QA report, methods, data dictionary, licensing, composition breaks, trial log, primer, contributions |
| `tools/` | Repository git hooks and their installer |

## Team

Group 7: Eliya Allam, Simone, Chiara, Mattia, Giuseppe. Owners and reviewers of each workstream are listed in
[docs/contribution_statement.md](docs/contribution_statement.md).
