"""The Out-of-Sample vault of protocol section 10: refuses any label or metric dated after the In-Sample end
until FROZEN.lock exists, and is the only path from the built data to models and agents.

Phase 2.2 (Eliya); decisions S22-7 and S22-8. Phase 3.1: forward returns (S31-1) and the ladder specs (S31-2).
Interfaces: docs/interfaces.md, contract 15.
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
from src.contracts import (
    validate_betas,
    validate_features,
    validate_forward_returns,
    validate_labels,
    validate_market_states,
    validate_scores,
)
from src.labels import label_end_by_week, walk_forward_folds
from src.models import (
    ENS_MEMBERS,
    GRID_KEYS,
    PARAM_KEYS,
    LadderData,
    grid,
    tuning_spec,
    walkforward_rung,
    walkforward_settings,
)

TRIAL_COLUMNS = ["trial_id", "timestamp", "author", "kind", "rung", "spec_hash", "params_json", "is_sharpe", "is_mdd",
                 "notes"]
TRIAL_KINDS = ("human", "agent")
FRAME_NAMES = ("features", "market_states", "labels", "momentum_variants", "sizing_betas", "forward_returns")
WEEKLY_FRAMES = ("market_states", "sizing_betas", "forward_returns")  # weekly index; the others (date_close, ticker)
REALISED_ON, PERIOD = "realised_on", "period"  # the date and period columns of forward_returns.csv (S31-1)
SPEC_DATE_KEYS = ("as_of", "end")
# anything else is refused (S22-12); params, tuning and members added for the ladder (S31-2)
SPEC_KEYS = ("rung", "feature", "author", "kind", "notes", "params", "tuning", "members") + SPEC_DATE_KEYS
MOMENTUM_VARIANT = re.compile(r"MOM\d+_1")
IMPLEMENTED_RUNGS = ("M0", "M1", "M2", "M3", "M0_star", "ENS")


class OOSAccessError(PermissionError):
    """A request touched a date after the In-Sample end (2019-12-27) while the vault is sealed (§10)."""


def _utc_now() -> str:
    """Current time in UTC, ISO-8601 to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _spec_json(spec: Mapping[str, object]) -> str:
    """Canonical JSON of a model spec: sorted keys, no spaces (dates written as text)."""
    return json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), default=str)


def spec_hash(spec: Mapping[str, object], cfg: dict) -> str:
    """The trial log's spec_hash (S23-6): SHA-256 (hex) of the canonical JSON (sorted keys, no spaces) of
    {"config": walkforward_settings(cfg), "spec": spec}. The config sections that determine the scores are part of the
    trial's identity, so the same spec under a changed config is a new trial.
    """
    return hashlib.sha256(_spec_json({"config": walkforward_settings(cfg), "spec": dict(spec)}).encode("utf-8")).hexdigest()


