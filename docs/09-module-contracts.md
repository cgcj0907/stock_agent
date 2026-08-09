# 09 统一模块契约（方案 1：强约束标准版）

> 目标：把 M1–M11 从「自由输出 + 字段名/字符串约定」升级为「程序可消费的契约数据」，
> 让下游（M4/M8/M9/M10/M11）、前端、备忘录、监控 runner 都消费**同一份 schema**，
> 而不是各自解析自然语言。
> 状态：设计定稿（2026-08-05）；待按 §8 分批落地。

## 1. 现状核对（对真实代码的体检结论）

现有 `ModuleResult` 已提供统一外壳：`module / status / score / outputs / evidence / llm_explanation`。
问题不在外壳，而在 **`outputs` 内部无 schema**：

| 模块 | 当前 outputs 形状 | 主要差距 |
|---|---|---|
| M1 | `business_type / one_liner / understandability / industry` + `llm_qualitative` | 规则事实与 LLM 定性并列塞在 outputs；未声明 `handoff.valuation_route` |
| M2 | `metrics / signals: list[str] / summary` | `signals` 是字符串数组，M9/M11 只能字符串转义，无法编排 |
| M3 | `growth_estimate / prosperity` | 无增长来源、可信度、情景；M4 直接读 `outputs.growth_estimate`（约定式 handoff） |
| M4 | `business_type / methods: dict / intrinsic_value / current_price / params` | 方法对象无统一 schema（dict 按方法名作键）；**降级态字段集合与正常态不一致** |
| M5 | `width / score / signals: list[str]` | 只有 `width` 一个标签，无来源/持久性/侵蚀风险 |
| M6 | `dividend_years / payout_latest / note / signals` + `handoff`（governance_score / capital_allocation_flag / governance_risk_codes） | 已接入治理事件 + LLM 风险码回填（M9 消费闭环）；规则层仍以分红代理为基底，治理事件真实数据源待接 |
| M7 | `pe_percentile / pb_percentile / position` | 无 `market_state` / `margin_adjustment` handoff |
| M8 | `price / discount / required_discount / buy_price / sell_price / status` | `status` 是自然语言；降级态字段集合不一致；无 `mos_state` 枚举 |
| M9 | `risk_items: list[str] / veto: list[str]` + `llm_red_team` | 字符串数组，不是 Risk Registry；对 M10/M11 是文案传递 |
| M10 | `dimensions / total / conclusion / position / vetoed` | 已较结构化；缺 `decision_reasons[]`，`conclusion` 是文案档位 |
| M11 | `monitor_rules: [{rule_type, trigger, description, severity}]` | 已结构化（最接近目标）；缺 `source_module / action`，未显式分 watch/alert/action |

### 1.1 真实存在的「handoff 断点」（本方案要一并修）

1. **依赖声明三处不一致**：
   - `sessions/manager.py::MODULE_DEPENDENCIES`：M9 依赖 `{M2,M3,M5,M6,M7,M8}`；
   - `config/workflows/default.yaml`：M9 的 `deps: [M2, M3, M5, M6]` —— **漏了 M7/M8**；
   - M9 引擎 `assess_risk` 实际读取 M7/M8 输出。
   → 结果：走 YAML 工作流时，M9 的 `ctx.inputs` 拿不到 M7/M8，估值情绪与安全边际风险静默缺失。
2. **`AgentSpec.inputs` ≠ 实际读取 ≠ workflow deps**：M4 的 `spec.inputs=["M1_business_model"]`，
   实际代码同时读 M3（`growth_estimate`）；M8 的 `spec.inputs` 声明 `[M4, M7]` 但只在 M4 缺失时兜底。
   → 约定：**`AgentSpec.inputs` = 引擎实际读取的 agent 集合**，并用测试强制与 workflow deps 对齐。
   → 状态：两条断点均已修复（批次 A 修 M9 YAML deps 漏 M7/M8；批次 D 补 M10/M11 消费声明、
     M3 inputs 置空），`tests/test_contracts.py` 防回归。

## 2. 统一模板骨架（所有模块的 outputs 内部结构）

