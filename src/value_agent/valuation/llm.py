"""M4 估值 LLM 行业校准层（可选）：规则估值打底，LLM 按行业校准路由/参数/权重。

与 M1/M5/M6 定性层同一套设计：
- 规则引擎永远是确定性内核；LLM 只在**有界范围内**微调，禁止编造财务数字
- 无 LLM（未配 LLM_API_KEY）时模块完全退化为规则结果，现有行为与测试不受影响
- 所有数值调整都会 clamp 到工程安全区间，防止单次 LLM 输出把估值拉爆
- 不同行业的估值体系差异体现在：business_type 路由确认/纠正 + 参数（增速/折现率/
  永续/无风险）+ 方法权重 + 置信度增量
"""
from __future__ import annotations

from value_agent.core.contracts import BusinessType
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.valuation.engine import METHOD_WEIGHTS

# 校准字段的工程安全区间（LLM 只能在这个范围内说话，超出会被丢弃）
CALIB_BOUNDS: dict[str, tuple[float, float]] = {
    "growth_rate": (0.0, 0.20),       # 保守增速上限（工程规范）
    "discount_rate": (0.07, 0.12),    # WACC 合理区间（默认 0.10）
    "terminal_growth": (0.0, 0.03),   # 永续增长 ≤3%
    "risk_free_rate": (0.01, 0.05),   # 无风险利率（唐朝法合理 PE 分母）
}
WEIGHT_BOUNDS = (0.05, 0.50)          # 方法权重下限/上限
CONFIDENCE_DELTA_BOUNDS = (-0.10, 0.10)
ROUTE_CONFIDENCE_MIN = 0.60           # route_confidence 低于此值不采用 business_type 覆盖

_BUSINESS_TYPES = {bt.value for bt in BusinessType}

INDUSTRY_CALIBRATION_SYSTEM = (
    "你是价值投资分析师，负责按行业估值惯例校准估值引擎。输入是规则引擎对某家 A 股公司的"
    "估值结果与财务信号，输出是结构化的行业校准建议。\n"
    "原则：\n"
    "1. 只输出一个合法 JSON 对象，不要 Markdown、不要多余文字。\n"
    "2. 禁止编造财务数字：只能基于输入信息判断；对没有把握的项保持不调整。\n"
    "3. 参数只能在范围内调整，超出范围引擎会丢弃：\n"
    "   growth_rate∈[0,0.20]、discount_rate∈[0.07,0.12]、terminal_growth∈[0,0.03]、\n"
    "   risk_free_rate∈[0.01,0.05]、method_weight∈[0.05,0.5]、valuation_confidence_delta∈[-0.10,0.10]。\n"
    "4. business_type_override 只能取 consumer_monopoly/growth/cyclical/financial/"
    "asset_based/stable_dividend 之一或 null；route_confidence<0.6 时引擎不会采用覆盖。\n"
    "5. 周期股（cyclical）注意：景气上行期禁用「当期盈利 × 历史中位 PE」高估（历史 PE 会被"
    "低谷年份顶高），应优先 PB/正常化盈利；method_weight_adjustments 只能对『当前适用方法』"
    "调整，不要给未路由的方法（如周期股的 dcf）设权重。\n"
    "6. 输出 JSON 结构：\n"
    '{"business_type_override": "consumer_monopoly|growth|cyclical|financial|asset_based|stable_dividend|null",\n'
    ' "route_confidence": 0.9,\n'
    ' "parameter_adjustments": {"growth_rate": 0.08, "discount_rate": 0.09, "terminal_growth": 0.02, "risk_free_rate": 0.025},\n'
    ' "method_weight_adjustments": {"dcf": 0.40, "relative_median_pe": 0.25},\n'
    ' "valuation_confidence_delta": 0.05,\n'
    ' "industry_notes": ["行业估值惯例说明"], "risk_notes": ["行业特有风险"], "reasons": ["为什么这样校准"]}\n'
    + LLM_JSON_RULE
)


