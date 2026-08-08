"""函数注册表（docs/12-v2-upgrade.md §5）。

- 确定性引擎函数登记为带 schema 的只读工具（输入/输出校验）；
- plan-then-execute：planner 输出 {tool, params} 序列 → `execute_plan` 批量执行；
- 工具输出必须过 schema 校验才能进入下一步（防脏数据 / prompt injection）。

已登记：M4 估值方法 ×12（valuation/methods.py）+ M2 财务质量（financials.quality）
+ M7 价格分位（market.percentile）。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

# 输出 schema 里的类型；值允许为 None（如 dcf 不适用时 value=None），非 None 时须匹配类型
OUTPUT_METHOD = {"name": str, "value": float, "low": float, "high": float, "params": dict, "note": str}


class ToolError(ValueError):
    """工具执行/校验失败（未知工具 / 缺参 / 类型错误 / 输出非法）。"""


@dataclass
class ToolSpec:
    name: str
    fn: Callable
    description: str
    # 字段 → 类型；None 值 = 可选参数（缺省时不校验）
    input_schema: dict[str, type | None]
    # 字段 → 类型；值允许 None，非 None 时须匹配类型
    output_schema: dict[str, type]


class ToolRegistry:
    """只读工具注册表 + 执行器（plan-then-execute）。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        fn: Callable,
        *,
        description: str,
        input_schema: dict[str, type | None],
        output_schema: dict[str, type],
    ) -> None:
        if name in self._tools:
            raise ToolError(f"工具重复注册：{name}")
        self._tools[name] = ToolSpec(name, fn, description, input_schema, output_schema)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def execute(self, name: str, params: dict) -> dict:
        """执行单个工具：输入 schema 校验 → 调用 → 输出 schema 校验。"""
        spec = self._tools.get(name)
        if spec is None:
            raise ToolError(f"未知工具：{name}")
        validated = _validate_input(spec, params)
        raw = spec.fn(**validated)
        if not isinstance(raw, dict):
            raise ToolError(f"工具 {name} 返回非 dict：{type(raw).__name__}")
        return _validate_output(spec, raw)

    def execute_plan(self, plan: list[dict]) -> list[dict]:
        """按序执行 [{tool, params}] → [{tool, result}]；任一步失败抛 ToolError。"""
        out: list[dict] = []
        for step in plan:
            name = step.get("tool")
            if not isinstance(name, str):
                raise ToolError(f"plan 步骤缺少 tool 名：{step}")
            result = self.execute(name, step.get("params") or {})
            out.append({"tool": name, "result": result})
        return out


def _validate_input(spec: ToolSpec, params: dict) -> dict:
    if not isinstance(params, dict):
        raise ToolError(f"工具 {spec.name} 参数必须是 dict")
    out: dict[str, Any] = {}
    for field, typ in spec.input_schema.items():
        if field not in params:
            if typ is None:
                continue
            raise ToolError(f"工具 {spec.name} 缺少必填参数：{field}")
        value = params[field]
        if typ is not None and not isinstance(value, typ):
            raise ToolError(
                f"工具 {spec.name} 参数 {field} 类型错误：期望 {typ.__name__}，实际 {type(value).__name__}"
            )
        out[field] = value
    return out


def _validate_output(spec: ToolSpec, result: dict) -> dict:
    for field, typ in spec.output_schema.items():
        if field not in result:
            raise ToolError(f"工具 {spec.name} 输出缺少字段：{field}")
        value = result[field]
        if value is not None and not isinstance(value, typ):
            raise ToolError(
                f"工具 {spec.name} 输出字段 {field} 类型错误：期望 {typ.__name__}，实际 {type(value).__name__}"
            )
    return result


def _wrap_method(fn: Callable) -> Callable:
    """估值方法返回 MethodResult → 转 dict（registry 只认 dict 输出）。"""
    return lambda **kw: asdict(fn(**kw))


def _wrap_financials_quality() -> Callable:
    """M2 财务质量引擎 → dict（FinancialQualityResult → 契约输出）。"""
    from value_agent.financials.quality import analyze_financial_quality

    def _fn(records: list[dict], business_type: str | None = None,
            financial_subtype: str | None = None) -> dict:
        r = analyze_financial_quality(
            records, business_type=business_type, financial_subtype=financial_subtype
        )
        return {
            "score": r.score,
            "metrics": r.metrics,
            "signals": [s.to_dict() for s in r.signals],
            "evidence": r.evidence,
            "details": r.details,
        }

    return _fn


