-- Supabase schema for ATS Score analytics and owner dashboard.
-- Run this in your Supabase SQL editor after creating the project.

create extension if not exists "pgcrypto";

create table if not exists public.analyses (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  user_email text default '',
  filename text not null,
  ats_score numeric(6, 2) default 0,
  keyword_match numeric(6, 2) default 0,
  missing_keywords jsonb default '[]'::jsonb,
  resume_text text default '',
  job_description text default '',
  analysis_result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists analyses_user_id_created_at_idx
  on public.analyses (user_id, created_at desc);

create index if not exists analyses_created_at_idx
  on public.analyses (created_at desc);

create table if not exists public.login_events (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  email text default '',
  provider text default '',
  event_type text not null default 'login',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists login_events_created_at_idx
  on public.login_events (created_at desc);

alter table public.analyses enable row level security;
alter table public.login_events enable row level security;

-- The backend writes with the Supabase service role key, so it bypasses RLS.
-- No public policies are added here on purpose.
