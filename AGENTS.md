# AGENTS.md — Agent 协作开发规范

> 本文件是项目内所有 Agent（AI 编程助手）的**总规范**。开始任何任务前先读本文件与相关文档，
> 并按规范维护文档记录。项目文档导航见 [docs/README.md](docs/README.md)。

## 1. 文档体系（先读再动手）

| 文件 | 作用 | 何时读 / 写 |
|---|---|---|
| [docs/README.md](docs/README.md) | 文档导航（阅读顺序） | 每次任务开始 |
| [docs/chat-record.md](docs/chat-record.md) | **对话档案**：每次新对话 + 每轮 1–2 句总结 | 新对话开始 / 每轮结束 |
| [docs/milestones.md](docs/milestones.md) | **里程碑记录**：非常关键性项目进展 | 有关键进展时 |
| [docs/progress.md](docs/progress.md) | 任务清单 + 完整历史日志 | 每完成一个任务 |
| [docs/01-design.md](docs/01-design.md) | 总体设计：理论体系 → 11 模块 | 涉及模块/架构 |
| [docs/04-development-guide.md](docs/04-development-guide.md) | 开发会话工作流 + 里程碑路线图 | 每个里程碑开工前 |
| [docs/05-coding-conventions.md](docs/05-coding-conventions.md) | 工程规范：目录/命名/数据口径/LLM 约束/测试/提交 | 写代码前 |
| [docs/09-module-contracts.md](docs/09-module-contracts.md) | 统一模块契约（五段式 outputs/handoff） | 模块间 handoff / 新增智能体 |

## 2. 会话开始前（必做）

1. 读 [docs/chat-record.md](docs/chat-record.md)，了解最近对话脉络；若这是**新对话**，先在文末新建 `## Chat #N`（主题 + 1–2 句总摘要）并更新「Chat 索引」；
2. 按 [docs/04-development-guide.md](docs/04-development-guide.md) §1.2 模板声明：`目标 / 范围 / 验收标准 / 相关文档`。

## 3. 每轮工作结束后（必做，三处记录）

1. **chat-record.md**：在同一对话内追加 `### 轮次 N`，用 **1–2 句话**总结该轮做了什么 + 结果；
2. **milestones.md**：仅当本次有**非常关键性**进展（体系成型 / 重大方向 / 关键修复 / 上线部署）时，新增 `### 日期 · 标题` + 1–3 行要点；
3. **progress.md**：勾选完成任务并写日期；详细进展追加到「历史变更日志」小节。

## 4. 开发规范

- 架构性改动**先改 docs/ 再写代码**；新增/变更模块先填 [docs/templates/module-spec.md](docs/templates/module-spec.md)，并遵守 [docs/09-module-contracts.md](docs/09-module-contracts.md)；
- 代码遵守 [docs/05-coding-conventions.md](docs/05-coding-conventions.md)：目录/命名、数据口径、LLM 约束、测试、提交规范；
- 每次提交只做一件事；一个里程碑一个提交（或按逻辑拆 2–3 个）；提交信息格式见 04 §1.4（`feat:/fix:/test:/docs:`）；
- 合入前必须验证：后端 `pytest` 全绿 + `ruff` 通过；前端 `tsc` / `eslint` 通过。

## 5. 红线（禁止）

- 不得把 `api_key` 等密钥明文落库 / 写进文档 / 提交；会话序列化必须脱敏；
- 不得在未更新对应记录（chat-record / milestones / progress）的情况下结束会话；
- 不得跳过测试直接提交；数据口径（百分比 vs 小数等）改动必须加回归测试；
- 破坏性操作（删表 / 改 schema / rm / git reset 等）先与用户确认。
