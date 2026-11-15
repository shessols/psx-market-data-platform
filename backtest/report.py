"""Builds data/backtest/report.html: one self-contained page with charts,
results tables and insights. Called by backtest.py."""
from __future__ import annotations

import base64
import html
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates
import matplotlib.pyplot as plt
import matplotlib.ticker
import pandas as pd
import yaml

AMOUNT = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())["strategy"]["amount_per_trade"]
OUT = Path(__file__).resolve().parents[1] / "data" / "backtest"
COLORS = {"loser": "#C0392B", "gainer": "#1B7F4B", "both": "#0F5C55", "random": "#8A94A0"}
LABEL = {"loser": "Biggest loser", "gainer": "Biggest gainer",
         "both": "Loser + gainer", "random": "Random pick (avg)"}
TITLE = {"hold": "Hold everything: paper profit vs money put in (before selling costs and tax)",
         "rules": "Sell by rules: realised profit"}


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    ax.axhline(0, color="#16202B", lw=0.8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"Rs {v:,.0f}"))


def curve_chart(curves: dict, mode: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.8))
    labels = []
    for side in ("loser", "gainer", "both", "random"):
        c = curves.get((side, mode))
        if c is None:
            continue
        ax.plot(c.index, c.values, color=COLORS[side], lw=2.2 if side != "random" else 1.6,
                ls="--" if side == "random" else "-", label=LABEL[side])
        labels.append((c.iloc[-1], side, c.index[-1]))
    # end labels, nudged apart so they never sit on top of each other
    labels.sort()
    span = (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.06
    last_y = None
    for y, side, x in labels:
        ty = y if last_y is None or y - last_y >= span else last_y + span
        ax.annotate(f"Rs {y:,.0f}", (x, y), xytext=(x + pd.Timedelta(days=5), ty), textcoords="data",
                    color=COLORS[side], fontsize=9, va="center", ha="left",
                    xycoords="data", annotation_clip=False)
        last_y = ty
    ax.set_title(TITLE[mode], loc="left", fontsize=12, weight="bold")
    _style(ax)
    ax.legend(frameon=False, fontsize=9, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %y"))
    return _png(fig)


def rolling_chart(roll: pd.DataFrame, mode: str) -> str | None:
    g = roll[roll["mode"] == mode]
    if g.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 3.2))
    for side, s in g.groupby("side"):
        ax.plot(pd.to_datetime(s["start"]), s["return_%"], marker="o", ms=3,
                color=COLORS[side], lw=2, label=LABEL[side])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.axhline(0, color="#16202B", lw=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.set_title(f"Every 1-year window in history ({mode}): return if you had started that month",
                 loc="left", fontsize=12, weight="bold")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %y"))
    ax.xaxis.set_major_locator(matplotlib.dates.AutoDateLocator(maxticks=8))
    ax.legend(frameon=False, fontsize=9, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    return _png(fig)


def _table(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = ""
    for _, r in df.iterrows():
        cells = ""
        for c, v in r.items():
            num = isinstance(v, (int, float)) and not isinstance(v, bool)
            classes = ["num"] if num else []
            if num and c in ("profit_Rs", "return_%", "avg_return_pct") and pd.notna(v):
                classes += ["pos"] if v > 0 else ["neg"] if v < 0 else []
            cls = f" class='{' '.join(classes)}'" if classes else ""
            txt = f"{v:,.2f}" if isinstance(v, float) else f"{v:,}" if isinstance(v, int) else v
            cells += f"<td{cls}>{html.escape(str(txt))}</td>"
        body += f"<tr>{cells}</tr>"
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _md(lines: list[str]) -> str:
    out, in_list = "", False
    for ln in lines:
        txt = html.escape(ln)
        txt = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
        txt = re.sub(r"_(.+?)_$", r"<em>\1</em>", txt)
        if ln.startswith("- "):
            if not in_list:
                out += "<ul>"; in_list = True
            out += f"<li>{txt[2:]}</li>"
        else:
            if in_list:
                out += "</ul>"; in_list = False
            out += f"<p>{txt}</p>"
    return out + ("</ul>" if in_list else "")


def build(results, curves, roll, trades, notes, sectors, window) -> Path:
    cols = ["mode", "strategy", "trades", "invested_Rs", "final_value_Rs", "profit_Rs",
            "return_%", "win_rate_%", "fees_tax_Rs", "avg_hold_days", "best_trade", "worst_trade"]
    res = results[[c for c in cols if c in results.columns]].copy()
    for c in ("trades", "invested_Rs", "final_value_Rs", "profit_Rs", "fees_tax_Rs"):
        res[c] = res[c].round().astype("Int64").astype(object)

    charts = ""
    for mode in results["mode"].unique():
        charts += f"<img alt='{mode} profit curve' src='data:image/png;base64,{curve_chart(curves, mode)}'>"
    for mode in results["mode"].unique():
        r = rolling_chart(roll, mode) if not roll.empty else None
        if r:
            charts += f"<img alt='{mode} rolling windows' src='data:image/png;base64,{r}'>"

    top = ""
    if not trades.empty:
        t = trades[trades["mode"] == trades["mode"].iloc[0]]
        top_df = (t.assign(sector=t["symbol"].map(sectors).fillna("Unknown") if sectors else "")
                  .groupby(["side", "symbol", "sector"])
                  .agg(times_picked=("symbol", "size"), avg_return_pct=("return_pct", "mean"))
                  .reset_index().sort_values(["side", "times_picked"], ascending=[True, False])
                  .groupby("side").head(8).round(2))
        top = "<h2>Most-picked stocks</h2>" + _table(top_df)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PSX Strategy Report</title>
<style>
:root {{ --bg:#F7F5F0; --card:#fff; --ink:#16202B; --muted:#5A6573; --rule:#D8DEE5; --pos:#1B7F4B; --neg:#C0392B; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#12181F; --card:#1A222B; --ink:#E9EEF2; --muted:#9AA6B2; --rule:#2A3138; --pos:#5CC48D; --neg:#F07B6E; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; padding:28px 16px 60px }}
main {{ max-width:1000px; margin:0 auto }}
h1 {{ font-size:28px; margin:0 0 4px }} h2 {{ font-size:18px; margin:28px 0 10px }}
.sub {{ color:var(--muted); margin:0 0 20px }}
.card {{ background:var(--card); border:1px solid var(--rule); border-radius:10px; padding:16px 20px; margin-bottom:14px }}
img {{ width:100%; height:auto; background:#fff; border-radius:8px; border:1px solid var(--rule); margin-bottom:12px }}
.scroll {{ overflow-x:auto }} table {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums }}
th,td {{ padding:6px 10px; border-bottom:1px solid var(--rule); text-align:left; white-space:nowrap }}
td.num {{ text-align:right }} th {{ color:var(--muted); font-weight:600 }}
.pos {{ color:var(--pos); font-weight:600 }} .neg {{ color:var(--neg); font-weight:600 }}
ul {{ padding-left:20px; margin:4px 0 12px }}
</style></head><body><main>
<h1>PSX Strategy Report</h1>
<p class="sub">Rs {AMOUNT:,} a day on the biggest % loser vs the biggest % gainer ·
{window[0]:%d %b %Y} to {window[1]:%d %b %Y} · fees and tax included</p>
<div class="card">{_md(notes)}</div>
<h2>Results</h2>{_table(res)}
<h2>Charts</h2>{charts}
{top}
<p class="sub">Files: trades.csv (every trade, with side and mode columns), results.csv, rolling_windows.csv, pnl_curves.csv. Not financial advice.</p>
</main></body></html>"""
    path = OUT / "report.html"
    path.write_text(page, encoding="utf-8")
    return path
