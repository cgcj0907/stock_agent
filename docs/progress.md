# 开发进度追踪

> **三层记录体系**（总规则见根 [AGENTS.md](../AGENTS.md)）：
> - [chat-record.md](chat-record.md) —— 每次新对话 & 每轮对话的 1–2 句话总结；
> - [milestones.md](milestones.md) —— **非常关键性**项目进展（体系成型/重大方向/关键修复/上线部署）；
> - 本文件 —— 任务级清单（勾选 + 写日期）+ 完整历史日志。
>
> 每完成一个任务勾选并写日期；里程碑完成时连同代码一起提交。
> 规则见 [04-development-guide.md](04-development-guide.md)。

## 当前状态（2026-08-09）

- 全模块真实实现 + V2 升级（P1–P5）已落地；前端 F0–F6 完成，生产部署链路（FC + Supabase + Vercel）打通；
- 本周聚焦真实会话稽核修复：M4 下沿/便宜度、M3 数据派生增速、M9 否决误杀、数据层超时加固等，全量测试 **522 通过**；
- 待办集中在：S0 数据推送/部署收尾、LLM 定性层接 key 验证、S5 会话重算→备忘录 v2 端到端验证、FC 超时调 600s。

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

## 当前待办

- [ ] S0 数据层：数据推送/部署收尾（真实 BaoStock + Supabase + 组合分红已就绪，见总览）
- [ ] S3：配置 `LLM_API_KEY` 后验证 LLM 定性层输出
- [ ] S5：会话重算 → 备忘录 v2 端到端验证（依赖重算已支持）
- [ ] 部署：FC 超时 300s → 600s（控制台配置，见 [10-fc-deployment.md](10-fc-deployment.md)）

## 任务清单（按里程碑）

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
- [x] M5 护城河 v2（两层制：规则层降级为「财务代理评级」+ 同行基准相对评分 + 来源识别 +
      侵蚀信号；LLM 定性回填 handoff durability/erosion_risks；宽度冲突处理；M9 真正消费
      erosion_risks）2026-08-07
- [x] M5 护城河 v3（行业细分基准：INDUSTRY_SEGMENT_BENCHMARKS ~25 细分，解析顺序
      细分>生意类型>generic；金融拆银行/保险/券商净利率口径，修掉「保险净利率被银行中位误伤」
      （中国平安 43窄→70宽）；周期行业 ROE/利润率/杠杆近 8 年跨周期均值；M1 依赖显式化；
      宽度合成门槛可配置 + competition_evidence 内容校验 + 参考池情绪词扩充）2026-08-07
- [x] M5 护城河 v3.1（真实同行中位数：moat/peer_benchmarks.py，AkShare 行业成分股财务中位，
      peer_medians 覆盖静态细分基准，real_peer_medians 开关 + 失败回退静态表；引擎/agent/测试接入）2026-08-07
- [x] M5 护城河 v3.2（provider 慢网加固：单次超时/总预算/并行拉取防挂死；5.9 档位横截面验证
      scripts/validate_moat_tiers.py（真实数据 评分 vs 长期 ROE 秩相关 0.709）；光伏周期误判修复
      （拆 solar 细分，隆基 无→窄））2026-08-08
- [x] M5 护城河 v3.3（5.13：M5 回填 handoff.moat_trend，M9 侵蚀风险 severity 三档：
      low+eroding→critical / 单条件→high / 否则 medium，闭环 LLM trend 消费）2026-08-08
- [x] M6 治理与资本配置（分红持续性代理评分）2026-08-04
- [x] M6 治理与资本配置 v2（治理事件非分红证据 + 结构化风险码 + LLM 风险回填 + 分数口径统一）2026-08-07
- [x] M2 财务质量 v2（12.1 分行业口径：按 M1 生意类型/金融细类路由，覆盖
      消费垄断/成长/周期/金融/资产/高分红六类 + bank/broker/insurance，现金流比仅年报+阈值放宽、
      金融高杠杆按行业常态 → 修复保险股 OCF/NP<0.8 误触发一票否决）2026-08-07
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

---

## 历史变更日志（详细）

> 要点版见 [milestones.md](milestones.md)；此处为完整明细，按时间倒序。

> ✅ 2026-08-09 **中国船舶（600150）会话稽核：M4 下沿穿透 + M10 LLM 方向误读**
> ① 会话结论「回避」内部自洽可辩护（M2=38 含亏损年、M4 现价>中值、M5 窄护城河、M8 安全边际为负）；
> ② **M4 下沿穿透**：方法偏态时 ±std 带下沿 9.78 低于最保守方法 16.52（无方法支撑）→ M8 买入价被压到 4.35。
>    修复：下沿一律 `max(最保守方法值, 中值−std)`，中国船舶 low 9.78→14.87；
> ③ **M10 LLM 复核方向误读**：把「治理风险 85 分」读成"治理存在重大隐患"（85=优秀）。
>    修复：复核 prompt 明示"分数越高越好、不得把高分解读为负面信号"；
> ④ 全量 **522 通过**（+1 回归）；ruff 通过。

