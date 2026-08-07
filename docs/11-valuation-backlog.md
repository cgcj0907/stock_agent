# 11 估值与成长体系改进待办（backlog）

> 记录 M3/M4 等模块落地后**仍未实施**的改进项：问题/价值、数据门槛、现状兜底、建议优先级。
> 已实施项见 [progress.md](progress.md)（2026-08-07 起：路由统一 / 加权中位数+离散度 /
> valuation_confidence / 质量乘数 / kill switch / 现金化 DCF / PEG / LLM 行业校准 /
> 周期股正常化+PB / 亏损股纯PB / 金融细类(银行 PB-ROE·券商正常化) / 公用事业+tang 封顶 / DDM 价差保护 /
> M3 无 EPS 缺省修复 / 景气度语义修正（零增长≠下行）/ M9·M11 契约消费 / CYCLICAL_DOWN 保留 PB 主方法 / M6 v2（治理事件+风险码+LLM 定性回填）/ M9 治理消费断点修复（读 handoff 而非不存在的 outputs["score"]）/ governance_score 口径统一（M4/M9/M10 同数）/ M8 `ReasonCode.PRICE_ABOVE_INTRINSIC` 枚举 + 高估态 reason_codes / M10 消费 `mos_state`（expensive 禁 buy）/ M10 agent 层门禁修复（LLM 抬分不覆盖 expensive 禁 buy）/ M10 契约输出（decision_reasons + handoff）/ M11 消费 M10 决策（decision_watch）/ M10·M11 走 ctx.inputs / 补回 M9 veto_flags 消费）。
>
> 优先级约定：**P1** = 数据稳定后应做；**P2** = 值得做但需数据/参数/重构投入；
> **P3** = 锦上添花，低优先。
>
> 📌 **2026-08-07 第二批/第三批已实施清单见文末；第三批把「数据其实拿得到」的项落地：
> 1.1 NAV/NCAV、1.4 归母口径、5.2 有息/合同负债、5.4 研发费用、6.2 股权集中度、
> 7.1 北向资金、7.2 两融余额、7.5 大盘情绪、7.12 多情绪合成、9.3 财报季复查（--quarterly）。
> 真正拿不到的只剩：保险 EV、客户集中度（转换成本）、专利数量、并购回报跟踪。**

---

## 1. 数据未到位（理念正确，工程上暂取不到数）

| # | 改进 | 问题 / 价值 | 数据门槛 | 现状兜底 | 优先级 |
|---|---|---|---|---|---|
| 1.1 | **NAV / NCAV 清算价值**（资产型/地产） | 困境/重资产公司的估值硬底线 | 需资产负债表明细（流动资产、总负债、优先股、可变现折扣），当前 `financials` 表没有 | PB 估值 + 格雷厄姆数 + kill switch 提示资产质量 | P2 |
| 1.2 | **真正的 Owner Earnings**（EPS + 折旧摊销 − 维持性资本开支） | 更贴近巴菲特口径，区分维持性/扩张性资本开支 | 折旧摊销与资本开支字段在免费源中口径不稳定，维持性 capex 难可靠区分 | DCF 用现金化代理（`ocf_to_np×EPS` / `OCFPS`） | P1（数据源稳定后） |
| 1.3 | **保险 EV（内含价值）** | 保险行业标准估值法 | 数据源无 EV 数据 | financial 路由暂用相对PE + DDM，输出标注「未用 EV」 | P2 |
| 1.4 | **东财财务摘要精度升级（归母口径）** | `ocf_to_np` 改用归母净利润/原始金额更准（新浪为总额口径） | `stock_financial_abstract` 是宽表（每期一列），解析成本高 | 新浪 `经营现金净流量与净利润的比率(%)` 列（总额口径） | P2 |

## 2. 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 2.1 | **三阶段 DCF**（高速 5y + 减速 5y + 永续） | 成长股估值比两阶段更精细（费雪视角） | 新增 `dcf_three_stage`，growth 路由启用，参数保守化 | P2 |
| 2.2 | **回测驱动的动态权重** | 替代现在写死的规则权重（`METHOD_WEIGHTS` / `TYPE_WEIGHTS`） | 用现有 `backtest/` 引擎回测后反推各方法权重 | P2 |
| 2.3 | **次新股最少样本门槛** | 历史短 → PE 中位与增速 CAGR 失真 | PE 样本 ≥250 交易日、年报 ≥3 期；不足降置信度或禁用相对估值 | P2 |
| 2.4 | **高分红股 payout 可持续性校验** | DDM 在低分红比例时低估公司价值 | 校验 payout 比率与分红覆盖（M6 已有分红代理），接入 DDM 前过滤 | P3 |
| 2.5 | **微利消费股正常化保护下沉** | 部分非周期股近 1 年 EPS 异常低，盈利类方法同样失真 | 把周期股正常化逻辑下沉到「近 1 年 EPS 显著低于多年中位」的非周期股 | P3 |
| 2.6 | **格雷厄姆公式仅在 PE<10 时启用** | 1970 年代 `4.4/Y` 参数过时，作为辅助参考更稳妥 | 按当期 PE 门控 `graham_formula` | P3 |
| 2.7 | **行业粒度路由表** | 生意类型（6 类）仍偏粗，同类型内行业差异大（白酒 vs 调味品、银行 vs 券商） | 把 `config/valuation_routing.yaml` 升级为行业级「方法 + 参数模板」，LLM 只做公司 → 行业映射 | P2（大重构） |

## 3. 工程质量（可选，非估值逻辑）

| # | 项 | 说明 |
|---|---|---|
| 3.1 | **整库 ruff 存量清理** | `ruff check src/ tests/` 约 27~40 个存量 lint 问题（`agents/base.py`、`workflow/engine.py`、`data/snapshots.py` 等，均非估值改动引入） |
| 3.2 | **`llm_qualitative.raw` 瘦身** | raw 仅用于调试，前端已不渲染；如需减 API payload 可去掉或截断 |

---

## 4. 成长与再投资（M3）改进待办

> M3 现状定位是「历史增长与保守估值输入模块」：规则层只用 历史 EPS CAGR + ROE + 负债率 + 波动
> （`growth/engine.py`）。距离设计稿 §3.3 的「成长与再投资分析模块」还差：行业空间/景气、
> 增长引擎拆解、ROIC vs WACC、增速情景区间、可监控验证点。
> 已修复（2026-08-07）：无 EPS 缺省异常（不再 UnboundLocalError）、景气度误判
> （零增长/微增长不再判「下行」，负增长或 ROE 同比下滑 ≥5pp 才下行）、
> M9/M11 改消费 `handoff.prosperity_code`、CYCLICAL_DOWN 保留周期股 PB 主方法。

### 数据未到位（理念正确，工程上暂取不到数）

