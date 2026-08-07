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
3. 端口 `9000`；内存 `1024MB`（够用且省）；超时 `300s`；最小实例数 `0`；磁盘默认。
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
5. **HTTP 触发器认证方式必须选「无需认证」**（否则报 `MissingRequiredHeader: Date` / `invalid authorization`）。
6. 改代码后：函数 → 配置 → **修改镜像**重新拉取（**保留现有 URL**；删除重建会换域名）。

## 六、数据层机制

- Supabase 5 张表：`company / financials / daily_price / valuation_history / dividends`。
- **读穿缓存**（`data/manager.py`）：先读 Supabase，缺失才拉实时源（AkShare），拉成功后台回写。
- **同步写入**：`DATA_WRITE_BACK=sync` 时写入在请求内完成（serverless 友好）；本地默认 async。
- **日线增量刷新**：`daily_prices` 有缓存时只拉「最新交易日之后」、只写新增行，失败回退缓存；进程内一次分析只刷新一次。
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
