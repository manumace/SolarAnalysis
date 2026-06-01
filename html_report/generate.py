"""
Generate a self-contained HTML dashboard (single file, no server needed).

Pulls from Supabase, computes analytics, and embeds a Plotly-powered report
with all data inlined. Open the resulting .html in any browser.

Run:
    python html_report/generate.py
    python html_report/generate.py --out data/solar_report.html
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import config
from src import db, analytics as A

SOLAR, BATTERY, IMPORT, EXPORT = "#F5A623", "#2ECC71", "#E74C3C", "#3498DB"


def build(out_path: str):
    df = db.load_daily()
    if df.empty:
        raise SystemExit("No data. Run `python -m src.refresh --full` first.")
    tariffs = db.load_tariffs()
    syscfg = db.load_system_config()
    df = A.apply_tariffs(df, tariffs)
    install_cost = float(syscfg.get("install_cost") or 15000)

    monthly = A.monthly_summary(df)
    roi = A.roi_series(df, install_cost)
    roi_sum = A.roi_summary(df, install_cost)
    anom = A.detect_battery_anomalies(df)
    episodes = A.anomaly_episodes(anom)

    totals = dict(
        solar=df["solar_total_kwh"].sum(),
        home=df["home_total_kwh"].sum(),
        imp=df["grid_import_kwh"].sum(),
        exp=df["grid_export_kwh"].sum(),
        net=df["net_cost"].sum(),
        saved=df["daily_saving"].sum(),
    )

    payload = {
        "months": monthly["month"].tolist(),
        "m_solar": monthly["solar_kwh"].tolist(),
        "m_home": monthly["home_kwh"].tolist(),
        "m_import": monthly["grid_import_kwh"].tolist(),
        "m_export": monthly["grid_export_kwh"].tolist(),
        "m_import_cost": monthly["import_cost"].tolist(),
        "m_export_credit": monthly["export_credit"].tolist(),
        "m_fixed": monthly["fixed_cost"].tolist(),
        "m_net": monthly["net_cost"].tolist(),
        "roi_dates": roi["date"].dt.strftime("%Y-%m-%d").tolist(),
        "roi_cum": roi["cum_saving"].round(2).tolist(),
        "bat_dates": anom["date"].dt.strftime("%Y-%m-%d").tolist(),
        "bat_charge": anom["battery_charge_total"].round(2).tolist(),
        "bat_baseline": anom["charge_baseline"].round(2).fillna(0).tolist(),
        "bat_anom_x": anom[anom["is_anomaly"]]["date"].dt.strftime("%Y-%m-%d").tolist(),
        "bat_anom_y": anom[anom["is_anomaly"]]["battery_charge_total"].round(2).tolist(),
        "install_cost": install_cost,
    }

    ep_rows = "".join(
        f"<tr><td>{r['start'].date()}</td><td>{r['end'].date()}</td><td>{int(r['days'])}</td></tr>"
        for _, r in episodes.iterrows()
    ) or '<tr><td colspan="3">None detected</td></tr>'

    html = HTML_TEMPLATE.format(
        generated=datetime.now().strftime("%d %b %Y, %H:%M"),
        date_from=df["date"].min().strftime("%d %b %Y"),
        date_to=df["date"].max().strftime("%d %b %Y"),
        days=len(df),
        solar=f"{totals['solar']:,.0f}",
        home=f"{totals['home']:,.0f}",
        imp=f"{totals['imp']:,.0f}",
        exp=f"{totals['exp']:,.0f}",
        net=f"${totals['net']:,.0f}",
        saved=f"${totals['saved']:,.0f}",
        roi_saved=f"${roi_sum['total_saving']:,.0f}",
        roi_pct=roi_sum["pct_recovered"],
        roi_break=roi_sum["est_breakeven_date"] or "—",
        install=f"${install_cost:,.0f}",
        ep_rows=ep_rows,
        data_json=json.dumps(payload),
        SOLAR=SOLAR, BATTERY=BATTERY, IMPORT=IMPORT, EXPORT=EXPORT,
    )

    Path(out_path).write_text(html, encoding="utf-8")
    print(f"✓ Wrote {out_path}  ({len(df)} days)")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar Energy Report</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=IBM+Plex+Mono:wght@400;500;600&family=Hanken+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --solar:{SOLAR}; --battery:{BATTERY}; --import:{IMPORT}; --export:{EXPORT};
    --ink:#0B0E14; --panel:#12161F; --line:#1F2530; --muted:#7A859A; --text:#E8ECF3;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--ink); color:var(--text); font-family:'Hanken Grotesk',sans-serif;
          background-image:radial-gradient(circle at 15% 0%, rgba(245,166,35,0.08), transparent 40%),
                           radial-gradient(circle at 85% 10%, rgba(46,204,113,0.06), transparent 40%); }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:48px 28px 80px; }}
  header {{ display:flex; justify-content:space-between; align-items:flex-end;
            border-bottom:1px solid var(--line); padding-bottom:24px; margin-bottom:36px; }}
  h1 {{ font-family:'Bricolage Grotesque',sans-serif; font-size:2.6rem; font-weight:700;
        letter-spacing:-0.03em; line-height:1; }}
  h1 .glow {{ color:var(--solar); }}
  .sub {{ color:var(--muted); font-size:0.9rem; margin-top:8px; }}
  .meta {{ text-align:right; color:var(--muted); font-size:0.82rem; font-family:'IBM Plex Mono',monospace; }}
  .grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:14px; margin-bottom:40px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:20px; }}
  .card .label {{ color:var(--muted); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.09em; }}
  .card .val {{ font-family:'IBM Plex Mono',monospace; font-size:1.7rem; font-weight:600; margin-top:8px; }}
  .card .unit {{ font-size:0.85rem; color:var(--muted); }}
  .card.solar .val {{ color:var(--solar); }}
  .card.batt .val {{ color:var(--battery); }}
  .card.imp .val {{ color:var(--import); }}
  .card.exp .val {{ color:var(--export); }}
  section {{ margin-bottom:44px; }}
  h2 {{ font-family:'Bricolage Grotesque',sans-serif; font-size:1.3rem; font-weight:600;
        margin-bottom:16px; display:flex; align-items:center; gap:10px; }}
  h2::before {{ content:""; width:4px; height:20px; background:var(--solar); border-radius:2px; }}
  .chart {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
  th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:500; text-transform:uppercase; font-size:0.72rem; letter-spacing:0.06em; }}
  td {{ font-family:'IBM Plex Mono',monospace; }}
  .roi-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:20px; }}
  footer {{ color:var(--muted); font-size:0.78rem; text-align:center; margin-top:60px;
            border-top:1px solid var(--line); padding-top:24px; }}
  @media (max-width:880px) {{ .grid{{grid-template-columns:repeat(2,1fr);}} .roi-row{{grid-template-columns:repeat(2,1fr);}} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Home <span class="glow">Solar</span> Report</h1>
      <div class="sub">{date_from} → {date_to} · {days} days monitored</div>
    </div>
    <div class="meta">Generated<br>{generated}</div>
  </header>

  <div class="grid">
    <div class="card solar"><div class="label">Solar Generated</div><div class="val">{solar}<span class="unit"> kWh</span></div></div>
    <div class="card"><div class="label">Home Consumed</div><div class="val">{home}<span class="unit"> kWh</span></div></div>
    <div class="card imp"><div class="label">Grid Import</div><div class="val">{imp}<span class="unit"> kWh</span></div></div>
    <div class="card exp"><div class="label">Grid Export</div><div class="val">{exp}<span class="unit"> kWh</span></div></div>
    <div class="card"><div class="label">Net Bill</div><div class="val">{net}</div></div>
    <div class="card batt"><div class="label">Saved vs Grid-only</div><div class="val">{saved}</div></div>
  </div>

  <section>
    <h2>Monthly Energy Flows</h2>
    <div class="chart"><div id="energy"></div></div>
  </section>

  <section>
    <h2>Monthly Bills</h2>
    <div class="chart"><div id="bills"></div></div>
  </section>

  <section>
    <h2>Return on Investment</h2>
    <div class="roi-row">
      <div class="card"><div class="label">Install Cost</div><div class="val">{install}</div></div>
      <div class="card batt"><div class="label">Saved So Far</div><div class="val">{roi_saved}</div><div class="unit">{roi_pct}% recovered</div></div>
      <div class="card"><div class="label">Est. Break-even</div><div class="val" style="font-size:1.2rem">{roi_break}</div></div>
      <div class="card solar"><div class="label">Status</div><div class="val" style="font-size:1.1rem">Tracking</div></div>
    </div>
    <div class="chart"><div id="roi"></div></div>
  </section>

  <section>
    <h2>Battery Health</h2>
    <div class="chart"><div id="battery"></div></div>
    <div style="margin-top:18px" class="chart">
      <table>
        <thead><tr><th>Episode Start</th><th>End</th><th>Days</th></tr></thead>
        <tbody>{ep_rows}</tbody>
      </table>
    </div>
  </section>

  <footer>SolarZero personal monitoring · data stored in Supabase · self-generated report</footer>
</div>

<script>
  const D = {data_json};
  const dark = {{ paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{{color:'#E8ECF3', family:'IBM Plex Mono'}}, margin:{{t:30,r:20,b:40,l:50}},
    legend:{{orientation:'h', y:1.15}}, xaxis:{{gridcolor:'#1F2530'}}, yaxis:{{gridcolor:'#1F2530'}} }};
  const cfg = {{ displayModeBar:false, responsive:true }};

  Plotly.newPlot('energy', [
    {{type:'bar', x:D.months, y:D.m_solar, name:'Solar', marker:{{color:'{SOLAR}'}}}},
    {{type:'bar', x:D.months, y:D.m_home, name:'Home', marker:{{color:'#6B7588'}}}},
    {{type:'scatter', x:D.months, y:D.m_import, name:'Import', line:{{color:'{IMPORT}',width:2}}}},
    {{type:'scatter', x:D.months, y:D.m_export, name:'Export', line:{{color:'{EXPORT}',width:2}}}}
  ], {{...dark, barmode:'group', height:400}}, cfg);

  Plotly.newPlot('bills', [
    {{type:'bar', x:D.months, y:D.m_import_cost, name:'Import $', marker:{{color:'{IMPORT}'}}}},
    {{type:'bar', x:D.months, y:D.m_fixed, name:'Fixed $', marker:{{color:'#6B7588'}}}},
    {{type:'bar', x:D.months, y:D.m_export_credit.map(v=>-v), name:'Export credit', marker:{{color:'{EXPORT}'}}}},
    {{type:'scatter', x:D.months, y:D.m_net, name:'Net bill', line:{{color:'{SOLAR}',width:3}}, mode:'lines+markers'}}
  ], {{...dark, barmode:'relative', height:400}}, cfg);

  Plotly.newPlot('roi', [
    {{type:'scatter', x:D.roi_dates, y:D.roi_cum, name:'Cumulative saving', fill:'tozeroy',
      line:{{color:'{BATTERY}',width:2}}}}
  ], {{...dark, height:400, shapes:[{{type:'line', x0:D.roi_dates[0], x1:D.roi_dates[D.roi_dates.length-1],
      y0:D.install_cost, y1:D.install_cost, line:{{color:'{SOLAR}',dash:'dash'}}}}],
      annotations:[{{x:D.roi_dates[Math.floor(D.roi_dates.length*0.5)], y:D.install_cost,
      text:'Install cost', showarrow:false, yshift:12, font:{{color:'{SOLAR}'}}}}]}}, cfg);

  Plotly.newPlot('battery', [
    {{type:'scatter', x:D.bat_dates, y:D.bat_charge, name:'Daily charge', line:{{color:'{BATTERY}',width:1.5}}}},
    {{type:'scatter', x:D.bat_dates, y:D.bat_baseline, name:'14-day baseline', line:{{color:'#6B7588',dash:'dot'}}}},
    {{type:'scatter', x:D.bat_anom_x, y:D.bat_anom_y, name:'Anomaly', mode:'markers',
      marker:{{color:'{IMPORT}',size:8,symbol:'x'}}}}
  ], {{...dark, height:400}}, cfg);
</script>
</body>
</html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.DATA_DIR / "solar_report.html"))
    args = ap.parse_args()
    build(args.out)
