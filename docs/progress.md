# 开发进度追踪

> 每完成一个任务勾选并写日期；里程碑完成时连同代码一起提交。
> 规则见 [04-development-guide.md](04-development-guide.md)。

## 总览

| 里程碑 | 状态 |
|---|---|
| S0 数据层 | 🔶 真实 BaoStock + Supabase + 组合分红( AkShare )均就绪；待数据推送/部署 |
| S1 智能体/工作流/会话/CLI/API | ✅ 骨架完成（2026-08-03） |
| S2 M2/M4/M8 | ✅ 完成（2026-08-04） |
| S3 M1/M5/M6 | ✅ 规则层完成（LLM 定性可选待接入 key）2026-08-04 |
| S4 M3/M7/M9 | ✅ 完成 2026-08-04 |
| S5 M10 决策报告 | ✅ 评分卡+备忘录完成（M10/M11 占位） |
| S6 M11 + 回测 | ✅ 完成 2026-08-04 |

---

> ✅ 2026-08-06 **LLM 流式管道（打字机 + 思考过程）**：`LlmClient.stream_chat()` 逐个 yield `(kind, delta)`（content 正文 / thinking 思考过程，兼容 DeepSeek Reasoner 的 `reasoning_content` 与 OpenAI o 系 `reasoning`）；`AgentContext.stream_llm()` 边生成边回调 `on_llm_chunk(step_id, kind, chunk)`，thinking 不混入正文返回值；`WorkflowEngine.run(on_llm_chunk=...)` 透传；`/events` SSE 新增 `llm_chunk{step,agent,kind,chunk}` 事件；M1/M5/M6/M9 定性调用全部切流式；前端 `StepActivityFeed` 渲染灰字思考区 + 正文打字机光标，对话页重跑同步；新增 `/chat/stream` 流式追问端点（`chat_chunk`/`done` 事件、assistant 落库），前端追问气泡打字机渲染。155 测试全绿 + 前端 tsc/eslint 通过。

> ✅ 2026-08-05 **方案 1 批次 E（增强项，docs/09-module-contracts.md §10.2）**：O-3 M10 决策快照审计（engine 在 M10 完成后写 session.decision_snapshots，含输入 handoff 摘要）；O-4 memo 质量自评（accuracy/logicality/storytelling 规则自评 + 降级标注）；O-5 输出稳定性测试（固定输入 3 次运行，outputs key 集合与契约枚举一致）；I-2 跨会话监控命中记忆（run_daily_monitor 把触发写入 session.monitor_hits，M11 将 warn/critical 历史命中回放为回顾规则）；配套测试 6 个。108 测试全绿 + 前端 tsc 通过。

> ✅ 2026-08-05 **市销率警告修复**：akshare 1.18.81 的 `stock_zh_valuation_baidu` 不支持「市销率」指标（可选值见 docstring），传入返回空结构报 NoneType 错；PS 无下游消费，从估值指标列表移除，records.ps 保持 None。真实验证 731 条估值记录正常、无警告。

> ✅ 2026-08-05 **分红数据修复**：AkShare 1.18.81 巨潮分红接口列名变更（报告期→报告时间、每股派息(税前)→派息比例），旧解析导致记录被全滤掉、分红为空。改用东财 `stock_fhps_detail_em`（标准报告期 + 现金分红比例 + 方案进度），仅保留已实施分红、滤掉 NaN/预披露、每10股→每股换算、按 period 倒序；来源 URL 同步东财 F10 分红页；解析逻辑抽纯函数 + 3 个离线单测。真实验证：M6 治理 50→85 分、M4 ddm 由「无分红数据」变为正确的 r≤g 判断。102 测试全绿。

> ✅ 2026-08-05 **真实数据验证 + 收尾修复（600519）**：AkShare+LLM 全链路跑通，M1~M11 契约字段（handoff/meta/signals/Risk Registry/source_module-action）真实数据核验通过；M8 补 handoff（mos_state/buy_zone/sell_zone/reason_codes）；修复 get_llm 先加载 .env 再读 key；_load_dotenv 支持行内注释；LLM 模型名按 provider 加前缀（deepseek/deepseek-chat）消除 litellm Provider List 噪音；配套测试。99 测试全绿 + 前端 tsc 通过。

