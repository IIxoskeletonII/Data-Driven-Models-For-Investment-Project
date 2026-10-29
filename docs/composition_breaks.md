# Composition breaks

> **Draft — owner: Simone, to review and finalise.** Facts observed in the archived data are marked *(data)*; facts about
> index and fund events are marked *(to verify)* against the issuer's and S&P Dow Jones Indices' notices before this
> draft is finalised and committed from the owner's account.

The universe is fixed (the nine original Select Sector SPDR ETFs), but the holdings behind two of them changed when GICS
was revised. Protocol section 04: composition breaks are logged here and analysed on In-Sample only. Both breaks below fall
inside the In-Sample period (through 27 Dec 2019).

## 2016: Real Estate becomes a GICS sector (XLF)

- *(to verify)* GICS moved equity REITs and real-estate management companies out of Financials into a new Real Estate
  sector in 2016. The Real Estate Select Sector SPDR (XLRE), launched in October 2015, is excluded from our universe for
  history length (protocol section 04).
- *(to verify)* XLF removed its real-estate holdings in September 2016 by distributing XLRE shares to XLF shareholders.
- *(data)* Yahoo books this event for XLF as a **split factor of 1.231 on 2016-09-19**, not as a dividend. A regular cash
  dividend of 0.092608 per share has its ex-date on 2016-09-16.
- *(data)* Because Yahoo treats the distribution as a split, its Close and Adj Close before 2016-09-19 are divided by 1.231:
  our adjusted series treats the distributed XLRE value as reinvested in XLF (a total-return convention). XLF's adjusted
  close-to-close return on 2016-09-19 is +0.64% (SPY +0.02%), and the largest absolute adjusted or Yahoo open/close
  return within two sessions of the event is 1.42%: no artificial drop of about 19% (`docs/qa_report.md`, corporate-action
  dates; `data/qa/corporate_action_windows.csv`).
- Effect on the strategy: before September 2016 XLF's returns include real estate; afterwards they do not. XLF's
  momentum, volatility and beta features span both compositions.

## 2018: Communication Services replaces Telecommunication Services (XLK, XLY)

- *(to verify)* GICS broadened Telecommunication Services into Communication Services in September 2018, moving large
  internet and media companies out of Information Technology and Consumer Discretionary. The Communication Services
  Select Sector SPDR (XLC), launched in June 2018, is excluded from our universe for history length (protocol section 04).
- *(to verify)* XLK and XLY sold the affected holdings at the index rebalance; there was no in-kind distribution.
- *(data)* No split factor, unusual distribution or adjustment step appears in 2018 for any ticker: the only Yahoo split
  factors in the snapshot are XLF on 2016-09-19 (1.231) and the 2:1 splits of XLB, XLE, XLK, XLU and XLY on 2025-12-05.
- Effect on the strategy: XLK and XLY change character in late 2018 (XLK loses part of its internet exposure, XLY its media
  exposure), inside the In-Sample period.

## In-Sample analysis (to do)

To be defined and run by the owner on In-Sample data only, e.g. whether the features of XLF, XLK and XLY behave differently
before and after each break.

## Sources (to complete)

- Select Sector SPDR Trust notices on the 2016 XLF distribution and the 2018 sector changes
- S&P Dow Jones Indices / MSCI, GICS structure changes of 2016 and 2018
