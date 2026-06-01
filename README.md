# Home Solar Energy Project

Personal monitoring & analytics for a SolarZero home solar + battery system
(site `SC-23-097707`). Local compute, **Supabase (Postgres)** for storage.

```
                          ┌─────────────────────────┐
  SolarZero API  ──auth──▶│  src/fetch.py            │
  (AWS Cognito)           │  src/refresh.py (orchestr)│──upsert──▶  Supabase
                          └─────────────────────────┘             (daily_energy,
                                     ▲                              tariffs,
  Windows Task Scheduler ────────────┘                             refresh_log)
                                                                        │
   dashboard/app.py  (Streamlit)  ◀──────────────────────────read──────┤
   html_report/generate.py (static HTML) ◀────────────────────read─────┘
```

## What it does
- **Fetch** daily energy data (solar / battery / grid / home flows) from the
  SolarZero portal API — no browser needed, authenticates via AWS Cognito.
- **Store** in Supabase with idempotent upserts (safe to re-run).
- **Analyse**: tariff-aware bills, ROI / break-even vs install cost, and
  battery fault detection (catches the Jan-2026 charging-collapse pattern).
- **Visualise**: an interactive Streamlit app and a self-contained HTML report.
- **Auto-refresh**: a scheduled task keeps the DB current each day.

---

## Setup (one time)

### 1. Create the Supabase project
1. Create a project at supabase.com.
2. Open **SQL Editor** → paste the contents of `sql/schema.sql` → Run.
3. Project Settings → Database → copy the **Connection string (URI)**
   (Session pooler is fine).

### 2. Configure
```powershell
cd C:\Manu\ClaudeWork\SolarEnergyProject
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env        # fill in email, password, DATABASE_URL
```

### 3. Load history
Two options:

**A. Seed from the CSV you already exported (fastest):**
```powershell
python -m src.seed_from_csv data\solarzero_2023Nov_2026Mar_all_daily.csv
```

**B. Or backfill straight from the API:**
```powershell
python -m src.refresh --full
```

---

## Daily use

**Refresh new data (incremental — re-fetches last 3 days for corrections):**
```powershell
python -m src.refresh
```

**Interactive dashboard:**
```powershell
streamlit run dashboard\app.py
```

**Static HTML report (share / archive):**
```powershell
python html_report\generate.py
# → data\solar_report.html
```

---

## Schedule auto-refresh (Windows Task Scheduler)
1. Open **Task Scheduler** → Create Basic Task → "SolarZero Refresh".
2. Trigger: Daily, ~06:00.
3. Action: Start a program → `C:\Manu\ClaudeWork\SolarEnergyProject\scripts\run_refresh.bat`.
4. Logs append to `data\refresh.log`.

---

## Layout
```
SolarEnergyProject/
├── config.py              # env-driven config
├── sql/schema.sql         # Supabase DDL + seed tariffs/system rows
├── src/
│   ├── fetch.py           # SolarZero API client (Cognito auth)
│   ├── db.py              # Supabase upserts + DataFrame reads
│   ├── analytics.py       # bills, ROI, battery anomaly detection
│   ├── refresh.py         # incremental/full orchestrator
│   └── seed_from_csv.py   # one-off CSV import
├── dashboard/app.py       # Streamlit dashboard
├── html_report/generate.py# self-contained HTML report
└── scripts/run_refresh.bat# scheduler entry point
```

## Notes
- **Tariffs are time-versioned** in the `tariffs` table — when your plan/rates
  change, add a new row (set the old one's `valid_to`) and historical bills stay
  accurate.
- **Battery anomaly detection** compares each day's charge to a trailing 14-day
  median and only flags drops on days with decent solar, so cloudy days aren't
  false-flagged. Tune thresholds in `analytics.detect_battery_anomalies`.