> ✅ 2026-08-05 **方案 1 批次 D（收尾对齐，docs/09-module-contracts.md §1.1/§8）**：全面核对 AgentSpec.inputs 与引擎实际读取——M3 只读数据置空 inputs（M2 顺序依赖留 MODULE_DEPENDENCIES）；M10 补全 9 模块消费声明（维度评分用 M1/M2/M3/M5/M6 score）；M11 补全 M2/M3/M7/M8/M9/M10 消费声明；MODULE_DEPENDENCIES 与 YAML deps 同步；强约束规范写入 05-coding-conventions §3.1 与 templates/module-spec；新增 inputs 消费集合锁定测试。97 测试全绿。

> ✅ 2026-08-05 **方案 1 批次 C（外围与风险契约，docs/09-module-contracts.md §4/§8）**：M1 handoff（valuation_route / understandability_level）；M3 handoff（recommended_growth_rate / growth_confidence / cyclicality_flag / prosperity_code）；M5 handoff（moat_width / moat_durability / erosion_risks）；M6 handoff（governance_score / capital_allocation_flag / governance_risk_codes）；M7 handoff（valuation_percentile / market_state / margin_adjustment）；M9 升级 Risk Registry（risk_items 对象化 id/category/severity/source_module/trigger/impact/mitigation/veto_candidate + vetoes[] + monitor_candidates，保留 veto 兼容列表）；M11 rules 补 source_module / action(watch|alert|action) 分层并消费 M9 对象；前端 labels 补契约字段标签；测试同步 + handoff 集成测试。96 测试全绿 + 前端 tsc 通过。

> ✅ 2026-08-05 **方案 1 批次 B（硬核链路契约，docs/09-module-contracts.md §4/§8）**：M2 `signals` 升级为结构化 RiskSignal 对象（code/severity/metric/message，M9/M11/memo 按 message 消费，兼容旧字符串）；M4 `methods` 统一为数组对象（method/applicable/value/low/high/reason/confidence）+ 降级态字段集合与正常态一致 + meta.degraded；M8 新增 `mos_state` 枚举（attractive/fair/expensive/unavailable）+ 降级 reason_codes/meta；M10 新增 `decision_code`（buy/watch/avoid）+ `blocked_by_veto`；前端 memo-card 同步 M2/M4 渲染；测试同步 + 契约断言。95 测试全绿 + 前端 tsc 通过。

> ✅ 2026-08-05 **方案 1 批次 A（统一模块契约，docs/09-module-contracts.md）**：新增 `core/contracts.py`（五段式常量/枚举/RiskSignal/meta 校验）；`ModuleResult` 增加 `meta` 字段（含序列化往返）；修复 M9 YAML deps 漏 M7/M8 的 handoff 断点；M4 `spec.inputs` 对齐实际读取（M1+M3）；新增 `tests/test_contracts.py` 11 个用例（含工作流依赖声明对齐防回归）。94 测试全绿。

> ✅ 2026-08-05 修复测试：新增 tests/conftest.py StubData 夹具（数据桩）注入引擎；修正 test_decision/test_sessions/test_financials 过期断言；**76 个测试全绿**。

> ✅ 2026-08-05 **会话持久化迁移到 Supabase**：新增 `SupabaseStore`（`sessions` jsonb 表）+ `SESSION_STORE` 环境切换；真实 Supabase 验证重启后会话恢复；本地默认 sqlite。

> ✅ 2026-08-05 收尾：自定义工作流 DAG 节点显示短编号（agent.code）；**LLM 按会话注入**（前端 BFF /api/sessions 服务端解密默认 LLM 配置 → 后端 llm_config → 引擎 _resolve_llm），真实账号验证注入成功，77 测试全绿。

> ✅ 2026-08-05 安全修复：会话 API 响应统一经 `_public_session` 脱敏（`llm_config.api_key` → `sk-••••••1234`），数据库 payload 仍存完整 Key 供重算/续跑。

