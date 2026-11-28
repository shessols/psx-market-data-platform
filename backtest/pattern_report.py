"""Pattern hunt on PSX data: where is there an edge, and does it survive realism checks?

Tests (all monthly, equal-weight, liquid stocks only):
  1. Decile study: forward 1-month return by rank of the past 1-month return.
  2. Short-term reversal (buy last month's worst 10) vs market, year by year.
  3. Split-half check: same rule in 2018-2022 vs 2023-2026.
  4. Cost stress: extra slippage per side (small PSX stocks are expensive to trade).
  5. Stricter liquidity (daily traded value) so the picks are actually buyable.
  6. Calendar effects: day of week and month of year for the equal-weight market.

    python backtest/pattern_report.py --data data/psx_daily_adj.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
S, FEES = CFG["strategy"], CFG["fees"]
FEE = (FEES["commission_pct"] + FEES["other_charges_pct"]) / 100
OUT = ROOT / "data" / "backtest"


def load(path: Path, min_value: float):
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["close"] >= S["min_price"]]
    px = df.pivot(index="date", columns="symbol", values="close").sort_index()
    vol = df.pivot(index="date", columns="symbol", values="volume").sort_index()
    val = (px * vol).rolling(60, min_periods=20).median()
    m = px.resample("ME").last()
    liquid = (vol.rolling(60, min_periods=20).median().resample("ME").last() >= S["min_volume"]) & (
        val.resample("ME").last() >= min_value)
    return px, m, liquid


def deciles(m, liquid):
    rows = []
    for i in range(2, len(m) - 1):
        past = m.iloc[i] / m.iloc[i - 1] - 1
        fwd = m.iloc[i + 1] / m.iloc[i] - 1
        ok = liquid.iloc[i].reindex(past.index).fillna(False) & past.notna() & fwd.notna()
        if ok.sum() < 50:
            continue
        d = pd.qcut(past[ok].rank(method="first"), 10, labels=False)
        rows.append(fwd[ok].groupby(d).mean())
    return pd.DataFrame(rows)


def reversal(m, liquid, n=10, extra_cost=0.0):
    rets, prev, mk = {}, set(), {}
    for i in range(2, len(m) - 1):
        past = m.iloc[i] / m.iloc[i - 1] - 1
        ok = liquid.iloc[i].reindex(past.index).fillna(False) & past.notna() & m.iloc[i + 1].notna()
        if ok.sum() < 30:
            continue
        sel = list(past[ok].nsmallest(n).index)
        fwd = m.iloc[i + 1] / m.iloc[i] - 1
        turn = len(set(sel) - prev) / n
        rets[m.index[i + 1]] = fwd[sel].mean() - 2 * (FEE + extra_cost) * turn
        mk[m.index[i + 1]] = fwd[ok].mean()
        prev = set(sel)
    return pd.Series(rets), pd.Series(mk)


def summ(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    yrs = max((r.index[-1] - r.index[0]).days / 365.25, 0.1)
    return {"per_year_%": round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1),
            "worst_drop_%": round(100 * (eq / eq.cummax() - 1).min(), 1),
            "months_beating_market_%": None}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/psx_daily_adj.csv")
    a = p.parse_args()
    res: dict = {}

    px, m, liquid = load(ROOT / a.data, min_value=0)
    dec = deciles(m, liquid)
    res["decile_fwd_1m_%"] = (100 * dec.mean()).round(2).to_dict()
    res["decile_months_positive_vs_all_%"] = None

    r, mk = reversal(m, liquid)
    res["reversal_all"] = summ(r) | {"market_per_year_%": summ(mk)["per_year_%"],
                                      "months_beating_market_%": round(100 * (r > mk).mean())}
    by_year = pd.DataFrame({"reversal_%": 100 * r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1),
                            "market_%": 100 * mk.groupby(mk.index.year).apply(lambda x: (1 + x).prod() - 1)}).round(1)
    res["by_year"] = by_year.to_dict("index")

    half = pd.Timestamp("2023-01-01")
    res["split_half"] = {
        "2018-2022": summ(r[r.index < half]) | {"market_%": summ(mk[mk.index < half])["per_year_%"]},
        "2023-2026": summ(r[r.index >= half]) | {"market_%": summ(mk[mk.index >= half])["per_year_%"]}}

    res["cost_stress"] = {f"+{int(c * 1e4)}bp_per_side": summ(reversal(m, liquid, extra_cost=c)[0])["per_year_%"]
                          for c in (0.0, 0.005, 0.01, 0.02)}

    strict = {}
    for mv in (5e6, 2e7):
        _, m2, l2 = load(ROOT / a.data, min_value=mv)
        r2, mk2 = reversal(m2, l2)
        strict[f"daily_value>=Rs{int(mv/1e6)}m"] = summ(r2) | {"market_%": summ(mk2)["per_year_%"]}
    res["stricter_liquidity"] = strict

    dr = px.pct_change(fill_method=None).where(lambda x: x.abs() < 0.11)
    mkt = dr.mean(axis=1).dropna()
    res["day_of_week_avg_%"] = (100 * mkt.groupby(mkt.index.dayofweek).mean()).round(3).rename(
        dict(enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]))).to_dict()
    mm = (1 + mkt).groupby([mkt.index.year, mkt.index.month]).prod() - 1
    res["month_of_year_avg_%"] = (100 * mm.groupby(level=1).mean()).round(2).to_dict()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pattern_report.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
