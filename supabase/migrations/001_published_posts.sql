-- Run in Supabase Dashboard → SQL Editor → New query → Run
-- Table appears under: Table Editor → schema "public" → published_posts

create table if not exists public.published_posts (
    id uuid primary key default gen_random_uuid(),
    facebook_post_id text not null unique,
    title text not null,
    description text,
    picture_url text,
    category text,
    content_batch_id text,
    publish_batch_id text,
    status text not null default 'published',
    dry_run boolean not null default false,
    error text,
    published_at timestamptz not null default now(),
    deleted_at timestamptz,
    created_at timestamptz not null default now(),
    constraint published_posts_status_check
        check (status in ('published', 'failed', 'deleted'))
);

create index if not exists idx_published_posts_facebook_post_id
    on public.published_posts (facebook_post_id);

create index if not exists idx_published_posts_status
    on public.published_posts (status);

create index if not exists idx_published_posts_published_at
    on public.published_posts (published_at desc);

-- Backend uses SUPABASE_SECRET_KEY (service role) — bypasses RLS.
-- Keep RLS off for simplicity; enable later if you add client-side access.
alter table public.published_posts disable row level security;

-- Verify (should return 1 row):
-- select table_name from information_schema.tables
-- where table_schema = 'public' and table_name = 'published_posts';
