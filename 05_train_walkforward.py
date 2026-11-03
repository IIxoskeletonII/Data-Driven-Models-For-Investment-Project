"""Score the AI ladder with the expanding In-Sample walk-forward of protocol sections 07 and 10: initial training
2003-2007, 12 yearly test folds 2008-2019 (48 quarterly refits), purged labels and a one-week embargo.

Phase 2.3a (Eliya): M0 (rank on MOM26_1, the hurdle). Phase 3.1: M1, M2, M3, ENS and M0* with the choice within the
fixed grids of Amendment 5 C1 (--model), and every grid value as a fixed configuration (--fixed, Amendment 5 C2). Every
model, label and return access goes through src/vault.py, which refuses any date after the In-Sample end (2019-12-27);
every fit, inner and outer, asserts the purge. No performance metric of the test weeks is computed here (06_backtest.py).
Decisions S23-2, S23-3, S23-5, S23-6, S31-2 to S31-7, S31-10.

Inputs:  data/processed/features.csv, market_states.csv, labels.csv, momentum_variants.csv, sizing_betas.csv,
         forward_returns.csv (03_build_features.py), data/processed/features_config.yaml (check_used)
Outputs: outputs/walkforward/<name>/scores.csv (contract 8: weekly scores of the test weeks, known after Friday close t),
         used.yaml (config sections seed, data, split, execution, features, models; check_used), summary.json (counts,
         dates, column sums, min, max, fixed spot values, SHA-256), and for M1, M2, M3, M0_star selection.csv (per
         refit: inner Sharpe of each grid value, the value chosen); one row in docs/trial_log.csv for a new spec (S23-2).
         Two runs give identical files.
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
from src.models import ENS_MEMBERS, PARAM_KEYS, grid, tuning_spec, walkforward_settings
from src.vault import Vault, spec_hash

RUNGS = ("M0", "M1", "M2", "M3", "ENS", "M0_star")  # --model: M0, and the tuned rungs (Amendment 5 C1)
FIXED_PREFIX = {"M1": "a", "M2": "a", "M3": "d", "M0_star": "L"}  # --fixed names: M1_a0.1, M3_d2, M0_L13 (S31-10)
AUTHOR = "Eliya Allam"
# Five (date_close, ticker) spot values reported in summary.json, fixed before the first run (S23-3)
SPOTS = (("2008-01-04", "XLB"), ("2008-10-10", "XLF"), ("2012-06-01", "XLK"), ("2016-02-12", "XLE"),
         ("2019-12-13", "XLY"))
FEATURES_CONFIG_NAME = "features_config.yaml"


def model_spec(rung: str, cfg: dict) -> dict:
    """The spec of a rung's walk-forward trial (S23-3, S31-2); with the config it gives the trial log's spec_hash (S23-6).

    M0: the Phase 2.3a spec, unchanged. M1, M2, M3, M0_star: the Amendment 5 C1 choice ("tuning" =
    src.models.tuning_spec(cfg)). ENS: members M1, M2, M3 (each tuned) and the same "tuning".
    """
    if rung == "M0":
        return {"rung": "M0", "feature": cfg["models"]["M0"]["feature"], "author": AUTHOR, "kind": "human",
                "notes": "M0 In-Sample walk-forward (Phase 2.3a)"}
    if rung == "ENS":
        return {"rung": "ENS", "members": list(ENS_MEMBERS), "tuning": tuning_spec(cfg), "author": AUTHOR, "kind": "human",
                "notes": "ENS: equal-weight rank average of M1, M2, M3, each tuned per Amendment 5 C1 (Phase 3.1)"}
    if rung not in RUNGS:
        raise ValueError(f"model_spec: unknown rung {rung!r}; known {list(RUNGS)}")
    return {"rung": rung, "tuning": tuning_spec(cfg), "author": AUTHOR, "kind": "human",
            "notes": f"{rung} with its grid value chosen at each refit per Amendment 5 C1 (Phase 3.1)"}


def fixed_names(cfg: dict) -> list[str]:
    """--fixed names, one per grid value (Amendment 5 C2, S31-10): M1_a<λ>, M2_a<λ>, M3_d<depth>, M0_L<lookback>."""
    names = []
    for rung, prefix in FIXED_PREFIX.items():
        stem = "M0" if rung == "M0_star" else rung
        names += [f"{stem}_{prefix}{format(value, 'g')}" for value in grid(rung, cfg)]
    return names


def fixed_spec(name: str, cfg: dict) -> dict:
    """The spec of a fixed grid value (S31-2, S31-6). M0_L26 is the M0 spec itself (same trial); M0_L13 and M0_L52 are M0
    on the variants MOM13_1 and MOM52_1; M1/M2 take {"alpha": λ}, M3 {"max_depth": d}.
    """
    if name not in fixed_names(cfg):
        raise ValueError(f"fixed_spec: unknown name {name!r}; known {fixed_names(cfg)}")
    stem, tag = name.split("_", 1)
    rung = "M0_star" if stem == "M0" else stem
    value = next(v for v in grid(rung, cfg) if format(v, "g") == tag[1:])
    if rung == "M0_star":
        if f"MOM{int(value)}_1" == cfg["models"]["M0"]["feature"]:
            return model_spec("M0", cfg)
        return {"rung": "M0", "feature": f"MOM{int(value)}_1", "author": AUTHOR, "kind": "human",
                "notes": f"M0 on a fixed {int(value)}-week lookback, an M0* grid value (Amendment 5 C2, Phase 3.1)"}
    key = PARAM_KEYS[rung]
    return {"rung": rung, "params": {key: value}, "author": AUTHOR, "kind": "human",
            "notes": f"{rung} with fixed {key} = {format(value, 'g')} (Amendment 5 C2, Phase 3.1)"}


def spec_for(name: str, cfg: dict) -> dict:
    """The spec of a --model rung or a --fixed name."""
    return model_spec(name, cfg) if name in RUNGS else fixed_spec(name, cfg)


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
              spots: Sequence[tuple[str, str]] = SPOTS, name: str | None = None) -> dict:
    """summary.json of a walk-forward run (S23-3): counts, first and last week, per-sector sums, min, max, the fixed spot
    values and the SHA-256 of scores.csv. No time or machine-dependent field, so equal scores give equal bytes.
    """
    values = scores.to_numpy(dtype=np.float64)
    closes = _closes(scores.index)
    return {
        "name": rung if name is None else name,
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


def run(name: str, cfg: dict, *, data_dir: Path, out_dir: Path, trial_path: Path, log_path: Path, lock_path: Path,
        spots: Sequence[tuple[str, str]] = SPOTS) -> dict:
    """Walk-forward scores of one rung or fixed grid value through the vault, written with used.yaml, summary.json and,
    for a tuned rung with a grid, selection.csv; returns the summary.

    name: a --model rung or a --fixed name; data_dir: data/processed (the tables of 03_build_features.py and
    features_config.yaml, checked first); out_dir: outputs/walkforward/<name>; trial_path, log_path, lock_path: the trial
    log, the vault access log and FROZEN.lock.
    """
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    spec = spec_for(name, cfg)
    rung = str(spec["rung"])
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
    selection = vault.last_selection
    if selection is not None:
        if len(selection) != len(folds):
            raise ValueError(f"selection.csv: {len(selection)} rows for {len(folds)} refits")
        write_csv(selection.set_index(["test_year", "refit"]), out_dir / "selection.csv")
    summary = summarise(scores, rung=rung, digest=spec_hash(spec, cfg), refits=len(folds),
                        scores_sha256=sha256(out_dir / "scores.csv"), spots=spots, name=name)
    _write_json(summary, out_dir / "summary.json")
    return summary


def main(argv: list[str] | None = None) -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model", choices=RUNGS, help="rung to score; M1, M2, M3, M0_star and ENS use Amendment 5 C1")
    group.add_argument("--fixed", choices=fixed_names(cfg), help="one grid value as a fixed configuration (Amendment 5 C2)")
    args = parser.parse_args(argv)

    name = args.model or args.fixed
    out_dir = ROOT / "outputs" / "walkforward" / name
    summary = run(name, cfg, data_dir=ROOT / cfg["data"]["data_dir"] / "processed", out_dir=out_dir,
                  trial_path=ROOT / "docs" / "trial_log.csv", log_path=ROOT / "outputs" / "vault_access_log.jsonl",
                  lock_path=ROOT / "FROZEN.lock")
    print(f"{name}: {summary['refits']} refits, {summary['weeks']} test weeks, {summary['first_week']} to "
          f"{summary['last_week']}, {summary['nan_count']} missing scores")
    extra = ", selection.csv" if (out_dir / "selection.csv").exists() and name in RUNGS and name != "M0" else ""
    print(f"Saved {out_dir.relative_to(ROOT).as_posix()}/scores.csv, used.yaml, summary.json{extra}")


if __name__ == "__main__":
    main()