```python
outputs = {
  "schema_version": "1.0",
  "module_type": "fact | risk | decision | monitor",
  "core_facts":  {...},   # 规则引擎产物，程序消费（指标/区间/评分）
  "qualitative": {...},   # LLM 定性，给人看 + 前端渲染（无 LLM 时为空/降级）
  "signals":     [...],   # 结构化风险信号，M9/M11 直接消费
  "handoff":     {...},   # 给下游模块的字段级契约（显式声明 required）
  "meta": {
    "confidence":   0.0,             # 0~1，规则层可信度
    "completeness": "high|medium|low",
    "degraded":     False,           # True = 降级态（status 仍可为 DONE）
    "reason_codes": [],              # 降级原因枚举，见 §3
  },
}
```

### 2.1 分层职责

| 键 | 谁消费 | 规则 |
|---|---|---|
| `core_facts` | 程序（引擎/下游 agent 计算） | 只放确定性产物；数值必须来自数据源 |
| `qualitative` | 人 / 前端 / memo | LLM 专属；无 LLM 时可为空或填规则解释 |
| `signals` | M9 风险聚合、M11 监控 | 统一对象 schema（见 §4.2） |
| `handoff` | 下游模块 | 只读；缺失即降级（completeness=low），不抛错 |
| `meta` | 工作流引擎 / 前端 / 备忘录 | 质量判断，不参与业务计算 |

> 现状兼容：`ModuleResult` 外层字段（`score / evidence / llm_explanation`）保持不变，
> 本次只约束 `outputs` 内部结构；`llm_explanation` 与 `outputs.qualitative` 去重后统一走 `qualitative`。

## 3. 统一降级态

所有模块降级时输出同一形状（字段集合与正常态**完全一致**，只是缺值）：

```python
outputs = {
  "schema_version": "1.0",
  "module_type": "...",
  "core_facts": {"<已算字段>": ..., "<缺失字段>": None},
  "qualitative": {},
  "signals": [],
  "handoff": {"<required 字段>": None},
  "meta": {
    "confidence": 0.0,
    "completeness": "low",
    "degraded": True,
    "reason_codes": ["DATA_UNAVAILABLE"],
  },
}
```

`reason_codes` 枚举（统一常量）：

```
DATA_UNAVAILABLE   # 数据源无数据/字段缺失
DATA_STALE         # 数据过旧（超过 N 期）
LLM_UNAVAILABLE    # 未配置 LLM 或调用失败
INPUT_MISSING      # 依赖模块 handoff 字段缺失
OUT_OF_RANGE       # 数值超出合理区间（数据异常）
DIV_ZERO           # 除零/不可计算
```

## 4. M1–M11 逐模块契约

> 字段命名约定：`core_facts` 尽量沿用现有 engine 字段名（减少改动）；`handoff` 用下划线英文名，
> 避免中文键跨模块传递。每个 handoff 字段标注 `[req]`（required）或 `[opt]`。

### M1 商业模式认知（fact）
- 依赖：无（读 `company_info` + `financials`）
- `core_facts`：`business_type`（枚举见下）、`industry`、`one_liner`、`understandability`
- `qualitative`（LLM）：`business_model`（一句话生意本质）、`understandability`、`reasons[]`
- `handoff`：
  - `valuation_route [req]`：`cyclical | consumer_monopoly | growth | financial | asset_based | stable_dividend`（供 M4 路由，M4 不再自己猜）
  - `understandability_level [req]`：`high | medium | low`（M4 保守度、M8 折扣调整）
- 消费方：M4、M10（business_moat 维度）

### M2 财务质量（fact）
- 依赖：M1（12.1 分行业口径：business_type / financial_subtype → 行业规则；M1 缺失回退通用口径）
- `core_facts`：`metrics`（现字段不变）、`score`
- `signals`：结构化信号数组（见 §4.2），从 `signals: list[str]` 升级
- `handoff`：
  - `quality_score [req]`：0–100（M9 阈值判断、M10 financial_quality 维度不再读 score 副作用）
  - `risk_signal_codes [req]`：命中信号 code 列表（M9 直接引用）
- 消费方：M3、M9、M10、M11

### M3 成长与再投资（fact）
- 依赖：M1、M2（2026-08-09：M1 判周期 → M3 周期增速正常化口径一致，避免 ROE 稳定但行业周期股漏判）
- `core_facts`：`growth_estimate`、`prosperity`、`roe_latest`、`growth_years`（可选）
- `qualitative`（LLM，可选）：`growth_drivers[]`（量/价/新业务/出海拆解）、`reinvestment_quality`
- `handoff`：
  - `recommended_growth_rate [req]`：供 M4 DCF（替代现在读 `outputs.growth_estimate`）
  - `growth_confidence [req]`：`high | medium | low`（由样本期数/波动决定）
  - `cyclicality_flag [req]`：`True/False`（周期行业 → M4 禁用 DCF/唐朝）
  - `prosperity_code [req]`：`up | flat | down`（M9/M11 消费，替代中文"下行"字符串）
