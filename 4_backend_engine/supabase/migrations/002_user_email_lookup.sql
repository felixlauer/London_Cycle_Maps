-- Lookup helper for password-reset email validation (service role only).
-- Run in Supabase SQL Editor after 001_profiles.sql.

create or replace function public.user_exists_by_email(check_email text)
returns boolean
language sql
security definer
set search_path = auth, public
stable
as $$
  select exists (
    select 1
    from auth.users u
    where lower(u.email) = lower(trim(check_email))
  );
$$;

revoke all on function public.user_exists_by_email(text) from public;
grant execute on function public.user_exists_by_email(text) to service_role;
