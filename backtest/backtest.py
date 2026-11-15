"""Backtest: put Rs 1,000 every trading day on the day's biggest % LOSER,
and separately on the day's biggest % GAINER. What happens over 365 days?

Two ways to exit (config.yaml -> strategy.exit_modes):
  hold  : keep every stock bought; value the whole pile today
  rules : sell each one on take profit / stop loss / max holding days

Results are kept separate per side (loser, gainer) and merged (loser + gainer),
and compared with buying a RANDOM liquid stock each day under the same rules.
Rolling 1-year windows over all history show how often each idea made money.
Fees, per-share minimum commission and capital gains tax are included.

    python backtest/backtest.py                    # last 365 days + full report
    python backtest/backtest.py --picks-only       # today's loser + gainer
    python backtest/backtest.py --data data/sample_psx_daily.csv --stocks data/sample_psx_stocks.csv
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
OUT = ROOT / "data" / "backtest"
LABEL = {"loser": "Biggest loser", "gainer": "Biggest gainer",
         "both": "Loser + gainer", "random": "Random pick"}


# ---------------------------------------------------------------- data
def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"]).sort_values(["symbol", "date"])
    df = df.reset_index(drop=True)
    df["prev_close"] = df.groupby("symbol")["close"].shift(1)
    df["pct_change"] = 100 * (df["close"] / df["prev_close"] - 1)
    df["eligible"] = (df["pct_change"].notna()
                      & (df["close"] >= S["min_price"])
                      & (df["volume"] >= S["min_volume"]))
    return df


def load_sectors(path: Path | None) -> dict:
    if path and path.exists():
        s = pd.read_csv(path)
        return dict(zip(s["symbol"].str.upper(), s["sector"].fillna("Unknown")))
    return {}


class Market:
    """Fast lookups: next-day rows per symbol, and close prices by date."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.dates = pd.DatetimeIndex(sorted(df["date"].unique()))
        self.rows = {s: g.reset_index(drop=True) for s, g in df.groupby("symbol", sort=False)}
        self.local = df.groupby("symbol").cumcount().to_numpy()  # row -> position in its symbol
        self.close = df.pivot(index="date", columns="symbol", values="close").ffill()

    def close_at(self, symbols: pd.Series, when: pd.Timestamp) -> np.ndarray:
        row = self.close.loc[:when].iloc[-1]
        return row.reindex(symbols).to_numpy()

    def trading_days_between(self, a: pd.Series, b: pd.Series) -> np.ndarray:
        return self.dates.searchsorted(b) - self.dates.searchsorted(a)


# ---------------------------------------------------------------- picks + entries
def picks(df: pd.DataFrame, side: str, start, end, seed: int = 0) -> pd.Index:
    e = df[df["eligible"] & (df["date"] >= start) & (df["date"] <= end)]
    n = S["top_n"]
    if side == "random":
        return e.groupby("date", group_keys=False).apply(
            lambda g: g.sample(min(len(g), n), random_state=seed)).index
    asc = side == "loser"
    return e.sort_values(["date", "pct_change"], ascending=[True, asc]).groupby("date").head(n).index


