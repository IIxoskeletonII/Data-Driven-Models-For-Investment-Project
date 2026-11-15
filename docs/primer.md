# Primer

For readers without a finance background: the ideas behind the project, in plain words. Owner: Giuseppe (workstream D).

## Sector ETFs and momentum

The US stock market is split into sectors: technology, energy, financials, health care, utilities and so on. A **sector
ETF** is one fund that holds every large company in a sector, so buying one share of XLK is like buying a slice of the
whole US technology sector. We use the nine original Select Sector SPDR funds, which have traded since December 1998:
XLB (materials), XLE (energy), XLF (financials), XLI (industrials), XLK (technology), XLP (consumer staples), XLU
(utilities), XLV (health care) and XLY (consumer discretionary).

**Momentum** is the observation, documented in many markets, that assets that rose most over the past months tend to keep
outperforming for a while, because news spreads slowly and money rotates between industries gradually. Our simplest rule,
M0, is exactly that: each week, rank the sectors by their return over the past six months (skipping the most recent week,
which tends to reverse), and favour the leaders.

Every model in the project only changes how a sector's **score** is computed. The trading rule is always the same: buy the
two sectors with the highest scores (+1), short the two with the lowest (−1), and leave the other five alone (0).
**Shorting** means borrowing a fund's shares and selling them, so that we gain when its price falls; the lender charges a
fee (2% a year in our backtest).

## The information clock: Friday close, next open

A backtest is only honest if every decision uses information that was really available at the time. Our clock is fixed:

1. **Friday after the close:** compute every score from data up to Friday's closing prices. Market indicators (the VIX
   "fear index", interest rates, the credit spread) are used with a one-day delay, because they are published later.
2. **Monday at the open:** trade to the new positions. Each trade costs 0.10% of the amount traded.
3. **The following Monday at the open:** measure the week's return, then repeat.

So the return we score, from one Monday open to the next, starts after the decision is made. Using Friday's close to
trade at Friday's close, or using data published later, would be **look-ahead bias**: profits that could never have been
earned.

## Dollar-neutral and market-neutral

**Dollar-neutral** means the money in the long bets equals the money in the short bets: 25% in each of the two longs and
25% in each of the two shorts. If the whole market rises 10%, the longs and the shorts both tend to rise, and the gains
and losses largely cancel. What is left is the difference between the strong and the weak sectors, which is what the
strategy bets on.

The cancellation is not perfect, because sectors react to the market by different amounts. A sector's **beta** measures
this: a beta of 1.2 means it typically moves 1.2% when the market moves 1%. If the two longs have higher betas than the
two shorts, the book still leans with the market. We correct this with a **hedge**: a position in IVV, an S&P 500 fund,
sized to cancel the remaining beta (capped at half the core). A book whose return no longer depends on the market's
direction is **market-neutral**. Out-of-Sample, our book's beta to the market was −0.04 and its correlation −0.08, so the
hedge worked; the strategy simply had no edge left to earn.

## In-Sample, walk-forward and the single Out-of-Sample run

The biggest risk in strategy research is fooling yourself: trying many ideas on the same history until one looks good by
chance. We split the data in two and treated the second part as sealed.

- **In-Sample (2003 to 27 December 2019):** the data on which models are built and compared. Even here we never grade a
  model on data it was trained on. With **walk-forward validation**, a model is trained only on the past, used for the
  next few weeks, then retrained with the new data added, repeated every quarter. Our 12 test years (2008 to 2019) gave
  624 weekly results per model. A one-week gap between training and testing data (the **embargo**) prevents overlap.
- **The selection rule:** written down before any result. A model is traded only if it beats the simple momentum rule
  clearly: a Sharpe ratio (return per unit of risk) at least 0.15 higher, a worst loss no more than 2 points deeper, and
  at least 80% probability of a real improvement in a resampling test (90% in the second round). No model passed, so the
  fallback M0\* was traded.
- **The freeze:** before looking at the sealed data, we locked the code, settings and every model result in a file
  (`FROZEN.lock`), and all five members signed it.
- **Out-of-Sample (30 December 2019 to 16 October 2026):** the sealed data, opened once to measure the frozen system. A log
  file proves it was run exactly once. M0\* lost 3.9% a year, close to what the In-Sample results predicted: the losses
  came from trading costs, not from a model that had memorised the past.
