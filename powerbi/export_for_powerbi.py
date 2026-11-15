"""Export the dbt marts (local DuckDB) to CSV so Power BI can load them
without a Snowflake account. With Snowflake, connect Power BI directly instead.

    python powerbi/export_for_powerbi.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "powerbi"
TABLES = ["dim_stock", "fct_daily_prices", "mart_daily_movers",
          "mart_sector_daily", "mart_market_breadth", "mart_mover_forward_returns", "mart_strategy_summary"]

OUT.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "data" / "psx.duckdb"), read_only=True)
for t in TABLES:
    con.sql(f"COPY mart.{t} TO '{OUT / (t + '.csv')}' (HEADER)")
    print(f"exported {t}")
for name in ["trades", "results", "rolling_windows", "pnl_curves"]:
    f = ROOT / "data" / "backtest" / f"{name}.csv"
    if f.exists():
        (OUT / f"backtest_{name}.csv").write_bytes(f.read_bytes())
        print(f"copied backtest_{name}")
