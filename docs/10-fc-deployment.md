# 阿里云 FC 部署总结（2026-08）

> 本文是「后端从 Render 迁移到阿里云函数计算 FC」的**状态快照 + 操作手册**，供后续对话直接参考。
> 配套：`deploy/Dockerfile`、`deploy/render.yaml`、`docs/07-deployment-guide.md`。

## 一、背景与目标

- **问题**：Render 服务器在海外，A 股数据源（东财/巨潮/新浪）反爬拦截海外 IP（SSL 断连/ConnectionError），导致 M4 等模块拉不到真实数据、降级空白。
- **方案**：后端迁到 **阿里云 FC（成都 cn-chengdu，大陆 IP）**，能直连 A 股数据源。
- **数据层**：**Supabase 作为持久缓存**（读穿 + 后台回写 + 增量刷新），不依赖任何后端的实时拉取。

## 二、当前部署状态

| 项 | 值 |
|---|---|
| FC 公网地址 | `https://value-agent-vjdugjsdaa.cn-chengdu.fcapp.run` |
| FC 服务/函数 | 服务 `value-agent` / 函数 `value-agent`（自定义容器） |
| 镜像 | `registry.cn-chengdu.aliyuncs.com/zgy_20223090903005/value-agent:latest`（~197MB, linux/amd64） |
| ACR | 成都个人版，仓库已设为**公开**（FC 拉取无障碍） |
| Render（旧） | `https://stock-agent-1xev.onrender.com` 仍在跑，但海外拉不到数据，仅读 Supabase 缓存 |
| 前端 | `NEXT_PUBLIC_API_BASE` 指向 FC 地址（或 Render，但需数据已预取） |

## 三、Dockerfile 要点（`deploy/Dockerfile`）

```dockerfile
# 国内/香港构建直连 Docker Hub 常 EOF → 用镜像源覆盖基础镜像
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}
ENV PYTHONPATH=/app/src
# 显式装运行时依赖（不 pip install .，避免旧 pip 对 pyproject 的坑）；清华 PyPI 镜像
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi uvicorn pandas numpy akshare litellm "psycopg2-binary" pyyaml pydantic httpx
COPY src ./src      # 依赖前置：改代码只触发秒级 COPY，不重装依赖
COPY config ./config  # quick 等 YAML 工作流需要
# 端口兼容 FC_SERVER_PORT(9000)/Render PORT
CMD ["sh","-c","uvicorn value_agent.main:app --host 0.0.0.0 --port ${FC_SERVER_PORT:-${PORT:-8000}}"]
```

- **镜像瘦身**：运行时不需要的重依赖（scipy/duckdb/chromadb/apscheduler/pandera）已移出核心依赖 → 1.53GB → **197MB**。
- **层缓存**：依赖先装、代码后 COPY → 改代码重建秒级。

## 四、构建 + 推送命令（在稳定网络机器上执行）

```bash
cd /Users/cgcj0907/code/ai/agent
# 国内用 daocloud 基础镜像源；国外（Render CI）可去掉 --build-arg 用默认 docker.io
docker build --platform linux/amd64 --provenance=false \
  --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim \
  -f deploy/Dockerfile \
  -t registry.cn-chengdu.aliyuncs.com/zgy_20223090903005/value-agent:latest .

# 推送（密码 = ACR 访问凭证里的固定密码）
docker login --username=<阿里云账号名> registry.cn-chengdu.aliyuncs.com
docker push registry.cn-chengdu.aliyuncs.com/zgy_20223090903005/value-agent:latest
```

> ⚠️ `--platform linux/amd64` 必加（Mac 是 arm64，FC 要 amd64）；`--provenance=false` 避免 OCI attestation 索引导致 FC 拉取失败。

## 五、FC 控制台配置（手动）

1. 区域切到 **cn-chengdu（成都）**（必须与 ACR 同区域）→ 创建函数 → **Web 函数**。
2. 运行环境：**自定义镜像** → 镜像 `registry.cn-chengdu.aliyuncs.com/zgy_20223090903005/value-agent:latest`。
3. 端口 `9000`；内存 `1024MB`（够用且省）；**超时 `600s`**（默认 300s 偏紧：完整 M1–M11 分析含 LLM 校准 + 实时补行情，
   实测 90~283s，未缓存标的最多可到几分钟，300s 会被 FC 掐断导致前端「卡在价格与估值分位」）；最小实例数 `0`；磁盘默认。
