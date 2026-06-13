-- Run this AFTER 001_published_posts.sql to confirm the table exists.

select table_schema, table_name
from information_schema.tables
where table_schema = 'public'
  and table_name = 'published_posts';

select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'published_posts'
order by ordinal_position;
