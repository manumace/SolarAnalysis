"""
SolarZero — Interactive Streamlit dashboard.

Run:
    streamlit run dashboard/app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import config
from src import db, analytics as A

# ── Page + theme ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Solar Energy", page_icon="◐", layout="wide")

SOLAR  = "#F5A623"   # amber
BATTERY = "#2ECC71"  # green
IMPORT = "#E74C3C"   # red
EXPORT = "#3498DB"   # blue
INK    = "#0E1117"

st.markdown(f"""
<style>
  .stApp {{ background: {INK}; }}
  h1, h2, h3 {{ font-family: 'Trebuchet MS', sans-serif; letter-spacing:-0.02em; }}
  [data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; }}
  .kpi {{ background:#161A23; border:1px solid #232936; border-radius:14px;
          padding:18px 20px; }}
  .kpi .label {{ color:#8B95A7; font-size:0.78rem; text-transform:uppercase;
                 letter-spacing:0.08em; }}
  .kpi .value {{ font-family:'IBM Plex Mono',monospace; font-size:1.9rem;
                 font-weight:600; margin-top:4px; }}
  .kpi .sub {{ color:#6B7588; font-size:0.8rem; margin-top:2px; }}
</style>
""", unsafe_allow_html=True)


# ── Data loading (cached) ─────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def load():
    df = db.load_daily()
    tariffs = db.load_tariffs()
    syscfg = db.load_system_config()
    df = A.apply_tariffs(df, tariffs)
    return df, tariffs, syscfg


try:
    df, tariffs, syscfg = load()
except Exception as e:
    st.error(f"Could not connect to Supabase. Check your .env DATABASE_URL.\n\n{e}")
    st.stop()

if df.empty:
    st.warning("No data yet. Run `python -m src.refresh --full` to backfill.")
    st.stop()

install_cost = float(syscfg.get("install_cost") or 15000)

# ── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.title("◐ Solar Energy")
min_d, max_d = df["date"].min().date(), df["date"].max().date()
dr = st.sidebar.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
if isinstance(dr, tuple) and len(dr) == 2:
    df = df[(df["date"] >= pd.Timestamp(dr[0])) & (df["date"] <= pd.Timestamp(dr[1]))]
st.sidebar.caption(f"Data: {min_d} → {max_d}  ·  {len(df)} days")

def kpi(col, label, value, sub=""):
    col.markdown(f'<div class="kpi"><div class="label">{label}</div>'
                 f'<div class="value">{value}</div>'
                 f'<div class="sub">{sub}</div></div>', unsafe_allow_html=True)

st.title("Home Solar Performance")

# ── Headline KPIs ─────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
kpi(c1, "Solar Generated", f"{df['solar_total_kwh'].sum():,.0f} kWh")
kpi(c2, "Home Consumed",   f"{df['home_total_kwh'].sum():,.0f} kWh")
kpi(c3, "Grid Import",     f"{df['grid_import_kwh'].sum():,.0f} kWh")
kpi(c4, "Grid Export",     f"{df['grid_export_kwh'].sum():,.0f} kWh")
kpi(c5, "Net Bill",        f"${df['net_cost'].sum():,.0f}",
    f"saved ${df['daily_saving'].sum():,.0f} vs grid-only")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["⚡ Energy Flows", "💰 Bills", "📈 ROI", "🔋 Battery Health"])

# ── Tab 1: Energy flows ───────────────────────────────────────────────────────
with tab1:
    monthly = A.monthly_summary(df)
    fig = go.Figure()
    fig.add_bar(x=monthly["month"], y=monthly["solar_kwh"], name="Solar", marker_color=SOLAR)
    fig.add_bar(x=monthly["month"], y=monthly["home_kwh"], name="Home", marker_color="#6B7588")
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["grid_import_kwh"],
                             name="Grid Import", line=dict(color=IMPORT, width=2)))
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["grid_export_kwh"],
                             name="Grid Export", line=dict(color=EXPORT, width=2)))
    fig.update_layout(template="plotly_dark", barmode="group", height=420,
                      title="Monthly Energy: Generation vs Consumption",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=60))
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        avg = dict(
            Solar_to_Home=df["solar_to_home"].sum(),
            Solar_to_Battery=df["solar_to_battery"].sum(),
            Solar_to_Grid=df["solar_to_grid"].sum(),
        )
        pie = px.pie(values=list(avg.values()), names=list(avg.keys()),
                     title="Where your solar goes", hole=0.5,
                     color_discrete_sequence=[BATTERY, SOLAR, EXPORT])
        pie.update_layout(template="plotly_dark", height=360)
        st.plotly_chart(pie, use_container_width=True)
    with col_b:
        src = dict(
            From_Solar=df["home_from_solar"].sum(),
            From_Battery=df["home_from_battery"].sum(),
            From_Grid=df["home_from_grid"].sum(),
        )
        pie2 = px.pie(values=list(src.values()), names=list(src.keys()),
                      title="How your home is powered", hole=0.5,
                      color_discrete_sequence=[SOLAR, BATTERY, IMPORT])
        pie2.update_layout(template="plotly_dark", height=360)
        st.plotly_chart(pie2, use_container_width=True)

# ── Tab 2: Bills ──────────────────────────────────────────────────────────────
with tab2:
    monthly = A.monthly_summary(df)
    fig = go.Figure()
    fig.add_bar(x=monthly["month"], y=monthly["import_cost"], name="Import $", marker_color=IMPORT)
    fig.add_bar(x=monthly["month"], y=monthly["fixed_cost"], name="Fixed $", marker_color="#6B7588")
    fig.add_bar(x=monthly["month"], y=-monthly["export_credit"], name="Export credit", marker_color=EXPORT)
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["net_cost"],
                             name="Net bill", line=dict(color=SOLAR, width=3), mode="lines+markers"))
    fig.update_layout(template="plotly_dark", barmode="relative", height=420,
                      title="Monthly Bill Breakdown (NZD)",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=60))
    st.plotly_chart(fig, use_container_width=True)

    show = monthly[["month", "days", "grid_import_kwh", "grid_export_kwh",
                    "import_cost", "export_credit", "fixed_cost", "net_cost",
                    "saving", "solar_coverage_pct"]].copy()
    show.columns = ["Month", "Days", "Import kWh", "Export kWh", "Import $",
                    "Export $", "Fixed $", "Net Bill $", "Saving $", "Solar Cover %"]
    st.dataframe(show, use_container_width=True, hide_index=True)

# ── Tab 3: ROI ────────────────────────────────────────────────────────────────
with tab3:
    full = db.load_daily()
    full = A.apply_tariffs(full, tariffs)
    roi = A.roi_series(full, install_cost)
    summary = A.roi_summary(full, install_cost)

    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Install Cost", f"${install_cost:,.0f}")
    kpi(c2, "Saved So Far", f"${summary['total_saving']:,.0f}", f"{summary['pct_recovered']}% recovered")
    kpi(c3, "Avg Daily Saving", f"${summary['avg_daily_saving']:.2f}")
    kpi(c4, "Est. Break-even",
        summary["est_breakeven_date"] or "—",
        "reached!" if summary["breakeven_reached"] else "projected")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=roi["date"], y=roi["cum_saving"], name="Cumulative saving",
                             line=dict(color=BATTERY, width=2), fill="tozeroy"))
    fig.add_hline(y=install_cost, line_dash="dash", line_color=SOLAR,
                  annotation_text=f"Install cost ${install_cost:,.0f}")
    fig.update_layout(template="plotly_dark", height=420,
                      title="Cumulative Savings vs Install Cost", margin=dict(t=60))
    st.plotly_chart(fig, use_container_width=True)

# ── Tab 4: Battery health ─────────────────────────────────────────────────────
with tab4:
    full = db.load_daily()
    anom = A.detect_battery_anomalies(full)
    episodes = A.anomaly_episodes(anom)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=anom["date"], y=anom["battery_charge_total"],
                             name="Daily charge", line=dict(color=BATTERY, width=1.5)))
    fig.add_trace(go.Scatter(x=anom["date"], y=anom["charge_baseline"],
                             name="14-day baseline", line=dict(color="#6B7588", dash="dot")))
    flagged = anom[anom["is_anomaly"]]
    fig.add_trace(go.Scatter(x=flagged["date"], y=flagged["battery_charge_total"],
                             name="Anomaly", mode="markers",
                             marker=dict(color=IMPORT, size=7, symbol="x")))
    fig.update_layout(template="plotly_dark", height=420,
                      title="Battery Daily Charge — anomaly detection",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=60))
    st.plotly_chart(fig, use_container_width=True)

    if not episodes.empty:
        st.subheader("⚠️ Detected fault episodes")
        ep = episodes.copy()
        ep["start"] = ep["start"].dt.date
        ep["end"] = ep["end"].dt.date
        ep.columns = ["Start", "End", "Days"]
        st.dataframe(ep, use_container_width=True, hide_index=True)
    else:
        st.success("No sustained battery charging anomalies detected in this range.")
