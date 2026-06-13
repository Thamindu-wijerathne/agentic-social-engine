-- =============================================================================
-- Agentic Social Engine — full Supabase schema (fresh install)
-- =============================================================================
-- Run in: Supabase Dashboard → SQL Editor → New query → Run
--
-- Use this when setting up from scratch or after dropping old tables.
-- Backend uses SUPABASE_SECRET_KEY (service role) — RLS stays disabled.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Reset (drops existing data)
-- -----------------------------------------------------------------------------
drop table if exists public.published_posts cascade;
drop table if exists public.token_usage_logs cascade;

-- -----------------------------------------------------------------------------
-- published_posts — Facebook publish trace (immediate + scheduled)
-- -----------------------------------------------------------------------------
create table public.published_posts (
    id uuid primary key default gen_random_uuid(),
    facebook_post_id text not null unique,
    title text not null,
    description text,
    picture_url text,
    picture_urls jsonb not null default '[]'::jsonb,
    category text,
    hashtags jsonb not null default '[]'::jsonb,
    content_batch_id text,
    publish_batch_id text,
    status text not null default 'published',
    dry_run boolean not null default false,
    error text,
    published_at timestamptz not null default now(),
    scheduled_publish_at timestamptz,
    deleted_at timestamptz,
    created_at timestamptz not null default now(),
    constraint published_posts_status_check
        check (status in ('published', 'scheduled', 'failed', 'deleted'))
);

create index idx_published_posts_facebook_post_id
    on public.published_posts (facebook_post_id);

create index idx_published_posts_status
    on public.published_posts (status);

create index idx_published_posts_published_at
    on public.published_posts (published_at desc);

create index idx_published_posts_scheduled_publish_at
    on public.published_posts (scheduled_publish_at desc);

create index idx_published_posts_content_batch_id
    on public.published_posts (content_batch_id);

create index idx_published_posts_hashtags
    on public.published_posts using gin (hashtags);

create index idx_published_posts_picture_urls
    on public.published_posts using gin (picture_urls);

alter table public.published_posts disable row level security;

-- -----------------------------------------------------------------------------
-- token_usage_logs — pipeline LLM token / cost history
-- -----------------------------------------------------------------------------
create table public.token_usage_logs (
    id uuid primary key default gen_random_uuid(),
    run_source text not null default 'pipeline',
    content_batch_id text,
    publish_batch_id text,
    pipeline_steps jsonb,
    trends_count integer not null default 0,
    research_count integer not null default 0,
    content_count integer not null default 0,
    published_count integer not null default 0,
    by_agent jsonb not null default '{}'::jsonb,
    total jsonb not null default '{}'::jsonb,
    estimated_cost_usd numeric(12, 6),
    model text,
    publish_dry_run boolean not null default false,
    created_at timestamptz not null default now()
);

create index idx_token_usage_logs_created_at
    on public.token_usage_logs (created_at desc);

create index idx_token_usage_logs_run_source
    on public.token_usage_logs (run_source);

create index idx_token_usage_logs_content_batch_id
    on public.token_usage_logs (content_batch_id);

alter table public.token_usage_logs disable row level security;

-- -----------------------------------------------------------------------------
-- Verify (optional — should return 2 tables)
-- -----------------------------------------------------------------------------
-- select table_name
-- from information_schema.tables
-- where table_schema = 'public'
--   and table_name in ('published_posts', 'token_usage_logs')
-- order by table_name;