| # | 改进 | 问题 / 价值 | 数据门槛 | 现状兜底 | 优先级 |
|---|---|---|---|---|---|
| 4.1 | **行业空间与景气数据**（行业收入增速、渗透率、政策、全球趋势传导：能源转型/AI/人口/国产替代/出海） | 设计稿 §3.3 要求；回答「未来 3–5 年行业还能不能长」，而非只看历史增速 | AkShare 宏观/行业接口 + LLM 研报新闻 RAG（未接入） | 历史 EPS CAGR + ROE 趋势代理 | P1（数据源接入后） |
| 4.2 | **ROIC vs WACC + 增量资本回报**（近 5 年投入资本产生的回报） | 设计稿要求；ROE 含杠杆放大，高杠杆高 ROE 公司会被误判「再投资创造价值」 | 需投入资本（IC）、NOPAT、行业化 WACC；`financials` 表暂无 | ROE vs 固定 WACC=0.10 | P1（数据源稳定后） |

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 4.3 | **公司增长引擎拆解**（量/价/新业务·新市场） | 设计稿 §3.3 要求；历史 CAGR 回答不了「未来靠什么涨」 | `GrowthResult` 增加增长引擎字段，LLM 从研报/新闻提取量价与新业务证据 | P2 |
| 4.4 | **增速情景区间（保守/中性/乐观）+ 增长确定性评级** | 设计稿要求；当前只给单一 `growth_estimate`（历史 CAGR 有界 0~20%） | `GrowthResult` 增加 scenario 区间，M4 DCF 用保守档参数 | P2 |
| 4.5 | **景气度可监控验证点** | 设计稿要求；当前 `prosperity` 只是历史增速/ROE 粗分类，无前瞻验证点 | 接入行业数据后输出可监控验证点（渗透率/政策事件），喂给 M11 | P2 |
| 4.6 | **WACC 参数化** | 当前全局常量 0.10，与公司/行业风险不匹配 | 按行业/公司资本结构参数化，再投资质量与 DCF 共用 | P2 |
| 4.7 | **CAGR 端点敏感性** | `_eps_cagr` 只用首尾两年，基期年份异常会放大/缩小增速 | 用多年几何平均/回归口径，或与中间年份交叉校验 | P3 |
| 4.8 | **ROE/负债率与 EPS 解耦** | 当前 `roe/debt` 只取自「有 EPS 的记录」，最新期缺 EPS 时 ROE 数据被丢弃 | 字段池独立过滤，不再以 EPS 是否存在为前提 | P3 |

---

## 5. 护城河（M5）改进待办

> M5 现状（2026-08-07 两层制落地后）：规则层 = **财务代理评级**（相对静态行业基准的
> ROE/利润率/杠杆评分 + 来源代理 + 侵蚀信号/周期备注），LLM 定性（来源/持久性/趋势/
> 侵蚀风险）回填 handoff，宽度两层合成，M9 消费 `erosion_risks`/`moat_durability`。
> 已修复（2026-08-07，详见 [progress.md](progress.md)）：规则层不再自称护城河结论 /
> 同行相对评分（`PEER_BENCHMARKS`）/ 来源识别（无形资产·成本规模代理）/ 侵蚀信号 +
> `cycle_notes`（周期 ROE 波动不入侵蚀）/ LLM 回填 + 宽度冲突处理 +
> `competition_evidence` 升级门槛 / 参考池过滤市场情绪新闻 / 周期行业跨周期 ROE /
> 「船舶·造船」周期关键词 / M9 契约闭环。

### 数据未到位（理念正确，工程上暂取不到数）

| # | 改进 | 问题 / 价值 | 数据门槛 | 现状兜底 | 优先级 |
|---|---|---|---|---|---|
| 5.1 | **真实同行中位数（8 年）** | 设计稿 §3.5 要求「ROE/毛利率 vs 同行中位数」；当前 `PEER_BENCHMARKS` 是每种生意类型一个静态中位代理，跨公司无差异，白酒 vs 调味品、银行 vs 券商被当成同一基准 | 按行业拉可比公司财务数据（行业成分股 + financials）计算中位数；`financials` 表现成单公司表，无行业对照 | 静态基准表 + evidence 注明「静态中位代理」 | P1（数据源接入后） |
| 5.2 | **有息负债 / 合同负债拆分** | `debt_to_assets` 含合同负债（客户预收），订单型行业（造船/建筑/设备）高负债率≠高杠杆风险，规则层会机械扣分 | 资产负债表明细字段（合同负债、短期/长期有息负债）；免费源口径需验证 | `peer.debt_note` 口径注记（不改分） | P1（数据源稳定后） |
| 5.3 | **转换成本 / 网络效应的规则代理** | 五类来源里这两类目前只能靠 LLM 定性，规则层无任何输入 | 需客户集中度、迁移成本、用户/活跃数据等非财务字段，`financials` 表没有 | LLM 定性 + 参考资料 | P2 |
| 5.4 | **研发 / 专利 / 牌照字段** | 「无形资产」来源只有「高毛利率」一个弱代理，专利/牌照壁垒无法从财务表识别 | 研发费用、专利数量、特许经营牌照等字段未入库 | 高毛利率弱代理 + LLM | P2 |

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 5.5 | **宽度合成规则参数化** | `competition_evidence` 门槛写死（≥1 条、升级/降级同门槛），无法按公司规模/数据完整度调整 | 门槛进 `config/`（证据条数、升级 vs 降级差异化、无参考资料时是否放行） | P3 |
| 5.6 | **跨周期 ROE 窗口固定化** | 周期行业现在用全部可用年份均值，年份数随数据变长而漂移；最新值仍可能被极端年拉偏 | 固定「近 8 年」窗口 + 与最新值交叉校验（差异过大时提示） | P3 |
| 5.7 | **周期行业利润率/杠杆同样去周期** | 只有 ROE 用了跨周期均值；利润率、杠杆仍是当期值，低谷期同样会误伤 | 周期基准下利润率/杠杆也用跨周期均值（或至少给周期位置提示） | P3 |
| 5.8 | **M5 与 M1 依赖显式化** | 目前 M5 软读 `ctx.inputs` 的 M1 `business_type` 但不声明依赖；并行运行且 M1 未先跑时回退自行分类，口径可能与用户覆盖不一致 | 若要求严格「先 M1 后 M5」：`config/workflows/default.yaml` + `MODULE_DEPENDENCIES` 加 `M5→M1`，更新契约测试 | P3 |
| 5.9 | **护城河档位与 M10/回测相关性验证** | M5 的 `score`/`width` 未经「宽中窄是否真的预示后续持续高 ROE/超额收益」验证，档位只是规则定义 | 用 `backtest/` 引擎检验档位持续性（宽护城河公司 3–5 年后 ROE/盈利是否仍领先） | P2 |

### 工程质量（可选，非估值逻辑）

| # | 项 | 说明 |
|---|---|---|
| 5.10 | **`competition_evidence` 内容校验** | 目前只做「非空」校验；LLM 可能用「股价上涨/机构看好」凑数。建议要求每条证据带类别标签（订单/份额/成本/技术/客户/其他）并二次过滤市场情绪词 |
| 5.11 | **参考池过滤词表维护** | `_SENTIMENT_TITLE_RE` 是静态正则（净流入/特大单/涨停/换手…），需随市场话术补充（如「蹭概念」「涨停潮」「吸筹」） |
| 5.12 | **真实数据端到端复核** | 测试用 StubData + 假 LLM；需用真实财报（600150/600519 等）跑通 M5，人工核对档位与证据链是否合理一次 |
| 5.13 | **M9 侵蚀风险 severity 细化** | 目前 `durability=low → high` 一刀切；可结合 `trend=eroding` 或规则层「利润率压缩+杠杆抬升」同时命中升级 critical |


---

## 6. 治理与资本配置（M6）改进待办

> M6 现状（2026-08-07 v2 修复后）：规则层 = 分红代理（连续分红年数 + 每股派息趋势）+
> 可选治理事件（质押/减持/监管处罚/审计变更/并购回报/回购，`data/sources/base.py::governance_events`，
> 目前返回空）；LLM 定性（shareholder_alignment / capital_allocation / governance_risks[] /
> disclosure_quality）回填 `handoff.governance_risk_codes` + `signals`，M9 已消费；
> `handoff.governance_score` 与最终分数同口径。
> 距离设计稿 §3.6「治理评级 + 资本配置评分」仍差：真实事件数据源、股权结构与激励绑定、
> 资本配置质量深化（并购回报/资本开支效率）、展示与报告闭环。
> 旧版问题（已修，见 [progress.md](progress.md) 2026-08-07）：纯分红代理无治理证据、
> M9 读 `outputs["score"]` 死代码分支（生产恒不触发，测试靠手工塞 `"score"` 掩盖）、
> LLM 定性只塞 `llm_qualitative` 未闭环、三个下游读三个分数口径。

