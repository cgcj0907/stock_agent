-- 会话存储表（SessionStore → Supabase，生产用）
-- 可在 Supabase SQL Editor 手动执行；后端 SupabaseStore 启动时也会自动建表
create table if not exists public.sessions (
  id text primary key,
  payload jsonb not null,
  updated_at timestamptz
);