> ✅ 2026-08-09 **M5 护城河 ROE 比较时间口径对齐（周期股）**
> ① 现象：周期股公司侧用近 8 年跨周期均值 ROE（去周期位置），但同行侧 PeerBenchmarkProvider
>    只取**最新一期**中位 → "公司 8 年均值 vs 同行最新中位"时点错配：周期高点系统性低估、
>    低点系统性高估公司护城河（且 Provider 其实已拉到多年数据，只是丢弃了）；
> ② 修复：Provider 同时计算同行**跨周期均值中位**（roe_median_cycle 等，近 8 年），
>    周期股引擎优先用跨周期中位与公司 8 年均值比较，最新中位与静态基准仅作兜底；
>    信号/证据明示「同行跨周期中位」；
> ③ 全量 **505 通过**（+2 回归）；ruff 通过。

> ✅ 2026-08-09 **M1 能力圈/判断理由前端恒空修复（前后端字段错位）**：
> ① 现象：UI「能力圈」一直显示 "—"、「判断理由」不展示——前端读 `outputs.llm_qualitative.understandability/reasons`，
>    但 M1 agent 从不把 `llm_qualitative` 整体写进 outputs（只拆散到顶层 business_model/understandability/reasons）；
> ② 修复：后端 M1 outputs 补存 `llm_qualitative`（与 M6/M7 一致）；前端改为优先读顶层 `outputs.understandability/reasons`
>    （后端始终回填规则/LLM 有效值），llm_qualitative 仅兜底；
> ③ 前端两个格子显示同一字段（可理解性/能力圈重复）——最终**保留「可理解性」、去掉「能力圈」**（同一字段，避免重复展示）；
> ④ 全量 **503 通过**（+1 回归）；ruff 通过。

> ✅ 2026-08-09 **M4 分数语义修复：覆盖度 → 估值便宜度**
> ① 现象：M4 分=方法覆盖度（浪潮 M4=85 但现价是内在上沿 2 倍），UI「估值 85 分」误导；
> ② 修复：`cheapness_score`（现价 vs 内在价值区间）——≤下沿 95 / ≤中值 70 / ≤上沿 45 / >上沿 15 / 数据不足 50；
>    覆盖度只保留在 `handoff.coverage`（方法覆盖/置信度不再混入估值分）；降级路径 score 0→50（与 M8 unavailable 一致）；
> ③ 影响回放（7 会话）：估值维与 M8/M7 口径统一——浪潮 33.3→10.0（watch→**avoid**，2× 高估+critical 风险，更正确）、
>    金风/大连圣亚估值维显著下调（本就 avoid）、三七/中国建筑不变、锦江/儒意微降；
> ④ 全量 **502 通过**（+2 回归）；ruff 通过。

> ✅ 2026-08-09 **M3 增速正常化改为数据派生 + 揪出 ROE/WACC 口径 bug**：
> ① 用户意见：增速不能简单写死——周期股低谷修复增长可能很高，硬封顶 10% 失真；
>    改为用**保守情景**（数据派生：中性×0.6、低信心×0.5）作为可持续增速（浪潮 20%→12%、山高环能 10%→5%），
>    情景带随正常化值重新派生（保守≤中性≤乐观自洽）；M4 对周期股本就不用 M3 增速（DCF 禁用），实际影响评分与展示；
> ② 顺带揪出**老 bug**：`roe >= 2*wacc` 里 roe 是百分数（12=12%）而 wacc 是小数（0.10），
>    12>=0.20 恒真 → 再投资质量分恒 +30（本应 ROE≥20% 才 +30、≥10% +20）——生产 M3 分普遍虚高 ~10 分，
>    已统一口径（wacc×100 再比较），新增回归测试；
> ③ 全量 **499 通过**（+1）；ruff 通过。

> ✅ 2026-08-09 **M1/M3 周期口径一致化（修复 4：浪潮信息漏判）**：
> ① 现象：浪潮信息 M1=cyclical（服务器行业周期），但 M3 仅看 ROE 波动（CV≤0.3）判非周期 → 20% 增速未被正常化、
>   growth_prosperity=70；锦江/中国建筑等 M1=cyclical 也只在 ROE 波动时才对上；
> ② 修复：M3 消费 M1 生意类型（`MODULE_DEPENDENCIES[M3]={M1,M2}` + YAML + 前端目录 + AgentSpec.inputs 同步），
>   `cyclicality_flag = ROE_CV>0.3 或 business_type==cyclical`；M1 判周期时增速按**保守情景**正常化（后改为数据派生，见下）+ 质量折扣 ×0.9，
>   evidence 标注「M1 生意类型判为周期」；
> ③ 契约测试同步（M3 inputs 空 → {M1_business_model}）；新增回归测试；
> ④ 全量 **499 通过**（+1）；ruff 通过。

> ✅ 2026-08-09 **第二批新会话稽核（7 家，修复后首轮）：M9 否决误杀修复**
> ① 复验：M4 下沿不再 0（浪潮 13.22 / 金风 7.22 …）、M8 档位全部 ≤ 买入价、M9 max_severity 取最严重、M3 周期增速封顶均生效；
> ② **M9 否决误杀（中国建筑）**：仅凭 M3 prosperity=down（任何负 EPS CAGR）+ 行业常规杠杆 77% 就硬否决"回避"——
>   该公司 ROE 稳定 11%、股息 6%、M2=56 无亏损年、PE 5% 分位。修复：否决需**真实恶化证据**
>   （M2 亏损年 LOSS_YEAR / M3 周期特征 / 财务质量 <50）；中国建筑不再否决，大连圣亚/儒意/金风（亏损或周期下行）保留；
> ③ 复验后仍待优化（未改，待决策）：M6 治理耗时 166~199s（定性 LLM + 校准 LLM 两次调用，校准 delta=0 基本无调整）；
>   M7 约 60s（实时情绪源，用户确认保留）；M4 分数=方法覆盖度而非便宜度（浪潮 M4=85 但现价 2× 内在上沿，展示易误导）；
>   M1/M3 周期判定口径不一致（浪潮 M1=cyclical 而 M3 非周期）；
> ④ 全量 **498 通过**（+1 否决回归）；ruff 通过。

