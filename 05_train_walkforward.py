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

Session 3.7 (decisions S37-4 to S37-7), In-Sample only:
  --agent-returns  re-scores, through the sealed vault, each agent candidate of the trial log that reached the
                   walk-forward, checks it reproduces its row, and writes outputs/agent_lab/walkforward/agent_cNN/
                   weekly.csv (realised_on, period, net, rf) and summary.json; adds no trial row.
  --select         reads the In-Sample baseline backtests of 06_backtest.py (outputs/backtests/<name>/), refusing stale
                   ones as 06 does, applies the §07 gate (src.stats.selection_gate, headline Sharpe with the weekly
                   T-bill, M5 absent) and writes outputs/metrics/selection_gate.json (read by 08_run_oos.py --freeze);
                   fills is_sharpe and is_mdd of the human rows of docs/trial_log.csv; writes the Deflated Sharpe Ratio
                   and PBO by CSCV to outputs/metrics/selection_bias.json.
"""

import argparse
import csv
import functools
import importlib.util
import io
import json
import math
import os
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from src import stats
from src.config import ROOT, check_used, load_config, save_used
from src.contracts import universe, validate_scores
from src.data import DATE_FORMAT, sha256, write_csv
from src.features import features_settings
from src.labels import label_end_by_week, walk_forward_folds
from src.metrics import max_drawdown, sharpe_ratio
from src.models import ENS_MEMBERS, PARAM_KEYS, grid, tuning_spec, walkforward_settings
from src.vault import TRIAL_COLUMNS, Vault, logged_spec_hashes, spec_hash

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


# -- the §07 selection gate, the trial metrics and the selection-bias diagnostics (decisions S37-4 to S37-7) -------------

GATE_MODELS = ("M0", "M1", "M2", "M3", "ENS")  # the hurdle, then the candidates that exist (S37-4)
ABSENT = ("M5",)  # no agent feature survived the lab, so M5 does not exist (S33-19, S37-1)
GATE_FILE = "outputs/metrics/selection_gate.json"  # read by 08_run_oos.py --freeze (S34-3)
BIAS_FILE = "outputs/metrics/selection_bias.json"
AGENT_DIR = "outputs/agent_lab/walkforward"
TRIAL_LOG = "docs/trial_log.csv"
AGENT_RUN_SUMMARY = "agent_lab/run/summary.json"
WALK_FORWARD_STAGE = "walk_forward"  # the agent trial rows that have weekly returns (S33-9, S37-6)
WEEK_COLUMNS = ["date_open", "date_close"]
RF_TOLERANCE = 1e-12  # the five backtests must carry the same weekly T-bill (S37-4)
REPRODUCTION_TOLERANCE = 1e-9  # re-scored agent candidate against its trial row (S37-6, S34-2)
FALLBACK_STATEMENT = ("No candidate passed the §07 gate, so M0* is traded: the ML models failed to beat the baseline "
                      "(pre-registration §07 step 5).")
RF_SOURCE = ("rf column of outputs/backtests/M0/weekly.csv: the weekly FRED 3-month T-bill return written by "
             "06_backtest.py (src.metrics.tbill_weekly_returns, DGS3MO lagged one session); Amendment 6 C1")


@functools.cache
def _backtest_script():
    """06_backtest.py, loaded by path from this folder and read only: backtest_used and cost_scenarios (S37-4)."""
    path = Path(__file__).resolve().parent / "06_backtest.py"
    spec = importlib.util.spec_from_file_location("backtest_script_for_select", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shown(path: Path, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _json_text(content: dict) -> str:
    """Sorted keys, indent 2, LF, no NaN (a non-finite value stops the run before anything is written)."""
    def plain(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"not JSON serialisable: {type(value).__name__}")
    try:
        return json.dumps(content, indent=2, sort_keys=True, allow_nan=False, default=plain) + "\n"
    except ValueError as error:
        raise SystemExit(f"refused: a non-finite value in the output ({error})") from None


def _write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def baseline_label(cfg: dict) -> str:
    """Label of the baseline cost scenario of 06_backtest.py (e.g. "10bps_2pct", S23-7)."""
    return next(label for label, _, _, is_baseline in _backtest_script().cost_scenarios(cfg) if is_baseline)


def read_weekly(path: Path) -> pd.DataFrame:
    """A weekly.csv of 06_backtest.py or of --agent-returns: weekly index, realised_on, period, net, rf, ..."""
    return pd.read_csv(path, index_col=WEEK_COLUMNS, parse_dates=[*WEEK_COLUMNS, "realised_on"])


def _check_in_sample_weekly(weekly: pd.DataFrame, cfg: dict, what: str) -> None:
    """Stop unless every week is In-Sample (period IS, date_close and realised_on on or before split.in_sample_end) and
    net and rf are finite (operating manual rule 3; S37-4)."""
    missing = [c for c in ("realised_on", "period", "net", "rf") if c not in weekly.columns]
    if missing or weekly.empty:
        raise SystemExit(f"refused: {what} is empty or lacks the columns {missing}")
    if not weekly.index.is_unique or not weekly.index.is_monotonic_increasing:
        raise SystemExit(f"refused: {what} has duplicate or unsorted weeks")
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    realised = pd.DatetimeIndex(weekly["realised_on"])
    bad = (_closes(weekly.index) > is_end) | realised.isna() | (realised > is_end) | (weekly["period"] != "IS").to_numpy()
    if bad.any():
        raise SystemExit(f"refused: {what} holds {int(bad.sum())} week(s) that are not In-Sample; Out-of-Sample results "
                         "exist only after 08_run_oos.py")
    try:
        values = weekly[["net", "rf"]].to_numpy(dtype=np.float64)
    except (TypeError, ValueError):
        values = np.array([np.nan])
    if not np.isfinite(values).all():
        raise SystemExit(f"refused: {what} has a missing or non-finite net or rf")


def trial_rows(root: Path) -> list[dict]:
    """The rows of docs/trial_log.csv as dictionaries of strings, in file order; stops on a missing file or header."""
    path = Path(root) / TRIAL_LOG
    if not path.exists():
        raise SystemExit(f"{TRIAL_LOG} not found")
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != TRIAL_COLUMNS:
            raise SystemExit(f"{TRIAL_LOG}: header {reader.fieldnames} differs from {TRIAL_COLUMNS}")
        rows = list(reader)
    for row in rows:
        if None in row or None in row.values():
            raise SystemExit(f"{TRIAL_LOG}: row {row.get('trial_id')} does not have exactly {len(TRIAL_COLUMNS)} fields")
    return rows


def refuse_after_freeze(root: Path) -> None:
    """Stop if FROZEN.lock exists: the gate file and the trial log are frozen artefacts (S34-3, S37-8)."""
    if (Path(root) / "FROZEN.lock").exists():
        raise SystemExit("refused: FROZEN.lock exists; the selection step and the trial log are frozen (S34-3, S37-8)")


def checked_backtest(name: str, cfg: dict, root: Path) -> pd.DataFrame:
    """weekly.csv of outputs/backtests/<name>/ after the checks of S37-4, which refuse what 06_backtest.py would:
    used.yaml against 06's backtest_used; the walk-forward and backtest summary.json spec_hash against
    spec_hash(spec_for(name, cfg), cfg) (S32-10) and the trial log; an In-Sample baseline summary; every week In-Sample
    with finite net and rf. Stops (SystemExit) on any failure."""
    root = Path(root)
    folder = root / "outputs" / "backtests" / name
    try:
        expected = spec_hash(spec_for(name, cfg), cfg)
        check_used(_backtest_script().backtest_used(cfg, name), folder / "used.yaml", f"06_backtest.py --model {name}")
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(f"refused: {name}: {error}") from None
    for path in (root / "outputs" / "walkforward" / name / "summary.json", folder / "summary.json"):
        if not path.exists():
            raise SystemExit(f"refused: {_shown(path, root)} not found (run 05 and 06 for {name})")
        recorded = _read_json(path).get("spec_hash")
        if recorded != expected:
            raise SystemExit(f"refused: {name}: stale output. {_shown(path, root)} has spec_hash {str(recorded)[:12]}…, "
                             f"the current config.yaml gives {expected[:12]}… (decision S32-10)")
    try:
        logged = logged_spec_hashes(root / TRIAL_LOG)
    except ValueError as error:
        raise SystemExit(f"refused: {error}") from None
    if expected not in logged:
        raise SystemExit(f"refused: {name}: spec_hash {expected[:12]}… is not a row of {TRIAL_LOG}")
    summary = _read_json(folder / "summary.json")
    if summary.get("period") != "IS" or summary.get("baseline") != baseline_label(cfg):
        raise SystemExit(f"refused: {_shown(folder, root)}/summary.json is not the In-Sample baseline backtest "
                         f"(period {summary.get('period')!r}, baseline {summary.get('baseline')!r})")
    path = folder / "weekly.csv"
    if not path.exists():
        raise SystemExit(f"refused: {_shown(path, root)} not found (run 06_backtest.py --model {name})")
    weekly = read_weekly(path)
    _check_in_sample_weekly(weekly, cfg, _shown(path, root))
    return weekly


def _gate_frames(cfg: dict, root: Path) -> dict[str, pd.DataFrame]:
    """Checked weekly.csv of M0 and of each candidate of models.candidate_order that is not absent, on one weekly index
    and one rf."""
    names = ["M0", *(name for name in cfg["models"]["candidate_order"] if name not in ABSENT)]
    if tuple(names) != GATE_MODELS:
        raise SystemExit(f"refused: the gate models {names} differ from {list(GATE_MODELS)} of decision S37-4")
    frames = {name: checked_backtest(name, cfg, root) for name in names}
    m0 = frames["M0"]
    for name, frame in frames.items():
        if not frame.index.equals(m0.index):
            raise SystemExit(f"refused: {name} and M0 are not backtested on the same weeks; the gate pairs them week by "
                             "week (§07 step 1)")
        gap = float(np.max(np.abs(frame["rf"].to_numpy(np.float64) - m0["rf"].to_numpy(np.float64))))
        if gap > RF_TOLERANCE:
            raise SystemExit(f"refused: the rf column of {name} differs from M0's by {gap:.3g}; one weekly T-bill series "
                             "serves every Sharpe")
    return frames


def gate_inputs(cfg: dict, root: Path) -> tuple[dict[str, pd.Series], pd.Series, pd.Series]:
    """(candidate name → weekly net returns, M0's weekly net returns, weekly T-bill rf) for src.stats.selection_gate."""
    return _gate_series(_gate_frames(cfg, root))


def _gate_series(frames: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.Series], pd.Series, pd.Series]:
    results = {name: frame["net"].astype(np.float64).rename(name) for name, frame in frames.items() if name != "M0"}
    return results, frames["M0"]["net"].astype(np.float64).rename("M0"), frames["M0"]["rf"].astype(np.float64).rename("rf")