- 消费方：M4、M9、M11

### M4 估值（fact）
- 依赖：M1、M2、M3、M5、M6（M2/M3/M5/M6 为**输入用**：质量乘数 + kill switch，不重跑）
- **模块分 = 估值便宜度**（2026-08-09 修复：原为方法覆盖度，现价 2× 内在上沿的浪潮 M4=85 展示误导）：
  `≤下沿→95 / ≤中值→70 / ≤上沿→45 / >上沿→15 / 数据不足→50`；方法覆盖度只进 `handoff.coverage`
- `core_facts`：`intrinsic_value {low, mid, high, std, method_agreement}`、`current_price`、
  `business_type`、`params`、`valuation_confidence`、`quality_multiplier`、`risk_multiplier`、
  `total_multiplier`、`quality_tier`、`kill_switches`
- 汇总口径（v2，2026-08-07）：**加权中位数 ± 加权标准差**（不再用 min~max 包络）；
  `low/mid/high = (中位 ∓ 离散度) × 质量乘数 × 风险折扣`
- **当前/未来估值区分（v2.3，2026-08-08）**：`horizon_years=None` 为**现值口径**（进入内在价值区间）；
  `horizon_years=3` 为**三年后估值**（唐朝法），只作参考展示、**不进入当前内在价值区间**
- `methods[]`（统一方法级 schema，含每方法置信度）：
  ```python
  {"method": "dcf", "applicable": True, "value": 25.0, "low": 20.0, "high": 30.0,
   "reason": "消费垄断+稳定增长，DCF 主用", "confidence": 0.75, "horizon_years": None}
  ```
- `handoff`：
  - `intrinsic_range [req]`：`{low, mid, high}`（M8/M10 消费）
  - `coverage [req]`：`high | medium | low`（方法覆盖度，来自 coverage_score）
  - `valuation_confidence [req]`：0–1
  - `methods_used [req]`：方法名列表
  - `quality_multiplier [opt]` / `kill_switches [opt]`（M10 质量维度辅助）
- kill switch 规则（全部复用上游信号）：`LOSS_YEAR`→禁 DCF/唐朝/PEG；
  `OCF_NP_DIVERGENCE`→DCF×0.85；负债率>70%→整体×0.85；
  周期特征+景气下行→只留相对/资产类；护城河缺失+治理弱→整体×0.9
- `llm_qualitative`（可选，v3，v2.1 更新）：**行业校准**——规则估值打底后，LLM 按行业惯例输出
  `{calibration: {parameter_adjustments, method_weight_adjustments,
  valuation_confidence_delta, industry_notes, risk_notes,
  reasons, calibrated_intrinsic}, raw}`；所有数值在 `valuation/llm.py` 里 clamp 到安全区间
  （增速≤20%、折现率 7~12%、永续≤3%、权重 0.05~0.5、置信度增量 ±0.1），
  校准后引擎用新参数重跑；**v2.1 起 business_type 由 M1 画像单一决策，本层不再覆盖类型**
  （`business_type_override`/`route_confidence` 已移除）；未配 LLM 时完全退化为规则结果
- 消费方：M8、M9、M10、M11
- 降级：`intrinsic_range=None` + `reason_codes=[DATA_UNAVAILABLE]`；**字段集合与正常态一致**（缺值置 None/空）

### M5 护城河（fact）—— 两层制：规则代理评级 × LLM 定性
- 依赖：**M1**（business_type 口径统一，`spec.inputs=[M1_business_model]`，工作流 deps 已对齐；
  另读 financials + company_info 行业）