def _wrap_market_percentile() -> Callable:
    """M7 价格分位引擎 → dict（MarketResult → 契约输出）。"""
    from value_agent.market.engine import assess_market

    def _fn(valuation_history: dict, business_type: str | None = None,
            financial_subtype: str | None = None) -> dict:
        r = assess_market(
            valuation_history,
            business_type=business_type,
            financial_subtype=financial_subtype,
        )
        return {
            "pe_percentile": r.pe_percentile,
            "pb_percentile": r.pb_percentile,
            "position": r.position,
            "score": r.score,
            "evidence": r.evidence,
        }

    return _fn


def build_tool_registry() -> ToolRegistry:
    """注册 M4 估值方法（docs/12-v2-upgrade.md §5 注册表示例）。"""
    from value_agent.valuation.methods import (
        dcf,
        dcf_three_stage,
        ddm,
        graham_formula,
        graham_number,
        nav,
        ncav,
        pb_band,
        pb_roe,
        peg,
        relative_median_pe,
        tang,
    )

    reg = ToolRegistry()
    reg.register(
        "valuation.dcf", _wrap_method(dcf),
        description="两阶段 DCF（现金化利润基数，含敏感性）",
        input_schema={"eps": float, "g": float, "r": float, "terminal_g": float,
                      "years": None, "cash_eps": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.dcf_three_stage", _wrap_method(dcf_three_stage),
        description="三阶段 DCF（费雪视角成长股：高速+减速+永续）",
        input_schema={"eps": float, "g": float, "r": float, "terminal_g": float,
                      "high_years": None, "decel_years": None, "cash_eps": None, "decel_factor": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.tang", _wrap_method(tang),
        description="唐朝估值法（三年后合理估值，买点 50% / 卖点 150%）",
        input_schema={"eps": float, "g": float, "risk_free": float, "pe_cap": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.graham_number", _wrap_method(graham_number),
        description="格雷厄姆数 √(22.5×EPS×每股净资产)",
        input_schema={"eps": float, "bvps": float},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.graham_formula", _wrap_method(graham_formula),
        description="格雷厄姆公式 EPS×(8.5+2g)×4.4/Y",
        input_schema={"eps": float, "g": float, "risk_free": float},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.ddm", _wrap_method(ddm),
        description="股利折现（要求 r>g）",
        input_schema={"div": float, "g": float, "r": float, "eps": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.relative_median_pe", _wrap_method(relative_median_pe),
        description="相对估值：历史中位 PE × EPS（周期股可传正常化 EPS + pe_cap 封顶）",
        input_schema={"eps": float, "pe_history": list, "normalized_eps": None, "pe_cap": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.pb_band", _wrap_method(pb_band),
        description="PB 历史分位带估值（周期/重资产主用）",
        input_schema={"bvps": float, "pb_history": list},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.pb_roe", _wrap_method(pb_roe),
        description="PB-ROE（银行/金融主方法：隐含 PB 夹逼）",
        input_schema={"bvps": float, "roe": float, "g": float, "r": float,
                      "pb_floor": None, "pb_cap": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.peg", _wrap_method(peg),
        description="PEG（PE 分位 × 增速）",
        input_schema={"eps": float, "g": float, "pe_history": list},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.nav", _wrap_method(nav),
        description="NAV 清算价值（资产负债表明细，资产型兜底）",
        input_schema={"bvps": float, "discount": None},
        output_schema=OUTPUT_METHOD,
    )
    reg.register(
        "valuation.ncav", _wrap_method(ncav),
        description="NCAV 净流动资产价值",
        input_schema={"ncav_ps": float, "discount": None},
        output_schema=OUTPUT_METHOD,
    )
    # M2 财务质量（分行业口径）
    reg.register(
        "financials.quality", _wrap_financials_quality(),
        description="M2 财务质量引擎：ROE/杜邦/现金流/杠杆/风险信号（按生意类型分行业口径）",
        input_schema={"records": list, "business_type": None, "financial_subtype": None},
        output_schema={"score": float, "metrics": dict, "signals": list,
                       "evidence": list, "details": dict},
    )
    # M7 价格分位
    reg.register(
        "market.percentile", _wrap_market_percentile(),
        description="M7 价格分位：PE/PB 历史分位 + 位置档位",
        input_schema={"valuation_history": dict, "business_type": None, "financial_subtype": None},
        output_schema={"pe_percentile": float, "pb_percentile": float,
                       "position": str, "score": float, "evidence": list},
    )
    return reg
