"""Monthly stock-picking research on PSX: momentum vs buying losers vs the market.

Each month: rank liquid stocks by past return, buy N equally, hold one month.
  momentum   = best performers over the last 12 months, skipping the latest month
  losers_Xm  = worst performers over the last X months
  market     = every liquid stock, equal amounts
Fees are included (per side, on the part of the portfolio that changes).
Capital gains tax is NOT included here.

Also prints THIS MONTH's momentum buy list.

    python backtest/research_monthly.py --data data/psx_daily_adj.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
S, FEES = CFG["strategy"], CFG["fees"]
FEE = (FEES["commission_pct"] + FEES["other_charges_pct"]) / 100
OUT = ROOT / "data" / "backtest"

STRATEGIES = {                       # name: (top N, lookback months, skip months, pick)
    "Momentum: best 10 (12m, skip 1)": (10, 12, 1, "best"),
    "Momentum: best 5 (12m, skip 1)": (5, 12, 1, "best"),
    "Losers: worst 10 (last 1m)": (10, 1, 0, "worst"),
    "Losers: worst 10 (last 6m)": (10, 6, 0, "worst"),
    "Losers: worst 10 (last 12m)": (10, 12, 0, "worst"),
    "Market: all liquid stocks": (0, 12, 0, "all"),
}


def monthly(df: pd.DataFrame):
    df = df[df["close"] >= S["min_price"]]
    px = df.pivot(index="date", columns="symbol", values="close").sort_index()
    vol = df.pivot(index="date", columns="symbol", values="volume").sort_index()
    m = px.resample("ME").last()
    liquid = vol.rolling(60, min_periods=20).median().resample("ME").last() >= S["min_volume"]
    return m, liquid


def ranked(m, liquid, i, look, skip, need_next=True):
    past = m.iloc[i - skip] / m.iloc[i - skip - look] - 1
    ok = liquid.iloc[i].reindex(past.index).fillna(False) & m.iloc[i].notna() & past.notna()
    if need_next:
        ok &= m.iloc[i + 1].notna()
    return past[ok]


def run(m, liquid, n, look, skip, pick, first_i):
    rets, prev = {}, set()
    for i in range(first_i, len(m) - 1):
        p = ranked(m, liquid, i, look, skip)
        sel = (list(p.nlargest(n).index) if pick == "best" else
               list(p.nsmallest(n).index) if pick == "worst" else list(p.index))
        if not sel:
            continue
        r = (m.iloc[i + 1][sel] / m.iloc[i][sel] - 1).mean()
        turnover = len(set(sel) - prev) / len(sel)
        rets[m.index[i + 1]] = r - 2 * FEE * turnover
        prev = set(sel)
    return pd.Series(rets)


def stats(r: pd.Series, start) -> dict:
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - start).days / 365.25
    yearly = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return {"per_year_%": round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1),
            "rs_1_lakh_became": round(100000 * eq.iloc[-1]),
            "worst_drop_%": round(100 * (eq / eq.cummax() - 1).min(), 1),
            "best_year_%": round(100 * yearly.max()), "worst_year_%": round(100 * yearly.min()),
            "yearly": {int(y): round(100 * v, 1) for y, v in yearly.items()}}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/psx_daily_adj.csv")
    p.add_argument("--stocks", default=CFG["data"]["stocks_file"])
    a = p.parse_args()
    df = pd.read_csv(ROOT / a.data, parse_dates=["date"])
    m, liquid = monthly(df)
    first_i = 13                      # same start for every strategy (needs 13 months history)
    if len(m) < first_i + 3:
        raise SystemExit("Need at least ~16 months of data.")
    start = m.index[first_i]

    rows, yearly = [], {}
    for name, args in STRATEGIES.items():
        st = stats(run(m, liquid, *args, first_i), start)
        yearly[name] = st.pop("yearly")
        rows.append({"strategy": name, **st})
    table = pd.DataFrame(rows)

    # this month's momentum list: rank at the latest month-end, no next month needed
    sectors = {}
    sp = ROOT / a.stocks
    if sp.exists():
        s = pd.read_csv(sp)
        sectors = dict(zip(s["symbol"], s["sector"]))
    last = len(m) - 1
    mom = ranked(m, liquid, last, 12, 1, need_next=False).nlargest(10)
    picks = pd.DataFrame({"symbol": mom.index, "return_12m_skip1_%": (100 * mom.values).round(1),
                          "last_close": m.iloc[last][mom.index].round(2).values,
                          "sector": [sectors.get(x, "") for x in mom.index]})

    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "monthly_strategies.csv", index=False)
    picks.to_csv(OUT / "momentum_picks.csv", index=False)
    (OUT / "monthly_strategies.json").write_text(json.dumps(
        {"from": str(start.date()), "to": str(df["date"].max().date()), "as_of": str(df["date"].max().date()),
         "table": rows, "yearly": yearly, "picks": picks.to_dict("records")}, indent=2))

    print(f"Monthly strategies, {start:%b %Y} to {df['date'].max():%d %b %Y} (fees in, tax not):\n")
    print(table.to_string(index=False))
    print(f"\nMomentum buy list (prices up to {df['date'].max():%d %b %Y}):")
    print(picks.to_string(index=False))


if __name__ == "__main__":
    main()
