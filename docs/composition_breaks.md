# Composition breaks

The universe is fixed (the nine original Select Sector SPDR ETFs), but the holdings behind three of them changed when the
GICS sector classification was revised. Protocol section 04: composition breaks are logged here. Both breaks fall inside
the In-Sample period (through 27 Dec 2019). Facts observed in our archived data are marked *(data)*; facts about index and
fund events cite their source.

## 2016: Real Estate becomes a GICS sector (XLF)

- In September 2016 real estate companies and REITs left the Financials sector and became the eleventh GICS sector; the
  S&P indices rebalanced on 16 September 2016 ([etf.com](https://www.etf.com/sections/features-and-news/what-new-real-estate-sector-means-etfs)).
- The Real Estate Select Sector SPDR (XLRE) has an inception date of 7 October 2015 and listed on NYSE Arca on
  8 October 2015 ([SSGA](https://www.ssga.com/us/en/individual/etfs/funds/real-estate-select-sector-spdr-fund-xlre)). It is
  excluded from our universe for history length (protocol section 04).
- XLF removed its real estate holdings by distributing its XLRE shares to XLF shareholders in a one-time, in-kind payout of
  nearly a fifth of the fund's assets, rather than by selling them ([etf.com](https://www.etf.com/node/95901.md)).
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

- GICS expanded Telecommunication Services into Communication Services, adding companies from Information Technology
  (including Alphabet and Facebook) and the media industry group from Consumer Discretionary; the change took effect after
  the close of 28 September 2018 ([ETF Database](https://etfdb.com/news/2018/09/25/impact-of-biggest-gics-changes-on-etf-investors/)).
- The Communication Services Select Sector SPDR (XLC) launched on NYSE Arca in June 2018. XLK and XLY were rebalanced to
  the reconstituted sectors after the close of 21 September 2018, with no action required from existing shareholders
  ([ETF Strategy](https://www.etfstrategy.com/ssga-launches-communication-services-select-sector-spdr-etf-xlc-based-on-new-gics-communication-services-sector-47483/)).
  XLC is excluded from our universe for history length (protocol section 04).
- *(data)* No split factor, unusual distribution or adjustment step appears in 2018 for any ticker: the only Yahoo split
  factors in the snapshot are XLF on 2016-09-19 (1.231) and the 2:1 splits of XLB, XLE, XLK, XLU and XLY on 2025-12-05.
- Effect on the strategy: XLK and XLY change character in late 2018 (XLK loses part of its internet exposure, XLY its media
  exposure), inside the In-Sample period.

## Treatment and limitation

- No adjustment is made to the strategy: each ETF is traded as it was at each date, which is what an investor could have
  held. The features are computed from the ETFs' own adjusted prices, so they reflect the composition of the time.
- A separate before-and-after comparison of XLF's, XLK's and XLY's features around each break was not run. This is
  recorded as a limitation: both breaks are a small share of the 624 In-Sample test weeks, and the traded model (M0\*)
  uses only price momentum, which the breaks do not distort beyond the change in holdings itself.
