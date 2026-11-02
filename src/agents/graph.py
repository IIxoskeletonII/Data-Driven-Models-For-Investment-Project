"""Orchestrator graph of the research lab (protocol section 08): agents propose features through the vault server only,
never trade; at most agent_lab.max_candidates candidates and a hard budget of agent_lab.budget_usd, every trial logged
and cached for offline replay.

Not implemented yet: Phase 3.3 (Eliya).
"""


def build_graph(cfg: dict | None = None) -> object:
    """The lab's orchestrator graph (proposer, critic and leakage checker around the vault server tools)."""
    raise NotImplementedError("Phase 3.3, Eliya")


def run_lab(cfg: dict | None = None, replay: bool = False) -> list[dict]:
    """Run the lab (or replay it from the cache with replay=True) within the candidate and budget limits; returns the
    logged trials.
    """
    raise NotImplementedError("Phase 3.3, Eliya")
