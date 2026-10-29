# Licensing: what goes where

> **Draft — owner: Simone, to review and finalise.** Facts and the protocol's table are filled in; the owner verifies
> the series notes and the pre-publication checklist, then commits the final version from her own account.

Raw vendor data is never committed to the public repository. It stays local in `data/raw/` (git-ignored) and ships only
in the LUISS submission zip, as the instructions require. Checksums and derived outputs are public.

## Table (protocol section 04)

| Data | Owner and terms | Public GitHub | LUISS zip |
| --- | --- | --- | --- |
| Yahoo prices via yfinance | Subject to Yahoo's terms; yfinance describes it as for personal use | Fetch script + checksums only | Raw files included |
| VIX | Cboe | Fetch script + checksums only | Included |
| FRED DGS3MO, DGS10 | Federal Reserve data via FRED | Fetch script; verify series notes before publishing | Included |
| FRED BAA10Y | Moody's, copyright noted on the FRED series | Fetch script only | Included |
| Bloomberg pulls | Bloomberg licence | Never | Included, as the instructions require |
| News raw text | Corpus licence | Never | Only if the licence allows; else derived features + fetch script |
| Derived outputs (features, signals, returns, metrics, plots, agent logs) | Ours | Yes | Yes |

Stooq daily prices, used as the second price source for the QA cross-check, are treated like Yahoo prices: fetch script
and checksums only in the public repository, raw files in the zip.

## How the repository enforces it

- `.gitignore` excludes `data/raw/` and `data/processed/` (processed files are derived from licensed prices).
- The `pre-commit` hook in `tools/git-hooks/` rejects any staged file under `data/raw/`.
- `tests/test_hooks_policy.py` fails in CI if any file under `data/raw/` is tracked.
- `data/checksums.json` records the SHA-256, source, URL or call, fetch time, row count and date range of every raw and
  processed file, without the data itself.
- `data/qa/` holds QA tables of returns and counts only, never price levels.

## Pre-publication checklist (to complete)

- [ ] FRED series notes of DGS3MO and DGS10 checked
- [ ] FRED BAA10Y copyright notice checked: no values in the public repository
- [ ] `git ls-files data/` lists no vendor price, index or rate values
- [ ] `outputs/` reviewed before results are published
