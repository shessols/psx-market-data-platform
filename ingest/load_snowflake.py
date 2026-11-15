"""Load prices and the stock list into Snowflake RAW (upsert on symbol + date).

storage.mode = local : pushes data/psx_daily.csv straight from pandas
storage.mode = s3    : COPY INTO from the S3 stage (Parquet), the production path

Credentials come from environment variables, never from code:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, SNOWFLAKE_WAREHOUSE
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import snowflake.connector
import yaml
from snowflake.connector.pandas_tools import write_pandas

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
SF = CFG["snowflake"]
MODE = CFG["storage"]["mode"]

MERGE_PRICES = """
MERGE INTO DAILY_PRICES t
USING (SELECT * FROM STG_PRICES QUALIFY ROW_NUMBER() OVER (PARTITION BY SYMBOL, DATE ORDER BY DATE) = 1) s
  ON t.SYMBOL = s.SYMBOL AND t.DATE = s.DATE
WHEN MATCHED THEN UPDATE SET
  OPEN = s.OPEN, HIGH = s.HIGH, LOW = s.LOW, CLOSE = s.CLOSE,
  VOLUME = s.VOLUME, LOADED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (SYMBOL, DATE, OPEN, HIGH, LOW, CLOSE, VOLUME)
  VALUES (s.SYMBOL, s.DATE, s.OPEN, s.HIGH, s.LOW, s.CLOSE, s.VOLUME)
"""

MERGE_STOCKS = """
MERGE INTO STOCKS t USING STG_STOCKS s ON t.SYMBOL = s.SYMBOL
WHEN MATCHED THEN UPDATE SET NAME = s.NAME, SECTOR = s.SECTOR, LOADED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (SYMBOL, NAME, SECTOR) VALUES (s.SYMBOL, s.NAME, s.SECTOR)
"""


def connect():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=SF["database"],
        schema=SF["schema_raw"],
    )


def stage_from_local(conn) -> None:
    df = pd.read_csv(ROOT / CFG["data"]["combined_file"], parse_dates=["date"])
    df.columns = [c.upper() for c in df.columns]
    df["DATE"] = df["DATE"].dt.date
    write_pandas(conn, df, "STG_PRICES", auto_create_table=False)
    stocks = ROOT / CFG["data"]["stocks_file"]
    if stocks.exists():
        s = pd.read_csv(stocks)
        s.columns = [c.upper() for c in s.columns]
        write_pandas(conn, s, "STG_STOCKS", auto_create_table=False)


def stage_from_s3(cur) -> None:
    # Loads every file into a fresh temp table; the MERGE makes re-runs safe.
    # A few hundred thousand rows is seconds of work for Snowflake.
    cur.execute("""
        COPY INTO STG_PRICES
        FROM @S3_LANDING/prices/
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        FILE_FORMAT = (FORMAT_NAME = PARQUET_FMT)
    """)
    cur.execute("""
        COPY INTO STG_STOCKS
        FROM @S3_LANDING/stocks/
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        FILE_FORMAT = (FORMAT_NAME = PARQUET_FMT)
    """)


def main() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TEMPORARY TABLE STG_PRICES LIKE DAILY_PRICES")
        cur.execute("CREATE TEMPORARY TABLE STG_STOCKS LIKE STOCKS")
        if MODE == "s3":
            stage_from_s3(cur)
        else:
            stage_from_local(conn)
        n = cur.execute(MERGE_PRICES).fetchone()
        cur.execute(MERGE_STOCKS)
        print(f"[{MODE}] merged prices (inserted, updated) = {n}")


if __name__ == "__main__":
    main()
