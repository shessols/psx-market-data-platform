"""Unit tests for the backtest engine: picks, fees, exits, hold valuation."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backtest"))
import backtest as bt  # noqa: E402


def market(prices: dict) -> tuple[pd.DataFrame, bt.Market]:
    """prices: {symbol: [(open, high, low, close), ...]} — one row per day."""
    rows = []
    for sym, days in prices.items():
        for i, (o, h, l, c) in enumerate(days):
            rows.append({"symbol": sym, "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                         "open": o, "high": h, "low": l, "close": c, "volume": 1_000_000})
    path = Path(__file__).with_name("_tmp_prices.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    df = bt.load(path)
    path.unlink()
    return df, bt.Market(df)


@pytest.fixture(autouse=True)
def fixed_rules(monkeypatch):
    monkeypatch.setitem(bt.S, "amount_per_trade", 1000)
    monkeypatch.setitem(bt.S, "top_n", 1)
    monkeypatch.setitem(bt.S, "buy_at", "next_open")
    monkeypatch.setitem(bt.S, "min_price", 5)
    monkeypatch.setitem(bt.S, "min_volume", 100)
    monkeypatch.setitem(bt.S, "exit", {"take_profit_pct": 5, "stop_loss_pct": 10, "max_hold_days": 3})


# day 0 -> day 1: AAA falls 8% (loser), BBB rises 6% (gainer)
BASE = {
    "AAA": [(100, 100, 100, 100), (100, 100, 91, 92), (92, 93, 91, 92), (92, 97, 91, 96), (96, 97, 95, 96)],
    "BBB": [(50, 50, 50, 50), (50, 53, 50, 53), (53, 54, 52, 53), (53, 53, 47, 47), (47, 48, 46, 47)],
}


def first_day(df):
    return df["date"].min() + pd.Timedelta(days=1)


def test_picks_loser_and_gainer_separately():
    df, _ = market(BASE)
    d = first_day(df)
    assert df.loc[bt.picks(df, "loser", d, d), "symbol"].tolist() == ["AAA"]
    assert df.loc[bt.picks(df, "gainer", d, d), "symbol"].tolist() == ["BBB"]


def test_entry_is_next_open_and_whole_shares():
    df, mkt = market(BASE)
    d = first_day(df)
    e = bt.entries(mkt, bt.picks(df, "loser", d, d), "loser")
    assert e.loc[0, "entry"] == 92 and e.loc[0, "shares"] == 10  # 1000 // 92


def test_commission_uses_per_share_minimum_on_cheap_stocks():
    # 500 shares at Rs 2 = Rs 1000. 0.15% = Rs 1.5, but 500 x 0.03 = Rs 15 wins
    assert bt.side_cost(2.0, 500) == pytest.approx(15 + 1000 * bt.FEES["other_charges_pct"] / 100)


def test_rules_take_profit_for_loser():
    df, mkt = market(BASE)
    d = first_day(df)
    t = bt.simulate(mkt, bt.entries(mkt, bt.picks(df, "loser", d, d), "loser"), "rules", mkt.dates[-1])
    assert t.loc[0, "reason"] == "take_profit" and t.loc[0, "exit"] == pytest.approx(96.6)


def test_rules_stop_loss_for_gainer():
    df, mkt = market(BASE)
    d = first_day(df)
    t = bt.simulate(mkt, bt.entries(mkt, bt.picks(df, "gainer", d, d), "gainer"), "rules", mkt.dates[-1])
    assert t.loc[0, "reason"] == "stop_loss" and t.loc[0, "profit"] < 0 and t.loc[0, "tax"] == 0


def test_hold_values_at_last_close():
    df, mkt = market(BASE)
    d = first_day(df)
    t = bt.simulate(mkt, bt.entries(mkt, bt.picks(df, "loser", d, d), "loser"), "hold", mkt.dates[-1])
    assert t.loc[0, "reason"] == "held" and t.loc[0, "exit"] == 96 and t.loc[0, "tax"] > 0


def test_combined_is_sum_of_sides():
    df, mkt = market(BASE)
    d = first_day(df)
    lo = bt.simulate(mkt, bt.entries(mkt, bt.picks(df, "loser", d, d), "loser"), "hold", mkt.dates[-1])
    ga = bt.simulate(mkt, bt.entries(mkt, bt.picks(df, "gainer", d, d), "gainer"), "hold", mkt.dates[-1])
    both = bt.summarise(pd.concat([lo, ga]), "both", "hold")
    assert both["profit_Rs"] == round(lo["profit"].sum() + ga["profit"].sum())


def test_skip_when_price_above_amount():
    df, mkt = market({"BIG": [(2000, 2000, 2000, 2000), (2000, 2000, 1800, 1800), (1800, 1810, 1790, 1800)]})
    d = first_day(df)
    assert bt.entries(mkt, bt.picks(df, "loser", d, d), "loser").empty
