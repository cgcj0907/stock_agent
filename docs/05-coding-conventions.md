# 工程规范

> 写代码前读本文档。核心目标：**可复现、可测试、可审计、LLM 不产生数字**。

---

## 1. 目录与命名

```text
src/value_agent/
├── main.py               # CLI 入口（argparse / typer）
├── core/                 # 配置、日志、pydantic 模型、错误定义
├── data/                 # 数据层（适配器/ETL/校验/快照）
├── sessions/             # 会话管理（M 系列模块的运行容器）
├── business_model/       # M1
├── financials/           # M2
├── growth/               # M3
├── valuation/            # M4（含 routing）
├── moat/                 # M5
├── governance/           # M6
├── market/               # M7
├── safety_margin/        # M8
├── risk/                 # M9
├── decision/             # M10
├── monitor/              # M11
├── agents/               # LLM 编排（orchestrator、各模块 agent、writer）
└── backtest/
```

- 模块目录内文件：`xxx.py`（计算）+ `schemas.py`（pydantic 输入输出）+ `agent.py`（LLM 解读，可选）。
- 包内不写业务逻辑，业务模块不 import 数据源细节（只通过 `data/` 接口取数）。

## 2. 数据口径（必须统一）

| 项 | 约定 |
|---|---|
| 行情 | 前复权做指标/回测；除权除息标记原始口径 |
| 财报 | 使用合并报表；区分年报/中报/一季报/三季报；标注报告期 |
| 盈利指标 | 默认 TTM（滚动 12 个月），注明使用口径 |
| 估值分位 | 10 年窗口（不足 10 年用全部历史并注明），剔除异常/亏损 PE |
| 时间 | 全部 UTC 存储，展示转 Asia/Shanghai |
| 快照 | 分析开始时打 point-in-time 快照，重算复用同一快照 |
| 货币 | 人民币元，单位在字段名注明（如 `revenue_yuan`） |

## 3. 模块接口约定

每个模块对外暴露统一结构（与 `sessions.ModuleResult` 一致）：

```python
@dataclass
class ModuleResult:
    module: str
    status: str                 # pending/running/done/failed/skipped
    score: float | None         # 0-100 子评分（M10 加权用）
    outputs: dict               # 结构化结果（指标表/估值区间/信号…）
    evidence: list[str]         # 数据来源/引用（必须非空，强制溯源）
    llm_explanation: str | None
```

- 模块**只读** `session.module_results[依赖模块]` 和 `assumptions`，不修改其他模块结果。
- 分数语义统一：0-100，越高越好；`score=None` 表示该模块不适用（如金融股跑 DCF）。

### 3.1 统一模块契约（方案 1：强约束标准版，见 [09-module-contracts.md](09-module-contracts.md)）

所有模块 `outputs` 内部必须符合五段式骨架：

```python
outputs = {
  "schema_version": "1.0",
  "module_type": "fact | risk | decision | monitor",
  "core_facts":  {...},   # 规则引擎产物，程序消费（LLM 禁止写入）
  "qualitative": {...},   # LLM 定性，给人看/前端渲染
  "signals":     [...],   # 结构化风险信号 {code, severity, metric, message, evidence}
  "handoff":     {...},   # 下游模块的字段级契约（枚举化、英文下划线键）
  "meta": {"confidence", "completeness", "degraded", "reason_codes"},
}
```

- **输入声明**：`AgentSpec.inputs` = 引擎实际读取的 agent 集合，必须满足
  `inputs ⊆ workflow deps ⊆ MODULE_DEPENDENCIES`（`sessions/manager.py` 为唯一事实源），
  由 `tests/test_contracts.py` 强制。
- **handoff**：下游只读 `outputs.handoff` 契约字段，禁止读 `outputs` 内非契约字段拼字符串；
  必需字段缺失 → 按降级运行（`completeness=low` + `reason_codes=[INPUT_MISSING]`），不抛错不阻断。
- **降级态**：字段集合与正常态完全一致，只缺值（None/空），并写
  `meta = {degraded: true, completeness: "low", reason_codes: [...]}`。
- 枚举与校验统一用 `core/contracts.py`（BusinessType / MosState / MarketState / Severity / ReasonCode / RiskSignal / build_meta / validate_meta）。

## 4. LLM 使用约束（幻觉控制清单）

1. 所有数字必须来自工具/规则引擎返回值，LLM 只解释，不计算。
2. LLM 输出后做**数值一致性校验**（与数据源比对），不一致则拒绝并重试/报错。
3. 关键结论必须带 `evidence` 引用（数据表名/公告/研报 ID）。
4. 假设必须显式化，默认值保守：永续 g ≤ 3%、增速 ≤ 15%、WACC 默认 8–10%。
5. `temperature ≤ 0.3`；输出用 pydantic schema 校验。
6. 模型版本写入 `session.model_version`，支持审计回溯。

## 5. 配置管理

- 配置在 `config/*.yaml`（指标/路由/评分/全局），密钥在 `.env`（不入库）。
- 代码不硬编码阈值；指标阈值改 `config/indicators.yaml`，评分权重改 `config/scoring.yaml`。
- 新增数据源/LLM 提供方通过配置切换，不改业务代码。

## 6. 测试要求

| 层级 | 要求 |
|---|---|
| 黄金样本 | 每模块用真实样本股数据锁定输出（防回归） |
| 边界 | 亏损 PE、空数据、ST 股、新股（数据不足 10 年） |
| 勾稽 | 财务勾稽、除权口径、快照一致性 |
| LLM | 数值一致性、拒绝编造数字、schema 校验 |
| 会话 | 状态机迁移、依赖链重算、断点续跑 |

## 7. 提交规范（Conventional Commits）

```text
feat(M2): 财务质量引擎 + 造假信号
fix(financials): 修正商誉占比口径
test(M4): 周期股路由禁用 DCF 用例
docs: 更新开发进度 S2
```

- 一个提交一件事；里程碑完成时更新 `docs/progress.md` 一起提交。

## 8. 错误处理

- 数据质量问题：标记 `quality_flag`，模块输出 `failed` 或降级，不静默继续。
- LLM 调用失败：可重试 2 次；仍失败则该模块跳过 LLM 解读（保留规则输出），不阻塞流水线。
- 会话内异常：状态置 `failed`，可重试恢复，禁止半写入脏状态。
