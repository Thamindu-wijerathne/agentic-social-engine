-- Run in Supabase Dashboard → SQL Editor (after 001_published_posts.sql)

alter table public.published_posts
    add column if not exists hashtags jsonb not null default '[]'::jsonb;

create index if not exists idx_published_posts_hashtags
    on public.published_posts using gin (hashtags);
