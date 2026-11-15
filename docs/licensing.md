# Licensing: what goes where

Raw vendor data is never committed to the public repository. It stays local in `data/raw/` (git-ignored) and ships only
in the LUISS submission zip, as the instructions require. Checksums and derived outputs are public.

## Table (protocol section 04)

| Data | Owner and terms | Public GitHub | LUISS zip |
| --- | --- | --- | --- |
| Yahoo prices via yfinance | Subject to Yahoo's terms; yfinance describes it as for personal use | Fetch script + checksums only | Raw files included |
| VIX | Cboe | Fetch script + checksums only | Included |
| FRED DGS3MO, DGS10 | Board of Governors of the Federal Reserve System (H.15) via FRED; tagged “Public Domain: Citation Requested” | Fetch script and checksums only (project policy) | Included, with citation |
| FRED BAA10Y | Spread calculated by the Federal Reserve Bank of St. Louis from Moody's Baa yields; the FRED notes carry Moody's copyright notice, which requires Moody's prior written consent to copy or redistribute | Fetch script only; never any values | Included in the private LUISS submission only, because the course instructions require the raw data for offline reproduction; it is not published or shared beyond the teaching team (see note) |
| Bloomberg pulls | Bloomberg licence | Not used in this project | Not used |
| News raw text | Corpus licence | Not used (M4, the news model, was dropped) | Not used |
| Derived outputs (features, signals, returns, metrics, plots, agent logs) | Ours | Summary tables, metrics, agent logs and the access log only; no file holding a full daily or weekly price or return series per ticker | Yes |

investing.com daily prices, used as the second price source for the QA cross-check (`data/raw/second_source/`), are
treated like Yahoo prices: never in the public repository, raw files in the zip only.

## How the repository enforces it

- `.gitignore` excludes `data/raw/` and `data/processed/` (processed files are derived from licensed prices).
- The `pre-commit` hook in `tools/git-hooks/` rejects any staged file under `data/raw/`.
- `tests/test_hooks_policy.py` fails in CI if any file under `data/raw/` is tracked.
- `data/checksums.json` records the SHA-256, source, URL or call, fetch time, row count and date range of every raw and
  processed file, without the data itself.
- `data/qa/` holds QA tables of returns and counts only, never price levels.

## Note on BAA10Y in the submission zip

Moody's notice on the FRED series requires prior written consent to copy or redistribute Moody's information, and we do
not hold such consent. The course instructions require the raw data inside the submitted project so that every result
reproduces offline, and the BAA10Y spread is an input of the pre-registered market state CREDIT. We therefore include it
only in the private LUISS submission zip, which goes to the teaching team through my.luiss for grading and is not
published, and never in the public repository. Anyone reproducing the project from the public repository fetches the
series from FRED themselves (`01_download_data.py`). This is our reading of the terms, not legal advice. If the teaching
team prefers, the series can be removed from the zip; an offline rerun would then need it fetched from FRED first.