def _to_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_calibration_prompt(
    *,
    company_name: str,
    code: str,
    industry: str,
    business_type: str,
    allowed: list[str],
    method_lines: list[str],
    intrinsic: dict,
    confidence: float,
    params: dict,
    upstream: dict,
    refs_block: str = "",
) -> str:
    """组装行业校准提示词：给 LLM 规则引擎的完整上下文 + 上游信号。"""
    lines = [
        f"公司：{company_name}（{code}）",
        f"行业：{industry or '未知'}；规则路由生意类型：{business_type}",
        f"当前适用方法：{', '.join(allowed)}",
        "各方法估值（元/股）：",
    ]
    lines += [f"  - {m}" for m in method_lines]
    iv = intrinsic or {}
    lines.append(
        f"内在价值区间：低 {iv.get('low')} / 中 {iv.get('mid')} / 高 {iv.get('high')}"
        f"（方法一致性 {iv.get('method_agreement')}，规则置信度 {confidence}）"
    )
    lines.append(
        f"当前参数：growth_rate={params.get('growth_rate')} discount_rate={params.get('discount_rate')} "
        f"terminal_growth={params.get('terminal_growth')} risk_free_rate={params.get('risk_free_rate')}"
    )
    lines.append("上游模块信号：")
    for key, value in upstream.items():
        lines.append(f"  - {key}: {value}")
    if refs_block:
        lines.append("参考资料（供判断行业惯例，禁止编造标题/链接，仅参考）：")
        lines.append(refs_block)
    lines.append("请按行业估值惯例输出行业校准 JSON（只输出 JSON 对象）。")
    return "\n".join(lines)


def clamp_calibration(raw: dict) -> dict | None:
    """把 LLM 原始输出规范化 + clamp 到安全区间；空校准返回 None。"""
    if not isinstance(raw, dict):
        return None
    out: dict = {}

    bt = raw.get("business_type_override")
    route_conf = _to_float(raw.get("route_confidence"), 0.0)
    route_conf = max(0.0, min(1.0, route_conf))
    if bt in _BUSINESS_TYPES and route_conf >= ROUTE_CONFIDENCE_MIN:
        out["business_type_override"] = bt
        out["route_confidence"] = round(route_conf, 3)

    params = {}
    for key, (lo, hi) in CALIB_BOUNDS.items():
        v = _to_float((raw.get("parameter_adjustments") or {}).get(key))
        if v is not None:
            params[key] = round(max(lo, min(hi, v)), 4)
    if params:
        out["parameter_adjustments"] = params

    weights = {}
    for key, v in (raw.get("method_weight_adjustments") or {}).items():
        fv = _to_float(v)
        if fv is not None and key in METHOD_WEIGHTS:
            weights[key] = round(max(WEIGHT_BOUNDS[0], min(WEIGHT_BOUNDS[1], fv)), 3)
    if weights:
        out["method_weight_adjustments"] = weights

    delta = _to_float(raw.get("valuation_confidence_delta"))
    if delta is not None:
        out["valuation_confidence_delta"] = round(
            max(CONFIDENCE_DELTA_BOUNDS[0], min(CONFIDENCE_DELTA_BOUNDS[1], delta)), 3
        )

    for key in ("industry_notes", "risk_notes", "reasons"):
        val = raw.get(key)
        if isinstance(val, list):
            cleaned = [str(x).strip() for x in val if str(x).strip()]
            if cleaned:
                out[key] = cleaned[:5]
        elif isinstance(val, str) and val.strip():
            out[key] = [val.strip()]

    return out or None


def parse_calibration(text: str | None) -> dict | None:
    """解析 LLM 回复 → 规范化校准；解析失败/空校准返回 None。"""
    if not text:
        return None
    raw = parse_llm_json(text)
    return clamp_calibration(raw)


def apply_calibration(
    params: dict, weights: dict, calib: dict,
) -> tuple[dict, dict, str | None, float]:
    """把校准应用到参数/权重 → (params, weights, business_type_override, confidence_delta)。"""
    p = {**params}
    p.update(calib.get("parameter_adjustments") or {})
    w = {**weights}
    w.update(calib.get("method_weight_adjustments") or {})
    bt = calib.get("business_type_override")
    delta = _to_float(calib.get("valuation_confidence_delta"), 0.0)
    return p, w, bt, delta
