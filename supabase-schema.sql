-- Run this in Supabase SQL Editor

create extension if not exists pgcrypto;

create table if not exists public.matches (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  sport text not null,
  location text not null,
  start_time timestamptz not null,
  lock_time timestamptz,
  max_players int not null check (max_players >= 2),
  duration_minutes int not null default 90 check (duration_minutes >= 30),
  created_at timestamptz not null default now()
);

create table if not exists public.participants (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  name text not null,
  email text not null,
  phone text not null,
  status text not null check (status in ('joined','waitlist','left')),
  created_at timestamptz not null default now()
);

create index if not exists idx_participants_match on public.participants(match_id);
create index if not exists idx_matches_start on public.matches(start_time);

create or replace view public.running_matches as
select
  m.*,
  (m.start_time + make_interval(mins => m.duration_minutes)) as end_time
from public.matches m;

-- For fast hackathon demo, allow public read/write using anon key.
-- Later, tighten with auth-based RLS.
alter table public.matches enable row level security;
alter table public.participants enable row level security;

drop policy if exists "public read matches" on public.matches;
create policy "public read matches"
on public.matches for select
using (true);

drop policy if exists "public insert matches" on public.matches;
create policy "public insert matches"
on public.matches for insert
to anon
with check (true);

drop policy if exists "public update matches" on public.matches;
create policy "public update matches"
on public.matches for update
to anon
using (true)
with check (true);

drop policy if exists "public read participants" on public.participants;
create policy "public read participants"
on public.participants for select
using (true);

drop policy if exists "public insert participants" on public.participants;
create policy "public insert participants"
on public.participants for insert
to anon
with check (true);

drop policy if exists "public update participants" on public.participants;
create policy "public update participants"
on public.participants for update
to anon
using (true)
with check (true);

-- Optional: prevent duplicate active participant in same match by email.
create unique index if not exists uniq_active_email_per_match
on public.participants(match_id, lower(email))
where status <> 'left';

-- Optional: prevent duplicate active participant in same match by phone.
create unique index if not exists uniq_active_phone_per_match
on public.participants(match_id, phone)
where status <> 'left';
