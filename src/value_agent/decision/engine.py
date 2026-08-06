"""M10 决策引擎：五维评分卡 + 结论档位 + 一票否决（docs/01-design.md §6）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.sessions.models import ModuleResult

# 五维权重（合计 100）—— 与 config/scoring.yaml 对齐，代码内为兜底
DIMENSIONS: dict[str, dict] = {
    "business_moat":       {"modules": ["M1_business_model", "M5_moat"], "weight": 25},
    "financial_quality":   {"modules": ["M2_financial_quality"], "weight": 20},
    "growth_prosperity":   {"modules": ["M3_growth"], "weight": 20},
    "valuation_margin":    {"modules": ["M4_valuation", "M7_market", "M8_safety_margin"], "weight": 25},
    "governance_risk":     {"modules": ["M6_governance", "M9_risk"], "weight": 10},
}

BANDS: list[dict] = [
    {"min_score": 80, "label": "强烈关注/可建仓", "position": 0.10},
    {"min_score": 65, "label": "关注", "position": 0.05},
    {"min_score": 50, "label": "中性/观察", "position": 0.00},
    {"min_score": 0,  "label": "回避", "position": 0.00},
]


@dataclass
class DecisionResult:
    dimensions: dict[str, float]
    total: float
    band: dict
    position: float
    conclusion: str
    decision_code: str  # buy | watch | avoid（契约字段，§4 M10）
    blocked_by_veto: bool
    vetoed: list[str]
    evidence: list[str] = field(default_factory=list)


def apply_band(total: float, vetoed: list[str] | bool) -> tuple[dict, float, str, str]:
    """按总分 + 否决标志算出（档位, 建议仓位, 结论, 决策码）。"""
    blocked = bool(vetoed)
    band = next((b for b in BANDS if total >= b["min_score"]), BANDS[-1])
    conclusion = "回避（触发一票否决）" if blocked else band["label"]
    position = 0.0 if blocked else band["position"]
    # 决策码：否决→avoid；≥80 可建仓→buy；50~80 观察→watch；<50→avoid
    if blocked:
        decision_code = "avoid"
    elif total >= 80:
        decision_code = "buy"
    elif total >= 50:
        decision_code = "watch"
    else:
        decision_code = "avoid"
    return band, position, conclusion, decision_code


def run_decision(module_results: dict[str, ModuleResult]) -> DecisionResult:
    """主入口：模块评分 → 五维加权 → 结论档位 + 否决检查。"""
    dims: dict[str, float] = {}
    for key, meta in DIMENSIONS.items():
        scores = [
            module_results[m].score
            for m in meta["modules"]
            if m in module_results and module_results[m].score is not None
        ]
        dims[key] = round(sum(scores) / len(scores), 1) if scores else 0.0

    total = round(
        sum(dims[k] * meta["weight"] for k, meta in DIMENSIONS.items()) / 100.0, 1
    )

    # 一票否决：M9 风险输出 veto 清单（stub 阶段为空；M9 落地后生效）
    vetoed: list[str] = []
    m9 = module_results.get("M9_risk")
    if m9 and m9.outputs.get("veto"):
        vetoed = list(m9.outputs["veto"])

    band, position, conclusion, decision_code = apply_band(total, vetoed)
    blocked = bool(vetoed)

    evidence = [
        f"五维评分：{dims}",
        f"加权总分：{total}（权重：{ {k: v['weight'] for k, v in DIMENSIONS.items()} }）",
        f"结论档位：{conclusion}（建议仓位 {position:.0%}）",
    ]
    if vetoed:
        evidence.append(f"⚠️ 触发否决项：{vetoed}")
    return DecisionResult(
        dimensions=dims, total=total, band=band,
        position=position, conclusion=conclusion,
        decision_code=decision_code, blocked_by_veto=blocked, vetoed=vetoed,
        evidence=evidence,
    )
