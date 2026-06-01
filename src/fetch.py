"""
SolarZero API client.

- Authenticates against AWS Cognito (USER_PASSWORD_AUTH) for a fresh JWT.
- Fetches daily performance data one month at a time.
- Returns clean list-of-dict rows ready for the DB layer.
"""
from __future__ import annotations

import uuid
import time
import requests
from datetime import datetime, timedelta, date

import config


# ── NZ daylight saving offset ────────────────────────────────────────────────
def nz_offset(month: int) -> str:
    """May–Sep = NZST (+12); all other months = NZDT (+13)."""
    return "+12:00" if month in (5, 6, 7, 8, 9) else "+13:00"


COLUMNS = [
    "date", "home_total_kwh", "home_from_solar", "home_from_battery",
    "home_from_grid", "solar_total_kwh", "solar_to_home", "solar_to_battery",
    "solar_to_grid", "battery_chg_solar", "battery_chg_grid",
    "battery_dis_home", "battery_dis_grid", "grid_import_kwh", "grid_export_kwh",
]


class SolarZeroClient:
    def __init__(self, email: str, password: str, site_id: str):
        self.email = email
        self.password = password
        self.site_id = site_id
        self._token: str | None = None
        self._token_time: float = 0.0

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _authenticate(self) -> str:
        resp = requests.post(
            config.COGNITO_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            json={
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": config.COGNITO_CLIENT,
                "AuthParameters": {"USERNAME": self.email, "PASSWORD": self.password},
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Auth failed ({resp.status_code}): {resp.text[:300]}")
        self._token = resp.json()["AuthenticationResult"]["IdToken"]
        self._token_time = time.time()
        return self._token

    def _get_token(self) -> str:
        # Refresh proactively every ~50 minutes (tokens last 1h)
        if self._token is None or (time.time() - self._token_time) > 3000:
            return self._authenticate()
        return self._token

    # ── Fetch one month ─────────────────────────────────────────────────────
    def fetch_month(self, year: int, month: int) -> list[dict]:
        mm = str(month).zfill(2)
        date_str = f"{year}-{mm}-01T00:00:00{nz_offset(month)}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_token()}",
            "x-correlation-id": str(uuid.uuid4()),
        }
        payload = {
            "siteId": self.site_id, "timezone": config.TIMEZONE,
            "date": date_str, "hasTou": False, "interval": "day",
        }
        resp = requests.post(f"{config.API_BASE}/performance/data",
                             headers=headers, json=payload, timeout=20)
        if resp.status_code == 401:                      # token expired
            self._authenticate()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = requests.post(f"{config.API_BASE}/performance/data",
                                 headers=headers, json=payload, timeout=20)
        resp.raise_for_status()

        reports = resp.json().get("reports", [])
        if not reports:
            return []
        return self._parse_report(reports[0], year, month)

    # ── Parse the API report into flat rows ──────────────────────────────────
    @staticmethod
    def _stack(section: dict, sid: str) -> list:
        for s in (section or {}).get("stack", []):
            if s.get("id") == sid:
                return s.get("series", [])
        return []

    @staticmethod
    def _r2(v):
        return "" if v is None or v == "" else round(float(v), 2)

    def _parse_report(self, r: dict, year: int, month: int) -> list[dict]:
        home, solar = r.get("home", {}), r.get("solar", {})
        battery, grid = r.get("battery", {}), r.get("grid", {})
        labels = r.get("xAxesLabels", [])
        start_dt = datetime.fromisoformat(r["startDate"].replace("Z", "+00:00"))
        nz_hours = 13 if nz_offset(month) == "+13:00" else 12

        def at(series, i):
            return series[i] if i < len(series) else None

        def absat(series, i):
            v = at(series, i)
            return abs(v) if v is not None else 0

        rows = []
        for i, _ in enumerate(labels):
            local_dt = start_dt + timedelta(days=i, hours=nz_hours)
            day_str = local_dt.strftime("%Y-%m-%d")
            y, m, _d = map(int, day_str.split("-"))
            if y != year or m != month:
                continue

            grid_import = (at(self._stack(grid, "home"), i) or 0) + \
                          (at(self._stack(grid, "tobattery"), i) or 0)
            grid_export = absat(self._stack(grid, "solar"), i) + \
                          absat(self._stack(grid, "frombattery"), i)

            rows.append({
                "date": day_str,
                "home_total_kwh":    self._r2(at(home.get("series", []), i)),
                "home_from_solar":   self._r2(at(self._stack(home, "solar"), i)),
                "home_from_battery": self._r2(at(self._stack(home, "battery"), i)),
                "home_from_grid":    self._r2(at(self._stack(home, "grid"), i)),
                "solar_total_kwh":   self._r2(at(solar.get("series", []), i)),
                "solar_to_home":     self._r2(at(self._stack(solar, "home"), i)),
                "solar_to_battery":  self._r2(absat(self._stack(solar, "battery"), i)),
                "solar_to_grid":     self._r2(at(self._stack(solar, "grid"), i)),
                "battery_chg_solar": self._r2(absat(self._stack(battery, "solar"), i)),
                "battery_chg_grid":  self._r2(absat(self._stack(battery, "fromgrid"), i)),
                "battery_dis_home":  self._r2(at(self._stack(battery, "home"), i)),
                "battery_dis_grid":  self._r2(at(self._stack(battery, "togrid"), i)),
                "grid_import_kwh":   self._r2(grid_import),
                "grid_export_kwh":   self._r2(grid_export),
            })
        return rows

    # ── Fetch a date range (inclusive) ───────────────────────────────────────
    def fetch_range(self, start: date, end: date, polite_delay: float = 0.3) -> list[dict]:
        rows: list[dict] = []
        y, m = start.year, start.month
        months = []
        while (y, m) <= (end.year, end.month):
            months.append((y, m))
            m = 1 if m == 12 else m + 1
            y = y + 1 if m == 1 else y
        for idx, (yy, mm) in enumerate(months):
            month_rows = self.fetch_month(yy, mm)
            month_rows = [r for r in month_rows
                          if start <= date.fromisoformat(r["date"]) <= end]
            rows.extend(month_rows)
            if idx < len(months) - 1:
                time.sleep(polite_delay)
        rows.sort(key=lambda r: r["date"])
        return rows
