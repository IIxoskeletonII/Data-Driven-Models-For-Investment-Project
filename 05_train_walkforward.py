"""Score the AI ladder with the expanding In-Sample walk-forward of protocol sections 07 and 10: initial training
2003-2007, 12 yearly test folds 2008-2019 (48 quarterly refits), purged labels and a one-week embargo.

Phase 2.3a (Eliya): only M0 (rank on MOM26_1, the hurdle); M1-M3, ENS and M0* in Phase 3.1. Every model and label
access goes through src/vault.py, which refuses any date after the In-Sample end (2019-12-27); every fit asserts the
purge. No performance metric is computed here (06_backtest.py, Phase 2.3b). Decisions S23-2, S23-3, S23-5.

Inputs:  data/processed/features.csv, market_states.csv, labels.csv, momentum_variants.csv (03_build_features.py),
         data/processed/features_config.yaml (check_used)
Outputs: outputs/walkforward/<rung>/scores.csv (contract 8: weekly scores of the test weeks, known after Friday close t),
         used.yaml (config sections seed, data, split, features, models; check_used), summary.json (counts, dates, column sums, min, max, fixed spot values, SHA-256);
         one row in docs/trial_log.csv for a new spec (S23-2). Two runs give identical files.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT, check_used, load_config, save_used
from src.contracts import universe, validate_scores
from src.data import DATE_FORMAT, sha256, write_csv
from src.features import features_settings
from src.labels import label_end_by_week, walk_forward_folds
from src.models import walkforward_settings
from src.vault import Vault, spec_hash

RUNGS = ("M0",)  # M1-M3, ENS and M0*: Phase 3.1
AUTHOR = "Eliya Allam"
# Five (date_close, ticker) spot values reported in summary.json, fixed before the first run (S23-3)
SPOTS = (("2008-01-04", "XLB"), ("2008-10-10", "XLF"), ("2012-06-01", "XLK"), ("2016-02-12", "XLE"),
         ("2019-12-13", "XLY"))
FEATURES_CONFIG_NAME = "features_config.yaml"


def model_spec(rung: str, cfg: dict) -> dict:
    """The spec of a rung's walk-forward trial (S23-3); its SHA-256 is the trial log's spec_hash."""
    if rung != "M0":
        raise NotImplementedError("Phase 3.1, Eliya")
    return {"rung": "M0", "feature": cfg["models"]["M0"]["feature"], "author": AUTHOR, "kind": "human",
            "notes": "M0 In-Sample walk-forward (Phase 2.3a)"}


def _closes(index: pd.MultiIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def _check_test_weeks(scores: pd.DataFrame, folds: list, is_end: pd.Timestamp) -> None:
    """Raise ValueError unless the scored weeks are exactly the test weeks of the folds, all In-Sample."""
    closes = _closes(scores.index)
    if closes.max() > is_end:
        raise ValueError(f"scores dated after the In-Sample end {is_end.strftime(DATE_FORMAT)}")
    if closes.min() != folds[0].test_start or closes.max() != folds[-1].test_end:
        raise ValueError(f"scored weeks {closes.min().date()}..{closes.max().date()} differ from the test weeks "
                         f"{folds[0].test_start.date()}..{folds[-1].test_end.date()}")


def _spot_values(scores: pd.DataFrame, spots: Sequence[tuple[str, str]]) -> list[dict]:
    """The score of each fixed (date_close, ticker); ValueError if that week or ticker was not scored."""
    by_close = scores.set_axis(_closes(scores.index))
    values = []
    for day, ticker in spots:
        close = pd.Timestamp(day)
        if close not in by_close.index or ticker not in by_close.columns:
            raise ValueError(f"spot value {day} {ticker} is not a scored week and sector")
        values.append({"date_close": close.strftime(DATE_FORMAT), "ticker": ticker,
                       "score": float(by_close.at[close, ticker])})
    return values


def summarise(scores: pd.DataFrame, *, rung: str, digest: str, refits: int, scores_sha256: str,
              spots: Sequence[tuple[str, str]] = SPOTS) -> dict:
    """summary.json of a walk-forward run (S23-3): counts, first and last week, per-sector sums, min, max, the fixed spot
    values and the SHA-256 of scores.csv. No time or machine-dependent field, so equal scores give equal bytes.
    """
    values = scores.to_numpy(dtype=np.float64)
    closes = _closes(scores.index)
    return {
        "rung": rung,
        "spec_hash": digest,
        "refits": int(refits),
        "rows": len(scores),
        "weeks": int(closes.nunique()),
        "values": int(np.isfinite(values).sum()),
        "nan_count": int(np.isnan(values).sum()),
        "first_week": closes.min().strftime(DATE_FORMAT),
        "last_week": closes.max().strftime(DATE_FORMAT),
        "column_sums": {str(column): float(scores[column].sum()) for column in scores.columns},
        "min": float(np.nanmin(values)),
        "max": float(np.nanmax(values)),
        "spots": _spot_values(scores, spots),
        "scores_sha256": scores_sha256,
    }


def _write_json(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2, sort_keys=True)
        f.write("\n")


def run(rung: str, cfg: dict, *, data_dir: Path, out_dir: Path, trial_path: Path, log_path: Path, lock_path: Path,
        spots: Sequence[tuple[str, str]] = SPOTS) -> dict:
    """Walk-forward scores of one rung through the vault, written with used.yaml and summary.json; returns the summary.

    data_dir: data/processed (the tables of 03_build_features.py and features_config.yaml, checked first); out_dir:
    outputs/walkforward/<rung>; trial_path, log_path, lock_path: the trial log, the vault access log and FROZEN.lock.
    """
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    spec = model_spec(rung, cfg)
    check_used(features_settings(cfg), data_dir / FEATURES_CONFIG_NAME, "03_build_features.py")
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    vault = Vault(is_end, lock_path=lock_path, log_path=log_path, data_dir=data_dir, cfg=cfg)

    scores = vault.run_walkforward(spec, trial_path=trial_path)
    validate_scores(scores)
    weeks = vault.market_states(is_end).index
    folds = walk_forward_folds(weeks, label_end_by_week(vault.labels(is_end), weeks), cfg)
    _check_test_weeks(scores, folds, is_end)

    scores = scores[list(universe(cfg).sectors)]
    write_csv(scores, out_dir / "scores.csv")
    save_used(walkforward_settings(cfg), out_dir / "used.yaml")
    summary = summarise(scores, rung=rung, digest=spec_hash(spec), refits=len(folds),
                        scores_sha256=sha256(out_dir / "scores.csv"), spots=spots)
    _write_json(summary, out_dir / "summary.json")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, choices=RUNGS, help="rung to score (only M0 until Phase 3.1)")
    args = parser.parse_args(argv)

    cfg = load_config()
    out_dir = ROOT / "outputs" / "walkforward" / args.model
    summary = run(args.model, cfg, data_dir=ROOT / cfg["data"]["data_dir"] / "processed", out_dir=out_dir,
                  trial_path=ROOT / "docs" / "trial_log.csv", log_path=ROOT / "outputs" / "vault_access_log.jsonl",
                  lock_path=ROOT / "FROZEN.lock")
    print(f"{args.model}: {summary['refits']} refits, {summary['weeks']} test weeks, {summary['first_week']} to "
          f"{summary['last_week']}, {summary['nan_count']} missing scores")
    print(f"Saved {out_dir.relative_to(ROOT).as_posix()}/scores.csv, used.yaml, summary.json")


if __name__ == "__main__":
    main()
