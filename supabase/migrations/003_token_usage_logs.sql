-- Run in Supabase SQL Editor to persist pipeline token/cost logs.

create table if not exists public.token_usage_logs (
    id uuid primary key default gen_random_uuid(),
    run_source text not null default 'pipeline',
    content_batch_id text,
    publish_batch_id text,
    pipeline_steps jsonb,
    trends_count integer not null default 0,
    research_count integer not null default 0,
    content_count integer not null default 0,
    published_count integer not null default 0,
    by_agent jsonb not null,
    total jsonb not null,
    estimated_cost_usd numeric(12, 6),
    model text,
    publish_dry_run boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists idx_token_usage_logs_created_at
    on public.token_usage_logs (created_at desc);

create index if not exists idx_token_usage_logs_run_source
    on public.token_usage_logs (run_source);

alter table public.token_usage_logs disable row level security;
