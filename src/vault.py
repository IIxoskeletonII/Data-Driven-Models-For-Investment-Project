"""The Out-of-Sample vault of protocol section 10: refuses any label or metric dated after the In-Sample end
until FROZEN.lock exists.

Not implemented yet: Phase 2.2 (Eliya); OOSAccessError is final. Interfaces: docs/interfaces.md, contract 15.
"""

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from src.config import ROOT


class OOSAccessError(PermissionError):
    """A request touched a date after the In-Sample end (2019-12-27) while the vault is sealed (§10)."""


class Vault:
    """The only path from data to models and agents (§10, contract 15).

    is_end: last In-Sample Friday (split.in_sample_end). Until lock_path (FROZEN.lock) exists, and even then except
    through the explicit unlock path of 08_run_oos.py, any request touching a later date raises OOSAccessError. Every
    call appends one JSON line (UTC time, method, as_of or spec hash, ok or refused) to log_path.
    """

    def __init__(self, is_end: pd.Timestamp, lock_path: Path = ROOT / "FROZEN.lock",
                 log_path: Path = ROOT / "outputs" / "vault_access_log.jsonl") -> None:
        self.is_end = pd.Timestamp(is_end)
        self.lock_path = Path(lock_path)
        self.log_path = Path(log_path)

    def features(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Asset features (contract 3) with date_close ≤ as_of, known after Friday close as_of."""
        raise NotImplementedError("Phase 2.2, Eliya")

    def market_states(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Market states (contract 4) with date_close ≤ as_of, known after Friday close as_of."""
        raise NotImplementedError("Phase 2.2, Eliya")

    def labels(self, as_of: pd.Timestamp) -> pd.DataFrame:
        """Labels (contract 6) with label_end ≤ as_of: only returns already realised at as_of."""
        raise NotImplementedError("Phase 2.2, Eliya")

    def run_walkforward(self, spec: Mapping[str, object]) -> pd.DataFrame:
        """Weekly scores (contract 8) of a model spec over the In-Sample walk-forward folds (contract 13); appends one row
        to docs/trial_log.csv.
        """
        raise NotImplementedError("Phase 2.2, Eliya")


def append_trial(row: Mapping[str, object], path: Path = ROOT / "docs" / "trial_log.csv") -> None:
    """Append one trial to the trial log (§10, §11): columns trial_id, timestamp, author, kind, rung, spec_hash,
    params_json, is_sharpe, is_mdd, notes (docs/data_dictionary.md). Every configuration evaluated on In-Sample data is
    one row; the count feeds the Deflated Sharpe Ratio.
    """
    raise NotImplementedError("Phase 2.2, Eliya")