def gate_result(cfg: dict, root: Path) -> dict:
    """Content of outputs/metrics/selection_gate.json (S37-4): the §07 rule on the In-Sample backtests, headline Sharpe
    with the weekly T-bill (Amendment 6 C1), M5 absent."""
    root = Path(root)
    frames = _gate_frames(cfg, root)
    results, m0, rf = _gate_series(frames)
    gate = stats.selection_gate(results, m0, cfg, rf=rf, absent=ABSENT)
    closes, realised = _closes(m0.index), pd.DatetimeIndex(frames["M0"]["realised_on"])
    fallback = gate["selected"] == stats.FALLBACK
    statement = (FALLBACK_STATEMENT if fallback else
                 f"{gate['selected']} is the first candidate to pass all three tests of the §07 gate and is traded "
                 "(pre-registration §07 step 4).")
    inputs = {name: {"spec_hash": spec_hash(spec_for(name, cfg), cfg),
                     "weekly_sha256": sha256(root / "outputs" / "backtests" / name / "weekly.csv")} for name in frames}
    return {
        "selected": gate["selected"], "candidates": gate["candidates"], "absent": list(ABSENT),
        "m0": {"sharpe": sharpe_ratio(m0, rf), "sharpe_zero_cost": sharpe_ratio(m0, 0.0), "mdd": max_drawdown(m0)},
        "thresholds": dict(cfg["selection"]), "seed": int(cfg["seed"]),
        "weeks": len(m0), "first_week": closes.min().strftime(DATE_FORMAT), "last_week": closes.max().strftime(DATE_FORMAT),
        "first_realised_on": realised.min().strftime(DATE_FORMAT), "last_realised_on": realised.max().strftime(DATE_FORMAT),
        "rf_source": RF_SOURCE,
        "rf_tbill_annual": _read_json(root / "outputs" / "backtests" / "M0" / "summary.json").get("rf_tbill_annual"),
        "inputs": inputs, "fallback": fallback, "statement": statement,
        "rule": "pre-registration §07 steps 1 to 5; headline Sharpe of Amendment 6 C1; M5 absent (S33-19, S37-1)",
    }


