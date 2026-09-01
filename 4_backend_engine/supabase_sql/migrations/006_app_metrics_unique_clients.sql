-- Distinct website clients that committed a route, without storing IPs.
-- Flask HMAC-SHA256s the client IP and sends only a 16-byte hex digest.
-- print_app_metrics.py reads unique_route_clients on app_metrics only —
-- it never selects this table.
--
-- Run in Supabase SQL Editor after 004_app_metrics.sql.
-- Flask writes with the SERVICE ROLE key (RLS bypassed).

alter table public.app_metrics
  add column if not exists unique_route_clients bigint not null default 0;

create table if not exists public.app_metrics_client_hashes (
  hash bytea primary key
);

alter table public.app_metrics_client_hashes enable row level security;

-- No policies for authenticated/anon — only service role can write.
grant insert on public.app_metrics_client_hashes to service_role;
grant usage on schema public to service_role;

-- Replace the one-arg route increment. Extra p_client_hash is optional so
-- an older caller still records distance; uniqueness is skipped when null.
drop function if exists public.app_metrics_record_route(double precision);

create or replace function public.app_metrics_record_route(
  p_distance_m double precision,
  p_client_hash text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted int := 0;
  raw bytea;
begin
  update public.app_metrics
  set routes_computed = routes_computed + 1,
      optimized_distance_m = optimized_distance_m
        + greatest(coalesce(p_distance_m, 0), 0),
      updated_at = now()
  where id = 1;

  if p_client_hash is null
     or length(p_client_hash) <> 32
     or p_client_hash !~ '^[0-9a-f]+$' then
    return;
  end if;

  begin
    raw := decode(p_client_hash, 'hex');
  exception when others then
    return;
  end;

  insert into public.app_metrics_client_hashes (hash)
  values (raw)
  on conflict do nothing;
  get diagnostics inserted = row_count;

  if inserted > 0 then
    update public.app_metrics
    set unique_route_clients = unique_route_clients + 1,
        updated_at = now()
    where id = 1;
  end if;
end;
$$;

revoke all on function public.app_metrics_record_route(double precision, text) from public;
grant execute on function public.app_metrics_record_route(double precision, text) to service_role;
