# Value Agent 前端（Next.js + Vercel）

面向 A 股市场的价值投资分析平台前端。规划见 [`docs/08-frontend-plan.md`](../docs/08-frontend-plan.md)。

## 技术栈
- Next.js 16（App Router + Turbopack）+ TypeScript + Tailwind CSS v4
- shadcn/ui（Radix 基础库，Nova 预设：Lucide 图标 + Geist 字体）
- 翡翠绿品牌色设计系统，支持亮/暗模式（next-themes）

## 本地开发
```bash
npm install
cp .env.example .env.local   # 填写后端地址与 Supabase 配置
npm run dev                  # http://localhost:3000（用 127.0.0.1 访问避免跨源拦截）
```

## 常用命令
```bash
npm run dev     # 开发
npm run build   # 生产构建
npm run lint    # ESLint
npm run start   # 生产预览
```

## 里程碑
- [x] M0 脚手架：Next.js 16 + shadcn/ui + 设计系统 + App Shell（侧边栏/顶栏/仪表盘占位）
- [x] M1 认证（Supabase Auth：登录/注册/忘记密码/更新密码 + 路由保护）
- [x] M2 LLM 服务商配置（/settings/llm：多服务商预设 CRUD + 默认 + 测试连通 + Key 加密存储）
- [x] M3 智能体广场（/agents：卡片/搜索/分类/详情/收藏 + 本地目录兜底）
- [ ] M4 工作流分析（/workflows，React Flow DAG + SSE）
- [ ] M5 对话记录（/conversations）
- [ ] M6 打磨与部署