### 数据未到位（理念正确，工程上暂取不到数）

| # | 改进 | 问题 / 价值 | 数据门槛 | 现状兜底 | 优先级 |
|---|---|---|---|---|---|
| 6.1 | **治理事件真实数据源**（质押/减持/回购/监管处罚/问询函/审计变更） | 让 M6 从「分红代理 + 空事件」变成「有真实治理证据」的关键一步；事件已能进评分与 `risk_codes`，但 `governance_events` 目前恒返回空 | AkShare/巨潮/东财 F10：股权质押、股东/高管减持公告、回购进展、监管处罚与问询函、审计机构变更 | 无事件时中性计（已如实标注，不臆测）；分红代理 + LLM 定性兜底 | P1（数据源接入后） |
| 6.2 | **股权结构与实控人 / 管理层激励绑定**（设计稿 §3.6 产出 1） | 回答「管理层值不值得托付」的核心证据：股权集中度、实控人、管理层持股与股权激励 | 股权结构 / 十大股东 / 管理层持股数据 | 暂无，仅靠分红代理 + LLM 定性 | P2 |
| 6.3 | **资本配置质量深化**（大额并购回报记录、资本开支效率） | 设计稿 §3.6 产出 2；当前只有「持续回购加分」，并购回报仅支持事件占位 | 并购事件 + 后续业绩/股价回报跟踪；资本开支与 ROIC 关系 | 事件扣分兜底 + LLM 定性 | P2 |

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 6.4 | **质押/减持比例分级** | 当前事件统一 medium 扣 15 分；质押 30% 与 80% 的治理含义完全不同 | 按比例阈值分级：如质押 >50% 或减持 >5% 升级 high/加扣，`description` 带比例 | P2 |
| 6.5 | **治理风险码 → 一票否决候选** | 重大监管处罚/实控人高质押等是否应直接 veto，而非仅进风险清单 | M9 对 `REGULATORY_PENALTY(high)` 等高危码配置 `veto_candidate` 白名单，M10 消费 | P2 |
| 6.6 | **扣分/加分参数校准** | 事件扣分封顶 40、回购 +10 是拍脑袋参数 | 用 `backtest/` 回测反推事件对收益的边际影响，校准分值 | P3 |
| 6.7 | **降级路径 `governance_score=0` 修正** | 分红数据获取失败被等价成「治理极差 0 分」，会拖累 M4 质量乘数（kill switch 误触发） | 降级态改为中性分（如 50）+ `reason_codes=DATA_UNAVAILABLE`，与「无数据中性」一致 | P2 |
| 6.8 | **shareholder_alignment / disclosure_quality 结构化** | 契约 qualitative 目前只有文本，无法进入评分与展示 | 增加档位字段（good/neutral/poor）供 M10 或展示层消费 | P3 |

### 展示与消费闭环（工程质量/产品）

| # | 项 | 说明 |
|---|---|---|
| 6.9 | **M6 治理定性进备忘录/报告** | `report/memo.py` 对 M6 零引用，LLM 治理判断与风险码「只存不用」；补 M6 摘要（治理评级 + 风险码 + LLM 结论）到 memo |
| 6.10 | **前端标签/展示补齐** | `frontend/src/lib/labels.ts` 仍只有旧字段（`governance_assessment`/`risks`），缺 `governance_risks`/`shareholder_alignment`/`disclosure_quality`/`governance_risk_codes`/`signals` 等新契约字段标签，且风险码未渲染 |


---

## 6. 安全边际（M8）改进待办

> M8 现状定位（2026-08-07 复核）：**基于 M4 估值下沿 + 生意类型基准折扣 + M7 情绪微调的单段式
> 安全边际计算器**。核心算术层成立（`discount = 1 − 现价/下沿`、`buy_price = 下沿×(1−要求折扣)`、
> `sell_price = 上沿×1.2`、五档 `mos_state`），链路已通：M7 `margin_adjustment` 叠加、
> M9 消费 `discount<0`、M11 消费买卖区间。
> 已修复（2026-08-07，详见 [progress.md](progress.md)）：`ReasonCode` 补 `PRICE_ABOVE_INTRINSIC`、
> M8 高估态真实输出 reason_codes（不再恒为 `[]`）、M10 消费 `mos_state`（expensive 禁止 buy）。
> 与设计稿 §3.8 的差距：确定性分级只按生意类型代理（未真正联动 M5/M9）、买卖纪律单段（无分批建仓）、
> 卖出阈值比「上沿附近」宽松、M11 未消费 `mos_state`。

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 6.1 | **要求折扣真正按确定性分级（M5/M9 联动）** | 设计 §3.8 要求「护城河宽+确定性高 → 20–25%；周期/高风险 → ≥50%」，但 `REQUIRED_DISCOUNT` 只按 `business_type` 取值（consumer_monopoly 25% / growth 35% / financial 30% / cyclical 50% / asset_based 40%），M5 `moat_width` 与 M9 `max_severity` 都没进折扣率本体，`ctx.assumptions["required_discount"]` 只是手动覆盖 | `required_discount = 生意类型基准 × moat 修正 × 风险修正`，夹逼到 [0.2, 0.6]。**注意依赖方向**：M8 不能直接消费 M9（M9 聚合依赖 M8，会成环）——确定性输入应取 M5 `moat_width/durability` + M3 周期/景气 + M2 财务风险等**上游信号**自算风险代理；或把 M9 的「安全边际」风险项从 `max_severity` 剔除后回传 | P2 |
| 6.2 | **分批建仓区间** | 设计 §3.8「打 6 折第一笔、5 折加仓」，当前只有单一 `buy_price`（`buy_zone`），无法支撑仓位管理 | `buy_tranches: [{price, weight, label}]`（如 0.75×下沿 1/3、0.65×下沿 1/3、0.5×下沿 1/3），M11 监控同步升级为分档触发（跌破第一档→建第一笔、第二档→加仓），memo/前端买卖区间卡同步渲染 | P2 |
| 6.3 | **卖出纪律收敛** | 当前 `sell_price = 上沿×1.2`，比设计「内在价值上沿附近兑现」宽松（涨过上沿 20% 才卖）；「估值分位 > 90%」那条腿只追加进 evidence，未进卖出判定 | 卖出区间收敛到上沿附近（如 ×1.0~1.1），并接 M7 `valuation_percentile > 0.9` 触发卖出参考（与 `position=高估/泡沫` 双信号），M11 `price_sell` 规则同步 | P2 |
| 6.4 | **M11 消费 `mos_state`** | 契约 §4 M8 写 `mos_state` 供 M10/M11 消费；M10 已接（expensive 挡 buy），M11 目前只消费 `buy_price/sell_price`，`mos_state=expensive` 时无对应监控规则 | M11 在 `mos_state=expensive` 时补一条「估值偏高，暂停买入」watch 规则，与 `price_sell` 区分 | P3 |

### 工程质量（可选，非估值逻辑）

| # | 项 | 说明 |
|---|---|---|
| 6.5 | **五段式 `qualitative.note` 落地** | 契约 §4 M8 要求自然语言放 `qualitative.note`（不再放 status）；当前全仓都未落五段式 `qualitative` 字段（全局迁移债，非 M8 特有），M8 的 `status` 仍是展示层中文文案。随五段式迁移批次把 `status`/evidence 摘要搬进 `qualitative.note`，展示与契约分层 | P3（全局迁移） |
| 6.6 | **正常态 `meta.reason_codes` 补全** | 当前正常态 `meta={}`（与 M4 约定一致），reason_codes 只在 handoff；前端若按 meta 判断质量/降级，正常态也带 `build_meta(...)` | P3 |

