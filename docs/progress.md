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
- [x] M6 治理与资本配置（分红持续性代理评分）2026-08-04
- [x] M6 治理与资本配置 v2（治理事件非分红证据 + 结构化风险码 + LLM 风险回填 + 分数口径统一）2026-08-07
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
