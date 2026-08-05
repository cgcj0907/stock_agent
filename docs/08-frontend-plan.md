# Vercel 前端规划：Next.js + TypeScript（智能体分析平台）

> 面向「Value Agent（价值投资 Agent · A 股）」的可视化前端，部署到 Vercel。
> 后端为现有 FastAPI（Render）+ Supabase（PostgreSQL），本文是前端的设计与实施计划。
> 阅读顺序：先看本文「2 素材库」与「3 设计系统」确认视觉基调，再按「8 里程碑」开发。

---

## 1. 目标与需求映射

| # | 需求 | 前端落点 | 后端现状 | 需新增/改动 |
|---|---|---|---|---|
| 1 | 自己配置 LLM 服务商和 API | `/settings/llm` 配置页：多服务商（DeepSeek/OpenAI/Qwen/Ollama/自定义）增删改查 + 默认服务商 + 连通性测试 | LLM 仅读环境变量（`core/llm.py`），全局单例 | 后端支持**按会话/按用户注入 LLM 配置**（新 API 或 `CreateSessionRequest` 加 `llm_config` 字段） |
| 2 | 智能体广场 | `/agents` 广场 + `/agents/[id]` 详情：M1–M11 + 自定义智能体，卡片/搜索/筛选/收藏/发起分析 | `GET /api/agents` 已返回全部 AgentSpec | 前端直接消费；「收藏」需新建 `agent_favorites` 表 |
| 3 | 工作流分析 | `/workflows` 列表 + `/workflows/[id]` 分析页（DAG 可视化 + SSE 进度 + 结果/备忘录）+ `/workflows/builder` 编排器（V2） | `GET /api/workflows`、`POST /api/sessions`、SSE `/api/sessions/{id}/events` 已就绪 | 前端主战场；自定义工作流保存需新建 `custom_workflows` 表 + 后端加载接口 |
| 4 | 用户注册 | `/register`、`/login`、`/forgot-password`，受保护路由 | 后端会话 API 无鉴权 | 接入 **Supabase Auth**（与现有 Supabase 同栈）；会话归属用前端 `conversations` 表关联 `user_id` |
| 5 | 用户对话记录 | `/conversations` 列表（状态/时间/搜索/操作）+ `/conversations/[id]` 详情（聊天 + 模块结果 + 备忘录） | `GET/POST /api/sessions` 等已就绪 | 前端建 `conversations` / `messages` 表做用户维度索引（后端 session 仍为主数据） |

---

## 2. 素材库（视觉/功能资产清单）⭐

> 选型原则：**免费、中文友好、与 Next.js App Router + Tailwind v4 兼容、控制包体积**。
> 核心组合：**shadcn/ui + Tailwind v4 + Lucide + Geist/Noto Sans SC + React Flow + ECharts + Motion**。

### 2.1 UI 组件库（三选一，推荐 shadcn/ui）

| 方案 | 版本 | 说明 | 结论 |
|---|---|---|---|
| **shadcn/ui** ✅ | 最新（React 19 + Tailwind 4） | 源码复制进项目、100% 可定制，Radix UI 无障碍底层；中文生态教程多 | **首选**：换肤（亮/暗）、品牌化最容易 |
| Ant Design | v5 | 中文生态、表格/表单开箱即用；但风格偏重、与 Tailwind 共存需适配 | 备选（团队熟 AntD 再用） |
| MUI | v7 | 组件全但体积大、Material 风格辨识度高 | 不推荐（与「金融数据感」审美有偏差） |

### 2.2 图标

| 库 | 说明 |
|---|---|
| **Lucide React** ✅ | 轻量、线性风格、与 shadcn 默认一致 |
| Heroicons | 可选补充（粗线风格） |
| Tabler Icons | 可选补充（图标更全，股票/图表类图标多） |

### 2.3 字体

| 字体 | 用途 | 加载方式 |
|---|---|---|
| **Geist Sans** ✅ | 英文/数字 UI 字体（Vercel 官方） | `next/font/google` 或本地包，自动子集化 |
| **Geist Mono** ✅ | 代码、数字、指标表 | `next/font` |
| **Noto Sans SC** ✅ | 中文正文（A 股用户） | `next/font/google` 子集化，控制体积 |
| JetBrains Mono | 可选备选等宽字体 | — |

### 2.4 动效与质感