---

## 7. 价格与情绪（M7）改进待办

> M7 现状（2026-08-07 契约落地 + 补全后）：**估值历史分位是主锚**（近 10 年窗口 +
> 首尾 1% 去异常），按生意类型选主指标（周期/资产型、银行/券商 → PB，其余 → PE，缺失回退
> max(PE,PB)），**换手率情绪叠加**（最新换手率历史分位 → 热度，过热 −5 / 过冷 +5，只调置信度
> 不改变价格位置），M8 真正消费 `margin_adjustment`、handoff 含 `sentiment_heat`。
> 已落地（2026-08-07，详见 [progress.md](progress.md)）：M8 消费 margin_adjustment /
> PB-only 回退不误伤 / 换手率情绪进结论 / 行业主指标 / 10 年口径 + 去异常 /
> 日线 turnover 字段落库（SCHEMA + 迁移 + schema.sql）。

### 数据未到位（理念正确，工程上暂取不到数）

| # | 改进 | 问题 / 价值 | 数据门槛 | 现状兜底 | 优先级 |
|---|---|---|---|---|---|
| 7.1 | **北向资金（个股持股/净买入）** | 设计 §3.7 情绪指标之一；外资动向是情绪/筹码的重要信号 | 免费源个股北向持股数据口径不稳定、延迟大（港交所每日披露加工成本高） | 未接入，情绪仅换手率 | P1（数据源稳定后） |
| 7.2 | **两融余额（个股融资/融券）** | 杠杆资金情绪；融资余额抬升常伴随追涨 | 个股两融数据需逐日拉取（东财/交易所披露），字段未入库 | 未接入 | P1（数据源稳定后） |
| 7.3 | **新发基金热度（行业/主题基金发行规模）** | 增量资金情绪；发行高峰常对应阶段顶部 | 需基金发行数据聚合（发行份额/只数），且是市场级而非个股级 | 未接入 | P2 |
| 7.4 | **舆论热度（新闻/研报情绪）** | 设计 §3.7「可用 LLM 扫描新闻舆情辅助」；散户/媒体热度是情绪直接来源 | 需舆情数据源 + LLM 舆情扫描接入（当前 LLM 仅用于评分/定性回填） | 未接入 | P2 |
| 7.5 | **大盘/行业级情绪**（市场整体换手、涨跌家数、行业轮动） | 个股换手率≠市场情绪；「市场先生」更多指市场整体报价 | 需指数/全市场聚合数据；当前只有单股票日线 | 仅个股换手率分位 | P2 |

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 7.6 | **主指标映射唯一事实来源** | `PRIMARY_METRIC` 在 `market/engine.py` 硬编码，与 `config/valuation_routing.yaml` 的路由偏好可能漂移 | 把「主估值指标」写进 routing yaml（cyclical→pb、bank→pb…），代码读配置，契约测试锁 YAML 与代码一致（同 M4 做法） | P2 |
| 7.7 | **10 年窗口精度** | 当前用 `365×10 天` 近似 + 非法日期丢弃，跨年/停牌日口径不精确 | 改用自然年/交易日历口径；`window_years` 参数化进 config | P3 |
| 7.8 | **异常期剔除升级** | 首尾 1% 裁剪偏粗，且只对样本 ≥100 生效；无法识别「已知泡沫/危机区间」 | winsorize 到 [1%,99%] 或按极端区间（历史 ±3σ 之外）剔除并打标签；小样本给降置信度而非直接裁剪 | P3 |
| 7.9 | **情绪叠加参数化** | 阈值（0.66/0.33）与幅度（±5）写死在引擎 | 进 `config/scoring.yaml`，允许按策略调（如趋势策略放大情绪权重） | P3 |
| 7.10 | **sentiment_heat 下沉到 M8/M10** | 目前只经 M7 score 间接影响 M10；「高估+情绪过热」「低估+情绪过热（接飞刀）」未被下游显式消费 | M8 对「高估+过热」额外叠加 margin_adjustment；M10 对「低估+过热」输出接飞刀提示/降档 | P2 |
| 7.11 | **换手率口径细化** | 当前用全历史（近 10 年）分位，次新股样本不足自动 None；长期分位偏「位置」、短期分位才像「情绪」 | 拆「长期位置分位 + 近 60/120 日短期情绪分位」，两者背离时提示 | P2 |
| 7.12 | **多情绪指标合成规则** | 接入北向/两融/基金/舆论后如何合成（等权 vs 按信号质量加权）未定义 | 定义各指标置信度与合成公式；缺某指标时降级为可用指标均值（现有 `avail` 逻辑已支持） | P2（随数据接入） |

### 工程质量（可选，非估值逻辑）

| # | 项 | 说明 |
|---|---|---|
| 7.13 | **真实数据端到端复核** | 测试用 StubData；需用真实日线（含换手率）跑通 M7 一次，人工核对情绪热度/分位是否与盘面直觉一致 |
| 7.14 | **M11 监控消费情绪** | 目前 monitor 只消费 position（高估/泡沫 → 卖出参考）；可加「换手率过热/过冷」监控规则候选，喂给 M11 持续跟踪 |
| 7.15 | **M9 风险消费 sentiment_heat** | 「高估/泡沫 + 情绪过热」估值风险项可升级 severity；「低估 + 情绪过热」可新增接飞刀风险项 |
| 7.16 | **模块命名与能力对齐** | 当前名称「价格与情绪」强于能力（只落地换手率一项情绪）；若短期不补北向/两融，可考虑改名「价格与估值分位」或在前端标注「情绪=换手率」 |

---

## 9. 跟踪监控（M11）改进待办

> M11 现状定位是「监控规则生成器 + 价格提醒 runner」，还不是完整的持有期管理模块：
> 规则生成层已结构化（`monitor/engine.py`，`rule_type/source_module/trigger/severity/action`），
> 消费 M2/M3/M7/M8/M9 输出 + M10 决策；M9→M11（`monitor_candidates` 优先 + M2 同源去重）与
> M10→M11（`decision_watch`）链路已通，测试覆盖尚可；但真正可执行的 daily runner
> （`monitor/runner.py`）只落价格触发，且**不消费 M11 自己生成的 `monitor_rules`**
> （价格逻辑从 M8 outputs 另行推导）。
> 距离设计稿 §3.11「持有期管理」还差：非价格规则可执行、财报季自动复查、事件推送多通道闭环。
> 已修复（2026-08-07）：记忆闭环——`cmd_monitor` 把命中写回存储；新分析经
> `SessionManager.prior_monitor_hits` 继承历史命中，`prior_hit_review` 回放真正生效
> （此前命中只改内存、进程退出即丢，测试已补持久化 round-trip 与端到端用例）。

### 执行层缺口（核心，决定「持有管理」是否成立）

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 9.1 | **runner 消费 `monitor_rules` 而非另写一份价格逻辑** | 规则生成与执行脱节：`run_daily_monitor` 直接读 M8 `buy_price/sell_price`，不读 M11 生成的规则；`action` 分层（watch/alert/action）是装饰性字段，无任何 dispatcher 分发 | runner 改为消费 M11 `outputs.monitor_rules`（先支持 `price_buy/price_sell`），命中时按 `action` 分层触发；让 `action` 字段具备真实语义 | P1 |
| 9.2 | **非价格 watch 接入可执行路径** | `prosperity_watch / fundamental_watch / risk_watch / decision_watch` 目前只展示在 memo，不触发任何复查或告警 | 对 `warn/critical` 级 watch 生成复查任务（重跑 M2/M3/M9 对应模块）或独立告警；景气/财务/风险信号变化时推送 | P2 |
| 9.3 | **财报季自动复查落地** | 设计 §3.11 产出 3「每季度重跑 M2/M3」，目前只有规则描述字符串里的「财报季重点复查」，无任何调度 | 季度调度（cron 按财报季）或检测财报发布后触发增量重跑 M2/M3，与现有 daily runner 并存 | P2 |

