# 模块规格模板（Module Spec）

> 开发任一模块前复制本文件到 `docs/specs/<module>.md` 并填写。
> 填写完再写代码。

## 基本信息
- 模块编号：M?
- 名称：
- 理论依据：（引用 docs/01-design.md §3.? 及著作/出处）
- 开发者 / 日期：

## 输入
- 依赖模块结果：（M? 的哪些字段，**必须写进 AgentSpec.inputs，且 = 引擎实际读取集合**）
- 数据：（表/接口，口径见 docs/05-coding-conventions.md §2）
- 用户假设/参数：（assumptions 中哪些 key）

## 输出（ModuleResult）
- `score`：评分规则（0-100 如何计算）
- `outputs`：**五段式骨架**（docs/09-module-contracts.md §2）：
  `schema_version / module_type / core_facts / qualitative / signals / handoff / meta`
- `handoff`：给下游的字段级契约，逐字段标注 `[req]`/`[opt]` + 消费方；枚举化、英文下划线键
- `signals`：结构化对象 `{code, severity, metric, message, evidence}`（不产字符串数组）
- `meta`：`{confidence, completeness, degraded, reason_codes}`（降级必填，reason_codes 用 core/contracts.ReasonCode）
- `evidence`：必须附哪些来源

## 计算逻辑
- 公式/规则（伪代码或数学式）
- 阈值与来源（写进 config/indicators.yaml 还是代码内？）

## 边界与异常
- 数据不足 / 亏损 / ST / 新股 / 行业不适用时如何处理
- **降级态必须与正常态字段集合一致**（缺值置 None/空）+ `meta.degraded=True` + `reason_codes`

## LLM 解读（可选）
- 需要 LLM 判断什么？禁止 LLM 判断什么？
- 幻觉校验点（哪些数字必须与数据源一致）

## 测试用例（黄金样本）
| 用例 | 样本股 | 期望输出 | 备注 |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

## 验收标准
- [ ] pytest 绿（含 `tests/test_contracts.py` 对齐断言：inputs ⊆ workflow deps ⊆ MODULE_DEPENDENCIES）
- [ ] outputs 符合五段式骨架，schema_version 一致
- [ ] handoff 字段被消费方直接读取，无字符串解析/转义
- [ ] 降级态字段集合与正常态一致，meta.reason_codes 齐全
- [ ] 黄金样本输出与人工核对一致
- [ ] 证据可溯源
- [ ] 已接入会话（支持重算依赖）