4. 环境变量（**DATABASE_URL 必配**，否则写入走容器本地盘、不进 Supabase）：
   | 变量 | 值 |
   |---|---|
   | `DATABASE_URL` | Supabase Pooler 连接串 |
   | `LLM_API_KEY` | DeepSeek key |
   | `LLM_MODEL` | `deepseek-chat` |
   | `LLM_BASE_URL` | `https://api.deepseek.com/v1` |
   | `CORS_ORIGINS` | `*` |
   | `SESSION_STORE` | `supabase` |
   | `DATA_WRITE_BACK` | **`sync`**（关键：FC 请求结束会回收实例掐掉后台线程，同步写保证落库） |
   | `SUPABASE_URL` | `https://<project-ref>.supabase.co`（**必配**：全局鉴权用它拉 JWKS 验 ES256 token） |
   | `SUPABASE_JWT_SECRET` | 可选：轮换前的 HS256 老 token 回退验签（当前是 ECC 新 key，可不配） |
   | `DAILY_TOKEN` | 可选：`/api/daily` 定时触发器鉴权（请求头 `x-daily-token`） |
5. **HTTP 触发器认证方式必须选「无需认证」**（否则报 `MissingRequiredHeader: Date` / `invalid authorization`）。
6. **应用级全局鉴权**：`/api/*` 现在要求 `Authorization: Bearer <Supabase 登录 token>`（ES256，JWKS 验签；
   可选 `SUPABASE_JWT_SECRET` 兼容轮换前 HS256 老 token）。前端已自动附加 token；`/health` 与
   `/api/daily` 例外（daily 用 `DAILY_TOKEN`）。
6. 改代码后：函数 → 配置 → **修改镜像**重新拉取（**保留现有 URL**；删除重建会换域名）。

## 六、数据层机制

- Supabase 5 张表：`company / financials / daily_price / valuation_history / dividends`。
- **读穿缓存**（`data/manager.py`）：先读 Supabase，缺失才拉实时源（AkShare），拉成功后台回写。
- **同步写入**：`DATA_WRITE_BACK=sync` 时写入在请求内完成（serverless 友好）；本地默认 async。
- **日线增量刷新**：`daily_prices` 有缓存时只拉「最新交易日之后」、只写新增行，失败回退缓存；进程内一次分析只刷新一次。
- **daily 任务只读**：不再批量写行情/估值（见第十节）；`value-agent data update`（手动/CLI）仍可增量写库，
  `daily_update` 对每只股票传 `start=库内最新交易日` 真增量拉取。
- **预取命令**（本地稳定网络跑一次，写全 5 张表）：
  ```bash
  uv run value-agent data fetch <代码>     # 例如：value-agent data fetch 600519
  ```

## 七、已知坑 & 修复记录

