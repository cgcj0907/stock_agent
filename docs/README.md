# 文档导航

按阅读顺序使用：

| # | 文档 | 内容 | 何时读 |
|---|---|---|---|
| 1 | [01-design.md](01-design.md) | **总体设计**：价值投资理论体系 → 11 个模块、指标库、估值路由、评分卡 | 开始前必读 |
| 2 | [02-agent-architecture.md](02-agent-architecture.md) | **智能体与工作流**：M1–M11 独立智能体、注册表、默认工作流、自由编排 | 开发 S1 前读 |
| 3 | [03-session-management.md](03-session-management.md) | **Agent 会话管理**：会话生命周期、状态机、追问/重算/断点续跑、API | 开发 S1 前读 |
| 4 | [04-development-guide.md](04-development-guide.md) | **开发引导**：里程碑路线图、开发会话工作流、模块开发流程、验收标准 | 每个里程碑开工前读 |
| 5 | [05-coding-conventions.md](05-coding-conventions.md) | **工程规范**：目录/命名、数据口径、LLM 约束、测试、提交规范 | 写代码前读 |
| 6 | [06-tech-stack.md](06-tech-stack.md) | **技术选型与部署**：前后端/数据库选型、Render+Supabase+Vercel 选型依据、备选方案 | 准备上线前读 |
| 7 | [07-deployment-guide.md](07-deployment-guide.md) | **部署指南**：Render(后端) + Supabase(数据库) + Vercel(前端) 操作手册、配置文件模板 | 实际部署时照着做 |
| 8 | [08-frontend-plan.md](08-frontend-plan.md) | **前端规划**：Next.js + Vercel 前端设计与实施计划（素材库/设计系统/路由/数据模型/里程碑） | 写前端前必读 |
| 6 | [templates/module-spec.md](templates/module-spec.md) | **模块规格模板**：新增/完善模块时填写 | 开发某个模块时 |
| 7 | [progress.md](progress.md) | **开发进度追踪**：勾选已完成任务，记录日期 | 每个里程碑结束时更新 |

## 开发节奏（一句话版）

> 读 `01-design` → 按 `04-development-guide` 的里程碑推进 → 每完成一个模块填 `templates/module-spec` 规格、
> 跑测试、更新 `progress.md`、提交一次 → 智能体与工作流见 `02-agent-architecture`，
> 会话管理见 `03-session-management`，工程细节见 `05-coding-conventions`。
