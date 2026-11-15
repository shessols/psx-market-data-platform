"""Back-adjust prices for splits, bonus shares and big dividends.

PSX caps a day's move at 10% of the previous close (or Rs 1 for cheap stocks).
A bigger jump can't be real trading, so it's a corporate action: we scale all
earlier prices by that day's ratio, so a 5-for-1 split no longer looks like
an 80% crash. Approximation: assumes no real price move on the action day.

    python ingest/adjust_prices.py data/psx_daily.csv data/psx_daily_adj.csv
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

LIMIT_PCT, LIMIT_RS, TOLERANCE = 0.10, 1.0, 0.005


def adjust(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    prev = df.groupby("symbol")["close"].shift(1)
    move = df["close"] - prev
    limit = np.maximum(prev * (LIMIT_PCT + TOLERANCE), LIMIT_RS + 0.01)
    action = prev.notna() & (move.abs() > limit)
    ratio = pd.Series(1.0, index=df.index)
    ratio[action] = (df.loc[action, "close"] / prev[action]).to_numpy()

    # factor for each row = product of ratios of all LATER action days in that symbol
    later = ratio.groupby(df["symbol"]).transform(lambda r: r[::-1].cumprod()[::-1].shift(-1).fillna(1.0))
    out = df.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = (out[c] * later).round(4)
    out["volume"] = (out["volume"] / later).round().astype("int64")
    events = df.loc[action, ["symbol", "date", "close"]].assign(
        prev_close=prev[action], ratio=ratio[action].round(4))
    return out, events


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    raw = pd.read_csv(src, parse_dates=["date"])
    if "is_anomaly" in raw:
        raw = raw[~raw["is_anomaly"].astype(bool)].drop(columns="is_anomaly")
    adj, ev = adjust(raw)
    adj.to_csv(dst, index=False)
    print(f"Adjusted {len(ev)} corporate-action days across {ev['symbol'].nunique()} stocks -> {dst}")