- `core_facts`：
  - `width`（宽|中|窄|无）：**两层合成后的最终护城河宽度**（M4/M9/M10 消费）
  - `width_source`：`rule_proxy | llm`；`width_conflict`：规则层与 LLM 不一致时 True
  - `rule_proxy`：规则层财务代理评级
    `{tier, score, signals, sources[], peer, erosion_signals[], cycle_notes[]}`
    - 规则层**不再自称护城河结论**：按同行基准相对评分（ROE/利润率/杠杆）。
      基准解析顺序：**真实同行中位数（`peer_medians`，backlog 5.1：AkShare 行业成分股
      财务中位，`moat/peer_benchmarks.py`）> 行业细分 `INDUSTRY_SEGMENT_BENCHMARKS`
      （~26 个细分：白酒/家电/银行/保险/券商/煤炭/钢铁/船舶/光伏/新能源/半导体…，按 industry
      关键词命中）> 生意类型 `PEER_BENCHMARKS`（6 类兜底）> generic**；
      金融细分子行业用净利率口径、跳过杠杆维度（银行 30% / 保险 10% / 券商 30%，
      避免保险净利率被银行中位误伤）；真实中位拉取失败/未配置时自动回退静态基准；
    - `sources[]`：可计算来源代理（无形资产/成本规模 + 可选研发费用率 `rd_ratio`；
      转换成本/网络效应待 LLM 定性）；
    - `erosion_signals[]`：结构侵蚀信号（利润率压缩/杠杆抬升；非周期行业含 ROE 下滑/波动大）；
    - `cycle_notes[]`：周期行业属性备注（ROE 波动/下滑对周期股是行业属性，**不进 erosion_risks**，
      避免污染 M9）；周期基准下 ROE/利润率/杠杆用**近 8 年跨周期均值**参与相对评分（去周期位置）；
    - `peer.debt_note`：debt_to_assets 含合同负债（客户预收），订单型/预收型行业
      高负债率≠高杠杆风险（口径明示，不做机械扣分；有 `contract_liability_ratio` 时按占比细分）
- `qualitative`（LLM，可选）：`moat_sources[]`（五类）、`width`（修正建议）、`durability`、
  `trend`（widening|stable|eroding）、`erosion_risks[]`、`competition_evidence[]`、
  `evidence[]`；枚举白名单清洗后回填
  - **宽度升级门槛**：LLM 的 `width` 与规则层冲突时，必须附带 ≥1 条 `competition_evidence`
    （订单/份额/成本/技术/客户/牌照/专利等竞争优势类事实），否则不采纳 LLM 宽度、回退规则层；
  - **参考池过滤**：M5 的参考资料剔除市场情绪/资金面新闻（净流入/特大单/主力资金/涨停/
    换手/龙虎榜等标题），护城河证据只能是竞争优势类资料
- `handoff`：
  - `moat_width [req]`：`wide | medium | narrow | none`（M10 用，替代中文"宽/中/窄/无"）
  - `moat_durability [req]`：`high | medium | low`（LLM 合法输出优先，否则规则映射）
  - `moat_trend [req]`：`widening | stable | eroding`（5.13：LLM 合法输出优先，否则规则侵蚀信号
    非空→eroding / 否则 stable；M9 用于侵蚀风险 severity 细化）
  - `erosion_risks [req]`：字符串数组（LLM 合法输出优先，否则规则侵蚀信号；**M9 风险聚合消费**）
- 消费方：M4（kill switch/质量乘数）、M9（width + erosion_risks + durability）、M10

### M6 治理（fact）
- 依赖：无
- `core_facts`：`dividend_years`、`payout_latest`、`note`（分红事实保留为证据，不再是全部）
- `qualitative`（LLM）：`shareholder_alignment`、`capital_allocation`、`governance_risks[]`、`disclosure_quality`
- `signals`：`governance_risks` 映射为结构化信号（severity 分级）
- `handoff`：
  - `governance_score [req]`：0–100（M9/M10 消费，替代读 score 副作用）
  - `capital_allocation_flag [req]`：`good | neutral | poor`
  - `governance_risk_codes [opt]`
- 消费方：M9、M10

### M7 价格与情绪（fact）
- 依赖：M1（生意类型 → 主估值指标：周期/资产型、银行/券商看 PB，其余看 PE）
- `core_facts`：`pe_percentile`、`pb_percentile`、`position`（中文标签保留给展示）、
  `sentiment_heat`（0–1 情绪热度，None=未接入）、`sentiment_signals[]`
- 口径：**近 10 年窗口** + 分位参考序列**剔除首尾 1% 异常期**（样本 ≥100 时生效）
- 主指标：按生意类型选 PE 或 PB 为锚（缺失回退 max(PE,PB) 保守口径）
- 情绪叠加：换手率历史分位（日线）→ 综合热度；过热 −5 分、过冷 +5 分，**只调置信度不改变价格位置**
- `handoff`：
  - `valuation_percentile [req]`：0–1（M8/M10 消费）
  - `market_state [req]`：`overheated | normal | cold | insufficient`
  - `margin_adjustment [req]`：安全边际折扣调整量（如过热 +0.05），M8 直接叠加
  - `sentiment_heat [opt]`：0–1 情绪热度（M10/报告展示）
