"""
Analytics — pure pandas functions on the daily_energy DataFrame.

Covers:
  - tariff-aware billing (handles time-versioned tariffs)
  - monthly / summary rollups
  - ROI & break-even vs install cost
  - battery fault / anomaly detection (the Jan-2026 charging collapse pattern)
  - seasonal helpers (NZ seasons)
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# ── Tariff-aware billing ──────────────────────────────────────────────────────
def apply_tariffs(df: pd.DataFrame, tariffs: pd.DataFrame) -> pd.DataFrame:
    """
    Attach import_rate, export_rate, daily_fixed to each day based on the
    tariff valid for that date. Adds cost columns.
    """
    df = df.copy()
    df["import_rate"] = np.nan
    df["export_rate"] = np.nan
    df["daily_fixed"] = np.nan

    for _, t in tariffs.iterrows():
        start = t["valid_from"]
        end = t["valid_to"] if pd.notna(t["valid_to"]) else pd.Timestamp.max
        mask = (df["date"] >= start) & (df["date"] <= end)
        df.loc[mask, "import_rate"] = float(t["import_rate"])
        df.loc[mask, "export_rate"] = float(t["export_rate"])
        df.loc[mask, "daily_fixed"] = float(t["daily_fixed"])

    df["import_cost"]   = df["grid_import_kwh"].fillna(0) * df["import_rate"]
    df["export_credit"] = df["grid_export_kwh"].fillna(0) * df["export_rate"]
    df["fixed_cost"]    = df["daily_fixed"]
    df["net_cost"]      = df["import_cost"] + df["fixed_cost"] - df["export_credit"]

    # Counterfactual: what the day would cost on grid-only (no solar/battery)
    df["grid_only_cost"] = df["home_total_kwh"].fillna(0) * df["import_rate"] + df["daily_fixed"]
    df["daily_saving"]   = df["grid_only_cost"] - df["net_cost"]
    return df


# ── Rollups ─────────────────────────────────────────────────────────────────
def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly aggregation of energy + cost columns."""
    d = df.copy()
    d["month"] = d["date"].dt.to_period("M").astype(str)
    agg = d.groupby("month").agg(
        days=("date", "count"),
        home_kwh=("home_total_kwh", "sum"),
        solar_kwh=("solar_total_kwh", "sum"),
        grid_import_kwh=("grid_import_kwh", "sum"),
        grid_export_kwh=("grid_export_kwh", "sum"),
        battery_charge_kwh=("battery_chg_solar", "sum"),
        import_cost=("import_cost", "sum"),
        export_credit=("export_credit", "sum"),
        fixed_cost=("fixed_cost", "sum"),
        net_cost=("net_cost", "sum"),
        grid_only_cost=("grid_only_cost", "sum"),
        saving=("daily_saving", "sum"),
    ).reset_index()
    agg["self_consumption_pct"] = (
        (1 - agg["grid_export_kwh"] / agg["solar_kwh"].replace(0, np.nan)) * 100
    ).round(1)
    agg["solar_coverage_pct"] = (
        (1 - agg["grid_import_kwh"] / agg["home_kwh"].replace(0, np.nan)) * 100
    ).round(1)
    return agg.round(2)


def bill_for_period(df: pd.DataFrame, start: str, end: str) -> dict:
    """Headline numbers for a date window (inclusive)."""
    m = df[(df["date"] >= start) & (df["date"] <= end)]
    return {
        "days": len(m),
        "import_kwh": round(m["grid_import_kwh"].sum(), 1),
        "export_kwh": round(m["grid_export_kwh"].sum(), 1),
        "import_cost": round(m["import_cost"].sum(), 2),
        "export_credit": round(m["export_credit"].sum(), 2),
        "fixed_cost": round(m["fixed_cost"].sum(), 2),
        "net_bill": round(m["net_cost"].sum(), 2),
        "saving_vs_grid_only": round(m["daily_saving"].sum(), 2),
    }


