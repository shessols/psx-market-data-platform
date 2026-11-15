"""FAKE random price data, only for testing that the code runs.
Its results mean nothing. Use real PSX data (ingest/extract_psx.py) for decisions.
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
dates = pd.bdate_range("2025-01-01", "2026-11-13")
rows = []
for n in range(120):
    price = rng.uniform(5, 400)
    for d in dates:
        ret = rng.normal(0.0003, 0.022)
        if rng.random() < 0.01:                       # occasional crash day
            ret = rng.uniform(-0.10, -0.05)
        ret = max(ret, -0.10)                          # lower circuit
        o = price * (1 + rng.normal(0, 0.006))
        price = max(price * (1 + ret), 1)
        h = max(o, price) * (1 + abs(rng.normal(0, 0.008)))
        l = min(o, price) * (1 - abs(rng.normal(0, 0.008)))
        rows.append((f"FAKE{n:03d}", d.date(), o, h, l, price, int(rng.lognormal(12, 1))))

data = Path(__file__).resolve().parents[1] / "data"
data.mkdir(exist_ok=True)
out = data / "sample_psx_daily.csv"
pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close", "volume"]).round(2).to_csv(out, index=False)
sectors = ["Banks", "Cement", "Fertilizer", "Oil & Gas", "Technology", "Textile"]
pd.DataFrame({"symbol": [f"FAKE{n:03d}" for n in range(120)],
              "name": [f"Fake Company {n}" for n in range(120)],
              "sector": [sectors[n % len(sectors)] for n in range(120)]}
             ).to_csv(data / "sample_psx_stocks.csv", index=False)
print(f"Wrote {len(rows):,} fake rows to {out} (+ sample_psx_stocks.csv)")