- 消费方：M8、M9、M10、M11

### M8 安全边际（decision）
- 依赖：M4、M7（backlog 6.1 起确定性分级还消费 M2/M3/M5 上游信号，见工作流 deps）
- `core_facts`：`discount`、`required_discount`、`buy_price`、`sell_price`、`price`
- `handoff`：
  - `mos_state [req]`：`attractive | fair | expensive | unavailable`（M10/M11 消费，替代中文 status）
  - `buy_zone [opt]`：`float | None`；`sell_zone [opt]`：`float | None`
  - `buy_tranches [opt]`：分批建仓档位 `[{price, weight, label}]`（backlog 6.2，M11 分档触发）
  - `sell_reference [opt]`：`bool`（backlog 6.3，M7 估值分位 > 90% 的卖出参考信号）
  - `reason_codes [req]`：如 `PRICE_ABOVE_INTRINSIC`、`INPUT_MISSING`
- `qualitative`：`note`（给人看的自然语言，放这里不再放 status）
- 消费方：M9、M10、M11
- 降级：`mos_state="unavailable"` + `reason_codes=[INPUT_MISSING]`，字段集合与正常态一致

### M9 风险与否决（risk）—— Risk Registry
- 依赖：M2、M3、M4、M5、M6、M7、M8（8.5 起含 M4：压力情景接入 intrinsic_range + current_price）
- `risk_items[]`（统一风险项对象）：
  ```python
  {"id": "R-001", "category": "财务|景气|护城河|治理|估值|安全边际",
   "severity": "low|medium|high|critical",
   "source_module": "M2_financial_quality",
   "trigger": "OCF_NP_DIVERGENCE",          # 来自上游 handoff/signals，不自己解析自然语言
   "impact": "盈利含金量存疑", "mitigation": "跟踪现金流/净利比",
   "veto_candidate": False}
  ```
- `vetoes[]`：`{"id", "reason", "severity"}`（一票否决，独立于 risk_items）
- `qualitative`（LLM 红队）：`key_assumptions[]`、`permanent_loss_paths[]`、`verdict`
- `handoff`：
  - `veto_flags [req]`：否决 id 列表（M10 用，替代读 `outputs.veto`）
  - `max_severity [req]`：`low|medium|high|critical`
  - `monitor_candidates [opt]`：需长期监控的风险项 id（M11 直接转规则）
- 消费方：M10、M11

### M10 决策（decision）
- 依赖：M1–M9（维度评分消费全部上游 score + M9 veto）
- `core_facts`：
  - `decision`：`buy | watch | avoid`（程序可消费，替代文案档位）
  - `position`：建议仓位 0–1（veto 时强制 0；8.2 起 = 档位基准 × M8 安全边际修正 × M9 风险修正）
  - `dimension_scores`（现有 dimensions）
  - `total`
  - 注：`core_facts` 已落地为顶层别名（backlog 8.7），与顶层字段同值
- `qualitative`：`decision_reasons[]`（为什么得到该结论，规则解释 + 可选 LLM 复核理由）
- `handoff`：
  - `decision_code [req]`：`buy | watch | avoid`
  - `blocked_by_veto [req]`：`True/False`
  - `position [req]`：0–1
- 消费方：memo、前端、M11、决策快照审计（8.6：快照含 decision_reasons + handoff）

### M11 监控（monitor）
- 依赖：M2、M3、M7、M8、M9、M10（读上游 handoff/signals）
- `rules[]`（每条规则统一 schema，基于现有 `MonitorRule` 扩展）：
  ```python
  {"rule_type": "price_buy|price_sell|valuation_sell|prosperity_watch|fundamental_watch|risk_watch|decision_watch|prior_hit_review|sentiment_watch|mos_watch",
   "source_module": "M8_safety_margin",      # 规则来源模块
   "trigger": "现价 ≤ 1500 元",               # 结构化触发器（数值阈值）
   "severity": "info|warn|critical",
   "action": "watch|alert|action",            # 分层动作
   "message": "跌破买入区间，可分批建仓"}       # 契约字段（9.4：代码与文档统一为 message）
  ```
  - 枚举补充（backlog 9.5）：`prior_hit_review`（跨会话历史命中回顾）、`decision_watch`（M10 决策监控）、
    `sentiment_watch`（换手率情绪过热/过冷）、`mos_watch`（M8 安全边际 expensive → 暂停买入）。
