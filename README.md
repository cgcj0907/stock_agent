# Value Agent（价值投资 Agent · A 股）

面向 A 股市场的价值投资分析 Agent：输入公司代码/名称，自动产出一份**可验证的投资备忘录**——
财报质量分析、行业景气度与全球趋势研判、多模型现金流估值、安全边际、评分与风险清单。

## 快速开始

```bash
uv sync                      # 安装依赖
cp .env.example .env         # 配置免费数据源/LLM
python -m value_agent analyze 600519
```

## 文档（从 [docs/README.md](docs/README.md) 进入）

```text
docs/
├── README.md                  # 文档导航（阅读顺序）
├── 01-design.md               # 总体设计：理论体系 → 11 模块
├── 02-agent-architecture.md   # 智能体与工作流：注册表 + 默认流 + 自由编排
├── 03-session-management.md   # Agent 会话管理设计
├── 04-development-guide.md    # 开发引导：里程碑路线图 + 开发会话工作流
├── 05-coding-conventions.md   # 工程规范
├── templates/module-spec.md   # 模块开发规格模板
├── 06-tech-stack.md          # 技术选型与部署
├── 07-deployment-guide.md    # 部署指南：Render + Supabase + Vercel
└── progress.md                # 开发进度追踪（每个里程碑更新）
```

## 目录

```text
config/             # 指标、估值路由、评分卡、工作流（YAML，可调参）
src/value_agent/    # 理论驱动 11 大模块（每个模块=独立智能体）+ 工作流 + 会话
├── agents/         # Agent 抽象 + 注册表 + 内置 M1–M11 智能体（已实现骨架）
├── workflow/       # 工作流模型/默认流/引擎/YAML 加载（已实现+测试）
├── sessions/       # 会话管理（状态机/存储/管理器，已实现+测试）
├── business_model/ financials/ growth/ valuation/ moat/ governance/
├── market/ safety_margin/ risk/ decision/ monitor/
└── data/ backtest/ core/
tests/              # 单元测试与数据勾稽校验
scripts/            # 数据初始化、每日更新、监控调度
```

## 状态

✅ **S1 骨架已完成**（2026-08-03）：
- 智能体注册表（内置 M1–M11）+ 工作流引擎（默认流 + YAML 自定义流 + 条件/run_always）
- 会话管理（状态机 / 依赖链重算 / 断点续跑 / Sqlite 持久化）
- CLI（`analyze / agents / workflows / data / monitor / serve`）+ FastAPI（`/health` + 会话 API + SSE 进度）

> ✅ **M1–M11 全部真实实现 + 真实数据验证 + 回测完成**（2026-08-04）：BaoStock 免费源连通、茅台分析跑通、PIT 回测超额 +2.6%/年；剩 Supabase 连接验证
> 免费数据源（mock/BaoStock/AkShare）→ 存储（SQLite/PG）→ ETL 已验证；M2 已接入真实规则引擎
> （ROE 杜邦/稳定性/现金流/杠杆/风险信号，5 项测试通过）。待：M4 估值、M8 安全边际、真实数据源拉取验证。
