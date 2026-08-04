"""M4 估值引擎：方法路由（按生意类型）+ 多模型交叉 + 内在价值区间。

业务类型默认来自 M1（当前为 stub，暂用 assumptions 覆盖），
路由表与 config/valuation_routing.yaml 一致（代码内为兜底默认值）。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .methods import (
    MethodResult,
    dcf,
    ddm,
    graham_formula,
    graham_number,
    relative_median_pe,
    tang,
)

# 兜底路由（与 config/valuation_routing.yaml 对齐；M1 落地后从输入取类型）
DEFAULT_ROUTING: dict[str, list[str]] = {
    "consumer_monopoly": ["dcf", "tang", "graham_number", "graham_formula", "ddm", "relative_median_pe"],
    "growth": ["dcf", "relative_median_pe"],
    "cyclical": ["relative_median_pe", "graham_number"],  # 禁 DCF/唐朝（周期股）
    "financial": ["relative_median_pe", "ddm"],           # 禁 DCF（现金流法不适用）
    "asset_based": ["graham_number"],
    "stable_dividend": ["ddm", "tang"],
}
DEFAULT_TYPE = "consumer_monopoly"


def default_params() -> dict:
    return {
        "growth_rate": 0.10,      # 保守增速（≤15% 上限见工程规范）
        "discount_rate": 0.10,    # WACC 默认
        "terminal_growth": 0.03,  # 永续增长（≤3%）
        "risk_free_rate": 0.04,   # 无风险利率（唐朝法合理PE=25）
    }


@dataclass
class ValuationResult:
    business_type: str
    methods: dict[str, MethodResult]
    intrinsic: dict
    coverage_score: float
    evidence: list[str]
    params: dict = field(default_factory=dict)


def run_valuation(
    *,
    eps: float | None,
    bvps: float | None,
    pe_history: list[float],
    dividend: float | None,
    business_type: str = DEFAULT_TYPE,
    params: dict | None = None,
) -> ValuationResult:
    """主入口：按业务类型路由方法 → 执行 → 汇总内在价值区间。"""
    p = {**default_params(), **(params or {})}
    allowed = DEFAULT_ROUTING.get(business_type, DEFAULT_ROUTING[DEFAULT_TYPE])
    g, r, tg, rf = p["growth_rate"], p["discount_rate"], p["terminal_growth"], p["risk_free_rate"]

    methods: dict[str, MethodResult] = {}
    if "dcf" in allowed:
        methods["dcf"] = dcf(eps, g, r, tg)
    if "tang" in allowed:
        methods["tang"] = tang(eps, g, rf)
    if "graham_number" in allowed:
        methods["graham_number"] = graham_number(eps, bvps)
    if "graham_formula" in allowed:
        methods["graham_formula"] = graham_formula(eps, g, rf)
    if "ddm" in allowed:
        methods["ddm"] = ddm(dividend, g, r)
    if "relative_median_pe" in allowed:
        methods["relative_median_pe"] = relative_median_pe(eps, pe_history)

    values = [m.value for m in methods.values() if m.value is not None]
    evidence = [f"生意类型：{business_type}；适用方法：{', '.join(allowed)}；参数：{p}"]
    for m in methods.values():
        if m.value is not None:
            evidence.append(f"{m.name}: {m.value} 元（{m.params}）")
        else:
            evidence.append(f"{m.name}: 跳过（{m.note}）")

    if not values:
        intrinsic = {"low": None, "high": None, "mid": None}
        score = 0.0
    else:
        low, high = min(values), max(values)
        intrinsic = {"low": round(low, 2), "high": round(high, 2), "mid": round(statistics.median(values), 2)}
        score = round(len(values) / len(allowed) * 100, 1)
        if high / low > 3:  # 方法间分歧过大，降低可估性评分
            score = max(0.0, score - 10)
            evidence.append(f"⚠️ 方法间分歧过大（区间 {low:.0f}~{high:.0f}），可估性降分")

    return ValuationResult(
        business_type=business_type,
        methods=methods,
        intrinsic=intrinsic,
        coverage_score=score,
        evidence=evidence,
        params=p,
    )
