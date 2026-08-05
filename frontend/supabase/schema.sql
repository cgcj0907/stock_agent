-- Value Agent 前端 M1：用户资料表
-- 在 Supabase Dashboard > SQL Editor 中执行（或本地 supabase CLI 迁移）

-- 1) 用户资料表（与 auth.users 一对一）
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null default '',
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2) 开启行级安全（RLS）——配合 Publishable key 的前端访问
alter table public.profiles enable row level security;

-- 3) RLS 策略：用户只能读写自己的资料
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);

create policy "profiles_insert_own" on public.profiles
  for insert with check (auth.uid() = id);

create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

-- 4) 注册时自动创建资料（security definer 绕开 RLS）
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 5) LLM 服务商配置表（M2）
-- api_key_enc：AES-256-GCM 密文（iv.tag.cipher base64），由前端服务端环境变量 LLM_SETTINGS_ENCRYPTION_KEY 加解密
create table if not exists public.user_llm_settings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  provider text not null,                 -- deepseek / openai / qwen / ollama / custom
  name text not null default '',
  base_url text not null,
  model text not null,
  api_key_enc text not null default '',
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_llm_settings enable row level security;

create policy "llm_settings_select_own" on public.user_llm_settings
  for select using (auth.uid() = user_id);
create policy "llm_settings_insert_own" on public.user_llm_settings
  for insert with check (auth.uid() = user_id);
create policy "llm_settings_update_own" on public.user_llm_settings
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "llm_settings_delete_own" on public.user_llm_settings
  for delete using (auth.uid() = user_id);

-- 每用户最多一个默认服务商
create unique index if not exists user_llm_settings_one_default
  on public.user_llm_settings (user_id) where is_default;

-- 6) 智能体收藏表（M3）
create table if not exists public.agent_favorites (
  user_id uuid not null references auth.users (id) on delete cascade,
  agent_id text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, agent_id)
);

alter table public.agent_favorites enable row level security;

create policy "agent_favorites_select_own" on public.agent_favorites
  for select using (auth.uid() = user_id);
create policy "agent_favorites_insert_own" on public.agent_favorites
  for insert with check (auth.uid() = user_id);
create policy "agent_favorites_delete_own" on public.agent_favorites
  for delete using (auth.uid() = user_id);
