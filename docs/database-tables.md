# 数据库建表语句总览

> 全项目 **CREATE TABLE 建表语句**整理索引：每张表「用途 / 定义文件 / 主键 / 索引 / RLS」一目了然。
> 整理日期：2026-08-11。规则：新增/变更表结构时，先改「单一事实源」，再同步本文件与对应 SQL。

## 0. 文件地图（谁定义了什么）

| 文件 | 定位 | 建的表 | 维护方式 |
|---|---|---|---|
| `src/value_agent/data/storage/base.py`（`SCHEMA`） | 行情/财务表**唯一事实源** | 9 张（见 §1） | 改这里，再 `python -m value_agent data ddl` 重新生成 |
| `data/schema.sql` | SCHEMA 生成的副本（脚本参考用） | 同 §1 | 自动生成，**请勿手改** |
| `src/value_agent/data/schema.sql` | SCHEMA 生成的副本（部署文档引用） | 同 §1 | 自动生成，**请勿手改** |
| `frontend/supabase/schema.sql` | 前端应用表基线（登录/会话/监控） | 9 张（见 §2） | 手动维护；含 RLS、存储桶、触发器 |
| `frontend/supabase/migrations/` | 增量迁移（已并入 schema.sql，老库升级用） | add_profile_fields / add_avatar_storage | 手动维护 |
| `deploy/supabase_sessions.sql` | 会话存储表（生产手动建表参考） | sessions（见 §3） | 手动维护 |

> 后端启动时也会自动建表（`PostgresMarketStorage` / `SupabaseStore` / `SupabaseRuleStore` /
> `SupabaseUserWebhookStore`），SQL 文件是「手动建表 / 部署参考」；两边都用
> `CREATE TABLE IF NOT EXISTS`，不会冲突。

## 1. 行情/财务数据表（9 张，SCHEMA 生成）

| 表 | 用途 | 主键 | 索引 | 字段 |
|---|---|---|---|---|
| `company` | 公司主档 | `code` | — | code, ts_code, name, industry, list_date, updated_at |
| `financials` | 财务报表（合并口径） | `(code, period)` | — | code, period, roe, grossprofit_margin, netprofit_margin, debt_to_assets, ocfps, eps, ocf_to_np, bvps, ncav_ps, rd_ratio, interest_debt_ratio, contract_liability_ratio, ocf_to_np_parent, updated_at |
| `daily_price` | 日行情 | `(code, trade_date)` | `idx_daily_price_code_date` | code, trade_date, open, close, high, low, volume, turnover, updated_at |
| `valuation_history` | 估值历史（PE/PB 等） | `(code, trade_date)` | `idx_valuation_history_code_date` | code, trade_date, pe, pe_ttm, pb, ps, dv_ttm, total_mv, updated_at |
| `dividends` | 分红送转 | `(code, period)` | — | code, period, cash_div_tax, div_proc, updated_at |
| `northbound` | 北向资金个股持股 | `(code, trade_date)` | — | code, trade_date, hold_shares, hold_ratio, updated_at |
| `margin` | 个股两融余额 | `(code, trade_date)` | — | code, trade_date, margin_balance, fin_balance, sec_balance, updated_at |
| `governance_events` | 治理事件（质押/减持/监管等） | `(code, event_date, kind)` | — | code, event_date, kind, holder, ratio, description, updated_at |
| `watchlist` | 自选股池（与 config/watchlist.yaml 对应） | `code` | — | code, name, added_at |

> 数值列用 `DOUBLE PRECISION`，其余 `TEXT`；所有表带 `updated_at TIMESTAMPTZ DEFAULT now()`（watchlist 除外）。
> 单一事实源 = `base.py` 的 `SCHEMA`，生成函数 `generate_pg_ddl()`。

## 2. 前端应用表（9 张，frontend/supabase/schema.sql）

| 表 | 用途 | 主键 | 索引 | RLS 策略 |
|---|---|---|---|---|
| `profiles` | 用户资料（与 auth.users 一对一，注册触发器自动建行） | `id → auth.users(id)` | — | select/insert/update own |
| `user_llm_settings` | LLM 服务商配置（api_key 存 AES-256-GCM 密文） | `id` | 唯一索引 `user_llm_settings_one_default (user_id) WHERE is_default` | select/insert/update/delete own |
| `agent_favorites` | 智能体收藏 | `(user_id, agent_id)` | — | select/insert/delete own |
| `conversations` | 会话记录（M4 落库） | `id` | `session_id` 唯一 | select/insert/update/delete own |
| `custom_workflows` | 自定义工作流 | `id` | — | select/insert/update/delete own |
| `messages` | 对话消息 | `id` | `messages_conversation_idx (conversation_id, created_at)` | select/insert/delete own |
| `memos` | 投资备忘录（按版本覆盖） | `id` | `memos_conversation_idx (conversation_id, version)` | select/insert/delete own |
| `monitor_rules` | 监控规则（M11 物化；user_id 空 = 全局规则） | `id` | `monitor_rules_session_idx (session_id)`、`monitor_rules_company_idx (company_code, active)` | select(含全局)/insert/update/delete |
| `user_webhooks` | 用户通知渠道（飞书/企微 webhook） | `(user_id, channel)`，channel 有 check | — | select/insert/update/delete own |

> 该文件还包含：`storage.buckets` 头像桶（avatars）、`storage.objects` 4 条 RLS 策略、
> `handle_new_user()` 触发器函数 + `on_auth_user_created` 触发器。

## 3. 会话存储表（deploy/supabase_sessions.sql）

| 表 | 用途 | 主键 | 索引 | RLS 策略 |
|---|---|---|---|---|
| `sessions` | 会话持久化（SessionStore → Supabase，payload 为 session.to_dict() 已剔除 api_key） | `id`（text） | — | `owner_read_sessions`：仅 `payload->>'user_id'` 归属用户可读 |

## 4. 去重与单一事实源说明（2026-08-11 整理）

1. **monitor_rules / user_webhooks**：原本在 `deploy/supabase_sessions.sql` 与 `frontend/supabase/schema.sql`
   各定义一份，易漂移。已**去重**——定义与 RLS 统一归 `frontend/supabase/schema.sql`，
   `deploy/supabase_sessions.sql` 只保留 `sessions`（后端启动仍会自动建表，互不影响）。
2. **data/schema.sql 与 src/value_agent/data/schema.sql**：内容完全一致，均由 `SCHEMA` 生成。
   保留两份分别供 `scripts/backtest_module.py` 参考与部署文档引用；改表结构只改 `base.py` 的 `SCHEMA` 后重新生成。
3. **frontend/supabase/migrations/**：`add_profile_fields.sql` / `add_avatar_storage.sql` 的变更
   已全部并入 `frontend/supabase/schema.sql`，仅作为老库增量升级保留。

## 5. 使用建议

- 新部署：依次执行 `src/value_agent/data/schema.sql` → `frontend/supabase/schema.sql` → `deploy/supabase_sessions.sql`。
- 改行情表：只改 `src/value_agent/data/storage/base.py` 的 `SCHEMA`，再 `python -m value_agent data ddl > src/value_agent/data/schema.sql`（并同步 data/schema.sql）。
- 改应用表：直接改 `frontend/supabase/schema.sql`，需要老库增量时再补 migrations 文件。