### 契约收口

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 9.4 | **规则字段 `description` → `message`** | 契约（`docs/09-module-contracts.md` §4 M11）示例字段是 `message`，代码输出 `description`（`engine.py` / `agent.py`），唯一消费方 memo 读的也是 `description`——内部一致但偏离文档 | 统一为 `message`（或同步契约文档），并加 schema 契约测试防回退 | P2 |
| 9.5 | **`rule_type` 枚举补 `prior_hit_review` / `decision_watch`** | 契约枚举只列 6 种，代码新增了 2 种（跨会话回顾、决策监控），文档未同步 | 契约文档补全枚举并注明语义 | P3 |
| 9.6 | **消除 `risk_items` 字符串回退路径** | 契约要求「只消费 handoff/signals 结构化字段，不再读 risk_items 字符串做转义」；代码仍直接遍历 `risk_items` 并保留旧字符串形态兼容分支 | M9 输出稳定后删掉字符串回退，只走 `monitor_candidates + 结构化 risk_items` | P3 |

### 规则质量与信息损失

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 9.7 | **M2 信号 severity 透传** | `fundamental_watch` 把 M2 信号统一拍平成 `warn`，`critical` 信号被降级 | 直接取 `sig.severity` 映射到规则 severity，保 critical 语义 | P2 |
| 9.8 | **评分改为质量加权而非规则计数** | `score = min(100, 40 + 10×规则数)` 是计数代理，规则越多分越高（噪音规则也加分） | 按规则覆盖维度（价格/景气/财务/风险/决策）+ severity 权重计分 | P3 |

### 生产部署与测试

| # | 项 | 说明 | 优先级 |
|---|---|---|---|
| 9.9 | **`cmd_monitor` 会话存储与生产一致** | `cmd_monitor` 硬编码本地 `SqliteStore`，不走 `SESSION_STORE`/`DATABASE_URL`；GitHub Actions 每次全新 runner、本地库为空——若生产 session 存 Supabase 且未同步，daily runner 可能长期空转「0 会话」 | P1（先核实部署：session 实际存在哪、daily.yml 能否读到） |
| 9.10 | **`notify_webhooks` 无测试** | 推送逻辑（FEISHU/WECHAT webhook 组装、异常兜底）无覆盖 | 用 httpx MockTransport 补单测 | P3 |

---

## 8. 风险与否决（M9）改进待办

> M9 现状（2026-08-07 补强后）：规则层 = 聚合 M2/M3/M5/M6/M7/M8 → Risk Registry
> （结构化风险项，按严重度排序）+ 一票否决（M2<30 / 造假信号命中≥2 / 审计非标 AUDIT_QUALIFIED /
> 质押率 >80%（M6 风险码 ratio）/ 行业景气明确下行+高杠杆 / 手工 veto_reasons）+
> `max_loss_scenario` 压力情景（景气腰斩+估值腰斩，基于 M8 折扣率估算）+ 严重度加权评分
> （critical 40 / high 25 / medium 10 / low 4，否决每条 -30）。契约已收口：
> `handoff.veto_flags / max_severity / monitor_candidates`，M10 读 veto_flags、
> M11 只消费 monitor_candidates。已修断点（详见 [progress.md](progress.md) 2026-08-07）：
> M2 分数读不存在的 `outputs["score"]`（M2<30 否决生产恒不触发，测试靠手工塞 `"score"` 掩盖）。
> 距离设计稿 §3.9「永久损失防线」仍差：概率×损失定量排序、真实审计意见数据源、
> 压力情景接入真实内在价值、LLM 红队永久损失路径未闭环为否决/监控、
> 单一客户/技术依赖与监管政策输入未聚合。

### 数据未到位（理念正确，工程上暂取不到数）

| # | 改进 | 问题 / 价值 | 数据门槛 | 现状兜底 | 优先级 |
|---|---|---|---|---|---|
| 8.1 | **审计非标（审计意见）真实数据源** | 设计否决项「审计非标」目前只能靠 M6 LLM 白名单上报 `AUDIT_QUALIFIED`，规则层无真实审计意见字段，否决全看 LLM 是否报 | 财报审计意见（标准/带强调事项/保留/无法表示意见）字段（东财/巨潮定期报告） | M6 白名单 + LLM 定性兜底；M9 `VETO_RISK_CODES` 消费链路已就绪 | P1（数据源接入后） |
| 8.2 | **单一客户 / 技术依赖、监管政策风险输入** | 设计 §3.9 输入聚合清单还差这两类；现在监管只有 M6 `REGULATORY_PENALTY` 一条路径，单一客户/技术依赖无来源 | 客户集中度（前五大客户占比）、研发替代风险、行业政策数据 | 暂无；LLM 红队 `permanent_loss_paths` 先兜底 | P2 |

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 8.3 | **概率 × 损失幅度定量排序** | 设计要求「风险清单按发生概率 × 损失幅度排序」，现在按严重度代理排序（critical>high>…），severity 是拍脑袋标签不是期望损失 | 为每类风险配（概率, 损失幅度）系数（如景气反转 P=0.3×L=40%、治理事件 P=0.1×L=60%…），`risk_items` 输出 `expected_loss = P×L` 并按此排序；M9 分数改按期望损失口径 | P2 |
| 8.4 | **权重/阈值参数校准** | `SEVERITY_WEIGHT`（40/25/10/4）、否决扣分 30、杠杆阈值 60%、质押阈值 80% 均为拍脑袋 | 用 `backtest/` 回测各类风险信号对后续收益的边际影响校准；阈值下沉到 `config` 可调 | P2 |
| 8.5 | **压力情景接入真实内在价值** | `max_loss_scenario` 只用 M8 折扣率估算百分比；M9 未接 M4 `intrinsic_range`/现价，无法输出「回撤金额 + 相对仓位」 | 把 M4 `intrinsic_range（low/mid/high）` + `current_price` 注入 M9（扩 `AgentSpec.inputs`/工作流 deps），压力情景给绝对金额与建议仓位上限 | P2 |
| 8.6 | **LLM 红队永久损失路径闭环** | `permanent_loss_paths` 目前只进 evidence 展示；设计要红队做强制反方论证，但结论不影响 veto/监控 | 红队输出增加结构化 `veto_candidate: true/false` 字段，高置信永久损失路径经规则/人工确认后进 `vetoes[]` 或 `monitor_candidates` | P2 |
| 8.7 | **M9 分数与 M10 治理维度解耦** | M9 严重度加权分数与 M6 分数在 M10 `governance_risk` 维度（权重 10%）直接平均；否决场景下分数含义失真（虽 veto 强制 avoid） | M10 治理维度改「M6 为主 + M9 只做否决/红旗标记」，或 M9 分数只展示不进加权 | P2 |
| 8.8 | **风险项去重 / 归一化** | 同一风险可能被多个上游重复上报（M2 现金流信号同时进 M2 signals 与 M9 risk_items；M11 已去 M2 同源，但 M9 自身清单仍重复） | M9 按 `trigger/code` 归一化去重，合并同类项并取最高 severity | P3 |

### 展示与消费闭环（工程质量/产品）