> ✅ 2026-08-09 **「卡在价格与估值分位」根因定位与加固（FC 300s 超时 + 数据层超时缺失）**：
> ① 定位：FC 配置超时 300s（docs/10-fc-deployment.md），完整分析实测 90~283s，未缓存标的最多几分钟；
>   FC 掐断请求 → SSE 中途断 → 前端停在 M7（首个实时补行情模块，单模块实测 56s）；
> ② `PostgresMarketStorage`：connect_timeout 15s + keepalive + statement_timeout 30s + 读操作断线重连一次
>   （此前单连接被 pooler 静默断开后无限阻塞，实测 SSL EOF + 2min+ 卡死）；
> ③ 实时源 `_fetch_with_retry`：socket 级 45s 超时兜底（akshare/requests 默认无超时）；
> ④ 日线增量刷新：曾加 `DAILY_FRESH_DAYS` 新鲜度跳过，**已按用户决策回退**——保留每次分析补写日线增量，靠提高 FC 超时解决；
> ⑤ M7 情绪数据源曾加整体限时 `SENTIMENT_BUDGET_SECONDS=20`，**已按用户决策回退**——情绪源不设预算，保留完整收集；
> ⑥ 建议：FC 超时 300s→600s（控制台配置，已在部署文档标注；用户确认靠提超时解决）；
> ⑦ 全量 **497 通过**（回归：断线重连）；ruff 通过。

> ✅ 2026-08-08 **会话模块生产数据稽核修复（Supabase sessions）**：
> ① 安全：`Session.to_dict` 序列化剔除 `llm_config.api_key`——明文 Key 不再落库；密钥仅存进程内缓存（TTL 6h，
>   创建→立即运行流用），`scripts/scrub_session_secrets.py` 回填清理历史数据（Supabase 原子 SQL 已执行，0 残留）；
> ② 数据质量：`workflow/engine.py` 保留 `started_at`（此前被 agent 返回结果覆盖，全量模块 started_at 为 None，无法审计时长）；
> ③ 输入校验：`normalize_company_code`（6 位 A 股代码，容忍 sh/sz/bj 前缀/后缀）——拦截 `6002579` 这类脏代码
>   产生的「全 DATA_UNAVAILABLE 却 completed」垃圾会话（API 400 / CLI 友好报错）；
> ④ 生产接线对齐 CLI：`POST /api/sessions` 补 `data_snapshot_id`（PIT 快照标识）+ `prior_monitor_hits`（I-2 跨会话记忆）；
> ⑤ `SessionManager.persist` 刷新 `updated_at`（步骤推进可见），`SupabaseStore` 连接加 keepalives/超时 + `close()`；
> ⑥ 全量 **492 通过**；ruff 通过。

> ✅ 2026-08-08 **跨类型公司模块合理性稽核修复（11 家真实会话回放）**：
> ① M4 内在价值下沿：方法分歧过大（加权离散度 ≥ 中值）时 ±std 带下穿被钳成 0 —— 下沿退化为最保守方法值
>   （000831 中国稀土 low 0→3.45、600519 茅台 0→612.77），修复 M8 因 low=0 直接 OUT_OF_RANGE 放弃的连锁问题；
> ② M8 分批档位：档位原锚在**内在价值下沿**（0.75/0.65/0.5×low），周期股要求折扣 50% 时第一档反而比买入价高 50%
>   （牧原 24.15 vs 16.1、铜业 12.52 vs 6.68）——改为锚定**买入价**（1.0/0.85/0.7×buy_price），档位不再超出买入区间；
> ③ M3 周期股增速正常化：景气高点 EPS CAGR 被外推成长期增速（江西铜业 20%、中远海控 10%）——
>   周期特征（ROE CV>0.3）时增速按保守情景正常化 + 成长质量 ×0.9，避免 M4/M10 被高估（初版封顶 10%，后按用户意见改为数据派生）；
> ④ M9 max_severity 严重度取反：按编号 max() 取到**最轻**等级（江西铜业含 critical 却报 low）——
>   改 min() 取最严重，恢复 M10 仓位风险修正（600362 low→critical、000831 medium→critical）；
> ⑤ 全量 **496 通过**（+4 回归）；ruff 通过。

> ✅ 2026-08-08 **当前/未来估值区分（v2.3）**：
> ① `valuation/methods.py` `MethodResult` 新增 `horizon_years`（None=现值口径；3=三年后）——唐朝法标为 `horizon_years=3`；
> ② `valuation/engine.py` 内在价值区间（low/mid/high）**只聚合现值口径方法**，未来估值（唐朝法）单独展示、不进入加权池，
>   evidence 标注「未来估值（非现值）不进入当前内在价值区间：tang=xxx（3年后）」；方法级置信度仍覆盖全部适用方法；
> ③ `valuation/agent.py` 方法列表输出 `horizon_years`；前端方法行显示「N年后」徽标 + 内在价值区间标题改为「现值口径」；
>   `report/memo.py` 方法表标注「N年后，非现值」；
> ④ 效果（美的）：区间由「混入唐朝 246 的 78.87~193.27」变为「纯现值 88.98~187.18」；r−g≥2% 钳制使 DDM 恢复可用；
> ⑤ 全量 **484 通过**；ruff 通过。

