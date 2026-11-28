# Pattern hunt: is there a tradable edge in PSX prices?

Data: 679 symbols, Nov 2016 to 27 Nov 2026, split/bonus adjusted. Equal-weight monthly
portfolios of liquid stocks, brokerage fees included, tax not. Reproduce with
`python backtest/pattern_report.py`.

## Result: no edge that survives realistic costs

| Test | Finding |
|---|---|
| Buy last month's 10 worst (reversal) | 12.9%/yr vs 10.9% market, but beats the market in only 42% of months |
| Split-half | 2018-2022: -4.4%/yr vs market -6.0%. 2023-2026: +45.8% vs +42.9%. The gain is one bull run |
| Extra slippage per side | +0.5% cuts it to 1.3%/yr; +1% makes it -9.3%/yr |
| Stricter liquidity (Rs 5m / Rs 20m daily value) | 6.2%/yr and -5.8%/yr, both below the market |
| Decile study (1-month forward return) | Worst and best deciles both beat the middle (about 2.0% vs 0.6-1.2%). A U-shape, not a clean rule |
| Day of week | Monday -0.17% average, Friday +0.22%. Too small to trade after fees |
| Month of year | Nov +6.9%, Feb -3.9%. Only 9 samples per month, so noise |

## Takeaway

The apparent reversal edge comes from illiquid small caps that are hard to buy and sell at
the modelled price. Treat any single-stock signal here as a research lead, not a trading rule.
Not investment advice.