- 消费方：`monitor --daily` runner、前端
- 规则：M11 **只消费上游 handoff/signals 的结构化字段**，不再自己读 `risk_items` 字符串做转义。
- M10 决策消费：M11 读 `M10_decision.handoff.decision_code / blocked_by_veto / position`，
  按结论生成 `decision_watch` 规则（avoid/veto → warn 跟踪解除；buy/watch → info 跟踪验证），
  使 M10 成为持有期管理的真正上游（不再只是展示层）。

### 4.2 统一风险信号对象（`signals[]`）

```python
{"code": "OCF_NP_DIVERGENCE", "severity": "medium",
 "metric": "ocf_to_np_min", "message": "经营现金流/净利润最低 0.62",
 "evidence": "M2_financial_quality: 2023-12-31 ~ 2024-12-31"}
```

M2/M6 产出的 `signals` 全部用此对象；M9 聚合时直接按 `code` 去重/映射，不再字符串转义；
M11 转监控规则时直接取 `message` + `severity`。

## 5. 统一 Prompt 模板（LLM 定性层）

### 5.1 结构

```
system:
  - 角色一句话（如"你是价值投资分析师"）
  - 数据边界：只能基于给定信息判断，禁止编造财务数字
  - 输出规范：LLM_JSON_RULE（只输出一个合法 JSON 对象，无 Markdown/代码块）
  - 幻觉校验：数值不得改写规则层 core_facts；references 必须是真实可核对的来源，
    无法确定返回 []

user:
  - 公司：名称（代码）
  - 规则层输入：core_facts / signals 的 JSON 摘要（LLM 只读不写）
  - 要求输出 JSON schema：
    {"<qualitative 字段>": ..., "signals": [...], "references": [{"title", "url"}]}
```

### 5.2 统一 JSON 包装

LLM 一律返回：

```json
{
  "qualitative": { "<各模块定性字段>": "..." },
  "signals": [],                    // 可选：LLM 发现的风险信号（结构化对象）
  "references": [{"title": "...", "url": "https://..."}]
}
```

模块 agent 负责把 `qualitative` 写入 `outputs.qualitative`、`signals` 并入 `outputs.signals`、
`references` 并入 `evidence`。**LLM 永不直接写 `core_facts` / `handoff`**。

### 5.3 幻觉校验点（每个模块的 prompt 都要写）

- 财务数字（EPS/ROE/负债率）以规则层数据为准，LLM 只能解读不能改动；
- `references` 数量 1–3 条，优先财报/公告/行业报告；无法确定返回 `[]`；
- LLM 输出解析失败 → `qualitative={}` + `meta.reason_codes=[LLM_UNAVAILABLE]`，不阻塞工作流。

## 6. 新增智能体标准模板

```python
# src/value_agent/<module>/agent.py
class M12XxxAgent(Agent):
    spec = AgentSpec(
        id="M12_xxx",
        name="...",
        description="...",
        inputs=["M1_business_model", "M2_financial_quality"],  # = 实际读取的 agent 集合
        requires_llm=True,          # 是否需要 LLM 定性层
        version="0.1.0",
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        result = run_xxx(ctx.inputs, ctx.assumptions)   # 纯函数引擎
        outputs = {
            "schema_version": "1.0",
            "module_type": "fact",                      # fact|risk|decision|monitor
            "core_facts": result.core_facts,
            "qualitative": {},
            "signals": result.signals,
            "handoff": result.handoff,
            "meta": {
                "confidence": result.confidence,
                "completeness": result.completeness,
                "degraded": result.degraded,
                "reason_codes": result.reason_codes,
            },
        }
        return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE,
                            score=result.score, outputs=outputs, evidence=result.evidence)
```

配套三处对齐（新增测试强制）：

```
AgentSpec.inputs ⊆ workflow deps（该 agent 在 workflow 中的 deps） ⊆ MODULE_DEPENDENCIES
```

注册：`agents/builtin.py` 或自定义注册表；工作流 `config/workflows/*.yaml` 声明 deps。

## 7. 统一 Workflow Handoff 模板

- 引用规范：下游只读 `ctx.inputs["<agent_id>"].outputs["handoff"]` 中的字段，
  如 `M4.handoff.valuation_route`；**禁止**直接读 `outputs.business_type` 这类非契约字段。
- 缺失处理：handoff 必需字段缺失 → 模块按降级运行（`completeness=low`，`reason_codes=[INPUT_MISSING]`），
  不抛错、不阻断下游（延续现有 M1/M4/M8 的 DONE 降级模式）。
