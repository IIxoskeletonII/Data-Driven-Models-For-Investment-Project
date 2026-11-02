"""MCP server `ddmi-vault` (protocol section 08): the agents' only access to data, wrapping src.vault.Vault.

Sectors appear as anonymised codes A1 ... A9; the tools return summary metrics, never price series, and every request
after the In-Sample end is refused by the vault.

Not implemented yet: Phase 3.3 (Eliya). Interfaces: docs/interfaces.md, contract 15.
"""

from collections.abc import Mapping


def get_features(as_of: str) -> dict:
    """Anonymised asset features known after Friday close `as_of` (ISO date ≤ the In-Sample end), via Vault.features."""
    raise NotImplementedError("Phase 3.3, Eliya")


def run_walkforward(spec: Mapping[str, object]) -> dict:
    """In-Sample walk-forward summary metrics of a feature or model spec, via Vault.run_walkforward; logs one trial."""
    raise NotImplementedError("Phase 3.3, Eliya")


def get_trial_history() -> list[dict]:
    """Every trial logged so far in docs/trial_log.csv (summary columns only)."""
    raise NotImplementedError("Phase 3.3, Eliya")