def entries(mkt: Market, idx: pd.Index, side: str) -> pd.DataFrame:
    out = []
    for gi in idx:
        sym = mkt.df.at[gi, "symbol"]
        rows, i = mkt.rows[sym], mkt.local[gi]
        if S["buy_at"] == "next_open":
            if i + 1 >= len(rows):
                continue
            ei, price = i + 1, rows.at[i + 1, "open"]
        else:
            ei, price = i, rows.at[i, "close"]
        if not price or price <= 0 or np.isnan(price):
            continue
        shares = int(S["amount_per_trade"] // price)
        if shares == 0:
            continue
        out.append({"side": side, "symbol": sym, "signal_date": rows.at[i, "date"],
                    "signal_pct": round(rows.at[i, "pct_change"], 2), "entry_date": rows.at[ei, "date"],
                    "entry_i": ei, "entry": float(price), "shares": shares})
    return pd.DataFrame(out)


# ---------------------------------------------------------------- exits
def exit_hold(mkt: Market, e: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    t = e.copy()
    t["exit_date"] = at
    t["exit"] = mkt.close_at(t["symbol"], at)
    t["reason"] = "held"
    t["hold_days"] = mkt.trading_days_between(t["entry_date"], pd.Series(at, index=t.index))
    return t


def exit_rules(mkt: Market, e: pd.DataFrame) -> pd.DataFrame:
    tp, sl, mh = (S["exit"]["take_profit_pct"] / 100, S["exit"]["stop_loss_pct"] / 100,
                  S["exit"]["max_hold_days"])
    res = []
    for r in e.itertuples():
        rows = mkt.rows[r.symbol]
        o, h, l, c = (rows[k].to_numpy() for k in ("open", "high", "low", "close"))
        ei, entry = r.entry_i, r.entry
        up, down = entry * (1 + tp), entry * (1 - sl)
        last = min(ei + mh, len(rows) - 1)
        first = ei if S["buy_at"] == "next_open" else ei + 1
        px, xi, why = None, last, "max_hold"
        for i in range(first, last + 1):
            if i > ei and o[i] <= down:
                px, xi, why = o[i], i, "stop_loss_gap"; break
            if l[i] <= down:                       # stop first if both hit (conservative)
                px, xi, why = down, i, "stop_loss"; break
            if i > ei and o[i] >= up:
                px, xi, why = o[i], i, "take_profit_gap"; break
            if h[i] >= up:
                px, xi, why = up, i, "take_profit"; break
        if px is None:
            px = c[last]
            if last == len(rows) - 1 and last < ei + mh:
                why = "still_open"
        res.append((rows.at[xi, "date"], float(px), why, xi - ei))
    t = e.copy()
    t[["exit_date", "exit", "reason", "hold_days"]] = pd.DataFrame(res, index=e.index)
    return t


def side_cost(price, shares):
    value = price * shares
    commission = np.maximum(value * FEES["commission_pct"] / 100,
                            shares * FEES["commission_per_share_min"])
    return commission + value * FEES["other_charges_pct"] / 100


def finalize(t: pd.DataFrame, mode: str) -> pd.DataFrame:
    t = t.copy()
    t["mode"] = mode
    t["invested"] = t["entry"] * t["shares"]
    t["fees"] = side_cost(t["entry"], t["shares"]) + side_cost(t["exit"], t["shares"])
    net = (t["exit"] - t["entry"]) * t["shares"] - t["fees"]
    t["tax"] = np.maximum(net, 0) * FEES["capital_gains_tax_pct"] / 100
    t["profit"] = net - t["tax"]
    t["return_pct"] = 100 * t["profit"] / t["invested"]
    t = t.drop(columns="entry_i")
    num = t.select_dtypes("number").columns
    t[num] = t[num].round(2)
    return t


def simulate(mkt: Market, e: pd.DataFrame, mode: str, at: pd.Timestamp) -> pd.DataFrame:
    if e.empty:
        return e
    return finalize(exit_hold(mkt, e, at) if mode == "hold" else exit_rules(mkt, e), mode)


# ---------------------------------------------------------------- summaries
def summarise(t: pd.DataFrame, name: str, mode: str) -> dict:
    if t.empty:
        return {"strategy": name, "mode": mode, "trades": 0}
    inv, prof = t["invested"].sum(), t["profit"].sum()
    return {
        "strategy": name, "mode": mode, "trades": len(t),
        "invested_Rs": round(inv), "final_value_Rs": round(inv + prof),
        "profit_Rs": round(prof), "return_%": round(100 * prof / inv, 2),
        "win_rate_%": round(100 * (t["profit"] > 0).mean(), 1),
        "fees_tax_Rs": round((t["fees"] + t["tax"]).sum()),
        "avg_hold_days": round(t["hold_days"].mean(), 1),
        "best_trade": f"{t.loc[t['return_pct'].idxmax(), 'symbol']} {t['return_pct'].max():+.1f}%",
        "worst_trade": f"{t.loc[t['return_pct'].idxmin(), 'symbol']} {t['return_pct'].min():+.1f}%",
    }


def pnl_curve(mkt: Market, t: pd.DataFrame, mode: str, start, end) -> pd.Series:
    """Profit-to-date per day. hold: paper value - money put in. rules: realised profit."""
    days = mkt.dates[(mkt.dates >= start) & (mkt.dates <= end)]
    if t.empty:
        return pd.Series(0.0, index=days)
    if mode == "rules":
        return t.groupby("exit_date")["profit"].sum().reindex(days, fill_value=0).cumsum()
    shares = (t.pivot_table(index="entry_date", columns="symbol", values="shares", aggfunc="sum")
              .reindex(days, fill_value=0).fillna(0).cumsum())
    value = (shares * mkt.close.reindex(index=days, columns=shares.columns)).sum(axis=1)
    put_in = t.groupby("entry_date")["invested"].sum().reindex(days, fill_value=0).cumsum()
    return value - put_in


def rolling_windows(mkt: Market, full: dict, mode: str) -> pd.DataFrame:
    """Every month-start in history: what if you ran the strategy for the next 365 days?"""
    first, last, span = mkt.dates[0], mkt.dates[-1], pd.Timedelta(days=S["window_days"])
    starts = [d for d in pd.date_range(first, last, freq="MS") if d + span <= last]
    rows = []
    for side, e in full.items():
        rules = simulate(mkt, e, "rules", last) if mode == "rules" else None
        for st in starts:
            en = st + span
            inside = e[(e["signal_date"] >= st) & (e["signal_date"] < en)]
            if inside.empty:
                continue
            if mode == "hold":
                t = simulate(mkt, inside, "hold", en)
            else:
                t = rules.loc[inside.index]
            inv, prof = t["invested"].sum(), t["profit"].sum()
            rows.append({"side": side, "mode": mode, "start": st.date(), "end": en.date(),
                         "trades": len(t), "invested_Rs": round(inv), "profit_Rs": round(prof),
                         "return_%": round(100 * prof / inv, 2)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- insights
def insights(results: pd.DataFrame, roll: pd.DataFrame, trades: pd.DataFrame,
             sectors: dict, window: tuple) -> list[str]:
    out = []
    r = results.set_index(["mode", "strategy"])
    for mode in S["exit_modes"]:
        if mode not in r.index.get_level_values(0):
            continue
        m = r.loc[mode]
        how = "kept every stock and valued it today" if mode == "hold" else \
              (f"sold at +{S['exit']['take_profit_pct']}%, −{S['exit']['stop_loss_pct']}% "
               f"or after {S['exit']['max_hold_days']} days")
        out.append(f"**{mode.upper()} ({how})**")
        for side in [s for s in S["sides"]] + ["both"]:
            if LABEL[side] not in m.index:
                continue
            x = m.loc[LABEL[side]]
            out.append(f"- {LABEL[side]}: put in Rs {x['invested_Rs']:,.0f} over {int(x['trades'])} trades → "
                       f"Rs {x['final_value_Rs']:,.0f} ({x['return_%']:+.2f}%), "
                       f"won {x['win_rate_%']:.0f}% of trades.")
        if {"Biggest loser", "Biggest gainer"} <= set(m.index):
            lo, ga = m.loc["Biggest loser", "return_%"], m.loc["Biggest gainer", "return_%"]
            better = "losers" if lo > ga else "gainers"
            out.append(f"- Buying {better} did better, by {abs(lo - ga):.2f} percentage points.")
        if LABEL["random"] in m.index:
            rnd = m.loc[LABEL["random"], "return_%"]
            for side in S["sides"]:
                if LABEL[side] in m.index:
                    gap = m.loc[LABEL[side], "return_%"] - rnd
                    verdict = ("beat random picks" if gap > 1 else
                               "did worse than random picks" if gap < -1 else
                               "was about the same as random picks: no real edge")
                    out.append(f"- {LABEL[side]} {verdict} ({gap:+.2f} pts vs random {rnd:+.2f}%).")
        if LABEL["both"] in m.index:
            b = m.loc[LABEL["both"]]
            share = 100 * b["fees_tax_Rs"] / max(b["invested_Rs"], 1)
            out.append(f"- Fees and tax took Rs {b['fees_tax_Rs']:,.0f} "
                       f"({share:.2f}% of everything put in).")
    if not roll.empty:
        out.append("**ROLLING 1-YEAR WINDOWS (all history)**")
        order = {s: i for i, s in enumerate(S["sides"])}
    for (side, mode), g in sorted(roll.groupby(["side", "mode"]), key=lambda kv: (kv[0][1] != S["exit_modes"][0], order.get(kv[0][0], 9))):
            pos = (g["profit_Rs"] > 0).mean() * 100
            out.append(f"- {LABEL[side]}, {mode}: profitable in {(g['profit_Rs'] > 0).sum()} of "
                       f"{len(g)} windows ({pos:.0f}%); median {g['return_%'].median():+.2f}%, "
                       f"best {g['return_%'].max():+.2f}%, worst {g['return_%'].min():+.2f}%.")
    if sectors and not trades.empty:
        out.append("**WHAT IT KEEPS BUYING (last 365 days)**")
        t = trades[trades["mode"] == S["exit_modes"][0]]
        for side in S["sides"]:
            ts = t[t["side"] == side]
            if ts.empty:
                continue
            sec = ts["symbol"].map(sectors).fillna("Unknown").value_counts()
            top = ts["symbol"].value_counts().head(3)
            out.append(f"- {LABEL[side]}: mostly {sec.index[0]} ({sec.iloc[0]} picks); "
                       f"most repeated stocks {', '.join(f'{s} ×{n}' for s, n in top.items())}.")
    n = results["trades"].max()
    if n < 200:
        out.append(f"- Caution: only {n} trading days in the test. Treat this as a first look.")
    out.append(f"_Window: {window[0]:%d %b %Y} to {window[1]:%d %b %Y}. Not financial advice._")
    return out


# ---------------------------------------------------------------- main
def todays_picks(df: pd.DataFrame) -> None:
    day = df["date"].max()
    print(f"Signals from {day:%d %b %Y} (buy at next open):")
    for side in S["sides"]:
        idx = picks(df, side, day, day)
        for r in df.loc[idx].itertuples():
            print(f"  {LABEL[side]:15s} {r.symbol:10s} {r.pct_change:+6.2f}%  Rs {r.close:,.2f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=CFG["data"]["combined_file"])
    p.add_argument("--stocks", default=CFG["data"]["stocks_file"])
    p.add_argument("--picks-only", action="store_true")
    p.add_argument("--no-report", action="store_true", help="skip the HTML report")
    a = p.parse_args()

    df = load(ROOT / a.data)
    if a.picks_only:
        return todays_picks(df)

    mkt, sectors = Market(df), load_sectors(ROOT / a.stocks)
    end = mkt.dates[-1]
    start = max(mkt.dates[0], end - pd.Timedelta(days=S["window_days"]))
    OUT.mkdir(parents=True, exist_ok=True)

    window_e = {s: entries(mkt, picks(df, s, start, end), s) for s in S["sides"]}
    full_e = {s: entries(mkt, picks(df, s, mkt.dates[0], end), s) for s in S["sides"]}
    rand_e = [entries(mkt, picks(df, "random", start, end, seed), "random")
              for seed in range(S["random_runs"])]

    results, all_trades, curves, rolls = [], [], {}, []
    for mode in S["exit_modes"]:
        per_side = {s: simulate(mkt, e, mode, end) for s, e in window_e.items()}
        for s, t in per_side.items():
            results.append(summarise(t, LABEL[s], mode))
            curves[(s, mode)] = pnl_curve(mkt, t, mode, start, end)
            all_trades.append(t)
        both = pd.concat(per_side.values(), ignore_index=True)
        results.append(summarise(both, LABEL["both"], mode))
        curves[("both", mode)] = pnl_curve(mkt, both, mode, start, end)

        rnd = [simulate(mkt, e, mode, end) for e in rand_e]
        rs = pd.DataFrame([summarise(t, LABEL["random"], mode) for t in rnd])
        avg = rs.mean(numeric_only=True).round(2).to_dict()
        results.append({"strategy": LABEL["random"], "mode": mode, **avg,
                        "best_trade": f"avg of {len(rnd)} runs", "worst_trade": ""})
        curves[("random", mode)] = pd.concat(
            [pnl_curve(mkt, t, mode, start, end) for t in rnd], axis=1).mean(axis=1)
        rolls.append(rolling_windows(mkt, full_e, mode))

    results = pd.DataFrame(results)
    results["trades"] = results["trades"].round().astype(int)
    trades = pd.concat(all_trades, ignore_index=True)
    roll = pd.concat(rolls, ignore_index=True) if rolls else pd.DataFrame()
    notes = insights(results, roll, trades, sectors, (start, end))

    trades.to_csv(OUT / "trades.csv", index=False)          # one file, side + mode columns
    results.to_csv(OUT / "results.csv", index=False)
    roll.to_csv(OUT / "rolling_windows.csv", index=False)
    pd.DataFrame({f"{s}_{m}": c for (s, m), c in curves.items()}).to_csv(OUT / "pnl_curves.csv")
    (OUT / "insights.md").write_text("\n".join(notes), encoding="utf-8")

    print(f"Data {mkt.dates[0]:%d %b %Y} to {end:%d %b %Y}, {df['symbol'].nunique()} stocks. "
          f"Test window: last {S['window_days']} days.\n")
    cols = ["mode", "strategy", "trades", "invested_Rs", "final_value_Rs", "profit_Rs",
            "return_%", "win_rate_%", "fees_tax_Rs", "avg_hold_days"]
    print(results[cols].to_string(index=False))
    print("\n" + "\n".join(n.replace("**", "") for n in notes))

    if not a.no_report:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import report  # same folder
        path = report.build(results, curves, roll, trades, notes, sectors, (start, end))
        print(f"\nReport: {path}")
    print(f"Files: {OUT}")


if __name__ == "__main__":
    main()