| 库 | 用途 |
|---|---|
| **Motion (framer-motion)** ✅ | 页面过渡、卡片入场、进度动效 |
| **Aceternity UI / Magic UI** | 灵感素材（渐变按钮、spotlight、bento grid），按需手抄样式 |
| CSS 渐变 + 玻璃拟态 | 品牌横幅、Agent 卡片背景（纯 CSS，零依赖） |

### 2.5 图表（金融数据）

| 库 | 用途 |
|---|---|
| **ECharts (echarts + echarts-for-react 或按需引入)** ✅ | K 线、PE/PB band、估值分位图、雷达图（评分）——A 股用户习惯 |
| Recharts | 简单图表（模块评分柱状/进度）可混用 |
| Nivo | 备选（响应式 SVG 图表） |

### 2.6 工作流可视化（需求 3 的核心）

| 库 | 用途 |
|---|---|
| **@xyflow/react (React Flow) v12** ✅ | 工作流 DAG 渲染：节点=Agent、边=依赖、运行中高亮当前节点；V2 做拖拽编排器 |
| React Flow UI（官方 shadcn 风格组件） | 加速节点/面板样式 |
| AntV X6 | 备选（国内生态） |

### 2.7 表格 / 表单 / 状态

| 库 | 用途 |
|---|---|
| **TanStack Table** ✅ | 会话记录、指标表（虚拟滚动/排序/筛选） |
| **react-hook-form + zod** ✅ | LLM 配置、工作流参数、注册表单（类型安全校验） |
| **TanStack Query** ✅ | 服务端数据缓存/失效 |
| **Zustand** ✅ | 客户端轻状态（LLM 配置草稿、UI 偏好） |

### 2.8 内容渲染（备忘录/对话）

| 库 | 用途 |
|---|---|
| **react-markdown + remark-gfm + rehype-highlight** ✅ | 备忘录、对话内容渲染 |
| **shiki** | 代码高亮（可选，替代 rehype-highlight） |
| **KaTeX** | 估值公式渲染（贴现模型等） |
| **react-pdf** 或 html2canvas + jspdf | 备忘录导出 PDF（V2） |

### 2.9 图片 / 视觉素材

| 素材 | 方案 |
|---|---|
| Agent 头像 | **Emoji + 品牌渐变底**（最轻、最统一，M1–M11 各配一个主题色） |
| 品牌 Logo | AI 生成（imagegen）或几何字标；先占位 |
| 首页/广场横幅 | 纯 CSS 渐变 + 网格纹理（不引图库，加载快） |
| 用户头像 | Supabase Storage 上传 + 默认 DiceBear 兜底 |

### 2.10 认证与数据库

| 库 | 用途 |
|---|---|
| **@supabase/ssr + Supabase Auth** ✅ | 邮箱+密码注册/登录/忘记密码；与现有 Supabase PG 同栈，免费 |
| Auth.js / Clerk | 备选（需额外配置，Clerk 免费额度够用但引入外部依赖） |

> ⚠️ 避免：不引重型 UI 全家桶（避免 AntD + MUI 混用）；图片素材尽量用 CSS/SVG 生成，保证 Lighthouse 高分与加载速度。

---

## 3. 设计系统（视觉规范）

### 3.1 品牌基调
- **关键词**：专业、可信、清爽的金融数据感；**亮色为主 + 暗色模式**。
- **主色**：翡翠绿 `#10B981`（价值投资/增长）或深蓝 `#1E40AF`（金融信任）→ 建议**翡翠绿主 + 石板灰中性**。
- **语义色**：success `#16A34A` / warning `#F59E0B` / danger `#EF4444` / info `#3B82F6`。

### 3.2 设计 Token（Tailwind v4 `@theme` 定义）
```css
@theme {
  --color-brand-50..900;      /* 翡翠绿阶 */
  --color-ink: #0F172A;       /* 主文字 */
  --color-paper: #FFFFFF;     /* 亮色背景 */
  --color-ink-dark: #E2E8F0;  /* 暗色主文字 */
  --radius-card: 16px;        /* 卡片圆角 */
  --shadow-soft: 0 1px 3px rgb(15 23 42 / .06), 0 8px 24px -12px rgb(15 23 42 / .12);
}
```
- 间距：4px 基数；卡片内 24px，页面级 32px。
- 字体层级：Display 32/40、H1 28/36、H2 20/28、Body 15/22、Caption 13/18。
- 组件：`<Card>` 统一圆角 16px + 软阴影；主按钮圆角 12px；输入框圆角 10px。

