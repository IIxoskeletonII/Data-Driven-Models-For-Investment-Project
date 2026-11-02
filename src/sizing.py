"""Discrete signals from scores and the sizing of protocol section 09: top/bottom 2, dollar-neutral core, IVV hedge
capped at 50% of core gross, whole book scaled to 100% gross.

Not implemented yet: Phase 2.1 (Mattia). Interfaces: docs/interfaces.md, contracts 8 to 11.
"""

import pandas as pd

from src.contracts import SizingResult


def signals_from_scores(scores: pd.DataFrame, top_k: int, bottom_k: int) -> pd.DataFrame:
    """Sector signals from model scores (§09 steps 1 to 3 and 5, contract 9).

    scores: weekly index × sectors, float64, known after Friday close t (contract 8). Each week the sectors are sorted by
    score, descending, exact ties broken alphabetically by ticker (the earlier ticker ranks higher); ranks 1..top_k get
    +1, the bottom_k lowest ranks get −1, the rest 0. A week with a missing score keeps the previous week's signals and
    the event is logged (§09 step 5). Returns an int8 frame on the same weekly index, columns = sectors, with exactly
    top_k values of +1 and bottom_k values of −1 per row. top_k and bottom_k come from config.yaml (signal.*).
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def target_weights(sector_signals: pd.DataFrame, betas: pd.DataFrame, core_weight: float, cap: float,
                   dead_band: float) -> SizingResult:
    """Target weights with the beta hedge (§09, contract 11).

    sector_signals: int8 frame of signals_from_scores; betas: raw BETA52 of the traded tickers (contract 10), both known
    after Friday close t. With β_c = Σ core_weight·s_i·β̂_i: h = clip(−β_c / β̂_IVV, −cap, cap), set to 0 if
    |h| < dead_band; w_i = core_weight·s_i / (1 + |h|), w_IVV = h / (1 + |h|), so Σ|w| = 1 (no leverage) and the
    weights are held from O(t+1) to O(t+2). Returns a SizingResult whose weights pass validate_weights.
    core_weight (0.25), cap (0.5) and dead_band (0.02) come from config.yaml (signal.*).
    """
    raise NotImplementedError("Phase 2.1, Mattia")
