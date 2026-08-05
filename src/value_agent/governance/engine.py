"""M6 治理与资本配置引擎：以分红持续性/回报股东倾向做确定性代理评估。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GovernanceResult:
    score: float
    dividend_years: int
    payout_latest: float | None
    note: str
    evidence: list[str] = field(default_factory=list)


def assess_governance(dividends: dict) -> GovernanceResult:
    """输入分红记录，输出治理/回报股东评分。

    代理：连续分红年数 + 每股派息趋势。
    股权结构/质押/减持/回购等事件待数据接入后补充。
    """
    recs = sorted(
        (r for r in dividends.get("records", []) if r.get("period")),
        key=lambda r: r["period"], reverse=True,
    )
    payouts = [r["cash_div_tax"] for r in recs if r.get("cash_div_tax") is not None]

    if not recs:
        return GovernanceResult(
            score=50.0, dividend_years=0, payout_latest=None,
            note="无分红数据，治理按中性计",
            evidence=["无分红数据，无法评估回报股东倾向"],
        )

    years = len(recs)
    score = 40.0 + min(years * 5, 30)  # 连续分红年数
    latest = payouts[0] if payouts else None
    if len(payouts) >= 2 and payouts[0] > payouts[1]:
        score += 15
        note = "分红连续且递增（回报股东意愿强）"
    elif payouts:
        score += 8
        note = "有持续分红"
    else:
        note = "有分红预案但无派息数据"

    evidence = [
        f"连续分红 {years} 期；最新每股派息 {latest} 元",
        note,
        "⚠️ 股权结构/质押/减持/回购等治理事件待接入后补充",
    ]
    return GovernanceResult(
        score=round(min(score, 100.0), 1), dividend_years=years,
        payout_latest=latest, note=note, evidence=evidence,
    )
