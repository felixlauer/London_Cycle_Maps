-- Tuned Cycling — user bug reports
-- Run in Supabase SQL Editor (or `supabase db push` via CLI).
--
-- Flask writes with the SERVICE ROLE key (RLS bypassed). Tenancy/abuse
-- control is application-layer (optional user_id from JWT + rate limits).
-- RLS below is defense-in-depth against direct PostgREST/anon access:
-- no anon/authenticated insert/select via the public API.

create table if not exists public.bug_reports (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users (id) on delete set null,
  message     text not null,
  page_url    text,
  user_agent  text,
  app_version text,
  theme       text,
  viewport    text,
  created_at  timestamptz not null default now(),

  constraint bug_reports_message_len check (
    char_length(message) >= 10 and char_length(message) <= 1500
  )
);

create index if not exists bug_reports_created_at_idx
  on public.bug_reports (created_at desc);

create index if not exists bug_reports_user_id_idx
  on public.bug_reports (user_id)
  where user_id is not null;

alter table public.bug_reports enable row level security;

-- No policies for authenticated/anon — only service role can read/write.
-- (Explicit deny by omitting policies while RLS is enabled.)

-- Table privileges (RLS bypass still needs GRANTs on some projects).
grant select, insert on public.bug_reports to service_role;
grant usage on schema public to service_role;
