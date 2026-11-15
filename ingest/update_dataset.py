"""Keep the public PSX dataset up to date in dataset/ (committed to GitHub).

    dataset/prices/2016-10.parquet ... 2026-11.parquet   raw daily OHLCV, one file per month
    dataset/stocks.csv                              symbol, name, sector
    dataset/latest.csv                              the most recent trading day
    dataset/metadata.json                           last update, rows, symbols, date range

    python ingest/update_dataset.py --full    # all history for every listed stock (first run)
    python ingest/update_dataset.py           # last 10 days, merged in (daily run)

Also writes data/psx_daily.csv (all years) for the rest of the pipeline.
Only the current month's file changes day to day, so the git repo stays small.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import psxdata

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "dataset"
PRICES = DS / "prices"
COLS = ["symbol", "date", "open", "high", "low", "close", "volume"]


def load_existing() -> pd.DataFrame:
    files = sorted(PRICES.glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=COLS)
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def universe() -> pd.DataFrame:
    s = psxdata.symbols()
    s = s[~s["is_etf"].astype(bool) & ~s["is_debt"].astype(bool)]
    s = s.assign(symbol=s["symbol"].str.upper()).rename(columns={"sector_name": "sector"})
    return s[["symbol", "name", "sector"]].drop_duplicates("symbol").sort_values("symbol")


def fetch(symbols: list[str], start: str | None) -> tuple[pd.DataFrame, list]:
    frames, failed = [], []
    for i, sym in enumerate(symbols, 1):
        for attempt in range(3):
            try:
                df = psxdata.stocks(sym, start=start, cache=False)
                if not df.empty:
                    df = df[~df["is_anomaly"].astype(bool)]
                    frames.append(df.assign(symbol=sym)[COLS])
                break
            except Exception as exc:  # retry, then record and move on
                if attempt == 2:
                    failed.append((sym, str(exc)[:80]))
                time.sleep(2 * (attempt + 1))
        if i % 50 == 0:
            print(f"  {i}/{len(symbols)} symbols")
        time.sleep(0.15)  # be polite to the PSX server
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)), failed


def main(full: bool) -> None:
    PRICES.mkdir(parents=True, exist_ok=True)
    stocks = universe()
    stocks.to_csv(DS / "stocks.csv", index=False)

    old = load_existing()
    start = None if full or old.empty else (date.today() - timedelta(days=10)).isoformat()
    print(f"{len(stocks)} stocks; fetching {'ALL history' if start is None else 'from ' + start}")
    new, failed = fetch(stocks["symbol"].tolist(), start)
    if new.empty:
        raise SystemExit("No data fetched. PSX may be down; try again later.")

    allp = pd.concat([old, new], ignore_index=True)
    allp["date"] = pd.to_datetime(allp["date"]).dt.normalize()
    allp = (allp.drop_duplicates(["symbol", "date"], keep="last")
                .sort_values(["symbol", "date"]).reset_index(drop=True))
    allp["volume"] = allp["volume"].fillna(0).astype("int64")

    month = allp["date"].dt.strftime("%Y-%m")
    changed = (sorted(pd.to_datetime(new["date"]).dt.strftime("%Y-%m").unique()) if not full
               else sorted(month.unique()))
    for mth in changed:
        allp[month == mth].to_parquet(PRICES / f"{mth}.parquet", index=False)

    last = allp["date"].max()
    allp[allp["date"] == last].to_csv(DS / "latest.csv", index=False)
    meta = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "first_date": str(allp["date"].min().date()), "last_date": str(last.date()),
        "rows": int(len(allp)), "symbols": int(allp["symbol"].nunique()),
        "failed_symbols": [s for s, _ in failed],
        "source": "PSX Data Portal (dps.psx.com.pk) via the psxdata library",
        "note": "Raw, unadjusted prices. Use ingest/adjust_prices.py for split/bonus adjustment.",
    }
    (DS / "metadata.json").write_text(json.dumps(meta, indent=2))

    (ROOT / "data").mkdir(exist_ok=True)
    allp.to_csv(ROOT / "data" / "psx_daily.csv", index=False)
    stocks.to_csv(ROOT / "data" / "psx_stocks.csv", index=False)
    print(f"Dataset: {meta['rows']:,} rows, {meta['symbols']} symbols, "
          f"{meta['first_date']} to {meta['last_date']}. Failed: {len(failed)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true", help="download all history (first run)")
    main(p.parse_args().full)
