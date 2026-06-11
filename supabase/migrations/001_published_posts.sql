-- Run this in Supabase SQL Editor to track published Facebook posts.

create table if not exists public.published_posts (
    id uuid primary key default gen_random_uuid(),
    facebook_post_id text not null unique,
    title text not null,
    description text,
    picture_url text,
    category text,
    content_batch_id text,
    publish_batch_id text,
    status text not null default 'published' check (status in ('published', 'failed', 'deleted')),
    dry_run boolean not null default false,
    error text,
    published_at timestamptz not null default now(),
    deleted_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists idx_published_posts_facebook_post_id
    on public.published_posts (facebook_post_id);

create index if not exists idx_published_posts_status
    on public.published_posts (status);

create index if not exists idx_published_posts_published_at
    on public.published_posts (published_at desc);

-- Optional: allow service role full access (backend uses secret key).
alter table public.published_posts enable row level security;

create policy "Service role can manage published_posts"
    on public.published_posts
    for all
    using (true)
    with check (true);