### 3.3 关键组件清单（shadcn 初始化）
Button / Card / Input / Select / Tabs / Dialog / Sheet（移动端抽屉）/ DropdownMenu / Table / Badge / Avatar / Progress / Tooltip / Sonner(toast) / Skeleton / Switch / Form / ScrollArea。

---

## 4. 信息架构与路由

```
/                      仪表盘：最近会话 + 快捷分析 + 常用智能体
/agents                智能体广场（搜索 / 分类 / 卡片）
/agents/[agentId]      智能体详情（能力、依赖、LLM 需求、发起分析、收藏）
/workflows            工作流列表（默认 / 快速 / 自定义）
/workflows/[workflowId]  工作流分析页：DAG 图 + 输入公司 + 运行 + SSE 进度 + 结果
/workflows/builder    工作流编排器（拖拽连边，V2）
/conversations        对话记录（状态筛选 / 搜索 / 删除 / 继续）
/conversations/[conversationId] 会话详情（聊天 + 模块结果 + 备忘录 Tabs）
/settings/llm         LLM 服务商配置（核心需求 1）
/settings             通用设置（默认工作流、个人资料）
/login | /register | /forgot-password   认证
/memo/[conversationId]  备忘录分享页（SSR、可打印）
```

---

## 5. 数据模型（Supabase 新增表）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `profiles` | id(PK=auth.users.id), display_name, avatar_url | 用户资料 |
| `user_llm_settings` | id, user_id, provider, name, base_url, model, api_key(服务端加密), is_default, created_at | 需求 1 |
| `conversations` | id, user_id, session_id(后端会话), company_code, company_name, workflow_id, status, created_at, updated_at | 需求 5 索引 |
| `messages` | id, conversation_id, role, content, created_at | 需求 5（同步后端消息） |
| `agent_favorites` | user_id, agent_id, created_at | 需求 2 |
| `custom_workflows` | id, user_id, name, description, definition(json/yaml), is_public | 需求 3（V2） |

---

## 6. 前后端集成（关键设计）

### 6.1 双通道策略
- **普通 API → BFF 代理**：`app/api/backend/[...path]/route.ts` 转发到 FastAPI。
  优点：统一鉴权、隐藏内部地址、服务端注入用户 LLM 配置。
- **SSE 进度 → 浏览器直连后端**（`GET /api/sessions/{id}/events`，CORS 已开）。
  原因：Vercel Serverless 函数有执行时长上限，长分析（1–2 分钟）不适合经 BFF 转发；直连后端无此限制。
  兜底：若直连不通，前端退化为「轮询 `GET /api/sessions/{id}` 状态」。

### 6.2 环境变量
```text
NEXT_PUBLIC_API_BASE=https://value-agent-api.onrender.com   # 直连（SSE 用）
API_BASE_SERVER=...                                        # BFF 转发目标（同值）
NEXT_PUBLIC_SUPABASE_URL=...                               # https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...    # 浏览器端（替代 legacy anon）
SUPABASE_SECRET_KEY=sb_secret_...                          # 仅服务端（替代 legacy service_role）
```

### 6.3 后端配合改动（已落地 ✅ 2026-08-05）
1. **LLM 按会话/用户注入** ✅：`CreateSessionRequest` 支持 `llm_config`；`core/llm.py` 新增 `llm_from_config` 工厂；`WorkflowEngine._resolve_llm` 优先按会话配置建 client。前端 BFF `/api/sessions` 服务端解密用户默认 LLM 配置后转发，Key 不落地浏览器。
2. **内联自定义工作流** ✅：`Session.workflow_steps` + 引擎按内联定义运行（M4.5）。
3. **消息/备忘录落库 Supabase** ✅（2026-08-05）：新增 `messages`/`memos` 表（RLS），前端运行后同步用户消息、assistant 摘要与 memo，会话详情页直接读 Supabase。

### 6.4 运行流程（工作流分析页）
```
用户输入公司 → POST /api/sessions → 拿到 session_id
→ 前端建 conversations 记录 → GET /api/sessions/{id}/events (SSE)
→ 收到 step 事件 → DAG 节点高亮 + 进度条 + 聊天流式输出
→ done 事件 → 拉取 GET /api/sessions/{id} 展示模块结果 → 可生成/查看备忘录
```

---

## 7. 目录结构（frontend/）

