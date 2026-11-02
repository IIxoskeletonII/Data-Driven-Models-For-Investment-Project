"""Discrete signals from scores and the sizing of protocol section 09: top/bottom 2, dollar-neutral core, IVV hedge
capped at 50% of core gross, whole book scaled to 100% gross.

Interfaces: docs/interfaces.md, contracts 8 to 11. Rules settled by Amendment 2 of docs/preregistration.md:
- C2 dead-band: the hedge is set to 0 (IVV signal 0) when the IVV weight |h| / (1 + |h|) is below signal.hedge_deadband;
- C3 missing input after the first valid week: last week's signals and target weights are carried forward (the engine
  rebalances back to them) and the event is logged; the book is flat (no row) before the first valid week;
- C4 sensitivity k = 1 or 3: core weight 0.5 / k per name (src.contracts.core_weight_for).
"""

import logging

import numpy as np
import pandas as pd

from src.config import load_config
from src.contracts import (
    SizingResult,
    core_weight_for,
    universe,
    validate_betas,
    validate_scores,
    validate_signals,
    validate_weights,
)

log = logging.getLogger(__name__)


def _missing_fields(index: pd.Index, missing: pd.DataFrame, mask: np.ndarray) -> str:
    """'week: field, field' for the weeks in mask, naming the True columns of `missing` (Amendment 2 C3 log)."""
    fridays = pd.DatetimeIndex(index.get_level_values("date_close"))
    flags = missing.to_numpy(bool)
    columns = np.asarray(missing.columns)
    return "; ".join(f"{fridays[i]:%Y-%m-%d}: {', '.join(columns[flags[i]])}" for i in np.flatnonzero(mask))


def _with_hedge_column(sector_signals: pd.DataFrame, hedge_signal: np.ndarray) -> pd.DataFrame:
    """Signals frame with the TRADED columns (sectors, then the hedge)."""
    u = universe()
    signals = sector_signals[list(u.sectors)].copy()
    signals[u.hedge] = hedge_signal
    return signals.astype(np.int8)


def signals_from_scores(scores: pd.DataFrame, top_k: int, bottom_k: int) -> pd.DataFrame:
    """Sector signals from model scores (§09 steps 1 to 3 and 5, contract 9).

    scores: weekly index × sectors, float64, known after Friday close t (contract 8). Each week the sectors are sorted by
    score, descending, exact ties broken alphabetically by ticker (the earlier ticker ranks higher); ranks 1..top_k get
    +1, the bottom_k lowest ranks get −1, the rest 0.

    Missing input (§09 step 5, Amendment 2 C3): a week with any missing score keeps the previous week's signals and the
    event is logged; weeks before the first week with every score are dropped (the book is flat there).

    Returns an int8 frame (columns = sectors, no hedge column: the IVV signal comes from target_weights) on the weekly
    index from the first complete week on, with exactly top_k values of +1 and bottom_k values of −1 per row; together
    with an IVV column it passes validate_signals. top_k and bottom_k come from config.yaml (signal.*, or
    signal.sensitivity_k for the sensitivity runs).
    """
    validate_scores(scores)
    sectors = list(universe().sectors)
    n = len(sectors)
    if top_k < 1 or bottom_k < 1 or top_k + bottom_k > n:
        raise ValueError(f"top_k ({top_k}) and bottom_k ({bottom_k}) must be >= 1 with top_k + bottom_k <= {n}")
    values = scores[sectors].to_numpy(dtype=np.float64)

    # rank[t, i] = number of sectors ahead of i: a higher score, or an equal score and an earlier ticker alphabetically
    alphabetical = np.argsort(np.argsort(np.array(sectors)))
    other, own = values[:, None, :], values[:, :, None]
    ahead = (other > own) | ((other == own) & (alphabetical[None, None, :] < alphabetical[None, :, None]))
    rank = ahead.sum(axis=2)
    signal = np.where(rank < top_k, 1.0, np.where(rank >= n - bottom_k, -1.0, 0.0))

    missing = np.isnan(values).any(axis=1)
    signal[missing] = np.nan
    frame = pd.DataFrame(signal, index=scores.index, columns=sectors).ffill()
    leading = frame.isna().any(axis=1).to_numpy()
    carried = missing & ~leading
    if leading.any():
        log.info("signals: %d week(s) before the first week with every score are flat (no position)", int(leading.sum()))
    if carried.any():
        log.warning("signals: missing score, previous signals kept (§09 step 5, Amendment 2 C3), week ending: %s",
                    _missing_fields(scores.index, scores[sectors].isna().add_prefix("score "), carried))
    signals = frame.loc[~leading].astype(np.int8)
    validate_signals(_with_hedge_column(signals, np.zeros(len(signals))), top_k=top_k, bottom_k=bottom_k)
    return signals