| # | 项 | 说明 |
|---|---|---|
| 8.9 | **M9 风险清单进备忘录/报告** | `report/memo.py` 对 M9 只用了 `veto_count` 与「risk_items 是否存在」，风险清单、`max_loss_scenario`、LLM 红队（key_assumptions / permanent_loss_paths / verdict）未展示；补 M9 摘要（Top 风险 + 否决 + 压力情景 + 红队结论） |
| 8.10 | **前端标签/展示补齐** | `frontend/src/lib/labels.ts` 缺 `risk_items / vetoes / max_loss_scenario / handoff.veto_flags / max_severity` 等新契约字段标签；前端未渲染风险清单卡与否决卡 |
| 8.11 | **端到端否决链路测试** | 引擎级测试已覆盖 M9 各规则，但默认工作流（stub 好财务）没有「坏财务 → M2<30 → M9 veto → M10 avoid」的全链路用例；补一个坏财务 stub 的默认工作流端到端断言 |

## 8. 决策输出（M10）改进待办

> M10 现状（2026-08-07 修复后）：五维评分卡（权重 25/20/20/25/10）+ 档位映射
> （强烈关注 10% / 关注 5% / 中性 0 / 回避 0）+ 一票否决（M9 `handoff.veto_flags` → avoid）
> + M8 安全边际门禁（`mos_state=expensive` → 禁止 buy，LLM 校准总分也不得覆盖）
> + 契约输出（`qualitative.decision_reasons[]` / `handoff.decision_code|blocked_by_veto|position`），
> M11 已按决策生成 `decision_watch` 规则（前端通用规则列表可直接渲染，无需另做）。
> 已修复（2026-08-07，详见 [progress.md](progress.md)）：agent 层重算冲掉 M8 门禁 /
> 契约字段补齐（decision_reasons + handoff）/ M11 消费 M10 / M10·M11 改走 `ctx.inputs` /
> 补回 M9 `veto_flags` 消费。
> 与设计稿 §6 的差距：仍是「综合评分器 + 档位映射」——LLM 只校准总分不产理由、
> 仓位固定档位未与安全边际幅度/风险联动、`core_facts` 契约分组未落地、
> 消费闭环（memo/前端展示 reasons、快照审计、runner 事件）未全通。

### 可做但需参数/重构权衡

| # | 改进 | 问题 / 价值 | 建议方案 | 优先级 |
|---|---|---|---|---|
| 8.1 | **LLM 总分校准幅度保护** | LLM 只校准总分、不产理由，78 分可被抬到 82 跨档变 buy；维度分仍是规则分，出现「维度一套、总分另一套」的语义漂移（评审已指出） | 校准幅度封顶（如 ±15 分），超限回退规则分并记 evidence；LLM 输出 `reason` 并入 `decision_reasons` | P2 |
| 8.2 | **仓位联动安全边际幅度 / 风险** | 档位仓位固定（buy=10%），未反映 M8 `discount` 大小与 M9 `max_severity`；呼应 backlog 5.9 / M8-6.1 的「确定性分级」主题 | `position = 档位基准 × M8 安全边际修正 × M9 风险修正`，夹逼 [0, 0.25]，`decision_reasons` 说明仓位依据 | P2 |
| 8.3 | **LLM 定性理由接入** | 契约 §4 M10 `qualitative.decision_reasons` 写「规则解释 + 可选 LLM」；当前 reasons 纯规则，无 LLM 对结论的校验/反驳 | LLM 对（维度分, 总分, 档位）给 1–2 条赞成/反对理由，白名单字段防幻觉，回填 `decision_reasons` | P3 |

### 消费闭环（工程质量/产品）

| # | 项 | 说明 |
|---|---|---|
| 8.4 | **decision_watch(avoid/veto) 进 runner 事件** | M11 已生成 `decision_watch`，但 `monitor --daily` runner 只触发 price_buy/price_sell；「一票否决解除前不建仓」没有形成提醒 | runner 对 `decision_watch` 且 `blocked_by_veto` 的会话补事件（或至少在 memo 提示「解除前不建仓」） | P3 |
| 8.5 | **memo/前端展示 decision_reasons 与 handoff** | memo 执行摘要与前端 memo-card 只渲染 conclusion/total/position/dimensions/vetoed，「为什么是这个结论」未展示（M11 的 decision_watch 已随通用规则列表渲染） | memo 加「决策理由」小节；前端 memo-card 渲染 `decision_reasons` 与 `handoff` | P3 |
| 8.6 | **决策快照审计纳入 reasons/handoff** | O-3 `build_decision_snapshot` 仍只读顶层字段，reasons/handoff 不进审计快照 | 快照补 `decision_reasons` + `handoff`，审计可回放「为什么是这个结论」 | P3 |
| 8.7 | **`core_facts` 契约分组落地** | §4 M10 要求 `core_facts{decision, position, dimension_scores, total}`，当前只有顶层等价字段 | 输出补 `core_facts` 别名（与顶层同值），消费方逐步迁移；契约测试锁一致 | P3 |
| 8.8 | **前端 workflow catalog deps 与真实消费对齐** | `frontend/src/lib/workflows/catalog.ts` 的 M9/M10/M11 deps 均滞后于 `config/workflows/default.yaml`（如 M10 显示 [M4,M7,M8,M9]，实际消费 M1..M9；M9 缺 M7/M8；M11 只显示 M10），UI 依赖图误导 | 展示 deps 与 `AgentSpec.inputs`/YAML deps 同步，契约测试锁三处一致 | P3 |

### 工程质量（可选，非估值逻辑）

| # | 项 | 说明 |
|---|---|---|
| 8.9 | **权重/档位单一事实来源** | `DIMENSIONS`/`BANDS` 在 `decision/engine.py` 硬编码兜底，`config/scoring.yaml` 已定义同款权重/档位/veto 但代码不读——「代码内为兜底」注释与实现不符，调参只能改代码 | 引擎读 `config/scoring.yaml`（权重/档位），代码保留兜底；契约测试锁「YAML 与代码一致」（同 M4/M7 做法） | P3 |
| 8.10 | **agent 层 veto_flags 回归测试** | 引擎层已测 `handoff.veto_flags` → reason；agent 层测试仍用旧 `outputs.veto` 形状 | 补 agent 层 `handoff.veto_flags` 测试，锁定「LLM 不覆盖 veto」在真实输出形状下也成立 | P3 |
| 8.11 | **全工作流级契约一致性断言** | 单测锁了 handoff 与顶层一致，但 O-5 工作流级测试未断言 | O-5 追加：M10 `handoff` 与顶层 `decision_code/position` 一致；M11 有 `decision_watch` 时 `source_module=M10_decision` | P3 |


---

## 已实施（第二批，2026-08-07）

> 本批把「可做但需参数/重构」「工程质量」「契约收口」类可落地项全部实施，
> 数据源未到位项保持 backlog（见各节 P1 数据门槛）。数据库新增 `governance_events` 表
> （SCHEMA/schema.sql/迁移自动生成，AkShare 质押 best-effort 接入，M6 消费）。

### 2. 估值方法
- ✅ **2.1 三阶段 DCF**：`methods.dcf_three_stage`（高速 5y + 减速 5y + 永续，减速档 g×0.5 保守化），
  growth 路由启用，与两阶段 DCF 交叉验证（值更保守）。
- ✅ **2.3 次新股最少样本门槛**：PE 历史 <250 交易日 → 相对估值置信度 −0.15 + evidence 提示；
  年报 <3 期 → 增速/正常化口径提示。
- ✅ **2.4 高分红股 payout 可持续性校验**：`ddm(eps=)` 校验分红率，>100% 标注可持续性存疑，
  <30% 提示 DDM 低估（配合盈利类方法交叉）。
- ✅ **2.5 微利消费股正常化保护下沉**：非周期股当期 EPS < 多年中位 50% → relative_median_pe
  改用正常化 EPS + evidence「微利保护」。