> ✅ 2026-08-08 **M1 生意类型改 LLM 主判（v2.1）+ 三个数据/口径修复（v2.2）**：
> ① v2.1：`planner/validator.py::resolve_profile` 冲突策略由「规则为准」改为「LLM 主判」——
>   与规则冲突且 confidence=high，或 medium+理由 → 采纳 LLM（`override`）；low 或 medium 无理由 → 回退规则；
>   `plan_trace` 新增 `llm_vs_rule`（consistent/conflict）；M1 prompt 改「规则候选 + 最终裁判」去锚定；
>   **M4 删除 `business_type_override`**（类型由 M1 画像单一决策，M2/M4/M7 消费同一份）；
> ② v2.2 数据/口径修复：`akshare_source.py` 归母权益加 `TOTAL_PARENT_EQUITY` 兜底并跳过 0/负值（修 000333 BVPS=0→29.77，
>   格雷厄姆数不再缺失）；`valuation/agent.py` BVPS≤0 走 close/pb 兜底；`financial_routing.yaml` 消费垄断现金流比
>   改为**仅年报**（家电等制造型季度季节性不再误触发 OCF_NP_DIVERGENCE，美的 M2 72→91）；`valuation/llm.py`
>   校准加 r−g≥2% 交叉校验（防 DDM 必跳过/薄价差 DCF）；`financials/quality.py` 现金流口径文案按生意类型输出
>   （不再对周期/成长写死「金融口径」）；
> ③ 全量 **481 通过**；ruff 通过。

> ✅ 2026-08-08 **冗余代码清理 + docs 优化**：
> ① 清理死代码：删除废弃的 `parse_llm_score`（v1 绝对分解析，含 3 条测试）、零引用的 `calibration_policy_for`/`cninfo_disclosure_url`/`register_many`；
> ② 去重：`scripts/validate_moat_tiers.py` 的本地 `spearman` 改为复用 `backtest/calibration_ab.py`（删 24 行重复实现）；
> ③ docs 优化：`docs/README.md` 修正编号冲突（templates/progress → 13/14）+ 顶部最新状态横幅 + 12 篇标注「已落地」；`docs/04-development-guide.md` 里程碑路线图补 S7 V2（P1–P5 落地表）；
> ④ 全量 **468 通过**（471 − 3 个删除的废弃测试）；ruff 通过。

> ✅ 2026-08-08 **函数注册表补全（docs/12-v2-upgrade.md §5）**：
> ① `financials.quality`——M2 财务质量引擎登记为工具（records + business_type/financial_subtype → score/metrics/signals[to_dict]/evidence/details）；
> ② `market.percentile`——M7 价格分位登记（valuation_history → pe/pb 分位 + position + score），样本不足优雅降级；
> ③ 注册表工具总数 12 → **14**（估值方法 ×12 + M2 + M7）；
> ④ 全量 **471 通过**（468 + 3）；ruff 通过。

> ✅ 2026-08-08 **backlog 落地：模块级评分的 PIT 组合级回测（docs/12-v2-upgrade.md §8.1）**：
> ① `backtest/module_score.py::module_pit_score`——M1 规则分类（快照无 industry 按财务特征兜底）→ M2 财务质量引擎（分行业口径）
> + M4 估值引擎（方法路由 → 内在价值 vs 现价便宜度，`cheapness_score` 0.8~1.2 线性映射），纯确定性、无 LLM；
> ② `run_backtest` 新增 `score_fn` 参数（默认 pit_score 不变），模块评分可接入同一 PIT 月度调仓框架；
> ③ `scripts/backtest_module.py`——对比基线（pit_score）vs 模块流水线（module_pit_score）的 PIT 超额（年化），
> 本地库 schema 过期时给出重新入库提示；
> ④ 全量 **468 通过**（464 + 4）；ruff 通过。

> ✅ 2026-08-08 **V2 P5：接线 + 函数注册表（V2 收尾，docs/12-v2-upgrade.md §5/§6.6）**：
> ① `core/scoring.py::confidence_from_completeness`——completeness → 校准置信度（high→±5 / medium→±10 / low→±15，非法回落 medium）；
> ② M1 接线：新增 meta（build_meta）——数据问题→low、plan 冲突回退→medium、采纳/覆盖→high；`llm_score` 传 confidence（plan 采纳时校准上限收紧到 ±5，测试验证 delta -12 被截断到 -5）；
> ③ M4 接线：数据降级→low、valuation_confidence≥0.7→high、否则 medium；正常路径也补 meta（降级路径保持不变）；
> ④ 函数注册表 `src/value_agent/tools/`：ToolRegistry（register/execute/execute_plan）+ 输入/输出 schema 校验 + 12 个估值方法登记（MethodResult→dict 适配），plan-then-execute 执行器就位；
> ⑤ 全量 **464 通过**（451 + 13：tools ×10、wiring ×3）；ruff 通过。**V2（P1–P5）全部完成。**