def _read_frame(name: str, path: Path) -> pd.DataFrame:
    """One built table of data/processed (git-ignored), with the index of its contract."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run 03_build_features.py (labels: Phase 2.3, S22-7)")
    if name == "forward_returns":
        frame = pd.read_csv(path, index_col=["date_open", "date_close"],
                            parse_dates=["date_open", "date_close", REALISED_ON], dtype={PERIOD: object})
        frame[PERIOD] = frame[PERIOD].astype(object).where(frame[PERIOD].notna(), None)
        numeric = [column for column in frame.columns if column not in (REALISED_ON, PERIOD)]
        return frame.astype(dict.fromkeys(numeric, np.float64))
    if name in WEEKLY_FRAMES:
        frame = pd.read_csv(path, index_col=["date_open", "date_close"], parse_dates=["date_open", "date_close"])
    else:
        dates = ["date_close", "label_end"] if name == "labels" else ["date_close"]
        frame = pd.read_csv(path, index_col=["date_close", "ticker"], parse_dates=dates)
    numeric = [column for column in frame.columns if column != "label_end"]
    return frame.astype(dict.fromkeys(numeric, np.float64))  # an all-integer column (BEAR24 0/1) reads back as int64


def _validate_frame(name: str, frame: pd.DataFrame, cfg: dict | None = None) -> None:
    """Contract check of a table entering the vault (cfg: the vault's configuration, config.yaml when None)."""
    if name == "features":
        validate_features(frame)
    elif name == "market_states":
        validate_market_states(frame)
    elif name == "labels":
        validate_labels(frame)
    elif name == "sizing_betas":
        validate_betas(frame)
    elif name == "forward_returns":
        fwd, realised_on, period = split_forward_returns(frame)
        validate_forward_returns(fwd, realised_on, period)
        realised = pd.DatetimeIndex(realised_on).dropna()
        configured_end = pd.Timestamp((load_config() if cfg is None else cfg)["split"]["in_sample_end"])
        if len(realised) and realised.max() > configured_end:
            raise OOSAccessError(f"forward_returns: a return realised on {realised.max().date()} is after the In-Sample "
                                 f"end {configured_end.date()} (S31-1)")
    else:
        validate_features(frame, columns=list(frame.columns))


def split_forward_returns(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """(fwd, realised_on, period) of contract 7 from the forward-returns table (tradables, realised_on, period; S31-1)."""
    fwd = table.drop(columns=[REALISED_ON, PERIOD]).astype(np.float64)
    realised_on = pd.Series(pd.to_datetime(table[REALISED_ON]).to_numpy(dtype="datetime64[ns]"), index=table.index,
                            name=REALISED_ON)
    return fwd, realised_on, table[PERIOD].astype(object).rename(PERIOD)


def _closes(frame: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


class Vault:
    """The only path from data to models and agents (§10, contract 15).

    is_end: last In-Sample Friday (split.in_sample_end). Until lock_path (FROZEN.lock) exists, and even then except
    through the explicit unlock path of 08_run_oos.py, any request touching a later date raises OOSAccessError. Every
    call appends one JSON line (UTC time, method, as_of or spec hash, ok or refused) to log_path.

    Keyword-only (S22-8): data_dir holds features.csv, market_states.csv, labels.csv, momentum_variants.csv,
    sizing_betas.csv (S23-4) and forward_returns.csv (S31-1), read lazily on first use; `frames` gives the same tables in
    memory instead (keys "features", "market_states", "labels", optional "momentum_variants", "sizing_betas" and
    "forward_returns"); cfg is the configuration (config.yaml when None). After a tuned run_walkforward call,
    `last_selection` holds its per-refit selection table (S31-10), else None.
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
        self.last_selection: pd.DataFrame | None = None
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
            _validate_frame(name, frame, self._cfg)
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

    def sizing_betas(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Raw BETA52 of the 9 sectors and IVV against SPY (contract 10) with date_close ≤ as_of, known after Friday close
        as_of; used to size the positions taken at O(t+1) (S23-4). Sealed and logged like the other tables.
        """
        return self._rows_until("sizing_betas", "sizing_betas", as_of)

    def forward_returns(self, as_of: pd.Timestamp) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        """Forward returns of contract 7 already realised at as_of (S31-1): (fwd, realised_on, period) on the rows with
        realised_on ≤ as_of. fwd[t] = O(t+2)/O(t+1) − 1 (decimal) for the 11 tradables, realised at the open of week
        t+2. Sealed at the In-Sample end and logged like every table; the full table is validated on first read.
        """
        as_of = pd.Timestamp(as_of)
        try:
            self._check_date("forward_returns", as_of)
            fwd, realised_on, period = split_forward_returns(self._frame("forward_returns"))
            keep = np.asarray(~realised_on.isna() & (realised_on <= as_of))
            result = fwd.loc[keep].copy(), realised_on.loc[keep].copy(), period.loc[keep].copy()
        except Exception:
            self._log("forward_returns", "refused", as_of=as_of)
            raise
        self._log("forward_returns", "ok", as_of=as_of)
        return result

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

    def _feature_column(self, feature: str, cfg: dict) -> None:
        """Raise ValueError unless `feature` is the momentum column of an M0 spec (contract 5): a feature column or a
        MOM{L}_1 variant (§07 M0*).
        """
        if feature in cfg["features"]["asset"]:
            return
        variants = self._has_frame("momentum_variants") and MOMENTUM_VARIANT.fullmatch(feature)
        if variants and feature in self._frame("momentum_variants").columns:
            return
        raise ValueError(f"run_walkforward: unknown feature {feature!r} (features.asset or a MOM{{L}}_1 variant)")

    def _check_spec(self, spec: Mapping[str, object], cfg: dict) -> str:
        """Unknown keys, then the seal check of the spec's dates, then its rung, kind and ladder keys; returns the rung
        (S22-12, S31-2).
        """
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
            raise ValueError(f"run_walkforward: unknown rung {rung!r}; implemented {list(IMPLEMENTED_RUNGS)}")
        kind = spec.get("kind")
        if kind is not None and kind not in TRIAL_KINDS:
            raise ValueError(f"run_walkforward: kind must be one of {TRIAL_KINDS}, got {kind!r}")
        _check_ladder_keys(str(rung), spec, cfg)
        return str(rung)

    def _ladder_data(self, cfg: dict, tuned: bool) -> LadderData:
        """The In-Sample tables of the ladder (rows known by is_end); betas and forward returns only for tuned runs."""
        is_end = self.is_end
        features = self._frame("features")
        labels = self._frame("labels")
        states = self._frame("market_states")
        momentum = self._frame("momentum_variants") if self._has_frame("momentum_variants") else None
        data = {
            "features": features.loc[np.asarray(_closes(features) <= is_end)],
            "states": states.loc[np.asarray(_closes(states) <= is_end)],
            "labels": labels.loc[np.asarray(pd.DatetimeIndex(labels["label_end"]) <= is_end)],
            "momentum": None if momentum is None else momentum.loc[np.asarray(_closes(momentum) <= is_end)],
        }
        if tuned:
            betas = self._frame("sizing_betas")
            fwd, realised_on, period = split_forward_returns(self._frame("forward_returns"))
            keep = np.asarray(~realised_on.isna() & (realised_on <= is_end))
            data.update(betas=betas.loc[np.asarray(_closes(betas) <= is_end)], fwd=fwd.loc[keep],
                        realised_on=realised_on.loc[keep], period=period.loc[keep])
        return LadderData(**data)

    def _walkforward_scores(self, spec: Mapping[str, object], rung: str,
                            cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        """Scores of the test weeks of every In-Sample fold (contract 13) on the weekly index (contract 8), and the
        selection table of a tuned rung (S31-10). Every fit asserts the purge (src.models.walkforward_rung).
        """
        data = self._ladder_data(cfg, tuned="tuning" in spec)
        folds = walk_forward_folds(data.states.index, label_end_by_week(data.labels, data.states.index), cfg)
        if rung == "M0":
            feature = str(spec.get("feature") or cfg["models"]["M0"]["feature"])
            self._feature_column(feature, cfg)
            return walkforward_rung("M0", data, folds, cfg, value=feature)
        if rung == "ENS":
            return walkforward_rung("ENS", data, folds, cfg, members=list(spec["members"]))
        params = spec.get("params")
        value = None if params is None else params[PARAM_KEYS[rung]]
        return walkforward_rung(rung, data, folds, cfg, value=value)

    def run_walkforward(self, spec: Mapping[str, object], evaluate: Callable[[pd.DataFrame], tuple[float, float]] | None = None,
                        *, trial_path: Path = ROOT / "docs" / "trial_log.csv") -> pd.DataFrame:
        """Weekly scores (contract 8) of a model spec over the In-Sample walk-forward folds (contract 13); appends one row
        to the trial log (docs/trial_log.csv) unless a row with the same spec_hash is already there (S23-2: one row per
        distinct configuration, so a rerun does not count as a new trial). spec_hash covers the spec and the config
        sections walkforward_settings(cfg) (S23-6); params_json is the spec's canonical JSON.

        spec (S31-2): "rung" M0, M1, M2, M3, M0_star or ENS; M0 takes "feature" (default models.M0.feature, MOM26_1, or a
        MOM{L}_1 variant); M1/M2/M3 take exactly one of "params" ({"alpha": λ} or {"max_depth": d}, a value of the
        config grid) and "tuning" (= src.models.tuning_spec(cfg): the Amendment 5 C1 choice); M0_star takes "tuning";
        ENS takes "members" (M1, M2, M3) and "tuning". Optional "author", "kind" ("human"/"agent"), "notes", "as_of",
        "end"; any other key is refused (ValueError), and a spec "as_of" or "end" after is_end is refused
        (OOSAccessError); every failure is logged as refused (S22-12). Only labels and returns realised by is_end are
        used; every fit is purged (assert_purged). Score of week t is known after Friday close t. A tuned rung leaves
        its selection table in `last_selection`. evaluate(scores) -> (In-Sample net Sharpe, max drawdown) fills
        is_sharpe and is_mdd (S22-8).
        """
        params_json = _spec_json(spec)
        cfg = load_config() if self._cfg is None else self._cfg
        digest = spec_hash(spec, cfg)
        self.last_selection = None
        try:
            rung = self._check_spec(spec, cfg)
            scores, selection = self._walkforward_scores(spec, rung, cfg)
            validate_scores(scores)
            sharpe, mdd = evaluate(scores) if evaluate is not None else ("", "")
        except Exception:
            self._log("run_walkforward", "refused", spec_hash=digest)
            raise
        self.last_selection = selection
        if digest not in logged_spec_hashes(trial_path):
            append_trial({"author": spec.get("author", ""), "kind": spec.get("kind", ""), "rung": rung,
                          "spec_hash": digest, "params_json": params_json, "is_sharpe": sharpe, "is_mdd": mdd,
                          "notes": spec.get("notes", "")}, path=trial_path)
        self._log("run_walkforward", "ok", spec_hash=digest)
        return scores


def _check_ladder_keys(rung: str, spec: Mapping[str, object], cfg: dict) -> None:
    """Raise ValueError unless the spec's feature, params, tuning and members fit its rung (S31-2)."""
    params, tuning, members = spec.get("params"), spec.get("tuning"), spec.get("members")
    if spec.get("feature") is not None and rung != "M0":
        raise ValueError(f"run_walkforward: 'feature' belongs to an M0 spec, not {rung}")
    if members is not None and rung != "ENS":
        raise ValueError(f"run_walkforward: 'members' belongs to an ENS spec, not {rung}")
    if rung == "M0":
        if params is not None or tuning is not None:
            raise ValueError("run_walkforward: an M0 spec takes only 'feature' (a fixed M0* lookback is M0 on MOM{L}_1)")
        return
    if tuning is not None and _canonical(tuning) != _canonical(tuning_spec(cfg)):
        raise ValueError("run_walkforward: 'tuning' must equal src.models.tuning_spec(cfg) (Amendment 5 C1, S31-2)")
    if rung == "ENS":
        if tuning is None or params is not None:
            raise ValueError("run_walkforward: an ENS spec takes 'members' and 'tuning'")
        if members is None or list(members) != list(ENS_MEMBERS):
            raise ValueError(f"run_walkforward: ENS members must be {list(ENS_MEMBERS)} (M5 joins in Phase 3.3, S31-5)")
        return
    if rung == "M0_star":
        if tuning is None or params is not None:
            raise ValueError("run_walkforward: an M0_star spec takes 'tuning' (Amendment 5 C1)")
        return
    if (params is None) == (tuning is None):
        raise ValueError(f"run_walkforward: a {rung} spec takes exactly one of 'params' and 'tuning' (S31-2)")
    if params is not None:
        key = PARAM_KEYS[rung]
        if not isinstance(params, Mapping) or set(params) != {key}:
            raise ValueError(f"run_walkforward: {rung} params must be {{{key!r}: value}}")
        value = params[key]
        if isinstance(value, bool) or not any(value == g and type(value) is type(g) for g in grid(rung, cfg)):
            raise ValueError(f"run_walkforward: {key} = {value!r} is not, with the same type, a value of the "
                             f"pre-registered grid {grid(rung, cfg)} of {rung} (models.{rung}.{GRID_KEYS[rung]}); one "
                             "configuration has one spec, so one spec_hash (S31-12)")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _existing_rows(path: Path) -> int:
    """Number of data rows of an existing trial log (0 when missing or empty); checks its header."""
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with open(path, encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.reader(handle) if row]
    if rows and rows[0] != TRIAL_COLUMNS:
        raise ValueError(f"{path}: header {rows[0]} differs from {TRIAL_COLUMNS}")
    return max(len(rows) - 1, 0)


def logged_spec_hashes(path: Path = ROOT / "docs" / "trial_log.csv") -> set[str]:
    """The spec_hash values already in the trial log (empty when the file is missing or empty); checks its header."""
    path = Path(path)
    if _existing_rows(path) == 0:
        return set()
    with open(path, encoding="utf-8", newline="") as handle:
        return {row["spec_hash"] for row in csv.DictReader(handle) if row.get("spec_hash")}


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
