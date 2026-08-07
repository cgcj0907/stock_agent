"""M11 监控计划引擎：从分析结果生成监控规则（持有期管理，docs/01-design.md §3.11）。

契约字段（docs/09-module-contracts.md §4 M11）：每条规则
{rule_type, source_module, trigger, severity, action, message}；
M11 只消费上游 handoff/signals 的结构化字段，不再读 risk_items 字符串做转义。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.sessions.models import ModuleResult

# rule_type → 覆盖维度（9.8 质量加权评分用）：价格/景气/财务/风险/决策
_DIMENSION_BY_TYPE: dict[str, str] = {
    "price_buy": "price",
    "price_sell": "price",
    "valuation_sell": "price",
    "mos_watch": "price",
    "prosperity_watch": "prosperity",
    "fundamental_watch": "fundamental",
    "risk_watch": "risk",
    "decision_watch": "decision",
    "prior_hit_review": "review",
    "sentiment_watch": "sentiment",
}

_SEVERITY_BONUS = {"critical": 5.0, "warn": 2.0, "info": 0.0}
_SEVERITY_MAP = {"low": "info", "medium": "warn", "high": "warn", "critical": "critical"}

# 情绪热度阈值（与 M7 engine 一致：≥0.66 贪婪 / ≤0.33 恐惧）
SENTIMENT_HOT = 0.66
SENTIMENT_COLD = 0.33


@dataclass
class MonitorRule:
    rule_type: str       # price_buy / price_sell / valuation_sell / prosperity_watch / fundamental_watch / risk_watch / decision_watch / prior_hit_review / sentiment_watch / mos_watch
    trigger: str
    message: str         # 契约字段（§4 M11），替代旧 description
    severity: str        # info / warn / critical
    source_module: str = ""   # 规则来源模块（§4 M11 契约）
    action: str = "watch"     # watch / alert / action 分层
    params: dict = field(default_factory=dict)  # 结构化阈值（runner 消费，如 {"price": 42.5}）


@dataclass
class MonitorPlan:
    rules: list[MonitorRule]
    score: float
    evidence: list[str] = field(default_factory=list)


def _severity_from_signal(sev: str | None) -> str:
    """M2 信号 severity 透传（9.7）：critical 不再被拍平成 warn。"""
    return _SEVERITY_MAP.get(sev, "warn")


def _rule_score(rules: list[MonitorRule]) -> float:
    """质量加权评分（9.8）：按规则覆盖维度数 + severity 权重，替代「40+10×条数」计数代理。

    基础 40 + 覆盖维度×10（最多 6 维：price/prosperity/fundamental/risk/decision/sentiment）
    + severity 加成（critical +5 / warn +2，封顶 100）。prior_hit_review 不计维度。
    """
    dims = {_DIMENSION_BY_TYPE[r.rule_type] for r in rules if r.rule_type in _DIMENSION_BY_TYPE}
    bonus = sum(min(_SEVERITY_BONUS.get(r.severity, 0.0), 5.0) for r in rules if r.severity == "critical")
    bonus += sum(min(_SEVERITY_BONUS.get(r.severity, 0.0), 2.0) for r in rules if r.severity == "warn")
    return round(min(100.0, 40.0 + 10.0 * len(dims) + min(bonus, 20.0)), 1)


def build_monitor_plan(
    module_results: dict[str, ModuleResult],
    prior_hits: list[dict] | None = None,
) -> MonitorPlan:
    """基于分析结果生成监控规则（卖出触发 + 验证点 + 风险项）。

    prior_hits（I-2 跨会话记忆）：历史监控命中作为 watch 回顾规则加入，
    只增强不覆盖当前规则。
    """
    rules: list[MonitorRule] = []

    # I-2：历史命中回顾（warn/critical 才回放，避免信息噪音）
    for hit in prior_hits or []:
        if hit.get("severity") not in ("warn", "critical"):
            continue
        rules.append(MonitorRule(
            "prior_hit_review",
            f"{hit.get('rule_type', '')}: {hit.get('message', '')}",
            "历史监控命中回顾（跨会话记忆）",
            "info",
            source_module="M11_monitor",
            action="watch",
        ))

    def get(aid: str) -> ModuleResult | None:
        return module_results.get(aid)

    m8 = get("M8_safety_margin")
    m8_handoff = (m8.outputs.get("handoff") or {}) if m8 else {}
    if m8 and m8.outputs.get("buy_price"):
        # 6.2：分批建仓档位（0.75/0.65/0.5 × 下沿）→ 分档触发；无档位时退回单一买入区间
        tranches = m8_handoff.get("buy_tranches") or m8.outputs.get("buy_tranches") or []
        if tranches:
            for t in tranches:
                if not isinstance(t, dict) or t.get("price") is None:
                    continue
                rules.append(MonitorRule(
                    "price_buy", f"现价 ≤ {t['price']} 元",
                    f"{t.get('label', '买入档')}：跌破 {t['price']} 元可建 {t.get('weight', 1/3):.0%} 仓位",
                    "info",
                    source_module="M8_safety_margin", action="action",
                    params={"price": t["price"]},
                ))
        else:
            rules.append(MonitorRule(
                "price_buy", f"现价 ≤ {m8.outputs['buy_price']} 元",
                "跌破买入区间，可分批建仓", "info",
                source_module="M8_safety_margin", action="action",
                params={"price": m8.outputs["buy_price"]},
            ))
    if m8 and m8.outputs.get("sell_price"):
        rules.append(MonitorRule(
            "price_sell", f"现价 ≥ {m8.outputs['sell_price']} 元",
            "达到卖出区间，考虑兑现", "warn",
            source_module="M8_safety_margin", action="action",
            params={"price": m8.outputs["sell_price"]},
        ))
    # M8-6.4：mos_state=expensive → 「估值偏高，暂停买入」watch（与 price_sell 区分）
    if m8_handoff.get("mos_state") == "expensive":
        rules.append(MonitorRule(
            "mos_watch", "M8 安全边际=expensive",
            "估值偏高（现价高于内在价值），暂停买入", "warn",
            source_module="M8_safety_margin", action="watch",
        ))

    m7 = get("M7_market")
    has_valuation_sell = False
    if m7 and m7.outputs.get("position") in ("高估", "泡沫"):
        has_valuation_sell = True
        rules.append(MonitorRule(
            "valuation_sell", f"估值位置={m7.outputs['position']}",
            "估值过热，卖出参考", "warn",
            source_module="M7_market", action="action",
        ))
    # 6.3：M8 卖出参考（估值分位 > 90%）双信号触发
    if m8_handoff.get("sell_reference") and not has_valuation_sell:
        rules.append(MonitorRule(
            "valuation_sell", "估值分位>90%",
            "估值分位超过 90%，卖出参考（与高估/泡沫双信号）", "warn",
            source_module="M8_safety_margin", action="action",
        ))
    # 7.14：情绪热度过热/过冷 → 监控规则候选（持续跟踪市场先生情绪）
    if m7:
        heat = m7.outputs.get("sentiment_heat")
        if heat is not None and heat >= SENTIMENT_HOT:
            rules.append(MonitorRule(
                "sentiment_watch", f"情绪热度={heat:.0%}",
                "换手率情绪过热，警惕追涨/高位接盘", "warn",
                source_module="M7_market", action="watch",
            ))
        elif heat is not None and heat <= SENTIMENT_COLD:
            rules.append(MonitorRule(
                "sentiment_watch", f"情绪热度={heat:.0%}",
                "换手率情绪过冷，关注错杀机会", "info",
                source_module="M7_market", action="watch",
            ))

    m3 = get("M3_growth")
    if m3 and (m3.outputs.get("handoff") or {}).get("prosperity_code") == "down":
        rules.append(MonitorRule(
            "prosperity_watch", "景气评级=下行",
            "行业景气下行，财报季重点复查", "warn",
            source_module="M3_growth", action="watch",
        ))

    m2 = get("M2_financial_quality")
    if m2:
        for sig in m2.outputs.get("signals") or []:
            if not isinstance(sig, dict):
                continue  # 契约：只消费结构化 signals，不做字符串转义
            rules.append(MonitorRule(
                "fundamental_watch",
                sig.get("message") or sig.get("code") or "",
                sig.get("message") or "财务信号监控",
                _severity_from_signal(sig.get("severity")),
                source_module="M2_financial_quality", action="alert",
            ))

    m9 = get("M9_risk")
    if m9:
        # 契约：M11 只转 M9 的 monitor_candidates（high/critical/veto_candidate）→ risk_watch；
        # 只消费结构化 risk_items，旧字符串形态不再兼容（9.6 收口）。
        raw_candidates = m9.outputs.get("monitor_candidates")
        candidates = set(raw_candidates) if raw_candidates is not None else None
        for item in m9.outputs.get("risk_items") or []:
            if not isinstance(item, dict):
                continue
            if candidates is not None and item.get("id") not in candidates:
                continue
            if item.get("source_module") == "M2_financial_quality":
                continue  # M2 信号已由 M2 直接转 fundamental_watch，避免双份规则
            rules.append(MonitorRule(
                "risk_watch",
                item.get("trigger") or item.get("impact") or "",
                item.get("impact") or "风险项监控",
                _SEVERITY_MAP.get(item.get("severity", ""), "info"),
                source_module=item.get("source_module") or "M9_risk",
                action="watch",
            ))

    m10 = get("M10_decision")
    if m10:
        handoff = m10.outputs.get("handoff") or {}
        code = handoff.get("decision_code") or m10.outputs.get("decision_code")
        blocked = handoff.get("blocked_by_veto") or m10.outputs.get("blocked_by_veto")
        if blocked or code == "avoid":
            rules.append(MonitorRule(
                "decision_watch", "M10 决策=avoid",
                "决策回避：一票否决生效，解除前不建仓", "warn",
                source_module="M10_decision", action="watch",
                params={"blocked_by_veto": True},
            ))
        elif code == "buy":
            rules.append(MonitorRule(
                "decision_watch", "M10 决策=buy",
                "决策买入：跟踪基本面验证买入逻辑与卖点触发", "info",
                source_module="M10_decision", action="watch",
            ))
        elif code == "watch":
            rules.append(MonitorRule(
                "decision_watch", "M10 决策=watch",
                "决策观察：等待安全边际/风险改善后再评估", "info",
                source_module="M10_decision", action="watch",
            ))

    score = _rule_score(rules)
    evidence = [f"生成 {len(rules)} 条监控规则：{', '.join(r.rule_type for r in rules) or '无'}"]
    dims_covered = sorted({_DIMENSION_BY_TYPE[r.rule_type] for r in rules if r.rule_type in _DIMENSION_BY_TYPE})
    if dims_covered:
        evidence.append(f"质量加权评分：覆盖维度 {dims_covered}（+{len(dims_covered)}×10）+ severity 加成")
    return MonitorPlan(rules=rules, score=score, evidence=evidence)
