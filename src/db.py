"""
Database layer — Supabase (Postgres) via SQLAlchemy.

Handles: engine creation, idempotent upserts of daily rows, and
DataFrame reads for analytics / dashboards.
"""
from __future__ import annotations

import pandas as pd
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import Table, MetaData

import config

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        config.require("DATABASE_URL")
        # pool_pre_ping handles Supabase pooler dropping idle connections
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    return _engine


# ── Writes ────────────────────────────────────────────────────────────────────
def upsert_daily(rows: list[dict]) -> int:
    """Insert or update daily_energy rows. Returns number processed."""
    if not rows:
        return 0
    engine = get_engine()
    meta = MetaData()
    tbl = Table("daily_energy", meta, autoload_with=engine)

    # Normalise empty strings to None
    clean = []
    for r in rows:
        clean.append({k: (None if v == "" else v) for k, v in r.items()})

    update_cols = [c.name for c in tbl.columns
                   if c.name not in ("date", "inserted_at")]

    with engine.begin() as conn:
        stmt = insert(tbl).values(clean)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date"],
            set_={c: stmt.excluded[c] for c in update_cols if c != "updated_at"}
                 | {"updated_at": text("now()")},
        )
        conn.execute(stmt)
    return len(clean)


def log_refresh(months: str, rows: int, status: str, message: str = "") -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""insert into refresh_log (months_fetched, rows_upserted, status, message)
                    values (:m, :r, :s, :msg)"""),
            {"m": months, "r": rows, "s": status, "msg": message[:500]},
        )


# ── Reads ─────────────────────────────────────────────────────────────────────
def latest_date() -> date | None:
    engine = get_engine()
    with engine.connect() as conn:
        res = conn.execute(text("select max(date) from daily_energy")).scalar()
    return res


def load_daily(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    engine = get_engine()
    q = "select * from daily_energy"
    conds = []
    params = {}
    if start:
        conds.append("date >= :start"); params["start"] = start
    if end:
        conds.append("date <= :end"); params["end"] = end
    if conds:
        q += " where " + " and ".join(conds)
    q += " order by date"
    df = pd.read_sql(text(q), engine, params=params, parse_dates=["date"])
    return df


def load_tariffs() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(text("select * from tariffs order by valid_from"), engine,
                       parse_dates=["valid_from", "valid_to"])


def load_system_config() -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("select * from system_config where id = 1")).mappings().first()
    return dict(row) if row else {}
