"""Asset-level features (MOM26_1, MOM52_4, REV1, VOL13, DD13, BETA52) and market states (BEAR24, MKT_VAR,
VIX_Z, TERM, CREDIT) of protocol section 06, using only data known at the Friday close.

Not implemented yet: Phase 2.2 (Eliya). Interfaces: docs/interfaces.md, contracts 1, 3, 4 and 10.
"""

from collections.abc import Sequence

import pandas as pd


def lag_one_session(series: pd.Series, sessions: pd.DatetimeIndex) -> pd.Series:
    """Market series known at each session (Amendment 1, contract 1).

    The value at session s is the last observation dated on or before the session before s; a Monday after a holiday
    uses the value of the session before the holiday. Missing observations are skipped. Returns a float64 Series on
    `sessions` with the input's name (NaN before the first observation).
    """
    raise NotImplementedError("Phase 2.2, Eliya")


def asset_features(daily_close: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """The six asset features of §06 (contract 3), cross-sectionally z-scored across the 9 sectors each Friday.

    daily_close: adjusted daily closes (total-return index, contract 1) of the sectors and SPY. Windows end at the last
    session of week t, so row (date_close, ticker) is known after Friday close t. Returns index (date_close, ticker),
    columns features.asset, float64, NaN only while a window is not full; passes validate_features.
    """
    raise NotImplementedError("Phase 2.2, Eliya")


def momentum_variants(daily_close: pd.DataFrame, lookbacks: Sequence[int] | None = None) -> pd.DataFrame:
    """M0* momentum variants (§07 fallback, contract 3): MOM{L}_1 = ln TR(t − 1w) − ln TR(t − L w), z-scored.

    lookbacks default to models.M0_star.lookback_weeks (13, 26, 52). Known after Friday close t. Returns index
    (date_close, ticker), one column per lookback; passes validate_features(columns=...).
    """
    raise NotImplementedError("Phase 2.2, Eliya")


def market_states(daily_close: pd.DataFrame, vix: pd.Series, fred: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """The five unscaled market states of §06 (contract 4) on the weekly index.

    BEAR24 from SPY's 104-week total return, MKT_VAR from 126 daily SPY returns, VIX_Z = VIX level, TERM = DGS10 −
    DGS3MO, CREDIT = BAA10Y; VIX and FRED values lagged one session (Amendment 1), so row t is known after Friday close
    t. Scaling happens in the model pipeline on training rows only. Passes validate_market_states.
    """
    raise NotImplementedError("Phase 2.2, Eliya")


def sizing_betas(daily_close: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Raw (not z-scored) BETA52 of each traded ticker against SPY (§06, §09, contract 10) on the weekly index.

    Daily simple returns whose end session lies in weeks t−51 … t; known after Friday close t and used to size the
    positions taken at O(t+1). NaN in the warm-up only. Passes validate_betas.
    """
    raise NotImplementedError("Phase 2.2, Eliya")
