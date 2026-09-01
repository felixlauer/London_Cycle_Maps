-- Tuned Cycling — aggregate product metrics (sessions, routes, distance).
-- Run in Supabase SQL Editor (or `supabase db push` via CLI).
--
-- Counts only — no user IDs, IPs, or route geometries.
-- Flask writes with the SERVICE ROLE key (RLS bypassed).

create table if not exists public.app_metrics (
  id                      int primary key default 1 check (id = 1),
  sessions                bigint not null default 0,
  routes_computed         bigint not null default 0,
  optimized_distance_m    double precision not null default 0,
  updated_at              timestamptz not null default now()
);

insert into public.app_metrics (id)
values (1)
on conflict (id) do nothing;

alter table public.app_metrics enable row level security;

-- No policies for authenticated/anon — only service role can read/write.

grant select, update on public.app_metrics to service_role;
grant usage on schema public to service_role;

-- Atomic increments (called from Flask via supabase-py .rpc).

create or replace function public.app_metrics_record_session()
returns void
language sql
security definer
set search_path = public
as $$
  update public.app_metrics
  set sessions = sessions + 1,
      updated_at = now()
  where id = 1;
$$;

create or replace function public.app_metrics_record_route(p_distance_m double precision)
returns void
language sql
security definer
set search_path = public
as $$
  update public.app_metrics
  set routes_computed = routes_computed + 1,
      optimized_distance_m = optimized_distance_m + greatest(coalesce(p_distance_m, 0), 0),
      updated_at = now()
  where id = 1;
$$;

revoke all on function public.app_metrics_record_session() from public;
revoke all on function public.app_metrics_record_route(double precision) from public;
grant execute on function public.app_metrics_record_session() to service_role;
grant execute on function public.app_metrics_record_route(double precision) to service_role;
