"""
One-off loader: import an existing SolarZero CSV (the one we already exported)
straight into Supabase, so you don't have to re-fetch the whole history.

Usage:
    python -m src.seed_from_csv path/to/solarzero_2023Nov_2026Mar_all_daily.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import csv
from src import db


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m src.seed_from_csv <file.csv>")
    path = sys.argv[1]

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Coerce numerics; keep date as string (YYYY-MM-DD)
    clean = []
    for r in rows:
        out = {"date": r["date"]}
        for k, v in r.items():
            if k == "date":
                continue
            out[k] = float(v) if v not in ("", None) else None
        clean.append(out)

    n = db.upsert_daily(clean)
    db.log_refresh(f"CSV seed: {Path(path).name}", n, "success")
    print(f"✓ Seeded {n} rows from {path}")


if __name__ == "__main__":
    main()