> ✅ 2026-08-08 **V2 P4：画像 planner 试点（M1→M4，docs/12-v2-upgrade.md §4）**：
> ① 新增 `planner/` 包：`CompanyProfile` 模型 + `parse_profile`（schema/枚举校验）+ `resolve_profile`（冲突回退：
> 画像与规则分类冲突且 confidence≠high → business_type 回退规则、high → 覆盖记 override）+ `stability_rate`（plan 稳定性指标）；
> ② M1 接线：LLM 分类调用升级为一次输出完整画像（business_type/financial_subtype/cyclicality/primary_metric/confidence/special_flags），
> 画像字段 + `plan_trace` 进 M1 handoff（M4 读 business_type/financial_subtype 路由，M7 后续消费 primary_metric）；
> ③ M4 接线：evidence 记录「M1 画像路由：plan=…」落审计；
> ④ `scripts/planner_stability.py`——对同一公司重复跑 M1 N 次，验收 business_type 一致率 ≥ 0.8；
> ⑤ M1 测试更新：LLM 覆盖规则需显式 `confidence: high`（冲突默认回退规则，审慎原则）；
> ⑥ 全量 **451 通过**（438 + 13）；ruff 通过。

> ✅ 2026-08-08 **V2 P3：校准 A/B 回放闭环（docs/12-v2-upgrade.md §8）**：
> ① `backtest/calibration_ab.py`——纯函数分析模块：从会话抽取校准样本（base=规则分/final=校准后分，跳过 disabled）、
> 前向收益（as_of 后 6 个月，覆盖度不足判缺失）、斯皮尔曼相关（规则 vs 校准）、档位翻转率（↑/↓）、delta 均值与 |Δ| 饱和、结果分布；
> ② `scripts/calibration_ab.py`——replay 脚本：读 data/sessions.db（SqliteStore）+ data/market.db，输出每模块 A/B 报告
> 与数据驱动建议（`enabled: false` / 收紧 cap），支持 `--json`、`--collect`（对 watchlist 建语料）、`--sessions-db/--market-db`；
> ③ 建议逻辑（§8.2）：相关增益 < -0.05 → 关闭；平均 |Δ| > 8 → 收紧 cap；平均 Δ 偏置 > 3 → 提示校准；n<10 → 保持现状；
> ④ 演示验证：合成语料 10 公司×3 模块 → M6 恶化建议关闭、M3 delta 偏大建议收紧 cap 输出正确；
> ⑤ 全量 **438 通过**（425 + 13）；ruff 通过。

> ✅ 2026-08-08 **V2 P2：校准策略配置化 + trace 落库（docs/12-v2-upgrade.md §6.5/§8.3）**：
> ① 新增 `config/llm_calibration.yaml`——校准策略（分模块 enabled/cap/require_evidence_for_up）+ 档位保护参数（margin/min_new_facts_to_cross）唯一事实来源，代码常量兜底，契约测试锁一致（防漂移）；
> ② `ModuleResult` 新增 `calibration` 字段（P1 校准轨迹），11 个 agent 调用 `llm_score(trace=...)` 并把轨迹挂到结果，随 `Session.to_dict()` 持久化；
> ③ 决策快照（`build_decision_snapshot`）新增 `calibration_trace`——每模块 {base, final, outcome, notes, delta, reasons, evidence_refs, new_facts}；
> ④ `llm_score` 全路径 trace：disabled（禁用/无 LLM）/ fallback（解析失败/调用异常）也记录 outcome，审计可追溯「为什么没校准」；
> ⑤ 全量 **425 通过**（417 + 8）；ruff 通过。

> ✅ 2026-08-08 **V2 P1：评分校准层 v2 落地（delta 制，docs/12-v2-upgrade.md §6）**：
> ① 绝对分替换 → **delta 制**：LLM 输出 `{delta, reasons, evidence_refs, new_facts}`，最终分 = clamp(规则分 + delta, 0, 100)，永不直接采纳 LLM 绝对分；
> ② 证据锚定：抬分（delta>0）必须引用素材下标或提供 new_facts，否则拒绝回退规则分；压分只需理由（审慎原则）；
> ③ 动态上限：模块策略 cap × 置信度 cap（high ±5 / medium ±10 / low ±15，confidence 未给出时只用模块 cap）；
> ④ 分模块差异化：纯数值模块（M2/M7/M8）禁用校准；语义模块（M1/M5/M6）±15；M3/M9/M4/M11 默认 ±10；M10 ±15（与 decision/engine CALIBRATION_CAP 双层保护）；
> ⑤ 档位边界保护：抬分跨档且贴近阈值（<5 分）时需 ≥2 条 new_facts，否则封顶在档内（压分不设此保护）；
> ⑥ 校准轨迹（trace）收集：`llm_score(trace=...)` 填充 outcome/notes，M10 校准 notes 并入 evidence（审计可追溯）；
> ⑦ 全量 **417 通过**（原 350 + 新增校准测试 20 余条）；ruff 通过（整库 3 条 pre-existing 告警在未触碰文件，非本次引入）。

