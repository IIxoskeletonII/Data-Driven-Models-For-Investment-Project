# Regime-aware sector momentum with a beta hedge

[![CI](https://github.com/IIxoskeletonII/Data-Driven-Models-For-Investment-Project/actions/workflows/ci.yml/badge.svg)](https://github.com/IIxoskeletonII/Data-Driven-Models-For-Investment-Project/actions/workflows/ci.yml)

Group 7 project for *Data-Driven Models for Investment* (LUISS, 2026–27).

Each Friday after the close, the system ranks the nine original Select Sector SPDR ETFs and gives each one a discrete signal:
+1 for the two highest scores, −1 for the two lowest, 0 for the rest. The signals are executed at the next session's open.
The long and short legs form a dollar-neutral core, an IVV leg hedges the core's estimated market beta, and the whole book is
scaled to 100% gross exposure with no leverage. The score comes from an AI ladder (ridge, regime interactions, gradient
boosting, an ensemble, agent-proposed features and, in a second pre-registered round, cost-aware models). Each rung is tested against a matched momentum rule with a single
pre-registered selection gate, using walk-forward validation inside the In-Sample period and one Out-of-Sample run.
The hypotheses, the split, the benchmarks, the gate and the tests are pre-registered in
[docs/preregistration.md](docs/preregistration.md) before any strategy result.

## Results

The pre-registered process ran to the end: In-Sample walk-forward selection (2003–2019, 624 test weeks), a signed freeze,
and one Out-of-Sample run (30 Dec 2019 to 16 Oct 2026, 355 weeks). All figures are net of 10 bps per trade and 2% a year
short borrow, with the Sharpe ratio measured against the T-bill.

- **Selection.** No candidate of either round passed the gate (Sharpe ≥ M0 + 0.15, drawdown no more than 2 points worse,
  bootstrap P(uplift > 0) ≥ 0.80 in round 1 and ≥ 0.90 in round 2), so the pre-registered fallback **M0\*** is traded
  ([decisions S37-9, S44-3](docs/decisions.md)). The agent lab produced no approved feature, so M5 and M9 are absent.
- **Out-of-Sample.** M0\* returned −3.9% a year (net Sharpe −0.77, maximum drawdown −42.5%); SPY returned +15.4% a year
  (Sharpe 0.66). No model was positive net of costs ([decision S45-2](docs/decisions.md)).

| | In-Sample net Sharpe | Out-of-Sample net Sharpe | Out-of-Sample gross return | Costs + borrow | Turnover / week |
| --- | ---: | ---: | ---: | ---: | ---: |
| M0\* (traded) | −0.63 | −0.77 | −0.55% a year | −3.0% a year | 0.39 |
| M7 (closest round-2 candidate) | −0.65 | −0.78 | −0.10% a year | −2.8% a year | 0.34 |
| M1, M2, M3, ENS (round 1) | −0.99 to −1.42 | −1.17 to −1.53 | −1.1% to +1.0% a year | −6.8% to −7.6% a year | 1.12 to 1.26 |

**How to read it.** Before costs every model is close to zero in both periods; trading costs and borrow make every book
negative, and the ranking of the models follows their turnover. Round 2 (Amendment 9) was a disclosed, pre-registered
response to that diagnosis: it cut turnover by about 73% and narrowed the loss, but left no positive edge. The traded
model's Out-of-Sample Sharpe (−0.77) is close to its In-Sample estimate (−0.63), and its cost structure is nearly
identical in both periods: the In-Sample evaluation described the strategy correctly, with no overfitting decay. The book
was market-neutral as designed (beta to SPY −0.04, correlation −0.08) but not profitable, so no bonus is claimed. The
deflated Sharpe ratio over all 72 trials is 2e-5 In-Sample and 0.005 Out-of-Sample.

## Quick start

Install [uv](https://docs.astral.sh/uv/), then from the project folder:

macOS: run `brew install libomp` once (LightGBM needs the OpenMP runtime).

```bash
uv sync                                    # Python 3.12 and every dependency, pinned by uv.lock
uv run python run_all.py                   # the whole In-Sample pipeline, from the raw snapshot, in one command
uv run pytest                              # tests on a synthetic fixture
```

`run_all.py` needs the raw data in `data/raw/` (it is in the submission zip; team members see [Contributing](#contributing))
and never downloads anything. It runs these commands in order, each as its own process, and they can also be run one by
one:

```bash
uv run python 01_download_data.py          # verify data/raw/ against its checksums, rebuild data/processed/ (offline)
uv run python 03_build_features.py         # features, market states, labels, forward returns (In-Sample)
uv run python 05_train_walkforward.py --model M0   # walk-forward of each rung (M0 to M3, ENS, M0_star, M6 to M8) ...
uv run python 05_train_walkforward.py --fixed M1_a1  # ... and of each fixed grid value (the list is read from 05)
uv run python 06_backtest.py --all         # In-Sample backtest of every walk-forward
uv run python 06_backtest.py --shift-check M0 M1 M2 M3 ENS M0_star M6 M7 M8   # one-week-shift leakage check
uv run python 06_backtest.py --placebo     # placebo books
uv run python 05_train_walkforward.py --agent-returns   # agent candidates re-scored through the sealed vault
uv run python 05_train_walkforward.py --select          # selection gate, trial metrics, DSR and PBO
uv run python 07_evaluate.py               # In-Sample metrics, benchmarks and plots
uv run python 06_backtest.py --ledger-years  # ledger reconciliation of the engine (last)
```

It stops at the first failing step and names it, and it ends with a table of every step and its time. Two runs give the
same files (the access logs aside). In a git checkout it refuses uncommitted changes and fails if a step changes a
tracked file; outside one (the zip) it says that this check is skipped. Once `FROZEN.lock` exists it refuses unless
`--after-freeze` is given; `--agent-returns` and `--select` are then skipped, because their outputs are frozen.

`run_all.py` never runs the other scripts. `00_smoke_test_data.py` checks that every series can be downloaded;
`02_validate_data.py` runs the data QA gates (`docs/qa_report.md`); `04_agent_lab.py` is the agent research lab, whose
results replay from the committed caches under `agent_lab/`; `08_run_oos.py` is the single Out-of-Sample run (Gate 4),
run by hand once, then `07_evaluate.py --period OOS`.

All settings are in [config.yaml](config.yaml); each script refuses outputs built with a different configuration.

## Contributing

Team members set up a clone once:

```bash
git clone https://github.com/IIxoskeletonII/Data-Driven-Models-For-Investment-Project.git
cd Data-Driven-Models-For-Investment-Project
uv sync                                    # locked environment
uv run python tools/install_hooks.py       # commit hooks + local exclusions in .git/info/exclude (safe to re-run)
```

Then place the raw data snapshot (shared privately, never committed): unzip `ddmi_raw_snapshot_2026-10-16.zip` at the
repository root, so that `data/raw/manifest.json` exists. Check the zip first; its SHA-256 must be
`424a7ed3d9f449b6aa2dbee4cddd7ca702b536aea0d6e3fc17003b1ad398e569`
(`certutil -hashfile <zip> SHA256` on Windows, `shasum -a 256 <zip>` on macOS). Then run
`uv run python 01_download_data.py`: it verifies every raw file against `data/raw/manifest.json` and
`data/checksums.json`, downloads nothing, and rebuilds `data/processed/`.

Work on one branch per subphase (`feat/<subphase>-<short-name>`) and open a pull request; `main` changes only through
reviewed pull requests with green CI. Run `uv run ruff check .` and `uv run pytest -q` before every commit.

## Reproduction

- **LUISS submission zip.** It contains the raw data in `data/raw/`, so every step reproduces offline:
  `01_download_data.py` finds the archived files, verifies their SHA-256 and does not download anything.
- **Public repository.** Raw vendor data (Yahoo, Cboe, FRED/Moody's, investing.com) is licensed and is not redistributed here.
  `01_download_data.py` fetches it again and compares it with `data/checksums.json`; any vendor revision is reported, not hidden.
  See [docs/licensing.md](docs/licensing.md).
- **CI.** Lint and tests run on Windows, macOS and Linux with a synthetic fixture only: no network, no licensed data.

## Building the submission

Build the zip after Gate 4, once the Out-of-Sample run of record and `07_evaluate.py --period OOS` are done. Run it from a
committed checkout, with the slides exported as a PDF:

```bash
uv run python make_submission.py --presentation PATH/TO/slides.pdf   # writes group_7.zip and prints its manifest
```

- **What goes in.** `group_7.zip` holds two things. The first is `project/`: every tracked file plus `data/raw/`,
  `data/processed/` and `outputs/`, so every result reproduces offline. The second is the slides, stored at the zip root
  as `presentation.pdf` whatever the file is called. Local tool settings files and synthetic test outputs are left out.
  `--out PATH` changes where the zip is written, and `--manifest PATH` also saves the manifest. The manifest lists the
  SHA-256 and size of every entry, then the zip's size and SHA-256.
- **When it refuses.** The build stops and writes nothing if a tracked file has uncommitted changes, if a file is a
  `.env` file or holds a key-like string, if the presentation is not a PDF, or if any output was built with another
  `config.yaml`.
- **Why the data ships only in the zip.** The course instructions require the raw data, the processed data and the
  results inside the submitted project, reproducible without downloading anything. The raw vendor data is licensed, so
  it is never committed to this public repository: `data/raw/` and `data/processed/` are git-ignored, and the commit
  hook and CI enforce this. The zip goes only to the teaching team, through my.luiss. See
  [docs/licensing.md](docs/licensing.md) and decisions S35-1 to S35-5 in [docs/decisions.md](docs/decisions.md).

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
| `outputs/` | Walk-forward scores, backtests, metrics, plots and the Out-of-Sample run: local and in the LUISS zip (only the access log is committed) |
| `docs/` | Pre-registration, decisions, QA report, methods, data dictionary, licensing, composition breaks, trial log, primer, contributions |
| `tools/` | Repository git hooks and their installer |

## Team

Group 7: Eliya Allam, Chiara Baldoni, Simone Cavallaro, Giuseppe Catrambone, Mattia Cervelli. Owners and reviewers of each workstream are listed in
[docs/contribution_statement.md](docs/contribution_statement.md).
