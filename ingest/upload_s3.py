"""Upload prices to the S3 landing zone as Parquet, one folder per trading day.

    s3://<bucket>/<prefix>/prices/date=2026-11-13/prices.parquet
    s3://<bucket>/<prefix>/stocks/stocks.parquet

    python ingest/upload_s3.py            # last 7 days (daily run)
    python ingest/upload_s3.py --all      # full history (first run)

AWS credentials come from the usual places (aws configure, env vars or an
IAM role), never from this code.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import boto3
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
ST = CFG["storage"]


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def main(all_days: bool) -> None:
    s3 = boto3.client("s3", region_name=ST["aws_region"])
    bucket, prefix = ST["s3_bucket"], ST["s3_prefix"].strip("/")

    prices = pd.read_csv(ROOT / CFG["data"]["combined_file"], parse_dates=["date"])
    if not all_days:
        cutoff = prices["date"].max() - pd.Timedelta(days=7)
        prices = prices[prices["date"] > cutoff]

    for day, part in prices.groupby(prices["date"].dt.date):
        key = f"{prefix}/prices/date={day}/prices.parquet"
        part = part.assign(date=part["date"].dt.date)
        s3.put_object(Bucket=bucket, Key=key, Body=to_parquet_bytes(part))
    print(f"Uploaded {prices['date'].dt.date.nunique()} day(s) to s3://{bucket}/{prefix}/prices/")

    stocks_file = ROOT / CFG["data"]["stocks_file"]
    if stocks_file.exists():
        s3.put_object(Bucket=bucket, Key=f"{prefix}/stocks/stocks.parquet",
                      Body=to_parquet_bytes(pd.read_csv(stocks_file)))
        print("Uploaded stocks list")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="upload full history")
    main(p.parse_args().all)