def _backtest_names(cfg: dict, root: Path) -> list[str]:
    """The names of S31-10 (the rungs, then the fixed grid values) that have a folder under outputs/backtests/."""
    return [name for name in (*RUNGS, *fixed_names(cfg)) if (Path(root) / "outputs" / "backtests" / name).is_dir()]


def trial_log_with_metrics(cfg: dict, root: Path) -> tuple[str, int]:
    """(new text of docs/trial_log.csv, number of cells filled): is_sharpe and is_mdd of every human row from the
    baseline backtest summary.json (net_sharpe_rf_tbill, max_drawdown) of the folders holding its spec_hash, each
    checked as in S37-4 (S37-5). Agent rows are unchanged; a filled cell is kept if equal and stops the run if not."""
    root = Path(root)
    rows = trial_rows(root)
    backtests: dict[str, list[tuple[str, dict]]] = {}
    for name in _backtest_names(cfg, root):
        checked_backtest(name, cfg, root)
        summary = _read_json(root / "outputs" / "backtests" / name / "summary.json")
        backtests.setdefault(summary["spec_hash"], []).append((name, summary))
    filled = 0
    for row in rows:
        if row["kind"] != "human":
            continue
        matches = backtests.get(row["spec_hash"])
        if not matches:
            raise SystemExit(f"refused: trial {row['trial_id']} ({row['rung']}, {row['spec_hash'][:12]}…) has no backtest "
                             "under outputs/backtests/; run 05 and 06 for it")
        values = {(float(s["net_sharpe_rf_tbill"]), float(s["max_drawdown"])) for _, s in matches}
        if len(values) != 1:
            raise SystemExit(f"refused: the backtests {[n for n, _ in matches]} of trial {row['trial_id']} disagree")
        for column, value in zip(("is_sharpe", "is_mdd"), values.pop(), strict=True):
            if not math.isfinite(value):
                raise SystemExit(f"refused: trial {row['trial_id']}: {column} is not finite")
            current = row[column]
            if current == "":
                row[column] = repr(value)
                filled += 1
                continue
            try:
                same = float(current) == value
            except ValueError:
                same = False
            if not same:
                raise SystemExit(f"refused: trial {row['trial_id']} already holds {column} {current}, but its backtest "
                                 f"gives {value!r}; the trial log or the backtest is stale (S37-5)")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(TRIAL_COLUMNS)
    for row in rows:
        writer.writerow([row[column] for column in TRIAL_COLUMNS])
    return buffer.getvalue(), filled


