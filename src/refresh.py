"""
Refresh orchestrator.

Determines which dates are missing (from the last date in Supabase up to
yesterday), fetches them from SolarZero, and upserts into the database.

Re-fetches the last ~3 days each run so that partial/most-recent days get
corrected once finalised.

Usage:
    python -m src.refresh                 # incremental (recommended for schedule)
    python -m src.refresh --full          # full backfill from go-live
    python -m src.refresh --start 2026-04-01 --end 2026-04-30
"""
from __future__ import annotations

import sys
import argparse
import traceback
from datetime import date, timedelta

import config
from src.fetch import SolarZeroClient
from src import db


def determine_range(args) -> tuple[date, date]:
    today = date.today()
    yesterday = today - timedelta(days=1)

    if args.full:
        return date.fromisoformat(config.SYSTEM_GO_LIVE), yesterday
    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else yesterday
        return start, end

    # Incremental: from (last_date - 3) to yesterday; re-fetch tail for corrections
    last = db.latest_date()
    if last is None:
        return date.fromisoformat(config.SYSTEM_GO_LIVE), yesterday
    start = last - timedelta(days=3)
    return start, yesterday


def main():
    parser = argparse.ArgumentParser(description="Refresh SolarZero data into Supabase.")
    parser.add_argument("--full", action="store_true", help="Full backfill from go-live")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    args = parser.parse_args()

    config.require("SOLARZERO_EMAIL", "SOLARZERO_PASSWORD", "DATABASE_URL")

    start, end = determine_range(args)
    if start > end:
        print(f"Nothing to do — DB already current (start {start} > end {end}).")
        db.log_refresh(f"{start}..{end}", 0, "skipped", "already current")
        return

    months = f"{start} .. {end}"
    print(f"Refreshing {months}")

    try:
        client = SolarZeroClient(config.SOLARZERO_EMAIL,
                                 config.SOLARZERO_PASSWORD, config.SITE_ID)
        rows = client.fetch_range(start, end)
        n = db.upsert_daily(rows)
        print(f"✓ Upserted {n} rows ({start} → {end})")
        db.log_refresh(months, n, "success")
    except Exception as e:
        print(f"✗ Refresh failed: {e}")
        traceback.print_exc()
        db.log_refresh(months, 0, "error", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