| # | 现象 | 原因 | 修复 |
|---|---|---|---|
| 1 | FC 报 `platform unknown` | Mac arm64 构建的 arm64 镜像 | `--platform linux/amd64` |
| 2 | FC 拉取失败 / `accelerated image not ready` | 私有仓库 + 镜像 1.53GB 太大 | 仓库改公开 + 依赖瘦身到 197MB |
| 3 | Docker Hub / PyPI 连不上（EOF/DNS） | 国内/香港网络 | daocloud 基础镜像 + 清华 PyPI 镜像 |
| 4 | 请求报 `Date` 头 / `invalid authorization` | HTTP 触发器是签名认证 | 触发器认证方式改「无需认证」 |
| 5 | 拉到了日线但 Supabase 没数据 | FC 回收实例掐掉 daemon 线程 | `DATA_WRITE_BACK=sync` |
| 6 | 东财日线接口偶发断连 | 裸 requests TLS 指纹被反爬 | 曾用 `curl_cffi` Chrome 伪装直连（**2026-08-07 已移除**，改多源回退链） |
| 7 | quick 工作流 404 | `config/` 没打进镜像 | Dockerfile `COPY config` |
| 8 | `s deploy` 报缺 `aliyunfcdefaultrole` | RAM 角色未创建 | 手动控制台部署（不走 s），或先在 RAM 建角色 |
| 9 | 日线仍偶发 `RemoteDisconnected` | 东财封 FC 出口 IP 时，akshare 回退打**同一个** `push2his.eastmoney.com` 域名 → 回退形同虚设 | `_daily_prices` 改多源回退链：东财 akshare → **新浪** → **腾讯**（独立主机），单位统一归一化（成交量→手、换手率→%） |
| 10 | 请求老「卡在价格与估值分位」、SSE 中途断 | 完整分析超 FC **300s 超时**被掐断 + 存储/实时源无超时可无限挂起 | ① FC 超时提到 600s；② `PostgresMarketStorage` 加 connect_timeout/keepalive/statement_timeout/断线重连；③ 实时源 `_fetch_with_retry` 加 socket 级 45s 超时。**注：日线增量每次补写 + M7 情绪源不设预算，均按用户决策保留**（靠提 FC 超时解决） |
| 9 | 日线仍偶发 `RemoteDisconnected` | 东财封 FC 出口 IP 时，akshare 回退打**同一个** `push2his.eastmoney.com` 域名 → 回退形同虚设 | `_daily_prices` 改多源回退链：东财 akshare → **新浪** → **腾讯**（独立主机），单位统一归一化（成交量→手、换手率→%） |
| 11 | `读 financials/600519 失败：column "bvps" does not exist`（读穿 SELECT 与后台回写 INSERT 都报） | backlog 第二批给 financials 加了 bvps/ncav_ps/rd_ratio/interest_debt_ratio/contract_liability_ratio/ocf_to_np_parent 6 列，但存量 Supabase 表是早先 DDL 建的，`CREATE TABLE IF NOT EXISTS` 不会改已存在表 | `PostgresMarketStorage.__init__` 新增 `_MIGRATIONS`：对 financials 幂等 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 补 6 列（含原 daily_price.turnover）；重新 build/push 后存量库自动补列 |
| 12 | `[cache] financials 后台回写失败：set_session cannot be used inside a transaction` | upsert 的 execute 抛非 OperationalError（如缺列）后事务残留，finally 直接置 `autocommit=True` 触发 psycopg2 set_session 报错，把真正的缺列错误掩盖 | upsert finally 先 `rollback()` 清事务再复位 autocommit；复位失败仅记 debug 日志，不吞原始异常 |
| 13 | `GET /api/sessions/<id>/memo` 500：`TypeError: sequence item 0: expected str instance, dict found` | 8.6 起红队 `permanent_loss_paths` 是结构化 dict（path/veto_candidate/confidence），备忘录 `'；'.join()` 按字符串处理 | `report/memo.py` 对 permanent_loss_paths 做 dict/字符串双兼容渲染（key_assumptions 同步过滤非字符串） |

## 八、快速验证

```bash
curl https://value-agent-vjdugjsdaa.cn-chengdu.fcapp.run/health   # → {"status":"ok"}
# 跑一次分析看 M4：
#  现价有 + 6 个估值方法 → 正常（大陆 IP 拉到全量数据）
#  现价无 + 降级徽标 → 日线没拉到或没缓存（先 data fetch 预取，或看分析依据里的失败原因）
```

## 九、相关文件

- `deploy/Dockerfile`、`deploy/render.yaml`
- `src/value_agent/data/manager.py`（读穿缓存/回写/增量刷新）、`sources/akshare_source.py`（日线多源回退链）、`pipelines/ingest.py`（预取）
- `src/value_agent/cli.py`（`data fetch` / `data ping`）
- 相关 commit：`cf9b5a6`（curl_cffi+sync 写入）、`b48aaf9/3240f8b/df0d76e/cb8d1ee`（Dockerfile 系列）、`c7622a1`（日线增量刷新）


## 十、每日定时任务（FC 定时触发器，替代 GitHub Actions daily.yml）

> **为什么**：GitHub Actions runner 是海外 IP，拉 A 股数据源（东财/巨潮/新浪）经常被断连；
> FC 是大陆 IP（成都），AkShare 已验证可用。FC 自己就能定时，不再依赖 GitHub Actions。
> 同款逻辑：`value-agent daily`（CLI）与 `POST /api/daily`（HTTP）都走 `run_daily_job()`。