def _notes(row: dict) -> dict:
    try:
        notes = json.loads(row.get("notes") or "")
    except ValueError:
        return {}
    return notes if isinstance(notes, dict) else {}


def walk_forward_agent_rows(rows: list[dict]) -> list[dict]:
    """Agent trial rows whose notes record the stage walk_forward: the candidates with weekly returns (S33-9, S37-6)."""
    return [row for row in rows if row["kind"] == "agent" and _notes(row).get("stage") == WALK_FORWARD_STAGE]


def agent_folder(root: Path, row: dict) -> Path:
    """outputs/agent_lab/walkforward/agent_c<candidate, 2 digits> of an agent trial row (S37-6)."""
    candidate = _notes(row).get("candidate")
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise SystemExit(f"refused: trial {row['trial_id']} has no candidate number in its notes")
    return Path(root) / AGENT_DIR / f"agent_c{candidate:02d}"


def _agent_spec(row: dict, cfg: dict) -> dict:
    """The spec of an agent trial row, refused if its spec_hash under cfg is not the row's (stale, S37-6)."""
    spec = json.loads(row["params_json"])
    digest = spec_hash(spec, cfg)
    if digest != row["spec_hash"]:
        raise SystemExit(f"refused: trial {row['trial_id']}: its spec gives spec_hash {digest[:12]}… under the current "
                         f"config.yaml, not the logged {row['spec_hash'][:12]}… (stale)")
    return spec


