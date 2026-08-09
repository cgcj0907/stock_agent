"""M8 安全边际引擎（格雷厄姆核心）：折扣率 + 要求折扣 + 买卖区间 + 状态。

backlog 2026-08-07 落地：
- 6.1 要求折扣按确定性分级：`基准 × moat 修正 × 风险修正`，夹逼 [0.2, 0.6]；
      确定性输入取 M5 moat_width + M2/M3 上游风险代理（不消费 M9，避免成环）。
- 6.2 分批建仓区间 buy_tranches（1.0/0.85/0.7 × 买入价，各 1/3），M11 分档触发；
      档位锚定**买入价**而非内在价值下沿——否则周期股（要求折扣 50%）第一档
      （下沿×0.75）会高于买入价（下沿×0.5），M11 在「买入区间」之外就触发建仓。
- 6.3 卖出纪律收敛：sell_price = 上沿 × 1.1（原 1.2），M7 估值分位 > 0.9 触发卖出参考。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.core.contracts import ReasonCode

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

# 确定性分级修正（6.1）：moat 越宽要求折扣越低，风险越高要求折扣越高
MOAT_FACTOR: dict[str, float] = {
    "wide": 0.90,
    "medium": 1.00,
    "narrow": 1.10,
    "none": 1.20,
}
RISK_FACTOR: dict[str, float] = {
    "low": 0.95,
    "medium": 1.00,
    "high": 1.10,
}
REQUIRED_CLAMP = (0.2, 0.6)  # 夹逼区间（设计 §3.8：20%~60%）

# 分批建仓档位（6.2）：跌破买入价的 1.0/0.85/0.7 各建 1/3（全部 ≤ 买入价，与买入区间一致）
BUY_TRANCHE_FRACS = ((1.00, "第一档（买入价）"), (0.85, "第二档（0.85×买入价）"), (0.70, "第三档（0.70×买入价）"))
BUY_TRANCHE_WEIGHT = 1 / 3

SELL_MULTIPLE = 1.1      # 卖出区间 = 上沿 × 1.1（6.3：原 1.2 收敛到上沿附近）
SELL_PERCENTILE = 0.9    # 估值分位 > 90% 触发卖出参考（与 position=高估/泡沫 双信号）


@dataclass
class SafetyMarginResult:
    price: float | None
    intrinsic: dict
    discount: float | None            # 安全边际 = 1 − 现价/内在价值下沿
    required_discount: float
    buy_price: float | None           # 买入区间 = 下沿 × (1 − 要求折扣)
    sell_price: float | None          # 卖出区间 = 上沿 × SELL_MULTIPLE
    status: str  # 中文状态（展示用）
    mos_state: str  # 契约枚举：attractive | fair | expensive | unavailable（§4 M8）
    score: float
    buy_tranches: list[dict] = field(default_factory=list)  # 分批建仓档位（6.2）
    sell_reference: bool = False      # 估值分位 > 90% 的卖出参考信号（6.3）
    reason_codes: list[str] = field(default_factory=list)  # 契约枚举：如 PRICE_ABOVE_INTRINSIC / INPUT_MISSING
    evidence: list[str] = field(default_factory=list)


def _certainty_adjusted_discount(
    base: float,
    *,
    moat_width: str | None,
    risk_level: str,
    margin_adjustment: float,
    persona_adjustment: float = 0.0,
) -> tuple[float, list[str]]:
    """确定性分级要求折扣（6.1）：基准 × moat 修正 × 风险修正 + 情绪调整 + 个人画像调整，夹逼 [0.2, 0.6]。

    persona_adjustment：M0 投资者画像注入（docs/13 §5.2）——能力圈外/低风险承受/短期资金要求更高折扣；
    与 margin_adjustment 同级叠加，夹逼区间不变。
    """
    notes: list[str] = []
    req = base
    if moat_width in MOAT_FACTOR:
        f = MOAT_FACTOR[moat_width]
        req *= f
        notes.append(f"护城河 {moat_width} → ×{f:.2f}")
    if risk_level in RISK_FACTOR:
        f = RISK_FACTOR[risk_level]
        req *= f
        notes.append(f"风险 {risk_level} → ×{f:.2f}")
    req += margin_adjustment
    if persona_adjustment:
        req += persona_adjustment
        notes.append(f"个人画像 → +{persona_adjustment:.2f}")
    low, high = REQUIRED_CLAMP
    req = round(min(high, max(low, req)), 4)
    return req, notes


def run_safety_margin(
    price: float | None,
    intrinsic: dict,
    business_type: str = "consumer_monopoly",
    required_discount: float | None = None,
    margin_adjustment: float = 0.0,
    persona_adjustment: float = 0.0,
    moat_width: str | None = None,
    risk_level: str = "medium",
    valuation_percentile: float | None = None,
    sell_multiple: float = SELL_MULTIPLE,
) -> SafetyMarginResult:
    """主入口：现价 vs 内在价值区间 → 安全边际与买卖区间。

    margin_adjustment：M7 市场情绪叠加量（过热 +0.05 / 样本不足 +0.10 / 正常 0 / 低估 −0.05）。
    persona_adjustment：M0 投资者画像叠加量（docs/13 §5.2；0 = 中性不调整）。
    moat_width / risk_level：M5/M2/M3 上游确定性分级（6.1），不消费 M9（避免成环）。
    valuation_percentile：M7 估值分位，> 0.9 时标记卖出参考（6.3）。
    """
    explicit = required_discount is not None
    base_req = required_discount if explicit else REQUIRED_DISCOUNT.get(business_type, DEFAULT_REQUIRED)
    if explicit:
        # 用户手动覆盖（assumptions.required_discount）：尊重原值，不走确定性公式与夹逼，
        # 但显式叠加（情绪/个人画像）仍并入
        req, certainty_notes = round(base_req + margin_adjustment + persona_adjustment, 4), []
    else:
        req, certainty_notes = _certainty_adjusted_discount(
            base_req, moat_width=moat_width, risk_level=risk_level,
            margin_adjustment=margin_adjustment, persona_adjustment=persona_adjustment,
        )
    low, high, mid = intrinsic.get("low"), intrinsic.get("high"), intrinsic.get("mid")

    if price is None or low is None:
        return SafetyMarginResult(
            price=price, intrinsic=intrinsic, discount=None, required_discount=req,
            buy_price=None, sell_price=None,
            status="数据不足", mos_state="unavailable", score=50.0,
            reason_codes=[ReasonCode.INPUT_MISSING.value],
            evidence=["缺少现价或内在价值下沿，无法计算安全边际"],
        )
    if low <= 0:
        return SafetyMarginResult(
            price=price, intrinsic=intrinsic, discount=None, required_discount=req,
            buy_price=None, sell_price=None,
            status="数据不足", mos_state="unavailable", score=50.0,
            reason_codes=[ReasonCode.OUT_OF_RANGE.value],
            evidence=[f"内在价值下沿无效（low={low}），无法计算安全边际"],
        )

    discount = 1 - price / low
    buy_price = low * (1 - req)
    sell_price = high * sell_multiple if high else None
    buy_tranches = [
        {
            "price": round(buy_price * frac, 2),
            "weight": BUY_TRANCHE_WEIGHT,
            "label": label,
        }
        for frac, label in BUY_TRANCHE_FRACS
    ]
    sell_reference = valuation_percentile is not None and valuation_percentile > SELL_PERCENTILE

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

    # 契约 reason_codes（§4 M8）：现价高于内在价值上沿 → PRICE_ABOVE_INTRINSIC，其余正常态为空
    reason_codes = (
        [ReasonCode.PRICE_ABOVE_INTRINSIC.value]
        if high is not None and price > high
        else []
    )
    evidence = [
        f"现价 {price} 元 vs 内在价值下沿 {low} / 中值 {mid} / 上沿 {high}",
        f"安全边际（折扣率）= 1 − 现价/下沿 = {discount:+.1%}（要求 ≥ {req:.0%}）",
        f"买入区间 ≤ {buy_price:.2f} 元；卖出区间 ≥ {sell_price:.2f} 元（{business_type}）",
        f"结论：{status}",
    ]
    if certainty_notes:
        evidence.insert(
            1,
            f"确定性分级要求折扣：{base_req:.0%} × {' × '.join(certainty_notes)} = {req:.0%}（夹逼 [{REQUIRED_CLAMP[0]:.0%}, {REQUIRED_CLAMP[1]:.0%}]）",
        )
    if margin_adjustment:
        evidence.insert(
            1,
            f"市场情绪调整（M7）：margin_adjustment {margin_adjustment:+.0%}",
        )
    if sell_reference:
        evidence.append(
            f"卖出参考：估值分位 {valuation_percentile:.0%} > {SELL_PERCENTILE:.0%}，"
            f"与 position=高估/泡沫 双信号，考虑兑现"
        )
    if buy_tranches:
        evidence.append(
            "分批建仓：" + "；".join(
                f"{t['label']} {t['price']:.2f} 元（{t['weight']:.0%} 仓位）" for t in buy_tranches
            )
        )
    return SafetyMarginResult(
        price=price, intrinsic=intrinsic, discount=round(discount, 4),
        required_discount=req, buy_price=round(buy_price, 2),
        sell_price=round(sell_price, 2) if sell_price else None,
        buy_tranches=buy_tranches, sell_reference=sell_reference,
        status=status, mos_state=mos_state, score=score,
        reason_codes=reason_codes, evidence=evidence,
    )