> ✅ 2026-08-07 **M10 决策输出修复（从「综合评分器」走向「可信最终决策器」）**：
> ① 修高优先级漏洞——`M10DecisionAgent.run()` 原先用 `apply_band(total, vetoed)` 重算结论，
> 不带 `mos_state` 约束，导致 M8 安全边际门禁（expensive → 禁止 buy）在真实 Agent 输出里被冲掉；
> 现在 LLM 校准后的最终总分仍走 `run_decision(total_override=...)` 同一决策函数，
> 否决 / M8 门禁等硬约束统一基于最终总分生效（含回归测试：LLM 抬分到 90 也不得覆盖门禁）；
> ② 补契约字段——输出 `qualitative.decision_reasons[]` + `handoff.decision_code/blocked_by_veto/position`
> （§4 M10），顶层字段保留向后兼容（memo/快照/前端不受影响）；
> ③ M11 真正消费 M10——按 `handoff.decision_code/blocked_by_veto/position` 生成 `decision_watch` 规则
> （avoid/veto → warn 跟踪解除；buy/watch → info 跟踪验证），M10 不再只是展示层；
> ④ M10/M11 改走 `ctx.inputs`（只读 spec.inputs 声明的模块），不再直接读全量
> `session.module_results`，局部重跑 / 分支工作流边界干净；
> ⑤ 顺带补回 M9 `handoff.veto_flags` 消费（经 `vetoes[]` 解析 reason，兼容旧 `outputs.veto`，
> 此前工作区实现缺失、靠陈旧 pyc 掩盖）；新增 11 个测试（M10 agent 门禁/契约/边界 ×6、
> M11 消费 M10 ×3、scoring 契约输入 ×2），相关 76 通过。

> 📋 已讨论但**尚未实施**的估值改进见 [11-valuation-backlog.md](11-valuation-backlog.md)
> （NAV/清算价值、Owner Earnings 完全体、回测权重、保险 EV 等数据源/回测驱动项；
> 第二批已实施清单见该文件文末「已实施（第二批）」）。

> ✅ 2026-08-07 **backlog 第二批（估值/护城河/治理/市场/风险/决策/监控）**：
> ① 估值——三阶段 DCF（growth 启用、保守化）、次新股最少样本门槛（PE<250 交易日）、
> DDM 分红覆盖校验、微利股正常化保护下沉、格雷厄姆公式 PE<10 门控；
> ② M3——增速情景区间（保守档喂 DCF）、WACC 参数化、CAGR 多年几何均值、ROE/负债率与 EPS 解耦；
> ③ M5——宽度合成规则参数化（config）、跨周期 ROE/利润率/杠杆固定 8 年窗口、M5→M1 依赖显式化、
> 竞争证据内容校验（类别词+情绪过滤）、情绪词表扩充；
> ④ M6——质押/减持比例分级、高危码 veto_candidate、降级态中性 50+DATA_UNAVAILABLE、
> 结构化档位字段、治理定性进 memo、`governance_events` 表落库（SCHEMA/ingest/AkShare 质押 best-effort）；
> ⑤ M8——要求折扣按确定性分级（moat×风险修正，[0.2,0.6]）、分批建仓档位、卖出纪律收敛（×1.1+分位>90%）、
> M11 消费 mos_state、正常态 meta.reason_codes；
> ⑥ M7——主指标读路由配置、自然年窗口、winsorize、情绪参数进 config、高估+过热加扣、
> 换手率长短分位、M11 情绪规则、M9 消费情绪（升级/接飞刀）；
> ⑦ M9——期望损失 P×L 排序、压力情景接 M4 内在价值（绝对回撤+仓位上限）、红队 veto_candidate 闭环、
> M9/M10 治理维度解耦、风险项去重、风险清单进 memo；
> ⑧ M10——LLM 校准 ±15 幅度保护、仓位联动安全边际/风险、LLM 定性理由、core_facts 分组、
> 决策快照含 reasons/handoff、权重/档位读 config；
> ⑨ M11——runner 消费 monitor_rules、非价格 watch 可执行、description→message、severity 透传、
> 质量加权评分、cmd_monitor 会话存储与生产一致、webhook 单测；
> ⑩ 工程质量——整库 ruff 0 error、raw 截断、前端 labels/catalog 对齐、契约测试补 8.10/8.11/5.8。
> 全量 **350 通过**（原 312 + 新增 38）。

> ✅ 2026-08-07 **backlog 第三批（「数据其实拿得到」——资产负债表/北向/两融/大盘情绪落地）**：
> ① 核实 AkShare 免费接口——1.1 NAV/NCAV、1.4 归母口径、5.2 有息/合同负债、5.4 研发费用、
> 6.2 股权集中度、7.1 北向、7.2 两融、7.5 大盘涨跌家数、7.12 多情绪合成、9.3 财报季复查全部可拿；
> ② `financials` 新增 bvps/ncav_ps/rd_ratio/interest_debt_ratio/contract_liability_ratio/ocf_to_np_parent，
> `_merge_financial_statements` 合并东财三大报表；新增 `nav`/`ncav` 估值方法并接入 asset_based/cyclical 路由；
> ③ 新增 `northbound`/`margin` 表 + ingest/DataManager，M7 聚合换手率+北向+两融+大盘情绪；
> ④ M5 杠杆改有息口径、研发强度进来源识别；M6 股权集中度 CONTROL_RISK；
> ⑤ `monitor --quarterly` 财报季复查提醒；
> ⑥ 真正拿不到只剩：保险 EV、客户集中度/转换成本、专利数量、并购回报跟踪。
> 全量 **359 通过**（+9）。

---

