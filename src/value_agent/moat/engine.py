"""M5 护城河引擎：以盈利质量/稳定性/杠杆做确定性代理评估 + 来源信号。"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from value_agent.financials.quality import annual_records


@dataclass
class MoatResult:
    width: str          # 宽 / 中 / 窄 / 无
    score: float
    signals: list[str]
    evidence: list[str] = field(default_factory=list)


def assess_moat(financials: dict) -> MoatResult:
    """输入财务记录，输出护城河宽度评级与信号。

    代理指标（晨星五源的可计算代理）：
    - 高且稳定的 ROE → 综合优势
    - 高毛利率 → 定价权/无形资产
    - 低杠杆 → 抗风险（成本/规模优势的弱代理）
    """
    recs = [r for r in financials.get("records", []) if r.get("period")]
    annual = sorted(annual_records(recs), key=lambda r: r["period"], reverse=True)
    roe = [r["roe"] for r in annual if r.get("roe") is not None]
    gm = [r["grossprofit_margin"] for r in annual if r.get("grossprofit_margin") is not None]
    debt = [r["debt_to_assets"] for r in annual if r.get("debt_to_assets") is not None]

    if not recs:
        return MoatResult("无", 0.0, [], ["无财务数据"])

    score, signals = 0.0, []
    if roe:
        latest, mean = roe[0], statistics.mean(roe)
        if latest >= 15 and mean >= 15:
            score += 30
            signals.append("ROE ≥15% 且长期稳定（综合优势）")
        elif latest >= 10:
            score += 20
            signals.append("ROE ≥10%")
        if len(roe) >= 3 and statistics.stdev(roe) / abs(mean) <= 0.15:
            score += 15
            signals.append("ROE 波动小")
    if gm:
        if gm[0] >= 40:
            score += 25
            signals.append("毛利率 ≥40%（定价权/无形资产代理）")
        elif gm[0] >= 25:
            score += 15
            signals.append("毛利率 ≥25%")
    if debt:
        if debt[0] <= 0.4:
            score += 10
            signals.append("低杠杆（抗风险）")

    width = "宽" if score >= 70 else "中" if score >= 50 else "窄" if score >= 30 else "无"
    evidence = [
        f"代理评分 {score:.0f}/100（ROE 稳定性 + 毛利率 + 杠杆）",
        f"信号：{signals if signals else '无明显护城河信号'}",
        "⚠️ 此为标准面代理评估；品牌/专利/网络效应等定性来源待 LLM 接入后补充",
    ]
    return MoatResult(width=width, score=round(score, 1), signals=signals, evidence=evidence)
