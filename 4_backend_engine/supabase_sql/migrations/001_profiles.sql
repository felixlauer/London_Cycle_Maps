-- Tuned Cycling — profiles table (schema v2 routing profiles)
-- Run in Supabase SQL Editor (or `supabase db push` via CLI).
--
-- Notes:
-- * Flask talks to this table with the SERVICE ROLE key, which BYPASSES RLS.
--   Tenancy is therefore also enforced at the application layer
--   (profile_store.SupabaseStore adds .eq('user_id', ...) on every user-row
--   query). The RLS policies below are defense-in-depth against direct
--   PostgREST/anon-key access.
-- * System presets (Fast / Safe / Leisure) are rows with is_system = true,
--   user_id = null, and a stable slug (preset_fast / preset_safe /
--   preset_leisure) so existing frontend localStorage ids keep working.

create table if not exists public.profiles (
  id         uuid primary key default gen_random_uuid(),
  -- Stable text id for system presets (preset_fast, ...); null for user rows.
  slug       text unique,
  user_id    uuid references auth.users (id) on delete cascade,
  name       text not null,
  preset     text,                                      -- 'fast' | 'safe' | 'leisure' | null
  bike_type  text not null default 'standard',
  toggles    jsonb not null default '{}'::jsonb,
  weights    jsonb not null,
  is_system  boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- System rows have no owner; user rows must have one.
  constraint profiles_system_ownership check (
    (is_system = true and user_id is null)
    or (is_system = false and user_id is not null)
  ),
  constraint profiles_bike_type check (
    bike_type in ('standard', 'road', 'ebike', 'cargo')
  )
);

create index if not exists profiles_user_id_idx on public.profiles (user_id);
create index if not exists profiles_is_system_idx on public.profiles (is_system) where is_system = true;

-- Keep updated_at fresh on every update.
create or replace function public.profiles_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists profiles_updated_at on public.profiles;
create trigger profiles_updated_at
  before update on public.profiles
  for each row execute function public.profiles_set_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;

-- Anyone (including anon) can read the system presets.
drop policy if exists read_system_presets on public.profiles;
create policy read_system_presets
  on public.profiles for select
  using (is_system = true);

-- Users can read their own profiles.
drop policy if exists read_own_profiles on public.profiles;
create policy read_own_profiles
  on public.profiles for select
  using (auth.uid() = user_id);

-- Users can insert only their own, non-system profiles.
drop policy if exists insert_own_profiles on public.profiles;
create policy insert_own_profiles
  on public.profiles for insert
  with check (auth.uid() = user_id and is_system = false);

-- Users can update only their own, non-system profiles.
drop policy if exists update_own_profiles on public.profiles;
create policy update_own_profiles
  on public.profiles for update
  using (auth.uid() = user_id and is_system = false)
  with check (auth.uid() = user_id and is_system = false);

-- Users can delete only their own, non-system profiles.
drop policy if exists delete_own_profiles on public.profiles;
create policy delete_own_profiles
  on public.profiles for delete
  using (auth.uid() = user_id and is_system = false);

-- ---------------------------------------------------------------------------
-- Table privileges (required for PostgREST / service_role API access)
-- RLS policies above filter rows; these grants let each role touch the table.
-- Without them you get: permission denied for table profiles (SQLSTATE 42501).
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on public.profiles to anon, authenticated, service_role;