> ✅ 2026-08-05 估值/财务数据修复：M4 改取**最新年报 EPS** + 过滤亏损期负 PE（修复 601919 负估值 -1.93 → 15.2~49.25）；M2 `years` 用年报数（41→10）；负债率超出合理区间按数据异常中性计（拦截 BaoStock 0.4% 坏值）。78 测试全绿。

> ✅ 2026-08-05 AkShare 数据源修复：估值历史改用 `stock_zh_valuation_baidu`（新版 akshare 已移除乐咕接口）；财务取最新 N 期 + 修正「摊薄每股收益(元)/每股经营性现金流(元)」列名；日线补默认日期范围。601919 AkShare 实测：负债率 41%、EPS 2.27、内在价值 17.3~28.0，数据正常。

> ✅ 2026-08-05 **数据源全面切 AkShare**：删除 BaoStock（baostock_source.py / combined.py / 依赖 / Dockerfile 引用），`primary: akshare`，回退 mock；AkShare 源已修复（估值接口、最新财报、列名、日线日期范围）。

> ✅ 2026-08-05 **消息/memo 落库 Supabase**：新增 `messages`/`memos` 表（RLS），前端运行后同步用户消息 + assistant 摘要 + 备忘录（版本覆盖），conversations 状态随运行更新；详情页展示对话气泡。

> ✅ 2026-08-05 **对话追问（chat）实现**：后端 `POST /api/sessions/{id}/chat`（按请求>会话>全局 LLM 回复）+ 前端对话输入框/LLM 选择器 + BFF 同步消息到 Supabase；修复 `SessionManager.add_message` 不更新内存 session 的 bug；memo 标题去掉数字编号。77 测试全绿。

> ✅ 2026-08-05 **Memo 卡片美化落地**：新增 `MemoCard` 结构化组件（Hero 指标/五维评分条/内在价值区间带/买卖区间卡/模块表/监控严重度徽章/假设键值网格），替换 markdown 渲染；配套后端韧性：AkShare 网络重试 + M1/M4/M8 数据失败降级为 DONE（工作流不再因数据源瞬时故障全灭）。

## S0 数据层（🔶 进行中）
- [x] 免费数据源适配器（mock + baostock + akshare 统一接口，字段已归一化）2026-08-04
- [x] 表结构（schema.sql：company/financials/daily_price/valuation_history/dividends/watchlist）
- [x] 存储层（SqliteMarketStorage 本地 + PostgresMarketStorage(Supabase)）
- [x] ETL 管线（ingest_company 全量 + daily_update 增量，已验证跳过/插入）
- [x] 自选股池 config/watchlist.yaml（10 只样本）
- [x] 勾稽校验 + quality_flag（validate.py：财务/行情/估值/分红 + ETL 入库前剔除）2026-08-04
- [x] point-in-time 数据快照（snapshots.py + records_before，回测防前视）2026-08-04
- [x] 真实免费数据源拉取验证（BaoStock 连通 ✅，10 只自选股 47,996 条入库，茅台完整分析跑通；修复季度/年度口径）2026-08-04
- [x] Supabase 建表 + DATABASE_URL 连接验证（Session Pooler 新加坡 5432，用户本机通过）2026-08-04
- 完成日期：

## S1 智能体 + 工作流 + 会话骨架 ✅ 2026-08-03
- [x] Agent 抽象 + 注册表（agents/base.py、registry.py）
- [x] 内置 M1–M11 智能体骨架（agents/builtin.py）
- [x] 工作流模型 + 默认工作流（workflow/）
- [x] 工作流引擎（拓扑/条件跳过/run_always/失败处理 + on_step 进度回调）
- [x] YAML 自定义工作流（config/workflows/）
- [x] sessions 数据模型 + 状态机（含迁移测试）
- [x] session store 持久化（InMemory + Sqlite，可换 Supabase）
- [x] session manager（create/rerun 依赖链/resume/archive）
- [x] CLI/API 骨架（main.py：/health + 会话 API + SSE；cli.py：analyze/agents/workflows/data/monitor/serve）