> ✅ 2026-08-07 **M9 风险与否决补强（从「风险聚合器」走向「永久损失防线」）**：
> ① 修 M2 分数断点——M2 输出 `handoff.quality_score / risk_signal_codes`（契约 §4 M2），
> M9 改读 handoff 并回退 `ModuleResult.score`（旧读不存在的 `outputs["score"]`，M2<30 否决生产恒不触发；
> 测试改真实输出形状 + 降级回退回归）；
> ② 补设计否决规则——造假信号命中（M2 多项红旗 ≥2）、审计非标（M6 `AUDIT_QUALIFIED` 白名单）、
> 质押率 > 80%（M6 规则层风险码透传 `ratio`）、行业明确下行 + 高杠杆（M3 prosperity=down × M2 负债率 ≥60%）；
> ③ 风险清单按严重度排序 + 严重度加权评分（critical 40 / high 25 / medium 10 / low 4），
> 新增 `max_loss_scenario` 压力情景（景气腰斩 + 估值腰斩，基于 M8 折扣率估算最大回撤）；
> ④ 契约收口——M9 输出 `handoff.veto_flags / max_severity / monitor_candidates`，
> M10 改读 `veto_flags`（经 vetoes[] 解析 reason，兼容旧 `outputs.veto`）；
> ⑤ M11 只消费 `monitor_candidates` 转监控规则（字段缺失回退全量），并去重 M2 同源信号双份规则；
> ⑥ 新增 15 个测试，全量 299 通过。

> ✅ 2026-08-07 **M6 治理与资本配置修复（不再是纯分红代理）**：
> ① 规则层补非分红证据——数据源 `governance_events`（质押/减持/监管处罚/审计变更/并购回报/回购）
> 进入评分并映射结构化 `risk_codes`（事件未接入时中性计，不臆测）；
> ② LLM 定性 schema 对齐契约（shareholder_alignment / capital_allocation / governance_risks[] /
> disclosure_quality），合法 `governance_risks` 回填 `handoff.governance_risk_codes` + `signals`（M9 消费闭环）；
> ③ 修 M9 断点——改读 `handoff.governance_score`（旧读 `outputs["score"]`，该键不存在导致
> 生产分支恒不触发，测试靠手工塞 `"score"` 掩盖）+ 消费 `governance_risk_codes`（severity 进 Risk Registry、high 进监控候选）；
> ④ `handoff.governance_score` = 最终分数（含 LLM 评分校准），M4/M9/M10 同口径；
> ⑤ 新增 11 个测试（M6 引擎 ×4、M6 agent ×5、M9 消费 ×2），全量 284 通过。

> ✅ 2026-08-07 **603049 除零事故修复（M8 降级 + M4 源头双保险）**：
> 事故链：中策橡胶（次新股，2025-06 上市）资产负债表缺失 → `bvps=0.0`（非 None）→ 周期股主方法
> `pb_band` 未挡 `bvps<=0`、产出估值 0.0 → 加权中位数被压成 0 → `intrinsic={low:0, mid:0, high:21.96}`
> → M8 `1−price/low` 除零崩溃 → 安全边际分析失败。
> ① **M8 防御层**：`low<=0` 视为异常输入降级 `unavailable` + `reason_codes=[OUT_OF_RANGE]`，
> agent 侧 `meta.degraded=true` / completeness=low（前端可识别），不再抛异常；
> ② **M4 源头**：`pb_band` 补 `bvps<=0` 防护（与 graham_number/nav 对齐），汇总层只认**正值**估值
> （0 是缺数不是估值），复跑同构场景 mid 由 0 → 43.75；③ 回归测试 +4
> （pb_band 零值 ×2、引擎级 603049 场景、M8 零下沿降级 ×2），384 全绿。

> ✅ 2026-08-07 **M8 契约断点补齐（reason_codes 枚举 + 高估态真实输出 + M10 消费 mos_state）**：
> ① `ReasonCode` 补 `PRICE_ABOVE_INTRINSIC`（此前文档 §4 M8 有、枚举缺失，validate_meta 会拒收）；
> ② M8 引擎/智能体按状态输出 reason_codes——现价高于内在价值上沿 → `PRICE_ABOVE_INTRINSIC`，
> 数据不足 → `INPUT_MISSING`，正常态空数组，`handoff.reason_codes` 不再恒为 `[]`；
> ③ M10 真实消费 `mos_state`：`expensive` 时禁止 buy（评分再高也只给 watch/关注，仓位 5%），
> 落地契约「M10 消费 mos_state」声明（此前仅展示层消费）；④ 新增 8 个测试
> （契约枚举 ×1、M8 引擎 reason_codes ×3、M8 智能体 ×2、M10 门禁 ×2），全绿。

> ✅ 2026-08-07 **M7 价格与情绪补全（情绪落地 + 行业主指标 + 10 年口径）**：① **换手率情绪真正进结论**——
> 东财日线新增 `turnover`（换手率）字段并落库（SCHEMA/迁移/schema.sql 同步），M7 把最新换手率
> 历史分位作为情绪热度，过热 −5 分 / 过冷 +5 分（只调置信度、不改价格位置），handoff 新增
> `sentiment_heat`；② **按生意类型选主指标**——M7 改为依赖 M1：周期/资产型、银行/券商主看 PB
> （不再被高 PE 用 max() 误伤），消费/成长/保险主看 PE，缺失回退 max(PE,PB)；③ **10 年口径 +
> 剔除异常期**——窗口只留近 10 年，分位参考序列剔除首尾 1% 极端值（样本 ≥100 时生效）；
> ④ 修复旧测试用非法日期（20250199）导致样本被严格校验过滤的问题，改用真实连续交易日。
> 新增 13 个测试（引擎窗口/主指标/情绪叠加 ×10 + 智能体接线/降级 ×3），262 全绿 + 前端 tsc 通过。