def agent_returns(cfg: dict, root: Path, server) -> list[dict]:
    """Re-score each agent candidate that reached the walk-forward and write its weekly In-Sample returns (S37-6).

    server: the lab's VaultServer on the sealed vault (src.agents.vault_server.real_server); its vault scores the spec
    (a logged spec adds no trial row, S23-2) and its book() is the computation that produced the trial row's figures.
    Stops unless the headline Sharpe and max drawdown reproduce the row's is_sharpe and is_mdd within 1e-9 and the trial
    log stays byte-identical. Writes AGENT_DIR/agent_cNN/weekly.csv (realised_on, period, net, rf) and summary.json."""
    root = Path(root)
    refuse_after_freeze(root)
    trial_path = root / TRIAL_LOG
    before = trial_path.read_bytes() if trial_path.exists() else None
    rows = walk_forward_agent_rows(trial_rows(root))
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    _, realised_on, period = server.vault.forward_returns(is_end)
    out = []
    for row in rows:
        spec = _agent_spec(row, cfg)
        folder = agent_folder(root, row)
        try:
            logged_sharpe, logged_mdd = float(row["is_sharpe"]), float(row["is_mdd"])
        except ValueError:
            raise SystemExit(f"refused: trial {row['trial_id']} has no recorded is_sharpe and is_mdd") from None
        scores = server.vault.run_walkforward(spec, trial_path=trial_path)
        if trial_path.read_bytes() != before:
            raise SystemExit(f"refused: {TRIAL_LOG} changed while re-scoring trial {row['trial_id']}; a logged spec must "
                             "add no row (S23-2)")
        book = server.book(scores)
        sharpe, mdd = float(book["net_sharpe"]), float(book["max_drawdown"])
        if abs(sharpe - logged_sharpe) > REPRODUCTION_TOLERANCE or abs(mdd - logged_mdd) > REPRODUCTION_TOLERANCE:
            raise SystemExit(f"refused: trial {row['trial_id']} does not reproduce: Sharpe {sharpe!r} against "
                             f"{logged_sharpe!r}, max drawdown {mdd!r} against {logged_mdd!r} (tolerance 1e-9, S37-6)")
        net = book["net"].astype(np.float64)
        weeks = net.index
        weekly = pd.DataFrame({"realised_on": realised_on.reindex(weeks), "period": period.reindex(weeks), "net": net,
                               "rf": pd.Series(book["rf"]).reindex(weeks).astype(np.float64)}, index=weeks)
        _check_in_sample_weekly(weekly, cfg, f"trial {row['trial_id']}'s re-scored book")
        closes = _closes(weeks)
        summary = {"trial_id": int(row["trial_id"]), "candidate": int(_notes(row)["candidate"]),
                   "spec_hash": row["spec_hash"], "net_sharpe_rf_tbill": sharpe, "max_drawdown": mdd,
                   "weeks": len(weeks), "first_week": closes.min().strftime(DATE_FORMAT),
                   "last_week": closes.max().strftime(DATE_FORMAT)}
        write_csv(weekly, folder / "weekly.csv")
        _write_text(_json_text(summary), folder / "summary.json")
        out.append(summary)
    return out