### 10.1 代码侧（已完成）

- `src/value_agent/daily.py::run_daily_job()`：读已完成会话 + `monitor_rules` 表（**唯一规则源**，
  不回退会话 JSONB/M8，删除表规则即不再触发）→ 按规则代码**实时拉最新价**判断 → 命中**写回会话 `monitor_hits`**（前端监控中心可读
  + 跨会话记忆，按 (code, rule_type) 去重）→ 按用户推送飞书/企微。
  **不写行情/估值数据**；价格获取失败只跳过不中断。
- `src/value_agent/main.py`：三个入口，任选其一（都走 `run_daily_job()`）：
  - `POST /invoke`：**FC 定时触发器（异步事件）对 Web 函数的实际调用路径**——FC 把控制台「触发消息」
    以 POST /invoke 发来（body 即 `{"action": "daily", "token": "<DAILY_TOKEN>"}`），手动解析兼容非 JSON content-type
  - `POST /`：兼容备用入口（同 /invoke 逻辑）
  - `POST /api/daily`：HTTP 直接调用（curl / FC「HTTP 触发」模式），可选鉴权头 `x-daily-token`
- **按用户通知**：`user_webhooks(user_id, channel, webhook_url)` 表 + `GET/PUT /api/webhooks` +
  `POST /api/webhooks/test`（JWT 鉴权，RLS 隔离）。分析会话从登录 JWT 绑定 `user_id`，M11 规则
  物化时带上归属；每日监控按规则归属推给对应（未配渠道的用户跳过，全局规则走环境变量 webhook）。
  前端「设置 → 通知设置」页面配置飞书/企微 webhook。

### 10.2 FC 控制台配置（异步事件模式，控制台默认样式）

1. 镜像需已包含上述入口（重新 build/push 一次，见第四节）。
2. 函数 `value-agent` → **触发器** → 创建触发器：
   - 类型：**定时触发器**（异步调用）
   - 触发方式：按表单选 **指定时间**（或 自定义 cron，控制台时区已是 `Asia/Shanghai`）
   - 指定时间：`14:00:00`（或你要的时刻；留空日期/星期 = 每天触发）
   - **触发消息**（Event Payload）填：
     ```json
     {"action": "daily", "token": "<你的 DAILY_TOKEN>"}
     ```
     （未设 `DAILY_TOKEN` 就不带 token 字段）
   - ⚠️ FC 定时触发器会把该事件 POST 到 **`/invoke`**（Web 函数事件入口），**不是 `/`**；
     代码已实现 `/invoke`（手动解析 body，兼容任意 content-type）。若 FC 上 `/invoke` 返回 404，
     说明镜像没包含最新代码，需重新 build/push 并「修改镜像」拉取。
3. 环境变量确认已有：`DATABASE_URL`、`SESSION_STORE=supabase`、`DATA_WRITE_BACK=sync`；
   新增可选 `DAILY_TOKEN`（与触发消息里的 token 一致）。
4. 超时 600s 已够用（完整 daily：自选股 ≤100 只增量更新 + 监控，通常 1–3 分钟）。

> 若你的 FC 控制台在创建定时触发器时提供「HTTP 触发」选项，也可以改用：
> 请求方法 `POST` + 路径 `/api/daily` + 请求头 `x-daily-token: <token>`，效果相同。

### 10.3 验证

```bash
# 手动触发一次（未设 DAILY_TOKEN 时）
curl -X POST https://value-agent-vjdugjsdaa.cn-chengdu.fcapp.run/api/daily
# 返回示例
# {"updated": {"daily_price": 60, "valuation_history": 40, "skipped": 3},
#  "session_count": 5, "monitor_events": 1,
#  "events": [{"severity": "info", "rule_type": "price_buy", "company_code": "600519",
#              "company_name": "贵州茅台", "message": "现价 xx ≤ 买入区间 xx，可分批建仓"}],
#  "pushed_channels": ["飞书"], "errors": []}
# 本地等价命令
value-agent daily
```

### 10.4 收尾

- GitHub Actions `daily.yml` 可停用（保留用于保活也可以，但 FC 每日写 Supabase 本身就在保活）。
- 数据源失败会自动降级：记录 `errors`，监控继续用缓存行情，不会 500。