def target_weights(sector_signals: pd.DataFrame, betas: pd.DataFrame, core_weight: float, cap: float,
                   dead_band: float, *, missing: pd.DataFrame | None = None) -> SizingResult:
    """Target weights with the beta hedge (§09, contract 11).

    sector_signals: int8 frame of signals_from_scores (an IVV column, if present, is ignored); betas: raw BETA52 of the
    traded tickers (contract 10), both known after Friday close t. With β_c = Σ core_weight·s_i·β̂_i:
    h = clip(−β_c / β̂_IVV, −cap, cap), set to 0 when the IVV weight |h| / (1 + |h|) < dead_band (Amendment 2 C2);
    w_i = core_weight·s_i / (1 + |h|), w_IVV = h / (1 + |h|), so Σ|w| = 1 (no leverage) and the weights are held from
    O(t+1) to O(t+2). Residual beta (β_c + h·β̂_IVV) / (1 + |h|) is non-zero only when the cap binds or the dead-band
    zeroes the hedge; net exposure is h / (1 + |h|); cap_binds is |β_c / β̂_IVV| > cap.

    Missing input (§09 step 5, Amendment 2 C3): a week with any missing sector score or any missing BETA52 (the 9 sectors
    and IVV, whether held that week or not; a zero IVV beta also counts, since h is undefined) carries last week's
    signals and target weights, and the event is logged with the week and the missing fields; weeks before the first
    valid week are dropped (flat). `missing` is a boolean frame on the weekly index whose True cells are missing upstream
    inputs, named by their column (size_book passes the scores as "score XLB", ...); absent weeks count as not missing.

    core_weight (0.25, or 0.5 / k in the sensitivity runs), cap (0.5) and dead_band (0.02) come from config.yaml
    (signal.*). Returns a SizingResult whose weights pass validate_weights.
    """
    validate_betas(betas)
    u = universe()
    sectors = list(u.sectors)
    signals = sector_signals[sectors]
    index = signals.index
    beta = betas.reindex(index)
    s = signals.to_numpy(dtype=np.float64)
    b = beta[sectors].to_numpy(dtype=np.float64)
    b_hedge = beta[u.hedge].to_numpy(dtype=np.float64)

    upstream = (pd.DataFrame(index=index) if missing is None
                else missing.reindex(index, fill_value=False).astype(bool))
    beta_missing = ~np.isfinite(beta[sectors + [u.hedge]]).add_prefix("BETA52 ")
    beta_missing[f"BETA52 {u.hedge}"] |= b_hedge == 0
    absent = pd.concat([upstream, beta_missing], axis=1)
    valid = ~absent.to_numpy(bool).any(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        beta_core = (core_weight * s * np.where(s != 0, b, 0.0)).sum(axis=1)
        unclipped = -beta_core / b_hedge
    h = np.clip(unclipped, -cap, cap)
    cap_binds = np.abs(unclipped) > cap
    h = np.where(np.abs(h) / (1 + np.abs(h)) < dead_band, 0.0, h)
    scale = 1 + np.abs(h)

    weights = pd.DataFrame(core_weight * s / scale[:, None], index=index, columns=sectors)
    weights[u.hedge] = h / scale
    fields = {
        "hedge": h,
        "residual_beta": (beta_core + h * b_hedge) / scale,
        "net_exposure": h / scale,
        "cap_binds": cap_binds.astype(np.float64),
    }
    hedge_signal = np.sign(h)

    # Carry the last valid week into invalid weeks; drop the weeks before the first valid one
    weights = weights.where(np.broadcast_to(valid[:, None], weights.shape)).ffill()
    series = {name: pd.Series(values, index=index).where(valid).ffill() for name, values in fields.items()}
    hedge_signal = pd.Series(hedge_signal, index=index).where(valid).ffill()
    signals = signals.astype(np.float64).where(np.broadcast_to(valid[:, None], signals.shape)).ffill()
    leading = weights.isna().any(axis=1).to_numpy()
    carried = ~valid & ~leading
    if leading.any():
        log.info("sizing: %d week(s) before the first valid week are flat (no position)", int(leading.sum()))
    if carried.any():
        log.warning("sizing: missing input, previous signals and target weights kept (§09 step 5, Amendment 2 C3), "
                    "week ending: %s", _missing_fields(index, absent, carried))

    keep = ~leading
    index = index[keep]
    weights = weights.loc[keep].astype(np.float64)
    out_signals = _with_hedge_column(signals.loc[keep], hedge_signal.loc[keep].to_numpy())
    result = SizingResult(
        weights=weights,
        signals=out_signals,
        hedge=series["hedge"].loc[keep].rename("hedge").astype(np.float64),
        residual_beta=series["residual_beta"].loc[keep].rename("residual_beta").astype(np.float64),
        net_exposure=series["net_exposure"].loc[keep].rename("net_exposure").astype(np.float64),
        cap_binds=series["cap_binds"].loc[keep].astype(bool).rename("cap_binds"),
    )
    if len(index):
        long_count = int((out_signals[sectors].to_numpy()[0] == 1).sum())
        short_count = int((out_signals[sectors].to_numpy()[0] == -1).sum())
        validate_signals(out_signals, top_k=long_count, bottom_k=short_count)
    validate_weights(weights, out_signals, core_weight=core_weight, cap=cap)
    return result


def size_book(scores: pd.DataFrame, betas: pd.DataFrame, cfg: dict | None = None, k: int | None = None) -> SizingResult:
    """Signals and hedged target weights of the week-t scores, with every setting from config.yaml (§09).

    k = None uses signal.top_k / signal.bottom_k (2 / 2); k = 1 or 3 is a sensitivity run (signal.sensitivity_k) with
    k longs, k shorts and core weight 0.5 / k (Amendment 2 C4). A week with any missing score keeps last week's signals
    and target weights (Amendment 2 C3).
    """
    cfg = cfg or load_config()
    signal = cfg["signal"]
    if k is not None and k != signal["top_k"] and k not in signal["sensitivity_k"]:
        raise ValueError(f"k = {k} is neither signal.top_k nor one of signal.sensitivity_k {signal['sensitivity_k']}")
    if signal["top_k"] != signal["bottom_k"]:
        raise ValueError("signal.top_k and signal.bottom_k must be equal for a dollar-neutral core")
    top_k = signal["top_k"] if k is None else k
    sector_signals = signals_from_scores(scores, top_k, top_k)
    return target_weights(sector_signals, betas, core_weight_for(k, cfg), signal["hedge_cap"], signal["hedge_deadband"],
                          missing=scores[list(universe().sectors)].isna().add_prefix("score "))