- 依赖对齐：以 `sessions/manager.py::MODULE_DEPENDENCIES` 为唯一事实源，YAML 工作流由它生成
  （或提供校验工具：`workflow validate` 检查 YAML deps 与 MODULE_DEPENDENCIES 一致 —— 修掉 §1.1 的 M9 断点）。
- 版本：`schema_version` 升级时，消费方按 `>=` 兼容读取；旧字段保留一个版本周期。

## 8. 落地迁移（3 批，保持测试全绿）

> 当前 78 个测试全绿；每批结束跑 `pytest` + 茅台（600519）黄金样本人工核对 + 更新 `docs/progress.md`。

| 批次 | 内容 | 涉及文件 |
|---|---|---|
| A 契约层 | 新增 `core/contracts.py`（枚举：business_type/mos_state/market_state/severity/reason_codes + 信号对象 schema + 校验函数）；`ModuleResult` 增加 `meta` 字段；新增 `tests/test_contracts.py`；修复 M9 YAML deps 缺失 M7/M8 | `core/contracts.py`、`sessions/models.py`、`config/workflows/default.yaml`、`tests/` |
| B 硬核链路 | M2 signals 结构化 → M4 methods[] + 统一降级态 → M8 mos_state 枚举 → M10 decision_code/blocked_by_veto；同步 memo/前端消费字段 | `financials/`、`valuation/`、`safety_margin/`、`decision/`、`report/memo.py`、`frontend/` |
| C 外围与风险 | M1/M3/M5/M6/M7 handoff 字段；M9 Risk Registry（risk_items 对象化 + vetoes + monitor_candidates）；M11 rules 补 source_module/action 分层 | `business_model/`、`growth/`、`moat/`、`governance/`、`market/`、`risk/`、`monitor/` |
| D 收尾 | `AgentSpec.inputs` 与引擎实际读取全面核对 + 新增对齐测试；更新 `docs/templates/module-spec.md` 与 `05-coding-conventions.md` 加入强约束规范 | `agents/`、`docs/` |
| E 输入输出规范增强（二轮优化，可选） | I-1 输入声明对齐测试、I-2 跨会话输入（M11 历史命中/上次结论）、O-3 输出快照审计、O-4 memo 质量自评、O-5 输出稳定性测试 | `sessions/`、`agents/`、`monitor/`、`decision/`、`report/`、`tests/` |

## 9. 验收标准

- [ ] 所有模块 `outputs` 符合五段式骨架，`schema_version` 一致
- [ ] `handoff` 字段被消费方直接读取，无字符串解析/转义
- [ ] 降级态字段集合与正常态一致，`meta.degraded/reason_codes` 齐全
- [ ] M9 的 YAML deps 与 `MODULE_DEPENDENCIES` 一致；`AgentSpec.inputs` 与引擎实际读取一致
- [ ] 前端/备忘录消费契约字段，展示层与计算层解耦
- [ ] 风控节点不可绕过：M9 一定执行（run_always），veto 影响 M10（有测试断言）
- [ ] 输出稳定性：固定输入连续 3 次运行，schema/枚举/关键字段齐全一致（数值允许波动）
- [ ] 数据时效性：分析绑定 `data_snapshot_id`（PIT 已有），回测无未来函数（test_backtest 已覆盖）
- [ ] 输出快照：每次 M10 运行可检索完整输出快照（含输入 handoff 摘要，供复盘/审计）
- [ ] 输入声明对齐：`AgentSpec.inputs` / workflow deps / 引擎实际读取 三处一致（测试强制）
- [ ] pytest 全绿 + 茅台黄金样本核对一致


## 10. 对标主流金融 Agent 的输入输出规范优化（二轮，2026-08-05）

> **立场**：本系统是**价值投资分析**（产出可验证的投资备忘录与结论），不是交易决策系统。
> 因此只借鉴主流金融 Agent 在**输入/输出规范、结构化契约、可追溯性**上的工程做法；
> **不借鉴**其决策机制（交易信号、Bull/Bear 辩论、交易员/组合经理审批、反思复盘、熵修正等）。

