"""M9 风险与否决引擎：聚合各模块风险信号 + 一票否决（确定性规则）。

Risk Registry（docs/09-module-contracts.md §4 M9）：risk_items 为结构化对象，
供 M10（vetoes）/ M11（monitor_candidates、severity）直接消费，不再字符串转义。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.sessions.models import ModuleResult


@dataclass
class RiskResult:
    risk_items: list[dict]  # [{id, category, severity, source_module, trigger, impact, mitigation, veto_candidate}]
    vetoes: list[dict]  # 一票否决对象 [{id, reason, severity}]
    veto: list[str]  # 兼容：否决 reason 字符串列表（M10 继续消费）
    monitor_candidates: list[str]  # 需长期监控的风险项 id（M11 直接转规则）
    score: float
    evidence: list[str] = field(default_factory=list)


def _risk_item(
    seq: int,
    category: str,
    severity: str,
    source_module: str,
    trigger: str,
    impact: str,
    mitigation: str = "",
    veto_candidate: bool = False,
) -> dict:
    return {
        "id": f"R-{seq:03d}",
        "category": category,
        "severity": severity,
        "source_module": source_module,
        "trigger": trigger,
        "impact": impact,
        "mitigation": mitigation,
        "veto_candidate": veto_candidate,
    }


def assess_risk(inputs: dict[str, ModuleResult], assumptions: dict | None = None) -> RiskResult:
    """聚合 M2/M3/M5/M6/M7/M8 输出，生成结构化风险清单与一票否决。"""
    assumptions = assumptions or {}
    items: list[dict] = []
    vetoes: list[dict] = []
    n = 0

    def out(mid: str) -> dict:
        r = inputs.get(mid)
        return r.outputs if r else {}

    # M2 财务风险
    m2 = out("M2_financial_quality")
    for sig in m2.get("signals") or []:
        n += 1
        if isinstance(sig, dict):
            items.append(_risk_item(
                n, "财务", sig.get("severity", "medium"), "M2_financial_quality",
                sig.get("code") or sig.get("message", ""), sig.get("message", ""),
                mitigation="跟踪现金流/利润勾稽",
            ))
        else:
            items.append(_risk_item(n, "财务", "medium", "M2_financial_quality", sig, sig))
    if m2.get("score") is not None:
        if m2["score"] < 30:
            vetoes.append({"id": "V-001", "reason": "财务质量极差（M2<30）", "severity": "critical"})
        elif m2["score"] < 60:
            n += 1
            items.append(_risk_item(n, "财务", "medium", "M2_financial_quality",
                                    "financial_quality_below_60", "财务质量一般"))

    # M3 景气风险
    m3 = out("M3_growth")
    if m3.get("prosperity") == "下行":
        n += 1
        items.append(_risk_item(n, "景气", "medium", "M3_growth", "prosperity=down",
                                "行业景气下行", mitigation="财报季重点复查景气指标"))

    # M5 护城河风险
    m5 = out("M5_moat")
    if m5.get("width") in ("无", "窄"):
        n += 1
        impact = "护城河无（竞争压力大）" if m5.get("width") == "无" else "护城河较窄（竞争压力大）"
        items.append(_risk_item(n, "护城河", "medium", "M5_moat", f"width={m5.get('width')}", impact))

    # M6 治理风险
    m6 = out("M6_governance")
    if m6.get("score") is not None and m6["score"] < 55:
        n += 1
        items.append(_risk_item(n, "治理", "medium", "M6_governance",
                                "governance_score<55", "治理/回报股东偏弱"))

    # M7 估值情绪风险
    m7 = out("M7_market")
    if m7.get("position") in ("高估", "泡沫"):
        sev = "high" if m7.get("position") == "泡沫" else "medium"
        n += 1
        items.append(_risk_item(n, "估值情绪", sev, "M7_market",
                                f"position={m7.get('position')}",
                                f"估值位置{m7['position']}（市场情绪过热）"))

    # M8 安全边际风险
    m8 = out("M8_safety_margin")
    if m8.get("discount") is not None and m8["discount"] < 0:
        n += 1
        items.append(_risk_item(n, "安全边际", "high", "M8_safety_margin",
                                "discount<0", "安全边际为负（现价高于内在价值下沿）"))

    # 显式否决（测试/用户覆盖）
    for reason in assumptions.get("veto_reasons") or []:
        vetoes.append({"id": f"V-{len(vetoes) + 1:03d}", "reason": str(reason), "severity": "critical"})

    veto = [v["reason"] for v in vetoes]
    monitor_candidates = [
        it["id"] for it in items
        if it["severity"] in ("high", "critical") or it["veto_candidate"]
    ]

    score = max(0.0, 100.0 - 15.0 * len(items) - 30.0 * len(vetoes))
    evidence = [
        f"风险清单（{len(items)} 项）：{[it['impact'] for it in items] if items else '未发现明显风险'}"
    ]
    if veto:
        evidence.append(f"🚫 一票否决：{veto}")
    evidence.append("⚠️ 质押/审计意见/减持等事件数据待接入；红队定性见 LLM 层")
    return RiskResult(
        risk_items=items, vetoes=vetoes, veto=veto,
        monitor_candidates=monitor_candidates,
        score=round(score, 1), evidence=evidence,
    )
