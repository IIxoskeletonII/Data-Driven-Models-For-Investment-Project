"""The Out-of-Sample vault of protocol section 10: refuses any label or metric dated after the In-Sample end
until FROZEN.lock exists, and is the only path from the built data to models and agents.

Phase 2.2 (Eliya); decisions S22-7 and S22-8. Interfaces: docs/interfaces.md, contract 15.
"""

import csv
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT, load_config
from src.contracts import universe, validate_features, validate_labels, validate_market_states, validate_scores
from src.labels import assert_purged, label_end_by_week, walk_forward_folds
from src.models import M0

TRIAL_COLUMNS = ["trial_id", "timestamp", "author", "kind", "rung", "spec_hash", "params_json", "is_sharpe", "is_mdd",
                 "notes"]
TRIAL_KINDS = ("human", "agent")
FRAME_NAMES = ("features", "market_states", "labels", "momentum_variants")
SPEC_DATE_KEYS = ("as_of", "end")
SPEC_KEYS = ("rung", "feature", "author", "kind", "notes") + SPEC_DATE_KEYS  # anything else is refused (S22-12)
MOMENTUM_VARIANT = re.compile(r"MOM\d+_1")
IMPLEMENTED_RUNGS = ("M0",)


class OOSAccessError(PermissionError):
    """A request touched a date after the In-Sample end (2019-12-27) while the vault is sealed (§10)."""


def _utc_now() -> str:
    """Current time in UTC, ISO-8601 to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _spec_json(spec: Mapping[str, object]) -> str:
    """Canonical JSON of a model spec: sorted keys, no spaces (dates written as text)."""
    return json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), default=str)


def _read_frame(name: str, path: Path) -> pd.DataFrame:
    """One built table of data/processed (git-ignored), with the index of its contract."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run 03_build_features.py (labels: Phase 2.3, S22-7)")
    if name == "market_states":
        frame = pd.read_csv(path, index_col=["date_open", "date_close"], parse_dates=["date_open", "date_close"])
    else:
        dates = ["date_close", "label_end"] if name == "labels" else ["date_close"]
        frame = pd.read_csv(path, index_col=["date_close", "ticker"], parse_dates=dates)
    numeric = [column for column in frame.columns if column != "label_end"]
    return frame.astype(dict.fromkeys(numeric, np.float64))  # an all-integer column (BEAR24 0/1) reads back as int64


def _validate_frame(name: str, frame: pd.DataFrame) -> None:
    """Contract check of a table entering the vault."""
    if name == "features":
        validate_features(frame)
    elif name == "market_states":
        validate_market_states(frame)
    elif name == "labels":
        validate_labels(frame)
    else:
        validate_features(frame, columns=list(frame.columns))


