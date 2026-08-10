-- 会话存储表（SessionStore → Supabase，生产用）
-- 可在 Supabase SQL Editor 手动执行；后端 SupabaseStore 启动时也会自动建表
create table if not exists public.sessions (
  id text primary key,
  payload jsonb not null,
  updated_at timestamptz
);

-- 监控规则表（M11 物化；后端 SupabaseRuleStore 启动时也会自动建表）
-- user_id 为空 = 系统/全局规则；前端用户编辑后归属 auth.users
create table if not exists public.monitor_rules (
  id uuid primary key default gen_random_uuid(),
  session_id text not null,
  company_code text not null,
  company_name text not null default '',
  rule_type text not null,
  source_module text not null default '',
  trigger text not null default '',
  message text not null default '',
  severity text not null default 'info',
  action text not null default 'watch',
  params jsonb not null default '{}'::jsonb,
  user_id uuid references auth.users (id) on delete cascade,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists monitor_rules_session_idx on public.monitor_rules (session_id);
create index if not exists monitor_rules_company_idx on public.monitor_rules (company_code, active);

-- 用户通知渠道（每个登录用户配自己的飞书/企微 webhook；后端 SupabaseUserWebhookStore 自动建表）
create table if not exists public.user_webhooks (
  user_id uuid not null references auth.users (id) on delete cascade,
  channel text not null check (channel in ('feishu', 'wechat')),
  webhook_url text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, channel)
);

-- 前端报告/备忘录导出页直接读取 sessions（payload 为 session.to_dict()，已剔除 api_key）。
-- 建议启用 RLS，仅允许会话归属用户读取：auth.uid() = payload->>'user_id'（后端走服务角色不受影响）。
-- 在 Supabase SQL Editor 执行一次即可。
alter table if exists public.sessions enable row level security;
drop policy if exists "owner_read_sessions" on public.sessions;
create policy "owner_read_sessions" on public.sessions
  for select
  using ((payload ->> 'user_id')::uuid = auth.uid());

-- 用户通知渠道同样启用 RLS：仅本人可读写（前端设置页/监控中心直读；后端服务角色不受影响）。
alter table if exists public.user_webhooks enable row level security;
drop policy if exists "owner_webhooks" on public.user_webhooks;
create policy "owner_webhooks" on public.user_webhooks
  for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
