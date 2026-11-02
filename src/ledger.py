"""Independent position-and-cash ledger (shares, raw opens, dividend cash flows, splits) used to verify the vectorised
engine within 1e-6 per week on three In-Sample years (protocol section 09).

Not implemented yet: Phase 2.1 (Mattia).
"""

import pandas as pd


def run_ledger(weights: pd.DataFrame, raw: dict[str, pd.DataFrame], initial_capital: float = 1.0) -> pd.Series:
    """Weekly gross returns of a book replayed with shares and cash, without costs (§09 ledger reconciliation).

    weights: target weights of week t (weekly index × traded tickers), decided after Friday close t. raw: per-ticker
    daily frames in Yahoo auto_adjust=False format (actual opens reconstructed from the split-adjusted ones with
    Stock Splits; dividends paid in cash on ex-dates, short positions pay them). The book is rebalanced to the weights at
    the first session open of week t+1 and valued at the first session open of week t+2. Returns a float64 Series named
    `gross` on the weights' index (simple weekly returns, decimals) that must match the vectorised engine's gross
    returns within 1e-6 per week.
    """
    raise NotImplementedError("Phase 2.1, Mattia")