> ✅ 2026-08-07 **M7 价格与情绪闭环（契约落地）**：① **M8 真正消费 `margin_adjustment`**——
> 此前该 handoff 只生产不消费，现在叠加到要求折扣上（过热 +0.05 / 样本不足 +0.10 / 低估 −0.05），
> 买入区间随市场温度收放，evidence 明示「要求折扣 base → effective」；② **M7 PB-only 回退**——
> PE 样本不足但 PB 完整时不再误判「样本不足」，改用 PB 分位判定价格位置（银行/保险/资产型公司），
> PE 缺失时盈利收益率标注「不可计算（PE 样本不足）」；③ 新增 10 个测试
> （M8 引擎叠加 ×3、M8 智能体消费 M7 handoff ×4、M7 PB-only/PE-only 回退 ×3），249 全绿。

> ✅ 2026-08-07 **M4 特殊类型估值（Tier 1：亏损股/金融细类/公用事业）**：① 亏损股（EPS≤0）
> 强制只用 PB 资产锚，不再整块估值空白；② 金融按细分行业路由——**银行 PB-ROE**（新增 `pb_roe`
> 方法：BVPS×(ROE−g)/(r−g)，隐含 PB 夹逼 0.4~3）、**券商正常化盈利+PB**（等同周期股）、保险暂用
> 相对PE+DDM；③ 公用事业关键词（电力/燃气/水务等）→ stable_dividend，唐朝法合理 PE 封顶 18 倍；
> DDM 增加 r−g≥2pct 最小价差保护（防折现率-增速价差过小时分母爆炸）。真实数据验证：中信证券
> (券商) mid 26.5、招商银行(PB-ROE) 61.5、长江电力(mid 27.8)。M1 handoff 新增 financial_subtype。
> 9 个新测试，239 全绿。

（中国船舶 600150 实证）**：`relative_median_pe` 增加**正常化保护**
> ——周期股用近 5 年 EPS 中位数代替当期 EPS，并把历史中位 PE 封顶 25 倍（修复「当期 EPS × 被低谷
> 年份顶高的历史 PE」双重失真：600150 由 141.95 元 → 16.52 元）；新增 **pb_band**（每股净资产 ×
> 历史 PB 中位/分位）作为重资产周期股主方法（cyclical 路由权重 0.50）。600150 实测：内在价值由
> 76~165（mid 120）修正为 24~40（mid 31.8，一致性 0.633→0.754），M8 结论由错误的「买入区间」
> 纠正为「合理偏上/无安全边际」。LLM 校准的权重调整现在只作用于最终路由的方法（周期股上给 dcf
> 设权重会被忽略并提示）。6 个新测试，225 全绿。

（v3，可选）**：规则估值打底 → LLM 按行业惯例输出结构化校准
> （business_type 路由覆盖 + 增速/折现率/永续/无风险参数 + 方法权重 + 置信度增量 ±0.1），
> 全部 clamp 到安全区间后用校准参数重跑引擎；不同行业估值体系差异由此落地（银行走 financial 禁 DCF、
> 成长股上调 PEG 权重、消费股上调 DCF 权重）。新增 `valuation/llm.py`（提示词/解析/clamp/应用）、
> M4 agent 接入 `llm_qualitative`（含 calibration + raw），memo 与前端 labels 同步；
> 未配 LLM 完全退化为规则结果（行为不变）。7 个新测试，208 全绿。

（新浪接口本就有该列，之前适配器没读）**：新浪财务指标接口
> `stock_financial_analysis_indicator` 自带 `经营现金净流量与净利润的比率(%)` 列（akshare 返回的
> 原始值已是比率，勿再 ÷100），适配器之前硬编码 `ocf_to_np: None` 导致该字段一直取不到；
> 现改为直接读取 + `ocfps/eps` 兜底。已用 600519/000333/601919/600036 真实验证：列名稳定、
> 数值与 ocfps/eps 完全一致（茅台 2025=0.7212）。库里旧数据（BaoStock 时代）该列为 NULL，
> 需 `value-agent data fetch <code>` 重抓才会写入。2 个新测试，201 全绿。

（大师视角收敛版）**：① 路由统一——`config/valuation_routing.yaml`
> 改为唯一事实来源，方法名=已实现函数（dcf/tang/graham_number/graham_formula/ddm/relative_median_pe/peg），
> 规划中方法（nav/dcf_three_stage 等）不写入，前端只展示可执行方法，测试锁定 YAML 与代码兜底一致；
> ② 汇总改加权中位数 ± 加权标准差（不再 min~max），新增 method_agreement；
> ③ 新增 valuation_confidence（方法级置信度 × 覆盖度 × 一致性）；
> ④ 质量乘数 0.85~1.1（克制区间）= 0.35×M2 + 0.25×M5 + 0.2×M3 + 0.2×M6；
> ⑤ kill switch 复用 M2/M3/M5/M6 信号（LOSS_YEAR/OCF_NP_DIVERGENCE/高杠杆/周期下行/护城河缺失）；
> ⑥ DCF 用现金化利润代理（ocf_to_np×EPS 或 OCFPS，financials 表字段）；
> ⑦ 新增 PEG 方法（growth 路由）；⑧ 买卖点仍归 M8 不重复；
> ⑨ M4 outputs/handoff 补全（intrinsic_range/coverage/valuation_confidence/methods_used），
> 前端 memo 卡展示置信度/质量乘数/风险开关。19 个新测试，199 全绿。

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

