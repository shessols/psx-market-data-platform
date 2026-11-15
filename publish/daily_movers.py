"""Make the daily "PSX Movers" post: a 1080x1350 chart image + WhatsApp text.

Ready to share on WhatsApp channels, Instagram or a YouTube Short.

    python publish/daily_movers.py
    python publish/daily_movers.py --data data/sample_psx_daily.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
S, C = CFG["strategy"], CFG["content"]

INK, MUTED, BG = "#16202B", "#5A6573", "#F7F5F0"
UP, DOWN, ACCENT = "#1B7F4B", "#C0392B", "#0F5C55"


def latest_movers(path: Path) -> tuple[pd.Timestamp, pd.DataFrame, pd.DataFrame, dict]:
    df = pd.read_csv(path, parse_dates=["date"]).sort_values(["symbol", "date"])
    df["pct"] = 100 * (df["close"] / df.groupby("symbol")["close"].shift(1) - 1)
    day = df["date"].max()
    today = df[(df["date"] == day) & df["pct"].notna()]
    breadth = {
        "up": int((today["pct"] > 0).sum()),
        "down": int((today["pct"] < 0).sum()),
        "flat": int((today["pct"] == 0).sum()),
    }
    liquid = today[(today["close"] >= S["min_price"]) & (today["volume"] >= S["min_volume"])]
    n = C["top_n"]
    return day, liquid.nlargest(n, "pct"), liquid.nsmallest(n, "pct"), breadth


def draw(day, gainers, losers, breadth, out: Path) -> None:
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=BG)
    fig.text(0.07, 0.94, "PSX Daily Movers", fontsize=40, weight="bold", color=INK)
    fig.text(0.07, 0.905, day.strftime("%A, %d %B %Y"), fontsize=20, color=MUTED)
    fig.text(0.07, 0.87,
             f"▲ {breadth['up']} up    ▼ {breadth['down']} down    ● {breadth['flat']} unchanged",
             fontsize=18, color=INK)

    for i, (title, data, color) in enumerate(
        [("Top gainers", gainers, UP), ("Top losers", losers, DOWN)]
    ):
        ax = fig.add_axes([0.21, 0.48 - i * 0.39, 0.72, 0.31], facecolor=BG)
        data = data.iloc[::-1]  # biggest move on top
        ax.barh(data["symbol"], data["pct"].abs(), color=color, height=0.62)
        for y, (_, r) in enumerate(data.iterrows()):
            ax.text(abs(r["pct"]) + 0.15, y, f"{r['pct']:+.2f}%   Rs {r['close']:,.2f}",
                    va="center", fontsize=17, color=INK)
        ax.text(-0.195, 1.04, title, transform=ax.transAxes, fontsize=24, weight="bold", color=color)
        ax.tick_params(axis="y", labelsize=19, colors=INK, length=0)
        ax.set_xticks([])
        ax.set_xlim(0, max(data["pct"].abs().max() * 1.75, 1))
        for side in ax.spines.values():
            side.set_visible(False)

    fig.text(0.07, 0.03, f"{C['brand']}  ·  Data: PSX  ·  Not investment advice",
             fontsize=15, color=MUTED)
    fig.text(0.07, 0.055, f"Liquid stocks only: price ≥ Rs {S['min_price']}, "
             f"volume ≥ {S['min_volume']:,}", fontsize=13, color=MUTED)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)


def whatsapp_text(day, gainers, losers, breadth) -> str:
    def lines(df):
        return "\n".join(f"{r.symbol}  {r.pct:+.2f}%  (Rs {r.close:,.2f})"
                         for r in df.itertuples())
    return (
        f"*PSX Daily Movers: {day:%d %b %Y}*\n"
        f"▲ {breadth['up']} up | ▼ {breadth['down']} down | ● {breadth['flat']} flat\n\n"
        f"*Top gainers*\n{lines(gainers)}\n\n"
        f"*Top losers*\n{lines(losers)}\n\n"
        f"_{C['brand']} · Not investment advice_"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=CFG["data"]["combined_file"])
    a = p.parse_args()
    day, gainers, losers, breadth = latest_movers(ROOT / a.data)
    out_dir = ROOT / C["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    img = out_dir / f"psx_movers_{day:%Y-%m-%d}.png"
    draw(day, gainers, losers, breadth, img)
    txt = whatsapp_text(day, gainers, losers, breadth)
    (out_dir / f"psx_movers_{day:%Y-%m-%d}.txt").write_text(txt, encoding="utf-8")
    print(txt)
    print(f"\nImage: {img}")


if __name__ == "__main__":
    main()
