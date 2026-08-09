# 文档导航

> 📌 最新状态：**V2 升级（P1–P5）已全部落地（2026-08-08）**——评分校准 v2、画像 Planner、函数注册表、
> 校准 A/B 与模块级 PIT 回测均已实现，见 [12-v2-upgrade.md](12-v2-upgrade.md)。
> 记录体系：对话脉络见 [chat-record.md](chat-record.md)，非常关键性进展见 [milestones.md](milestones.md)，
> 任务清单与历史日志见 [progress.md](progress.md)；Agent 维护规则见根 [AGENTS.md](../AGENTS.md)。

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
| 9 | [09-module-contracts.md](09-module-contracts.md) | **统一模块契约**（方案 1：强约束标准版）：输入输出规范 / outputs 五段式骨架 / 逐模块 schema / 统一 Prompt / 统一降级态 | 模块间 handoff 与新增智能体时读 |
| 10 | [10-fc-deployment.md](10-fc-deployment.md) | **阿里云 FC 部署**：镜像/Dockerfile/控制台配置/数据层机制/已知坑 | 部署与排查时读 |
| 11 | [11-valuation-backlog.md](11-valuation-backlog.md) | **估值与成长体系改进待办**：未实施项清单（数据门槛/优先级/方案） | 排期估值/成长优化时读 |
| 12 | [12-v2-upgrade.md](12-v2-upgrade.md) | **V2 升级方案（已落地）**：画像 Planner（LLM 规划层）+ 评分校准 v2（delta 制/证据校验/动态上限/档位保护）+ 函数注册表 + 校准 A/B 与模块 PIT 回测 | 维护校准/规划/回测机制时读 |
| 13 | [13-investor-profile-agent.md](13-investor-profile-agent.md) | **投资者画像智能体（M0，可选）**：学历/投资风格/能力圈 → 个人可理解性 + 安全边际/风险注入 | 新增/维护投资者画像与个性化注入时读 |
| 14 | [chat-record.md](chat-record.md) | **对话档案**：每次新对话（Chat）+ 每轮 1–2 句总结（轮次），Agent 自动维护 | 新对话开始 / 每轮结束时更新 |
| 15 | [milestones.md](milestones.md) | **里程碑记录**：非常关键性项目进展（体系成型/重大方向/关键修复/上线部署），Agent 自动维护 | 有关键进展时更新 |
| 16 | [templates/module-spec.md](templates/module-spec.md) | **模块规格模板**：新增/完善模块时填写 | 开发某个模块时 |
| 17 | [progress.md](progress.md) | **任务清单 + 历史日志**：勾选已完成任务并写日期；要点版见 milestones.md | 每个里程碑结束时更新 |

## 开发节奏（一句话版）

> 读 `01-design` → 按 `04-development-guide` 的里程碑推进 → 每完成一个模块填 `templates/module-spec` 规格、
> 跑测试、更新 `progress.md`、提交一次 → 每轮结束把对话总结写进 `chat-record.md`、关键进展写进 `milestones.md` →
> 智能体与工作流见 `02-agent-architecture`，会话管理见 `03-session-management`，工程细节见 `05-coding-conventions`。