## S2 硬核三模块（纯规则）
- [x] M2 财务质量（ROE 杜邦 + 现金流 + 杠杆 + 风险信号）2026-08-04（financials/quality.py + agent）
- [x] M4 估值引擎（方法路由 + DCF/唐朝/格雷厄姆/DDM/相对中位PE + 敏感性）2026-08-04（valuation/ + agent）
- [x] M8 安全边际（折扣率 + 要求折扣分级 + 买卖区间）2026-08-04（safety_margin/ + agent）
- 完成日期：2026-08-04

## S3 认知与质量（规则层 + LLM 可选）
- [x] M1 商业模式认知（生意类型分类 → M4 路由 + 能力圈评级）2026-08-04
- [x] M5 护城河（标准面代理：ROE/毛利率/杠杆 → 宽度评级）2026-08-04
- [x] M6 治理与资本配置（分红持续性代理评分）2026-08-04
- [ ] 配置 LLM_API_KEY 后验证 LLM 定性层输出
- 完成日期：

## S4 成长与市场 ✅ 2026-08-04
- [x] M3 成长与再投资（EPS CAGR + 景气评级 + 增速假设 → M4 采用）
- [x] M7 价格与情绪（估值历史分位 + 股债性价比 + 样本不足降级）
- [x] M9 风险与否决（聚合 M2/M3/M5/M6/M7/M8 + 一票否决 + LLM 红队可选）
- 完成日期：2026-08-04

## S5 决策与报告
- [x] M10 评分卡引擎（五维加权 + 档位 + 一票否决）2026-08-04（decision/engine.py + agent）
- [x] 投资备忘录生成（markdown：M10 结论 + M2/M4/M8 要点）2026-08-04
- [ ] 会话重算 → 备忘录 v2（依赖重算已支持，接 API 端到端验证待做）
- 完成日期：

## S6 监控与回测 ✅ 2026-08-04
- [x] M11 跟踪监控（规则生成 + 每日价格触发 + 飞书/企微推送）2026-08-04
- [x] point-in-time 回测（PIT 评分选股 + 月度调仓 + 指标；真实数据超额 +2.6%/年）2026-08-04
- 完成日期：2026-08-04

## 前端（F 系列）
- [x] F0 脚手架：Next.js 16 + TS + Tailwind v4 + shadcn/ui（Nova/Radix）+ 翡翠绿设计系统（亮/暗）+ App Shell（侧边栏/顶栏/仪表盘占位）2026-08-04
- [x] F1 认证（Supabase Auth：登录/注册/忘记密码/更新密码/auth callback + proxy 路由保护 + NavUser 真实用户）2026-08-05
- [x] F2 LLM 服务商配置（/settings/llm：DeepSeek/OpenAI/Qwen/Ollama/自定义 + CRUD + 默认 + 测试连通；Key AES-256-GCM 加密存 Supabase）2026-08-05
- [x] F3 智能体广场（/agents：M1–M11 卡片 + 搜索/分类 + 详情页 + 收藏（agent_favorites）+ 发起分析入口 + 后端离线本地目录兜底）2026-08-05
- [x] F4.5 自定义工作流编排器（/workflows/builder：Agent 面板 + React Flow 拖拽连线 + 保存 custom_workflows；后端 Session 支持内联 workflow_steps；真实账号端到端验证：建流→保存→运行→结果 90/83/10 + 备忘录）2026-08-05
- [x] F4 工作流分析（/workflows：React Flow DAG 可视化 + 输入公司发起分析 + SSE 实时进度 + 结果卡片 + 备忘录渲染 + conversations 落库；后端 curl E2E 验证通过）2026-08-05
- [x] F5 对话记录（/conversations 列表（搜索/状态筛选/删除）+ 详情（DAG/结果/备忘录/重新分析）+ 仪表盘最近会话；真实账号端到端验证通过）2026-08-05
- [x] F6 打磨与部署（品牌 icon.svg + openGraph/SEO + 404 页 + 路由 loading 骨架 + 按钮光标/选中色；生产构建 npm run start 验证通过；Vercel 部署文档与环境变量清单就绪）2026-08-05