def trial_matrix(cfg: dict, root: Path) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """(weekly net returns, one column per distinct spec_hash with In-Sample returns, on the common weeks; the column
    descriptions; the trial rows without weekly returns) for the DSR and PBO (S37-7). Columns: the backtest folders
    (checked as in S37-4; M0_L26 shares M0's column) and the agent folders of S37-6 (checked by spec hash)."""
    root = Path(root)
    rows = trial_rows(root)
    ids: dict[str, list[int]] = {}
    for row in rows:
        ids.setdefault(row["spec_hash"], []).append(int(row["trial_id"]))
    by_hash = {row["spec_hash"]: row for row in rows}
    columns: dict[str, pd.Series] = {}
    described: dict[str, dict] = {}
    for name in _backtest_names(cfg, root):
        weekly = checked_backtest(name, cfg, root)
        digest = spec_hash(spec_for(name, cfg), cfg)
        if digest in described:
            described[digest]["aliases"].append(name)
            continue
        columns[digest] = weekly["net"].astype(np.float64).rename(name)
        described[digest] = {"name": name, "kind": by_hash[digest]["kind"], "rung": by_hash[digest]["rung"],
                             "spec_hash": digest, "trial_ids": ids[digest], "aliases": [],
                             "source": f"outputs/backtests/{name}/weekly.csv"}
    for row in rows:
        if row["kind"] == "human" and row["spec_hash"] not in described:
            raise SystemExit(f"refused: human trial {row['trial_id']} ({row['rung']}) has no backtest under "
                             "outputs/backtests/")
    for row in walk_forward_agent_rows(rows):
        _agent_spec(row, cfg)
        folder = agent_folder(root, row)
        shown = _shown(folder, root)
        if not (folder / "summary.json").exists() or not (folder / "weekly.csv").exists():
            raise SystemExit(f"refused: {shown} not found; run 05_train_walkforward.py --agent-returns first (S37-6)")
        if _read_json(folder / "summary.json").get("spec_hash") != row["spec_hash"]:
            raise SystemExit(f"refused: {shown}/summary.json does not hold trial {row['trial_id']}'s spec_hash (stale)")
        weekly = read_weekly(folder / "weekly.csv")
        _check_in_sample_weekly(weekly, cfg, f"{shown}/weekly.csv")
        name = folder.name
        columns[row["spec_hash"]] = weekly["net"].astype(np.float64).rename(name)
        described[row["spec_hash"]] = {"name": name, "kind": "agent", "rung": row["rung"], "spec_hash": row["spec_hash"],
                                       "trial_ids": ids[row["spec_hash"]], "aliases": [],
                                       "source": f"{AGENT_DIR}/{name}/weekly.csv"}
    matrix = pd.concat(list(columns.values()), axis=1, join="inner")
    if matrix.empty or matrix.isna().any().any():
        raise SystemExit("refused: the trial matrix has no common week or a missing value")
    excluded = [{"trial_id": int(row["trial_id"]), "kind": row["kind"], "rung": row["rung"],
                 "stage": str(_notes(row).get("stage", "")), "spec_hash": row["spec_hash"],
                 "reason": "no weekly In-Sample returns: the proposal stopped before the walk-forward"}
                for row in rows if row["spec_hash"] not in described]
    return matrix, [described[digest] for digest in columns], excluded


def selection_bias(cfg: dict, root: Path, selected: str) -> dict:
    """Content of outputs/metrics/selection_bias.json (S37-7): the Deflated Sharpe Ratio of the selected model's
    In-Sample net returns with N = every trial-log row, the trial Sharpes from the matrix of trial_matrix, and PBO by
    CSCV with inference.pbo_blocks blocks on that matrix. Sharpes are per week, mean/std (ddof=1), zero rf (S31-9)."""
    root = Path(root)
    matrix, described, excluded = trial_matrix(cfg, root)
    rows = trial_rows(root)
    n_trials = len(rows)
    net = checked_backtest(selected, cfg, root)["net"].astype(np.float64)
    periods = int(cfg["metrics"]["periods_per_year"])
    trial_sharpes = matrix.mean() / matrix.std(ddof=1)
    variance = float(trial_sharpes.var(ddof=1))
    sharpe_weekly = float(net.mean() / net.std(ddof=1))
    blocks = int(cfg["inference"]["pbo_blocks"])
    logits = stats.cscv_logits(matrix, blocks)
    closes = _closes(matrix.index)
    sr0 = stats.expected_max_sharpe(n_trials, variance)
    return {
        "selected": selected,
        "dsr": {"value": stats.deflated_sharpe_ratio(net, n_trials, trial_returns=matrix), "n_trials": n_trials,
                "n_trials_human": sum(row["kind"] == "human" for row in rows),
                "n_trials_agent": sum(row["kind"] == "agent" for row in rows),
                "trial_sharpe_columns": int(matrix.shape[1]), "trial_sharpe_variance_weekly": variance,
                "sr0_weekly": sr0, "sr0_annualised": sr0 * math.sqrt(periods), "sharpe_weekly": sharpe_weekly,
                "sharpe_annualised": sharpe_weekly * math.sqrt(periods), "weeks": len(net),
                "convention": "per-week Sharpe mean/std (ddof=1) of the net returns, zero rf; annualised = weekly × √52 "
                              "(S31-9, S31-12)"},
        "pbo": {"value": float(np.mean(logits <= 0)), "blocks": blocks, "splits": len(logits),
                "block_weeks": len(matrix) // blocks, "weeks_dropped": len(matrix) % blocks,
                "median_logit": float(np.median(logits))},
        "matrix": {"weeks": len(matrix), "first_week": closes.min().strftime(DATE_FORMAT),
                   "last_week": closes.max().strftime(DATE_FORMAT), "columns": described},
        "excluded": excluded,
    }


