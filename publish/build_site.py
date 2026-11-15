"""Build the public GitHub Pages site into site/:
today's movers, this month's momentum list, strategy comparison,
the full backtest report, and dataset download links.

    python publish/build_site.py
"""
from __future__ import annotations

import html
import json
import os
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
BT = ROOT / "data" / "backtest"
POSTS = ROOT / "data" / "posts"
REPO = os.environ.get("GITHUB_REPOSITORY", "shessols/psx-market-data-platform")
RAW = f"https://raw.githubusercontent.com/{REPO}/main"


def esc(x) -> str:
    return html.escape(str(x))


def table(df: pd.DataFrame, pct_cols=()) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    rows = ""
    for _, r in df.iterrows():
        cells = ""
        for c, v in r.items():
            num = isinstance(v, (int, float))
            cls = "num"
            if c in pct_cols and num:
                cls += " pos" if v > 0 else " neg" if v < 0 else ""
            txt = f"{v:,.1f}" if isinstance(v, float) else f"{v:,}" if isinstance(v, int) else v
            cells += f"<td class='{cls if num else ''}'>{esc(txt)}</td>"
        rows += f"<tr>{cells}</tr>"
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    meta = json.loads((ROOT / "dataset" / "metadata.json").read_text())

    movers_img, movers_txt = "", ""
    posts = sorted(POSTS.glob("psx_movers_*.png"))
    if posts:
        shutil.copy(posts[-1], SITE / "movers.png")
        movers_img = "<img src='movers.png' alt='PSX daily movers chart' width='540'>"
        txt = posts[-1].with_suffix(".txt")
        if txt.exists():
            movers_txt = f"<pre>{esc(txt.read_text(encoding='utf-8'))}</pre>"

    research = ""
    rj = BT / "monthly_strategies.json"
    if rj.exists():
        r = json.loads(rj.read_text())
        t = pd.DataFrame(r["table"]).rename(columns={
            "strategy": "Strategy", "per_year_%": "Per year %", "rs_1_lakh_became": "Rs 1 lakh became",
            "worst_drop_%": "Worst drop %", "best_year_%": "Best year %", "worst_year_%": "Worst year %"})
        p = pd.DataFrame(r["picks"]).rename(columns={
            "symbol": "Symbol", "return_12m_skip1_%": "12-month return %", "last_close": "Last close (Rs)",
            "sector": "Sector"})
        research = f"""
<section><h2>Momentum list: top 10 by 12-month return (skipping the latest month)</h2>
<p class="sub">Prices up to {esc(r['as_of'])}. Research output, not a recommendation.</p>
{table(p, pct_cols=('12-month return %',))}</section>
<section><h2>Which monthly strategy worked on PSX?</h2>
<p class="sub">{esc(r['from'])} to {esc(r['to'])} · fees included, capital gains tax not · adjusted for splits and bonus shares</p>
{table(t, pct_cols=('Per year %', 'Worst drop %', 'Best year %', 'Worst year %'))}</section>"""

    report_link = ""
    if (BT / "report.html").exists():
        shutil.copy(BT / "report.html", SITE / "report.html")
        report_link = ("<p><a class='btn' href='report.html'>Full report: Rs 1,000 a day on the biggest "
                       "loser vs the biggest gainer →</a></p>")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PSX Market Data</title>
<meta name="description" content="Free daily Pakistan Stock Exchange data, daily movers and strategy research.">
<style>
:root {{ --bg:#F7F5F0; --card:#fff; --ink:#16202B; --muted:#5A6573; --rule:#D8DEE5; --accent:#0F5C55; --pos:#1B7F4B; --neg:#C0392B; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#12181F; --card:#1A222B; --ink:#E9EEF2; --muted:#9AA6B2; --rule:#2A3138; --accent:#7FC4B8; --pos:#5CC48D; --neg:#F07B6E; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; padding:32px 16px 64px }}
main {{ max-width:960px; margin:0 auto }}
h1 {{ font-size:32px; margin:0 0 6px }} h2 {{ font-size:19px; margin:0 0 6px }}
section {{ background:var(--card); border:1px solid var(--rule); border-radius:12px; padding:20px; margin:16px 0 }}
.sub {{ color:var(--muted); margin:0 0 12px }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:16px 0 }}
.stat {{ background:var(--card); border:1px solid var(--rule); border-radius:10px; padding:12px 14px }}
.stat b {{ display:block; font-size:22px; color:var(--accent) }} .stat span {{ color:var(--muted); font-size:13px }}
.grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; align-items:start }}
@media (max-width:720px) {{ .grid {{ grid-template-columns:1fr }} }}
img {{ max-width:100%; height:auto; border-radius:8px; border:1px solid var(--rule) }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:var(--bg); padding:12px; border-radius:8px; font-size:13px }}
.scroll {{ overflow-x:auto }} table {{ border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums }}
th,td {{ padding:7px 10px; border-bottom:1px solid var(--rule); text-align:left; white-space:nowrap }}
th {{ color:var(--muted); font-weight:600 }} td.num {{ text-align:right }}
.pos {{ color:var(--pos); font-weight:600 }} .neg {{ color:var(--neg); font-weight:600 }}
code {{ background:var(--bg); padding:2px 6px; border-radius:4px; font-size:13px; word-break:break-all }}
a {{ color:var(--accent) }} .btn {{ display:inline-block; padding:10px 14px; border:1px solid var(--accent); border-radius:8px; text-decoration:none; font-weight:600 }}
footer {{ color:var(--muted); font-size:13px; margin-top:24px }}
</style></head><body><main>
<h1>PSX Market Data</h1>
<p class="sub">Free, daily-updated Pakistan Stock Exchange prices with movers and strategy research. Updated automatically every weekday after market close.</p>
<div class="stats">
  <div class="stat"><b>{meta['symbols']:,}</b><span>stocks</span></div>
  <div class="stat"><b>{meta['rows']:,}</b><span>daily price rows</span></div>
  <div class="stat"><b>{esc(meta['first_date'][:4])}–{esc(meta['last_date'][:4])}</b><span>history</span></div>
  <div class="stat"><b>{esc(meta['last_date'])}</b><span>latest trading day</span></div>
</div>
<section><h2>Today's movers</h2><div class="grid"><div>{movers_img}</div><div>{movers_txt}</div></div></section>
{research}
<section><h2>Strategy test</h2>{report_link or "<p class='sub'>Report appears after the first full run.</p>"}</section>
<section><h2>Use the data</h2>
<p>Monthly Parquet files of raw daily OHLCV for every listed stock, plus a stock list with sectors.</p>
<pre>import pandas as pd
latest = pd.read_csv("{RAW}/dataset/latest.csv")
stocks = pd.read_csv("{RAW}/dataset/stocks.csv")
month  = pd.read_parquet("{RAW}/dataset/prices/{esc(meta['last_date'][:7])}.parquet")</pre>
<p>Full history: clone <a href="https://github.com/{REPO}">github.com/{REPO}</a> and read <code>dataset/prices/*.parquet</code>. Prices are raw (not adjusted for splits); see <code>ingest/adjust_prices.py</code>.</p>
</section>
<footer>Source: PSX Data Portal, collected with the open-source psxdata library. Last updated {esc(meta['last_updated_utc'])} UTC.
For education and research only. Not investment advice. Built by Abdullah Sherwani · <a href="https://github.com/{REPO}">code on GitHub</a></footer>
</main></body></html>"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"Site built in {SITE}")


if __name__ == "__main__":
    main()