# ── ROI / break-even ──────────────────────────────────────────────────────────
def roi_series(df: pd.DataFrame, install_cost: float) -> pd.DataFrame:
    """Cumulative savings vs install cost, with break-even flag."""
    d = df.sort_values("date").copy()
    d["cum_saving"] = d["daily_saving"].cumsum()
    d["remaining_to_breakeven"] = install_cost - d["cum_saving"]
    return d[["date", "daily_saving", "cum_saving", "remaining_to_breakeven"]]


def roi_summary(df: pd.DataFrame, install_cost: float) -> dict:
    d = roi_series(df, install_cost)
    total_saving = d["cum_saving"].iloc[-1] if len(d) else 0.0
    days = len(d)
    avg_daily = total_saving / days if days else 0.0
    pct = (total_saving / install_cost * 100) if install_cost else 0.0

    breakeven = d[d["cum_saving"] >= install_cost]
    breakeven_date = breakeven["date"].iloc[0] if len(breakeven) else None
    if breakeven_date is None and avg_daily > 0:
        remaining = install_cost - total_saving
        est_days = remaining / avg_daily
        est_breakeven = d["date"].iloc[-1] + pd.Timedelta(days=est_days)
    else:
        est_breakeven = breakeven_date

    return {
        "install_cost": install_cost,
        "total_saving": round(total_saving, 2),
        "pct_recovered": round(pct, 1),
        "avg_daily_saving": round(avg_daily, 2),
        "days_tracked": days,
        "breakeven_reached": breakeven_date is not None,
        "breakeven_date": str(breakeven_date.date()) if breakeven_date is not None else None,
        "est_breakeven_date": str(est_breakeven.date()) if est_breakeven is not None else None,
    }


# ── Battery fault / anomaly detection ─────────────────────────────────────────
def detect_battery_anomalies(df: pd.DataFrame,
                             window: int = 14,
                             drop_ratio: float = 0.25,
                             min_solar: float = 8.0) -> pd.DataFrame:
    """
    Flag days where battery charging collapses relative to its recent norm.

    The Jan-2026 pattern: daily charge fell from ~8.6 kWh to ~0.5 kWh while
    solar was still plentiful. We compare each day's total battery charge to a
    trailing median and flag sustained drops on days that had decent solar
    (so we don't flag genuinely cloudy days).
    """
    d = df.sort_values("date").copy()
    d["battery_charge_total"] = d["battery_chg_solar"].fillna(0) + d["battery_chg_grid"].fillna(0)
    d["charge_baseline"] = (
        d["battery_charge_total"].rolling(window, min_periods=5).median().shift(1)
    )
    d["is_anomaly"] = (
        (d["charge_baseline"] > 2.0) &                                  # had a real baseline
        (d["battery_charge_total"] < d["charge_baseline"] * drop_ratio) &  # collapsed
        (d["solar_total_kwh"].fillna(0) >= min_solar)                   # solar was available
    )
    return d[["date", "battery_charge_total", "charge_baseline",
              "solar_total_kwh", "is_anomaly"]]


def anomaly_episodes(anom: pd.DataFrame, min_run: int = 3) -> pd.DataFrame:
    """Collapse consecutive anomaly days into episodes (start, end, days)."""
    d = anom[anom["is_anomaly"]].copy()
    if d.empty:
        return pd.DataFrame(columns=["start", "end", "days"])
    d = d.sort_values("date")
    gap = (d["date"].diff().dt.days.fillna(1) > 1).cumsum()
    episodes = d.groupby(gap).agg(start=("date", "min"),
                                  end=("date", "max"),
                                  days=("date", "count")).reset_index(drop=True)
    return episodes[episodes["days"] >= min_run].reset_index(drop=True)


# ── Seasons (NZ) ──────────────────────────────────────────────────────────────
def nz_season(dt: pd.Timestamp) -> str:
    m = dt.month
    if m in (12, 1, 2):
        return "Summer"
    if m in (3, 4, 5):
        return "Autumn"
    if m in (6, 7, 8):
        return "Winter"
    return "Spring"
