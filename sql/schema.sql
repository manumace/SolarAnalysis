-- ============================================================
--  SolarZero Energy Project — Supabase / Postgres schema
--  Run this once in the Supabase SQL editor (or via psql)
-- ============================================================

-- Daily energy facts (one row per day) ------------------------
create table if not exists daily_energy (
    date                date primary key,
    home_total_kwh      numeric(8,2),
    home_from_solar     numeric(8,2),
    home_from_battery   numeric(8,2),
    home_from_grid      numeric(8,2),
    solar_total_kwh     numeric(8,2),
    solar_to_home       numeric(8,2),
    solar_to_battery    numeric(8,2),
    solar_to_grid       numeric(8,2),
    battery_chg_solar   numeric(8,2),
    battery_chg_grid    numeric(8,2),
    battery_dis_home    numeric(8,2),
    battery_dis_grid    numeric(8,2),
    grid_import_kwh     numeric(8,2),
    grid_export_kwh     numeric(8,2),
    inserted_at         timestamptz default now(),
    updated_at          timestamptz default now()
);

create index if not exists idx_daily_energy_date on daily_energy (date);

-- Tariffs (time-versioned, so historical bills stay accurate) --
create table if not exists tariffs (
    id            serial primary key,
    plan_name     text not null,
    valid_from    date not null,
    valid_to      date,                       -- null = still current
    import_rate   numeric(8,5) not null,      -- $/kWh
    export_rate   numeric(8,5) not null,      -- $/kWh
    daily_fixed   numeric(8,4) not null        -- $/day
);

-- Seed the current Pulse Energy plan (edit as needed) ----------
insert into tariffs (plan_name, valid_from, valid_to, import_rate, export_rate, daily_fixed)
select 'Pulse Energy', '2023-11-01', null, 0.17550, 0.15597, 1.5000
where not exists (select 1 from tariffs);

-- System metadata (single row) --------------------------------
create table if not exists system_config (
    id              int primary key default 1,
    site_id         text,
    install_cost    numeric(10,2),     -- e.g. 15000 NZD
    install_date    date,
    battery_kwh     numeric(6,2),
    array_kw        numeric(6,2),
    constraint single_row check (id = 1)
);

insert into system_config (id, site_id, install_cost, install_date, battery_kwh, array_kw)
select 1, 'SC-23-097707', 15000.00, '2023-11-05', 10.74, 3.12
where not exists (select 1 from system_config);

-- Refresh run log ---------------------------------------------
create table if not exists refresh_log (
    id              serial primary key,
    run_at          timestamptz default now(),
    months_fetched  text,
    rows_upserted   int,
    status          text,
    message         text
);
