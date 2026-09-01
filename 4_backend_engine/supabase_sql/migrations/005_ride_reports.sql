-- Tuned Cycling — in-ride route feedback (TBT "Report" flag)
-- Run in Supabase SQL Editor (or `supabase db push` via CLI).
--
-- One row per rider tap. This is the forensic source of truth: the routing
-- overlay (crowd_overlays.py) is derived from these rows and is rebuildable,
-- so nothing here is ever mutated by the cost pipeline.
--
-- Flask writes with the SERVICE ROLE key (RLS bypassed). Tenancy/abuse control
-- is application-layer (optional user_id from JWT + rate limits). RLS below is
-- defense-in-depth against direct PostgREST/anon access, matching 003.
--
-- Guests may report: user_id is null and device_id carries the anonymous
-- installation id, so global corroboration can still count distinct people.

create table if not exists public.ride_reports (
  id              uuid primary key default gen_random_uuid(),
  -- Client-generated; the idempotency key for offline queue retries.
  client_event_id uuid not null unique,
  user_id         uuid references auth.users (id) on delete set null,
  -- Anonymous installation id. Distinct-contributor counting uses
  -- coalesce(user_id::text, 'dev:' || device_id).
  device_id       text,
  category        text not null check (category in (
                    'surface', 'dangerous', 'impassable',
                    'speeding', 'unlit', 'general'
                  )),
  source          text not null default 'tbt_island',
  lat             double precision not null,
  lon             double precision not null,

  -- Filled by the backend snap (Phase B); null until then or on a snap miss.
  snapped_u       text,
  snapped_v       text,
  snapped_eid     integer,
  snap_dist_m     double precision,
  osm_id          text,

  -- Full versioned client snapshot (schema 1). Keys are kept even when unused.
  payload         jsonb not null,

  applied         text not null default 'none'
                  check (applied in ('none', 'personal', 'global')),
  -- Desk replay (EXPO_PUBLIC_NAV_SIMULATE): stored, never routed on.
  simulate        boolean not null default false,
  -- Test build (EXPO_PUBLIC_RIDE_REPORT_PERSONAL_ONLY): drives that user's own
  -- routing but is excluded from every global aggregate.
  personal_only   boolean not null default false,
  created_at      timestamptz not null default now()
);

create index if not exists ride_reports_created_at_idx
  on public.ride_reports (created_at desc);

create index if not exists ride_reports_user_id_idx
  on public.ride_reports (user_id)
  where user_id is not null;

create index if not exists ride_reports_device_id_idx
  on public.ride_reports (device_id)
  where device_id is not null;

create index if not exists ride_reports_category_created_at_idx
  on public.ride_reports (category, created_at desc);

-- No spatial index: corroboration runs in Python over the rows pulled into RAM
-- (crowd_overlays.rebuild_global), so earthdistance/PostGIS stays unrequired.

alter table public.ride_reports enable row level security;

-- No policies for authenticated/anon — only service role can read/write.
-- (Explicit deny by omitting policies while RLS is enabled.)

-- Table privileges (RLS bypass still needs GRANTs on some projects).
grant select, insert, update on public.ride_reports to service_role;
grant usage on schema public to service_role;
