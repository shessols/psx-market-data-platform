"""Pull daily OHLCV prices for every listed PSX stock.

Uses the free `psxdata` library, which reads the public PSX data portal
(dps.psx.com.pk). Run it after market close.

    python ingest/extract_psx.py              # full history from config start_date
    python ingest/extract_psx.py --days 5     # just the last few days (daily run)
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import psxdata
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())


def stock_universe() -> list[str]:
    """All listed symbols, minus ETFs and debt instruments if configured.
    Also saves the symbol -> name/sector list for the dim_stock table."""
    syms = psxdata.symbols()
    if CFG["data"]["skip_etfs"]:
        syms = syms[~syms["is_etf"].astype(bool)]
    if CFG["data"]["skip_debt"]:
        syms = syms[~syms["is_debt"].astype(bool)]
    syms = syms.assign(symbol=syms["symbol"].str.upper())
    stocks_out = ROOT / CFG["data"]["stocks_file"]
    stocks_out.parent.mkdir(parents=True, exist_ok=True)
    syms.rename(columns={"sector_name": "sector"})[
        ["symbol", "name", "sector"]
    ].drop_duplicates("symbol").to_csv(stocks_out, index=False)
    return sorted(syms["symbol"].unique())


def fetch_symbol(symbol: str, start: str) -> pd.DataFrame:
    df = psxdata.stocks(symbol, start=start)
    if df.empty:
        return df
    df = df[~df["is_anomaly"].astype(bool)].drop(columns=["is_anomaly"])
    df.insert(0, "symbol", symbol)
    return df


def main(days: int | None) -> None:
    start = (
        (date.today() - timedelta(days=days)).isoformat()
        if days
        else CFG["data"]["start_date"]
    )
    raw_dir = ROOT / CFG["data"]["raw_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    symbols = stock_universe()
    print(f"{len(symbols)} symbols, from {start}")
    frames, failed = [], []
    for i, sym in enumerate(symbols, 1):
        try:
            df = fetch_symbol(sym, start)
            if not df.empty:
                if not days:  # keep one raw file per symbol from the full pull
                    df.to_csv(raw_dir / f"{sym}.csv", index=False)
                frames.append(df)
        except Exception as exc:  # keep going, report at the end
            failed.append((sym, str(exc)[:80]))
        if i % 50 == 0:
            print(f"  {i}/{len(symbols)}")
        time.sleep(0.2)  # be polite to the PSX server

    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"]).dt.date
    out = ROOT / CFG["data"]["combined_file"]
    if days and out.exists():  # daily run: add new days to the full history
        old = pd.read_csv(out, parse_dates=["date"])
        old["date"] = old["date"].dt.date
        combined = (
            pd.concat([old, combined], ignore_index=True)
            .drop_duplicates(["symbol", "date"], keep="last")
            .sort_values(["symbol", "date"])
        )
    combined.to_csv(out, index=False)
    print(f"Saved {len(combined):,} rows to {out}")
    if failed:
        print(f"{len(failed)} symbols failed, e.g. {failed[:3]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=None, help="only fetch the last N days")
    main(p.parse_args().days)
