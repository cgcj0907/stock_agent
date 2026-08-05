"""M8 安全边际引擎（格雷厄姆核心）：折扣率 + 要求折扣 + 买卖区间 + 状态。"""
from __future__ import annotations

from dataclasses import dataclass, field

# 要求折扣率按生意类型/确定性分级（docs/01-design.md §3.8）
REQUIRED_DISCOUNT: dict[str, float] = {
    "consumer_monopoly": 0.25,  # 护城河宽 + 确定性高
    "stable_dividend": 0.25,
    "growth": 0.35,
    "financial": 0.30,
    "cyclical": 0.50,           # 周期/高风险
    "asset_based": 0.40,
}
DEFAULT_REQUIRED = 0.30


@dataclass
class SafetyMarginResult:
    price: float | None
    intrinsic: dict
    discount: float | None            # 安全边际 = 1 − 现价/内在价值下沿
    required_discount: float
    buy_price: float | None           # 买入区间 = 下沿 × (1 − 要求折扣)
    sell_price: float | None          # 卖出区间 = 上沿 × 1.2
    status: str  # 中文状态（展示用）
    mos_state: str  # 契约枚举：attractive | fair | expensive | unavailable（§4 M8）
    score: float
    evidence: list[str] = field(default_factory=list)


def run_safety_margin(
    price: float | None,
    intrinsic: dict,
    business_type: str = "consumer_monopoly",
    required_discount: float | None = None,
) -> SafetyMarginResult:
    """主入口：现价 vs 内在价值区间 → 安全边际与买卖区间。"""
    req = required_discount if required_discount is not None else REQUIRED_DISCOUNT.get(business_type, DEFAULT_REQUIRED)
    low, high, mid = intrinsic.get("low"), intrinsic.get("high"), intrinsic.get("mid")

    if price is None or low is None:
        return SafetyMarginResult(
            price=price, intrinsic=intrinsic, discount=None, required_discount=req,
            buy_price=None, sell_price=None,
            status="数据不足", mos_state="unavailable", score=50.0,
            evidence=["缺少现价或内在价值下沿，无法计算安全边际"],
        )

    discount = 1 - price / low
    buy_price = low * (1 - req)
    sell_price = high * 1.2 if high else None

    if price <= buy_price:
        status, score, mos_state = "买入区间（安全边际充足）", 95.0, "attractive"
    elif price <= low:
        status, score, mos_state = "低估（折扣未达要求，可观望）", 80.0, "fair"
    elif price <= mid:
        status, score, mos_state = "合理偏下", 60.0, "fair"
    elif price <= high:
        status, score, mos_state = "合理偏上（安全边际为负）", 30.0, "expensive"
    else:
        status, score, mos_state = "高估（高于内在价值上沿）", 10.0, "expensive"

    evidence = [
        f"现价 {price} 元 vs 内在价值下沿 {low} / 中值 {mid} / 上沿 {high}",
        f"安全边际（折扣率）= 1 − 现价/下沿 = {discount:+.1%}（要求 ≥ {req:.0%}）",
        f"买入区间 ≤ {buy_price:.2f} 元；卖出区间 ≥ {sell_price:.2f} 元（{business_type}）",
        f"结论：{status}",
    ]
    return SafetyMarginResult(
        price=price, intrinsic=intrinsic, discount=round(discount, 4),
        required_discount=req, buy_price=round(buy_price, 2),
        sell_price=round(sell_price, 2) if sell_price else None,
        status=status, mos_state=mos_state, score=score, evidence=evidence,
    )