- ✅ **2.6 格雷厄姆公式 PE 门控**：当期 PE ≥10 时跳过 graham_formula（1970s 4.4/Y 参数过时，
  仅深度价值辅助）。

### 3. 工程质量
- ✅ **3.1 整库 ruff 清理**：`ruff check src/ tests/` 0 error（含 DTZ011/S112/PERF402/RUF007 等）。
- ✅ **3.2 llm_qualitative.raw 瘦身**：解析失败原文截断 2000 字符（仅调试用）。

### 4. 成长（M3）
- ✅ **4.4 增速情景区间**：`GrowthResult.scenarios{conservative/neutral/optimistic}`，
  M4 DCF 采用保守档（low 信心再 ×0.5）。
- ✅ **4.6 WACC 参数化**：`assess_growth(wacc=)`，agent 从 assumptions 读取。
- ✅ **4.7 CAGR 端点敏感性**：多年几何平均（逐年 YoY 几何均值）与首尾口径交叉校验取保守者。
- ✅ **4.8 ROE/负债率与 EPS 解耦**：字段池独立过滤，最新期缺 EPS 不再丢弃 ROE/负债率。

### 5. 护城河（M5）
- ✅ **5.5 宽度合成规则参数化**：`config/scoring.yaml` 的 `moat` 段（min_competition_evidence /
  downgrade_requires_evidence），升级必须附证据、降级按配置。
- ✅ **5.6 跨周期 ROE 窗口固定化**：固定近 8 年窗口（CYCLE_WINDOW_YEARS=8），不再随总年数漂移。
- ✅ **5.7 周期行业利润率/杠杆同样去周期**：ROE/利润率/杠杆都用近 8 年跨周期均值参与相对评分。
- ✅ **5.8 M5 与 M1 依赖显式化**：`MODULE_DEPENDENCIES` + default.yaml + spec.inputs 加 M5→M1，
  契约测试锁一致。
- ✅ **5.10 competition_evidence 内容校验**：类别关键词（订单/份额/成本/技术/客户/牌照…）+ 情绪词过滤。
- ✅ **5.11 参考池过滤词表维护**：补充 蹭概念/涨停潮/吸筹/拉升/异动/出货/洗盘/妖股/题材/炒作/情绪/人气。
- ✅ **5.13 M9 侵蚀风险 severity 细化**：`moat_durability=low` 或 `trend=eroding` → high
  （规则层利润率压缩+杠杆抬升 双信号可升 critical，经 rule_proxy 读取）。

### 6. 治理（M6）与安全边际（M8）
- ✅ **6.4 质押/减持比例分级**：质押 >50% / 减持 >5% → high + 加扣，description 带比例。
- ✅ **6.5 治理风险码 → veto_candidate**：REGULATORY_PENALTY/SHARE_PLEDGE 高危码标记
  veto_candidate，M9 转监控候选、M11 长期跟踪。
- ✅ **6.7 降级路径 governance_score=0 修正**：降级态改中性 50 + `reason_codes=[DATA_UNAVAILABLE]`。
- ✅ **6.8 shareholder_alignment / disclosure_quality 结构化**：档位字段（good/neutral/poor）进 handoff。
- ✅ **6.9 M6 治理定性进备忘录**：memo 增加「治理与资本配置（M6）」节（评分/风险码/资本配置/LLM 结论）。
- ✅ **6.10 前端标签补齐**：labels.ts 新增 M6/M8/M9/M10/M11 契约字段标签。
- ✅ **6.1 治理事件数据源落库**（部分）：新增 `governance_events` 表 + 存储/ingest + AkShare 质押
  best-effort；减持/回购/监管等公告类仍待稳定源。
- ✅ **M8-6.1 要求折扣按确定性分级**：`基准 × moat 修正 × 风险修正` 夹逼 [0.2,0.6]，
  确定性输入取 M5 moat_width + M2/M3 风险代理（不消费 M9 避免成环）。
- ✅ **M8-6.2 分批建仓区间**：`buy_tranches[{price,weight,label}]`（0.75/0.65/0.5 × 下沿各 1/3），
  M11 分档触发。
- ✅ **M8-6.3 卖出纪律收敛**：sell_price = 上沿 ×1.1（原 1.2），M7 估值分位 >90% → sell_reference
  双信号（M11 valuation_sell）。
- ✅ **M8-6.4 M11 消费 mos_state**：expensive → `mos_watch`「估值偏高，暂停买入」。
- ✅ **M8-6.6 正常态 meta.reason_codes 补全**：正常态也 build_meta（confidence/completeness/reason_codes）。

### 7. 价格与情绪（M7）
- ✅ **7.6 主指标映射唯一事实来源**：`config/valuation_routing.yaml` 的 primary_metric，
  代码读配置（金融细类 bank/broker→pb、insurance→pe 覆盖），测试锁一致。
- ✅ **7.7 10 年窗口精度**：自然年日历（today − N 年同日），替代 365×N 天近似。
- ✅ **7.8 异常期剔除升级**：winsorize 到 [1%,99%]（样本 ≥30），小样本不裁剪。
- ✅ **7.9 情绪叠加参数化**：`config/scoring.yaml` 的 market_sentiment（阈值/幅度）。
- ✅ **7.10 sentiment_heat 下沉**：M7 高估+过热 → margin_adjustment 额外 +5pct（M8 消费）；
  M10 低估+过热 → 决策理由提示接飞刀。
- ✅ **7.11 换手率口径细化**：长期位置分位 + 近 60 日短期情绪分位，背离 ≥25pp 提示。
- ✅ **7.14 M11 监控消费情绪**：情绪过热/过冷 → `sentiment_watch` 规则。
- ✅ **7.15 M9 风险消费 sentiment_heat**：高估/泡沫+过热 → severity 升级；低估+过热 → 接飞刀项。
- ✅ **7.16 模块命名与能力对齐**：前端 M7 改名「价格与估值分位」，标注「情绪=换手率」。

### 8. 风险（M9）与决策（M10）
- ✅ **8.1 LLM 总分校准幅度保护**：|校准−规则分| >15 → 回退规则分 + evidence（防 78 抬到 82 跨档）。
- ✅ **8.2 仓位联动安全边际/风险**：position = 档位基准 × M8 discount 修正 × M9 max_severity 修正，
  夹逼 [0,0.25]，decision_reasons 说明仓位依据。
- ✅ **8.3 概率×损失定量排序**：risk_items 输出 expected_loss=P×L，按期望损失排序，
  分数改按期望损失口径（严重度权重 × 0.5~1.5 因子）。
- ✅ **8.4 权重/阈值参数校准**（部分）：阈值下沉 config（scoring.yaml market_sentiment/moat），
  回测反推留给 backtest。
- ✅ **8.5 压力情景接入真实内在价值**：M9 注入 M4 intrinsic_range + current_price →
  estimated_downside_amount + suggested_position_cap；工作流 deps 加 M9→M4。
- ✅ **8.6 LLM 红队永久损失路径闭环**：permanent_loss_paths 结构化
  {path, veto_candidate, confidence}，高置信候选进 monitor_candidates + handoff 标注（待人工确认）。
- ✅ **8.7 M9 分数与 M10 治理维度解耦**：governance_risk 维度 = M6 为主，M9 只做否决/红旗。
- ✅ **8.8 风险项去重/归一化**：(source_module, trigger, impact) 去重保留最高 severity。
- ✅ **8.9 M9 风险清单进备忘录**：memo「风险与否决（M9）」节（Top 风险/否决/压力情景/红队结论）。
- ✅ **8.10 前端标签/展示补齐**：labels.ts 新增 M9 字段标签。
- ✅ **8.11 端到端否决链路测试**：新增测试（stub 好财务 → 否决 → M10 avoid）。
- ✅ **8.3(M10) LLM 定性理由接入**：LLM 对（维度分,总分,档位）给 1–2 条赞成/反对理由，
  白名单后并入 decision_reasons。
