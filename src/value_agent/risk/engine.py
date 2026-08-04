"""M9 风险与否决引擎：聚合各模块风险信号 + 一票否决（确定性规则）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.sessions.models import ModuleResult


@dataclass
class RiskResult:
    risk_items: list[str]
    veto: list[str]
    score: float
    evidence: list[str] = field(default_factory=list)


def assess_risk(inputs: dict[str, ModuleResult], assumptions: dict | None = None) -> RiskResult:
    """聚合 M2/M3/M5/M6/M7/M8 输出，生成风险清单与一票否决。"""
    assumptions = assumptions or {}
    risks: list[str] = []
    veto: list[str] = []

    def out(mid: str) -> dict:
        r = inputs.get(mid)
        return r.outputs if r else {}

    # M2 财务风险
    m2 = out("M2_financial_quality")
    for sig in m2.get("signals") or []:
        risks.append(f"财务信号：{sig}")
    if m2.get("score") is not None:
        if m2["score"] < 30:
            veto.append("财务质量极差（M2<30）")
        elif m2["score"] < 60:
            risks.append("财务质量一般")

    # M3 景气风险
    m3 = out("M3_growth")
    if m3.get("prosperity") == "下行":
        risks.append("行业景气下行")

    # M5 护城河风险
    m5 = out("M5_moat")
    if m5.get("width") in ("无", "窄"):
        risks.append(f"护城河{('无' if m5.get('width') == '无' else '较窄')}（竞争压力大）")

    # M6 治理风险
    m6 = out("M6_governance")
    if m6.get("score") is not None and m6["score"] < 55:
        risks.append("治理/回报股东偏弱")

    # M7 估值情绪风险
    m7 = out("M7_market")
    if m7.get("position") in ("高估", "泡沫"):
        risks.append(f"估值位置{m7['position']}（市场情绪过热）")

    # M8 安全边际风险
    m8 = out("M8_safety_margin")
    if m8.get("discount") is not None and m8["discount"] < 0:
        risks.append("安全边际为负（现价高于内在价值下沿）")

    # 显式否决（测试/用户覆盖）
    for v in assumptions.get("veto_reasons") or []:
        veto.append(v)

    score = max(0.0, 100.0 - 15.0 * len(risks) - 30.0 * len(veto))
    evidence = [f"风险清单（{len(risks)} 项）：{risks if risks else '未发现明显风险'}"]
    if veto:
        evidence.append(f"🚫 一票否决：{veto}")
    evidence.append("⚠️ 质押/审计意见/减持等事件数据待接入；红队定性见 LLM 层")
    return RiskResult(risk_items=risks, veto=veto, score=round(score, 1), evidence=evidence)
