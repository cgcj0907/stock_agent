-- 会话存储表（SessionStore → Supabase，生产用）
-- 可在 Supabase SQL Editor 手动执行；后端 SupabaseStore 启动时也会自动建表
--
-- 整理说明（2026-08-11）：
--  · monitor_rules / user_webhooks 的定义与 RLS 已统一维护在 frontend/supabase/schema.sql，
--    此处不再重复建表（避免两处定义漂移）；后端 SupabaseRuleStore / SupabaseUserWebhookStore
--    启动时同样会自动建表。
--  · 全项目建表语句总览见 docs/database-tables.md。
create table if not exists public.sessions (
  id text primary key,
  payload jsonb not null,
  updated_at timestamptz
);

-- 前端报告/备忘录导出页直接读取 sessions（payload 为 session.to_dict()，已剔除 api_key）。
-- 建议启用 RLS，仅允许会话归属用户读取：auth.uid() = payload->>'user_id'（后端走服务角色不受影响）。
-- 在 Supabase SQL Editor 执行一次即可。
alter table if exists public.sessions enable row level security;
drop policy if exists "owner_read_sessions" on public.sessions;
create policy "owner_read_sessions" on public.sessions
  for select
  using ((payload ->> 'user_id')::uuid = auth.uid());