> 参考来源（仅取规范/契约/工程维度）：
> - **TradingAgents**（TauricResearch）：structured-output agents / 持久化日志 / 断点续跑 / 回测日期保真
>   <https://github.com/TauricResearch/TradingAgents>
> - **FinRobot**（AI4Finance）：三层 CoT（Data→Concept→Thesis）+ 报告质量三指标
>   <https://arxiv.org/abs/2411.08804>
> - **FinMem**（Stevens，AAAI-SS 2024）：分层记忆把历史信息作为**输入**分层注入
>   <https://researchwith.stevens.edu/en/publications/finmem-a-performance-enhanced-llm-trading-agent-with-layered-memo-2/>
> - **LLM Agents in Finance Survey**（EMNLP 2025）：三大挑战——数值推理 / 提示敏感 / 实时适配
>   <https://aclanthology.org/2025.findings-emnlp.972/>

### 10.1 对标矩阵（只取输入输出规范维度）

| 外部方案 | 可借鉴的规范设计 | 我们方案的落点 |
|---|---|---|
| TradingAgents v0.2.4 | structured-output agents：每个 Agent 输出由 schema 强约束，下游直接消费 | §2 五段式骨架 + §4 逐模块 schema（方案主体） |
| TradingAgents | 持久化决策日志 / checkpoint 续跑 / 回测日期保真 | O-3 输出快照审计；断点续跑已有；PIT 快照已有 |
| FinRobot | 三层 CoT：Data 层结构化指标 → Concept 层定性解释 → Thesis 层综合报告 | O-2 输出三层语义：core_facts(规则层) / qualitative(LLM 层) / 报告层(memo) |
| FinRobot | 报告质量三指标（Accuracy / Logicality / Storytelling） | O-4 memo 输出质量自评 |
| FinMem | 分层记忆把历史信息作为**输入**注入 | I-2 跨会话输入：历史监控命中 / 上次结论 |
| EMNLP Survey | 数值推理弱 / 提示敏感 / 实时适配 | O-2 数值由规则层独占；O-5 固定 schema+校验；I-3 数据快照绑定 |

### 10.2 新增设计（分输入规范 / 输出规范）

**输入规范（Input Contract）**
- **I-1 输入声明对齐**：每个 agent 显式声明三类输入——消费的 agent 集合（`AgentSpec.inputs`）、
  所需 handoff 字段、数据表与 assumptions 参数；`inputs ⊆ workflow deps ⊆ MODULE_DEPENDENCIES` 由测试强制。
- **I-2 跨会话输入**（FinMem 借鉴，仅输入侧）：新一轮分析可注入「历史监控命中（M11）」「上次结论（M10）」；
  只作上下文输入，不覆盖当前数据。
- **I-3 数据输入规范**：分析绑定 `data_snapshot_id`（PIT），输入带 period/时间戳，防未来函数（已有，纳入验收）。

**输出规范（Output Contract）**
- **O-1 五段式 + 逐模块 schema**：方案主体（§2/§4），不变。
- **O-2 输出三层语义**（FinRobot）：`core_facts` 只放规则层数值（LLM 禁止写入）；
  `qualitative` 只放 LLM 定性；报告层（memo）只做综合展示，不反向覆盖 core_facts。
- **O-3 输出快照审计**（TradingAgents 持久化日志借鉴，仅输出侧）：M10 每次运行存完整输出快照
  （decision/position/vetoes/reasons/meta + 输入 handoff 摘要），供复盘/审计，非决策机制。
- **O-4 报告输出质量自评**（FinRobot 三指标）：memo 附 `self_check`（accuracy/logicality/storytelling），
  不改变内容，只标记待人工确认项。
- **O-5 输出稳定性**：固定输入连续运行，schema/枚举/关键字段一致（数值允许波动）。

### 10.3 明确不采纳（决策机制，不适用于价值投资分析）

- TradingAgents 的 Bull/Bear 交易辩论、交易员/组合经理审批流；
- FinCon / FinAgent 的反思复盘、自批判决策回路；
- ALERA 的熵修正决策不确定性；
- 任何交易信号 / 仓位动态调整 / 交易执行类设计。

> 我们保留自身的价值投资流程：M9 风险否决（veto 硬闸门）与 M10 结论输出，
> 这是 M1–M11 理论设计（docs/01-design.md）的一部分，并非借鉴外部交易系统。

### 10.4 与本方案的关系

- 增量不改变 §2 五段式骨架与 §4 逐模块契约；
- I-1/I-2 落在 §6/§7（输入声明与 handoff）强化；O-2/O-4 落在 §5（Prompt）与 memo；O-3/O-5 落在 sessions 与 tests；
- 批次 E 与批次 A–D 解耦，可单独排期。
