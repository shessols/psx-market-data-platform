# Power BI dashboard: build guide

## 1. Get the data in
- **With Snowflake:** Get Data → Snowflake → your account → database `PSX`, schema `MART`. Pick the tables below. Use **Import** mode.
- **Without Snowflake:** run `dbt build --target local`, then `python powerbi/export_for_powerbi.py`, and load the CSVs from `data/powerbi/`.

Tables: `dim_stock`, `fct_daily_prices`, `mart_daily_movers`, `mart_sector_daily`, `mart_market_breadth`, `mart_mover_forward_returns`, `mart_strategy_summary`, plus the backtest files `backtest_trades`, `backtest_results`, `backtest_rolling_windows`, `backtest_pnl_curves`.

## 2. Model (star schema)
- Create the `Dates` table from `measures.dax`. Mark it as date table.
- `dim_stock[symbol]` 1 → * `fct_daily_prices[symbol]`, `mart_daily_movers[symbol]`, `backtest_trades[symbol]`
- `Dates[Date]` 1 → * `fct_daily_prices[trade_date]`, `mart_market_breadth[trade_date]`, `mart_sector_daily[trade_date]`
- Paste the measures from `measures.dax`.

## 3. Pages
1. **Market overview.** KPI cards (Stocks Traded, Value Traded, Advancers, Decliners, Breadth Ratio). Line chart of `mart_market_breadth` advancers vs decliners. Date slicer.
2. **Daily movers.** Two tables from `mart_daily_movers` (filter `loser_rank <= 5` and `gainer_rank <= 5`), single-date slicer, conditional formatting on % change.
3. **Sectors.** Matrix: sector × month with Avg % Change, red–green colour scale (a heatmap). Bar chart of value traded by sector.
4. **Stock detail.** Symbol slicer. Line chart of close + `sma_20`, columns for volume, card for Latest Close and Return % (period).
5. **Strategy lab: loser vs gainer.** Slicer on `mode` (hold / rules). Cards: Money Put In, Final Value, Strategy Return %, Win Rate, Fees + Tax. Line chart of `backtest_pnl_curves` (loser, gainer, both, random). Clustered bar of Strategy Return % with `side` on the axis; remove `side` to see both merged. Rolling-windows line from `backtest_rolling_windows`. From `mart_mover_forward_returns`: Bounce Rate 5d and forward returns by `side` and sector.

## 4. Publish
Save as `PSX_Market_Dashboard.pbix`. Add a screenshot of each page to `docs/` for the GitHub README, so recruiters see it without opening Power BI.