def _closes(frame: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


class Vault:
    """The only path from data to models and agents (§10, contract 15).

    is_end: last In-Sample Friday (split.in_sample_end). Until lock_path (FROZEN.lock) exists, and even then except
    through the explicit unlock path of 08_run_oos.py, any request touching a later date raises OOSAccessError. Every
    call appends one JSON line (UTC time, method, as_of or spec hash, ok or refused) to log_path.

    Keyword-only (S22-8): data_dir holds features.csv, market_states.csv, labels.csv and momentum_variants.csv, read
    lazily on first use; `frames` gives the same tables in memory instead (keys "features", "market_states", "labels",
    optional "momentum_variants"); cfg is the configuration (config.yaml when None).
    """

    def __init__(self, is_end: pd.Timestamp, lock_path: Path = ROOT / "FROZEN.lock",
                 log_path: Path = ROOT / "outputs" / "vault_access_log.jsonl", *,
                 data_dir: Path = ROOT / "data" / "processed", frames: Mapping[str, pd.DataFrame] | None = None,
                 cfg: dict | None = None) -> None:
        self.is_end = pd.Timestamp(is_end)
        self.lock_path = Path(lock_path)
        self.log_path = Path(log_path)
        self.data_dir = Path(data_dir)
        self._given = None if frames is None else dict(frames)
        self._cfg = cfg
        self._cache: dict[str, pd.DataFrame] = {}
        self._unlocked = False
        configured_end = pd.Timestamp((load_config() if cfg is None else cfg)["split"]["in_sample_end"])
        if self.is_end > configured_end:
            self._log("__init__", "refused", as_of=self.is_end)
            raise OOSAccessError(f"Vault: is_end {self.is_end.date()} is after split.in_sample_end {configured_end.date()}; "
                                 "Out-of-Sample dates open only through unlock() after the freeze (§10, S22-12)")

    # -- access log and the seal ---------------------------------------------------------------------------------------

    def _log(self, method: str, result: str, *, as_of: pd.Timestamp | None = None, spec_hash: str | None = None) -> None:
        """Append one JSON line to the access log (parent directory created if missing)."""
        record: dict[str, str] = {"utc": _utc_now(), "method": method}
        if as_of is not None:
            record["as_of"] = as_of.strftime("%Y-%m-%d")
        if spec_hash is not None:
            record["spec_hash"] = spec_hash
        record["result"] = result
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps(record) + "\n")

    def _is_open(self) -> bool:
        """True only after unlock() and while FROZEN.lock exists (Gate 4, 08_run_oos.py)."""
        return self._unlocked and self.lock_path.exists()

    def _check_date(self, method: str, as_of: pd.Timestamp) -> None:
        """Raise OOSAccessError for a date after is_end while the vault is sealed (the caller logs the refusal)."""
        if as_of > self.is_end and not self._is_open():
            raise OOSAccessError(f"Vault.{method}: {as_of.date()} is after the In-Sample end {self.is_end.date()}; "
                                 "the vault stays sealed until FROZEN.lock exists and 08_run_oos.py unlocks it (§10)")

    def unlock(self) -> None:
        """Open the vault for Out-of-Sample dates; called only by 08_run_oos.py after the freeze (Gate 4).

        Raises OOSAccessError (logged as refused) when lock_path (FROZEN.lock) does not exist.
        """
        if not self.lock_path.exists():
            self._log("unlock", "refused")
            raise OOSAccessError(f"Vault.unlock: {self.lock_path} does not exist; the vault stays sealed (§10)")
        self._unlocked = True
        self._log("unlock", "ok")

    # -- tables ---------------------------------------------------------------------------------------------------------

    def _frame(self, name: str) -> pd.DataFrame:
        """A table from `frames` or data_dir, validated once against its contract (not logged)."""
        if name not in self._cache:
            if self._given is not None:
                if name not in self._given:
                    raise KeyError(f"Vault: frames has no {name!r} table")
                frame = self._given[name]
            else:
                frame = _read_frame(name, self.data_dir / f"{name}.csv")
            _validate_frame(name, frame)
            self._cache[name] = frame
        return self._cache[name]

    def _has_frame(self, name: str) -> bool:
        if self._given is not None:
            return name in self._given
        return (self.data_dir / f"{name}.csv").exists()

    def _rows_until(self, method: str, name: str, as_of) -> pd.DataFrame:
        """Rows of a table with date_close ≤ as_of, after the seal check; logged ok or refused (any failure)."""
        as_of = pd.Timestamp(as_of)
        try:
            self._check_date(method, as_of)
            frame = self._frame(name)
            rows = frame.loc[np.asarray(_closes(frame) <= as_of)].copy()
        except Exception:
            self._log(method, "refused", as_of=as_of)
            raise
        self._log(method, "ok", as_of=as_of)
        return rows

    def features(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Asset features (contract 3) with date_close ≤ as_of, known after Friday close as_of."""
        return self._rows_until("features", "features", as_of)

    def market_states(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Market states (contract 4) with date_close ≤ as_of, known after Friday close as_of."""
        return self._rows_until("market_states", "market_states", as_of)

    def labels(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Labels (contract 6) with label_end ≤ as_of: only returns already realised at as_of."""
        as_of = pd.Timestamp(as_of)
        try:
            self._check_date("labels", as_of)
            frame = self._frame("labels")
            rows = frame.loc[np.asarray(pd.DatetimeIndex(frame["label_end"]) <= as_of)].copy()
        except Exception:
            self._log("labels", "refused", as_of=as_of)
            raise
        self._log("labels", "ok", as_of=as_of)
        return rows

    # -- walk-forward ---------------------------------------------------------------------------------------------------

    def _feature_column(self, feature: str, cfg: dict) -> pd.DataFrame:
        """The single momentum column M0 scores (contract 5): from features, or a MOM{L}_1 variant (§07 M0*)."""
        if feature in cfg["features"]["asset"]:
            return self._frame("features")[[feature]]
        if MOMENTUM_VARIANT.fullmatch(feature) and self._has_frame("momentum_variants"):
            variants = self._frame("momentum_variants")
            if feature in variants.columns:
                return variants[[feature]]
        raise ValueError(f"run_walkforward: unknown feature {feature!r} (features.asset or a MOM{{L}}_1 variant)")

    def _check_spec(self, spec: Mapping[str, object]) -> str:
        """Unknown keys, then the seal check of the spec's dates, then its rung and kind; returns the rung (S22-12)."""
        unknown = sorted(set(spec) - set(SPEC_KEYS))
        if unknown:
            raise ValueError(f"run_walkforward: unknown spec keys {unknown}; allowed {list(SPEC_KEYS)}")
        for key in SPEC_DATE_KEYS:
            if spec.get(key) is not None:
                self._check_date("run_walkforward", pd.Timestamp(spec[key]))
        rung = spec.get("rung")
        if rung is None:
            raise ValueError("run_walkforward: the spec must name a rung")
        if rung not in IMPLEMENTED_RUNGS:
            raise NotImplementedError("Phase 3.1, Eliya")
        kind = spec.get("kind")
        if kind is not None and kind not in TRIAL_KINDS:
            raise ValueError(f"run_walkforward: kind must be one of {TRIAL_KINDS}, got {kind!r}")
        return str(rung)

    def _walkforward_scores(self, feature: str, cfg: dict) -> pd.DataFrame:
        """M0 scores of the test weeks of every In-Sample fold (contract 13), on the weekly index (contract 8)."""
        is_end = self.is_end
        labels = self._frame("labels")
        labels = labels.loc[np.asarray(pd.DatetimeIndex(labels["label_end"]) <= is_end)]
        states = self._frame("market_states")
        weeks = states.index[np.asarray(_closes(states) <= is_end)]
        folds = walk_forward_folds(weeks, label_end_by_week(labels, weeks), cfg)
        column = self._feature_column(feature, cfg)
        column = column.loc[np.asarray(_closes(column) <= is_end)]
        dates = _closes(column)
        model = M0(feature=feature)
        scored = []
        for fold in folds:
            train = column.loc[np.asarray((dates >= fold.train_start) & (dates <= fold.train_end))]
            train = train.loc[train.index.isin(labels.index)]
            assert_purged(labels.loc[train.index, "label_end"], fold)
            model.fit(train, labels.loc[train.index, "y"])
            scored.append(model.score(column.loc[np.asarray((dates >= fold.test_start) & (dates <= fold.test_end))]))
        week_closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
        test_weeks = weeks[np.asarray((week_closes >= folds[0].test_start) & (week_closes <= folds[-1].test_end))]
        return _weekly_scores(pd.concat(scored), test_weeks, cfg)

    def run_walkforward(self, spec: Mapping[str, object], evaluate: Callable[[pd.DataFrame], tuple[float, float]] | None = None,
                        *, trial_path: Path = ROOT / "docs" / "trial_log.csv") -> pd.DataFrame:
        """Weekly scores (contract 8) of a model spec over the In-Sample walk-forward folds (contract 13); appends one row
        to the trial log (docs/trial_log.csv).

        spec: {"rung": "M0" (others: Phase 3.1), "feature": default models.M0.feature (MOM26_1), optional "author",
        "kind" ("human"/"agent"), "notes", "as_of", "end"}; any other key is refused (ValueError), and a spec "as_of" or
        "end" after is_end is refused (OOSAccessError); every failure is logged as refused (S22-12). Only labels
        with label_end ≤ is_end are used; every fit is purged (assert_purged). Score of week t is known after Friday
        close t. evaluate(scores) -> (In-Sample net Sharpe, max drawdown) fills is_sharpe and is_mdd (S22-8).
        """
        params_json = _spec_json(spec)
        spec_hash = hashlib.sha256(params_json.encode("utf-8")).hexdigest()
        try:
            rung = self._check_spec(spec)
            cfg = load_config() if self._cfg is None else self._cfg
            feature = str(spec.get("feature") or cfg["models"]["M0"]["feature"])
            scores = self._walkforward_scores(feature, cfg)
            validate_scores(scores)
            sharpe, mdd = evaluate(scores) if evaluate is not None else ("", "")
        except Exception:
            self._log("run_walkforward", "refused", spec_hash=spec_hash)
            raise
        append_trial({"author": spec.get("author", ""), "kind": spec.get("kind", ""), "rung": rung, "spec_hash": spec_hash,
                      "params_json": params_json, "is_sharpe": sharpe, "is_mdd": mdd, "notes": spec.get("notes", "")},
                     path=trial_path)
        self._log("run_walkforward", "ok", spec_hash=spec_hash)
        return scores


def _weekly_scores(scores: pd.Series, weeks: pd.MultiIndex, cfg: dict) -> pd.DataFrame:
    """Row scores (date_close, ticker) as a weekly frame (contract 8): weekly index `weeks`, columns the sectors, float64,
    NaN where a week or sector has no score.
    """
    wide = scores.unstack("ticker").reindex(columns=list(universe(cfg).sectors))
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    wide = wide.reindex(closes).astype(np.float64)
    index = pd.MultiIndex.from_arrays([closes - pd.Timedelta(days=4), closes], names=["date_open", "date_close"])
    wide.index = index
    wide.columns.name = None
    return wide


def _existing_rows(path: Path) -> int:
    """Number of data rows of an existing trial log (0 when missing or empty); checks its header."""
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with open(path, encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.reader(handle) if row]
    if rows and rows[0] != TRIAL_COLUMNS:
        raise ValueError(f"{path}: header {rows[0]} differs from {TRIAL_COLUMNS}")
    return max(len(rows) - 1, 0)


def append_trial(row: Mapping[str, object], path: Path = ROOT / "docs" / "trial_log.csv") -> None:
    """Append one trial to the trial log (§10, §11): columns trial_id, timestamp, author, kind, rung, spec_hash,
    params_json, is_sharpe, is_mdd, notes (docs/data_dictionary.md). Every configuration evaluated on In-Sample data is
    one row; the count feeds the Deflated Sharpe Ratio.

    Unknown keys raise ValueError. A missing trial_id is 1 + the number of existing data rows; a missing timestamp is the
    current UTC time (ISO-8601); other missing fields are empty. The header is written when the file is missing or
    empty. UTF-8, LF line endings.
    """
    unknown = sorted(set(row) - set(TRIAL_COLUMNS))
    if unknown:
        raise ValueError(f"append_trial: unknown columns {unknown}; allowed {TRIAL_COLUMNS}")
    path = Path(path)
    existing = _existing_rows(path)
    values = {column: "" if row.get(column) is None else row[column] for column in TRIAL_COLUMNS}
    if row.get("trial_id") is None:
        values["trial_id"] = existing + 1
    if row.get("timestamp") is None:
        values["timestamp"] = _utc_now()
    write_header = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if write_header:
            writer.writerow(TRIAL_COLUMNS)
        writer.writerow([values[column] for column in TRIAL_COLUMNS])