def select(cfg: dict, root: Path) -> dict:
    """--select: the gate (S37-4), the trial metrics (S37-5) and the diagnostics (S37-7). Every check runs and every
    output is built first; the three texts go to temporary files next to their targets, which then replace the targets
    (os.replace), so a failed write leaves the old files in place. Refused once FROZEN.lock exists (S37-8)."""
    root = Path(root)
    refuse_after_freeze(root)
    gate = gate_result(cfg, root)
    log_text, filled = trial_log_with_metrics(cfg, root)
    bias = selection_bias(cfg, root, gate["selected"])
    trial_path = root / TRIAL_LOG
    outputs = [(_json_text(gate), root / GATE_FILE), (_json_text(bias), root / BIAS_FILE)]
    if trial_path.read_text(encoding="utf-8") != log_text:
        outputs.append((log_text, trial_path))
    staged = []
    try:
        for text, path in outputs:
            temporary = path.with_name(path.name + ".tmp")
            _write_text(text, temporary)
            staged.append((temporary, path))
        for temporary, path in staged:
            os.replace(temporary, path)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return {"gate": gate, "bias": bias, "filled": filled}


def _verdict(ok: bool) -> str:
    return "pass" if ok else "fail"


def print_selection(result: dict) -> None:
    gate, bias = result["gate"], result["bias"]
    m0 = gate["m0"]
    print(f"Section 07 gate, In-Sample {gate['first_week']} to {gate['last_week']} ({gate['weeks']} weeks), headline Sharpe "
          f"with the weekly T-bill; M0: Sharpe {m0['sharpe']:.3f}, MDD {m0['mdd']:.2%}")
    for c in gate["candidates"]:
        if c["status"] == "absent":
            print(f"  {c['name']:4} absent")
            continue
        print(f"  {c['name']:4} Sharpe {c['sharpe']:.3f} ({_verdict(c['passes_sharpe'])}), MDD {c['mdd']:.2%} "
              f"({_verdict(c['passes_mdd'])}), P(uplift > 0) {c['p_uplift_positive']:.3f} "
              f"({_verdict(c['passes_bootstrap'])}) -> {'PASS' if c['passes'] else 'FAIL'}")
    print(f"Selected: {gate['selected']}. {gate['statement'].replace('§', 'section ')}")
    print(f"DSR {bias['dsr']['value']:.4f} (N = {bias['dsr']['n_trials']}); PBO {bias['pbo']['value']:.4f} "
          f"({bias['matrix']['weeks']} weeks x {len(bias['matrix']['columns'])} configurations, "
          f"{bias['pbo']['blocks']} blocks); trial-log cells filled: {result['filled']}")
    print(f"Saved {GATE_FILE}, {BIAS_FILE}" + (f", {TRIAL_LOG}" if result["filled"] else ""))


def main(argv: list[str] | None = None) -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model", choices=RUNGS, help="rung to score; M1, M2, M3, M0_star and ENS use Amendment 5 C1")
    group.add_argument("--fixed", choices=fixed_names(cfg), help="one grid value as a fixed configuration (Amendment 5 C2)")
    group.add_argument("--select", action="store_true",
                       help="apply the §07 gate, fill the trial metrics and write the selection-bias diagnostics")
    group.add_argument("--agent-returns", action="store_true",
                       help="re-score the agent candidates that reached the walk-forward (weekly returns for PBO)")
    args = parser.parse_args(argv)

    if args.select:
        print_selection(select(cfg, ROOT))
        return
    if args.agent_returns:
        from src.agents.vault_server import real_server  # the lab's server on the sealed vault (S37-6)
        base_rung = _read_json(ROOT / AGENT_RUN_SUMMARY)["base_rung"]
        server = real_server(base_rung, cfg, run_dir=ROOT / "outputs" / "agent_lab" / "rescore",
                             trial_path=ROOT / TRIAL_LOG)
        for summary in agent_returns(cfg, ROOT, server):
            print(f"agent_c{summary['candidate']:02d} (trial {summary['trial_id']}): Sharpe "
                  f"{summary['net_sharpe_rf_tbill']:.4f}, MDD {summary['max_drawdown']:.2%}, {summary['weeks']} weeks "
                  "(reproduced)")
        print(f"Saved {AGENT_DIR}/agent_cNN/weekly.csv, summary.json")
        return

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
