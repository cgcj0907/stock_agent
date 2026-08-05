"""M11 监控计划引擎：从分析结果生成监控规则（持有期管理，docs/01-design.md §3.11）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.sessions.models import ModuleResult


@dataclass
class MonitorRule:
    rule_type: str       # price_buy / price_sell / valuation_sell / prosperity_watch / fundamental_watch / risk_watch
    trigger: str
    description: str
    severity: str        # info / warn / critical


@dataclass
class MonitorPlan:
    rules: list[MonitorRule]
    score: float
    evidence: list[str] = field(default_factory=list)


def build_monitor_plan(module_results: dict[str, ModuleResult]) -> MonitorPlan:
    """基于分析结果生成监控规则（卖出触发 + 验证点 + 风险项）。"""
    rules: list[MonitorRule] = []

    def get(aid: str) -> ModuleResult | None:
        return module_results.get(aid)

    m8 = get("M8_safety_margin")
    if m8 and m8.outputs.get("buy_price"):
        rules.append(MonitorRule(
            "price_buy", f"现价 ≤ {m8.outputs['buy_price']} 元",
            "跌破买入区间，可分批建仓", "info",
        ))
    if m8 and m8.outputs.get("sell_price"):
        rules.append(MonitorRule(
            "price_sell", f"现价 ≥ {m8.outputs['sell_price']} 元",
            "达到卖出区间，考虑兑现", "warn",
        ))

    m7 = get("M7_market")
    if m7 and m7.outputs.get("position") in ("高估", "泡沫"):
        rules.append(MonitorRule(
            "valuation_sell", f"估值位置={m7.outputs['position']}",
            "估值过热，卖出参考", "warn",
        ))

    m3 = get("M3_growth")
    if m3 and m3.outputs.get("prosperity") == "下行":
        rules.append(MonitorRule(
            "prosperity_watch", "景气评级=下行",
            "行业景气下行，财报季重点复查", "warn",
        ))

    m2 = get("M2_financial_quality")
    if m2:
        for sig in m2.outputs.get("signals") or []:
            message = sig.get("message") if isinstance(sig, dict) else sig
            rules.append(MonitorRule("fundamental_watch", message, "财务信号监控", "warn"))

    m9 = get("M9_risk")
    if m9:
        for item in m9.outputs.get("risk_items") or []:
            rules.append(MonitorRule("risk_watch", item, "风险项监控", "info"))

    score = min(100.0, 40.0 + 10.0 * len(rules))
    evidence = [f"生成 {len(rules)} 条监控规则：{', '.join(r.rule_type for r in rules) or '无'}",]
    return MonitorPlan(rules=rules, score=round(score, 1), evidence=evidence)