```text
frontend/
├── app/
│   ├── (auth)/login|register|forgot-password/page.tsx
│   ├── (dashboard)/layout.tsx          # 侧边栏 + 顶栏（App Shell）
│   │   ├── page.tsx                    # 仪表盘
│   │   ├── agents/[agentId]/page.tsx
│   │   ├── workflows/[workflowId]/page.tsx
│   │   ├── conversations/[conversationId]/page.tsx
│   │   └── settings/llm/page.tsx
│   ├── memo/[conversationId]/page.tsx  # SSR 分享/打印
│   └── api/backend/[...path]/route.ts  # BFF 代理
├── components/
│   ├── ui/            # shadcn 组件
│   ├── agents/        # AgentCard / AgentGrid / AgentDetail
│   ├── workflow/      # FlowCanvas / StepNode / ProgressRail / WorkflowForm
│   ├── chat/          # MessageList / MessageBubble / Composer
│   ├── dashboard/     # StatCard / RecentSessions
│   └── settings/      # LlmProviderForm / ProviderPresets
├── lib/
│   ├── supabase/      # client / server / middleware
│   ├── api/           # backend.ts（BFF 客户端）、sse.ts（SSE 客户端）
│   ├── llm/providers.ts  # 服务商预设字典（deepseek/openai/qwen/ollama/custom）
│   └── utils.ts
├── hooks/             # useSse / useConversation / useAgents
├── stores/            # useUiStore.ts (zustand)
├── types/             # 与后端 Pydantic 模型对齐（session/agent/workflow/module）
├── styles/globals.css
├── middleware.ts      # Supabase 会话保护
├── next.config.ts
└── vercel.json        # rewrites 模板（docs/07 §3.2）
```

---

## 8. 里程碑计划（每步可独立提交、可演示）

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M0 脚手架** | `create-next-app`(Next 16 + TS + Tailwind v4) + shadcn 初始化 + 字体/主题 Token + App Shell 布局 | 亮/暗色切换可用，首页壳渲染 |
| **M1 认证** | Supabase Auth：注册/登录/忘记密码 + middleware 路由保护 + profiles | 注册→登录→访问受保护页闭环 |
| **M2 LLM 配置** ⭐需求1 | `/settings/llm`：服务商预设 + 自定义增删改查 + 默认服务商 + 测试连通 + 加密存储 | 配置保存后建会话可用该 LLM |
| **M3 智能体广场** ⭐需求2 | `/agents` 卡片网格 + 搜索/分类 + 详情页 + 收藏 + 「发起分析」跳转 | M1–M11 全部展示，可收藏 |
| **M4 工作流分析** ⭐需求3 | DAG 可视化(React Flow) + 输入公司运行 + SSE 进度 + 模块结果/备忘录展示 + 自定义工作流 V1（YAML 编辑） | 茅台分析跑通，进度实时刷新 |
| **M5 对话记录** ⭐需求5 | `/conversations` 列表 + 筛选/搜索 + 详情（聊天+结果+备忘录 Tabs）+ 重算/删除/归档 | 历史会话可查可续 |
| **M6 打磨部署** | 响应式（移动端抽屉）/ 空态/加载态 / SEO / vercel.json / Vercel 部署 + 后端 CORS 核对 | Vercel 预览可访问，Lighthouse ≥ 90 |

> 依赖顺序：M0 → M1 → M2（前置数据模型）→ M3/M4/M5 可并行 → M6。

---

## 9. 风险与决策备忘

| 风险/取舍 | 应对 |
|---|---|
| LLM Key 安全 | 前端永不接触 Key：存 Supabase 服务端加密，经 BFF/后端注入；测试连通走服务端 |
| Vercel Serverless 时长限制 | SSE 直连后端；长分析任务不被 Vercel 截断；BFF 只转发普通 API |
| 中文字体体积 | `next/font` 子集化 Noto Sans SC，仅加载用到的字形子集 |
| Supabase 免费层 7 天暂停 | 复用现有 GitHub Actions 每日保活机制 |
| 后端全局 LLM 单例 | 按会话注入 LLM 配置（§6.3 第 1 条）列入后端 backlog |

---

## 10. 下一步（建议执行顺序）

1. ✅ 本文档确认（含素材库与设计基调：shadcn/ui + Tailwind v4 + 翡翠绿主题）
2. M0：在仓库新建 `frontend/`，初始化 Next.js 16 项目
3. M1：接入 Supabase Auth
4. 按 §8 里程碑逐个开发，每个里程碑提交一次并更新 `docs/progress.md`