- ✅ **8.4 decision_watch 进 runner 事件**：runner 对 blocked_by_veto 的 decision_watch 发提醒事件。
- ✅ **8.5 memo/前端展示 decision_reasons 与 handoff**：memo「决策理由（M10）」+ handoff 小节。
- ✅ **8.6 决策快照审计纳入 reasons/handoff**：build_decision_snapshot 补 decision_reasons + handoff。
- ✅ **8.7 core_facts 契约分组落地**：M10 输出 core_facts{decision, position, dimension_scores, total} 别名。
- ✅ **8.8 前端 workflow catalog deps 对齐**：catalog.ts 与 YAML/MODULE_DEPENDENCIES 三处一致（M5/M8/M9/M10/M11）。
- ✅ **8.9 权重/档位单一事实来源**：M10 引擎读 config/scoring.yaml（weights/bands），代码保留兜底。
- ✅ **8.10 agent 层 veto_flags 回归测试**：真实输出形状下 LLM 不得覆盖 veto。
- ✅ **8.11 全工作流级契约一致性断言**：M10 handoff 与顶层一致、M11 decision_watch 来源断言。

### 9. 跟踪监控（M11）
- ✅ **9.1 runner 消费 monitor_rules**：runner 读 M11 规则（price_buy/price_sell 用 params.price 阈值），
  旧会话回退 M8。
- ✅ **9.2 非价格 watch 接入可执行路径**：decision_watch(veto) / valuation_sell / mos_watch / critical 级
  risk·fundamental watch → 每日提醒事件。
- ✅ **9.4 规则字段 description → message**：引擎/agent/memo/前端统一 `message`，契约测试防回退。
- ✅ **9.5 rule_type 枚举补全**：契约文档补 prior_hit_review / decision_watch / sentiment_watch / mos_watch。
- ✅ **9.6 消除 risk_items 字符串回退路径**：M11 只消费结构化 risk_items，字符串形态忽略。
- ✅ **9.7 M2 信号 severity 透传**：fundamental_watch 保留 critical 语义。
- ✅ **9.8 评分改为质量加权**：按覆盖维度（价格/景气/财务/风险/决策/情绪）×10 + severity 加成。
- ✅ **9.9 cmd_monitor 会话存储与生产一致**：改用 create_session_store()（SESSION_STORE/DATABASE_URL）。
- ✅ **9.10 notify_webhooks 无测试**：补 httpx MockTransport 单测（推送 + 空事件 + 失败兜底）。

### 数据库
- ✅ **governance_events 表**：SCHEMA/schema.sql/迁移自动生成（code/event_date/kind/holder/ratio/description），
  storage（sqlite/postgres）自动建表，ingest 接入，M6 引擎消费（质押比例分级 + veto_candidate）。

### 仍未实施（数据源/回测驱动，保持 backlog）
- 1.1 NAV/NCAV、1.2 Owner Earnings、1.3 保险 EV、1.4 东财归母口径、5.1 真实同行中位数、
  5.2 有息/合同负债拆分、5.3 转换成本/网络效应规则代理、5.4 研发/专利字段、
  6.2 股权结构/实控人、6.3 资本配置深化、7.1 北向资金、7.2 两融余额、7.3 基金发行、
  7.4 舆论热度、7.5 大盘/行业情绪、7.12 多情绪指标合成、9.3 财报季自动复查（调度层）、
  2.2 回测动态权重、5.9 护城河档位回测验证、6.6 扣分参数回测校准、8.4 风险阈值回测校准、
  5.12/7.13 真实数据端到端复核（需真实数据源+人工核对）。


---

## 已实施（第三批，2026-08-07 —— 「数据其实拿得到」）

> 核实：这些项的数据源在 AkShare（免费）均有对应接口，已落地；真正拿不到的是
> 保险 EV（无免费个股 EV 接口）、客户集中度/转换成本（无免费 API）、专利数量（无免费 API）、
> 并购回报跟踪（公告结构化困难）。

### 数据与表
- ✅ **1.1 NAV/NCAV 清算价值**：`_merge_financial_statements` 拉东财资产负债表/利润表/现金流量表，
  `financials` 新增 `bvps`/`ncav_ps`；新增 `nav`/`ncav` 估值方法，asset_based 路由 `[nav, ncav, graham_number, graham_formula]`、
  cyclical 补 `nav` 资产兜底；M4 agent 优先用财报 BVPS。
- ✅ **1.4 东财归母口径**：`financials.ocf_to_np_parent`（经营现金流净额/归母净利润），与新浪总额口径并列。
- ✅ **5.2 有息负债/合同负债拆分**：`financials.interest_debt_ratio` / `contract_liability_ratio`；
  M5 杠杆对比改用有息口径，合同负债占比 ≥15% 给口径注记。
- ✅ **5.4 研发/专利字段（研发部分）**：`financials.rd_ratio`（研发费用率），M5 无形资产来源新增
  「研发 ≥5% → 技术壁垒代理」；专利数量/牌照仍无免费 API。
- ✅ **6.2 股权结构（集中度部分）**：akshare `stock_gdfx_top_10_em` → 前十大股东合计比例 ≥70%
  产出 `CONTROL_RISK`（low）治理风险码；实控人/管理层激励数据仍缺。
- ✅ **7.1 北向资金**：新增 `northbound` 表（code/trade_date/hold_shares/hold_ratio），
  akshare `stock_hsgt_hold_stock_em` best-effort，历史序列算分位进 M7 情绪。
- ✅ **7.2 两融余额**：新增 `margin` 表，akshare `stock_margin_detail_sse/szse` best-effort，
  融资融券余额分位进 M7 情绪。
- ✅ **7.5 大盘/行业情绪**：akshare `stock_market_activity_legu` → 全市场上涨家数占比（breadth）进 M7 情绪。
- ✅ **7.12 多情绪指标合成**：M7 聚合 换手率（长/短）+ 北向 + 两融 + 大盘 breadth，缺指标降级为可用均值。

### 调度/工程
- ✅ **9.3 财报季自动复查（调度层）**：`monitor --quarterly` 对 warn/critical 非价格 watch
  补发「财报季复查」提醒（runner `quarterly_review` 参数 + CLI flag）。
- ✅ 存储/ingest：`northbound`/`margin` 表自动建表 + `ingest_company` 落库 + DataManager 查询接口。

### 核实后仍拿不到（免费源无接口 / 需人工/付费）
- 1.3 保险 EV（内含价值）：无免费个股 EV 数据源（年报手工整理，未结构化）。
- 5.3 转换成本/网络效应的规则代理：需客户集中度/迁移成本，无免费 API（仅 LLM 定性）。
- 5.4 专利数量/牌照壁垒：无免费 API（研发费用可拿，已落地）。
- 6.3 资本配置深化（并购回报跟踪）：并购事件公告结构化困难；资本开支（capex）其实在现金流表有，
  可后续接入 ROIC 深化。
- 7.3 新发基金热度：`fund_new_found_em` 存在（市场级），未接线（低优先）。
- 7.4 舆论热度：`stock_news_em`/`stock_research_report_em` 存在，CompanyReferences 已抓新闻喂 LLM，
  单独舆情分位未做（LLM 定性已覆盖）。
- 5.1 真实同行中位数：`stock_board_industry_cons_em` 行业成分存在，需批量拉全行业财务算中位数（重），
  列为可做但需批量工程。
- 2.2/5.9/6.6/8.4 回测校准：数据已有（backtest 引擎 + 入库数据），属回测工程，可做。
- 5.12/7.13 真实数据端到端复核：需要真实数据源 + 人工核对，网络可用时执行。
