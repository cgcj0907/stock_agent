"""M8 安全边际引擎单元测试：状态判定/折扣率/买卖区间/要求折扣分级。"""
import pytest

from value_agent.safety_margin.engine import run_safety_margin

INTRINSIC = {"low": 56.67, "mid": 111.21, "high": 149.74}


def test_below_buy_price_is_buy_zone():
    r = run_safety_margin(40.0, INTRINSIC)
    assert "买入区间" in r.status
    assert r.mos_state == "attractive"
    assert r.score == 95
    assert r.buy_price == pytest.approx(56.67 * 0.75, abs=0.01)


def test_between_mid_and_high_is_fair():
    r = run_safety_margin(130.0, INTRINSIC)
    assert "合理偏上" in r.status
    assert r.mos_state == "expensive"
    assert r.score == 30


def test_above_high_is_overvalued():
    r = run_safety_margin(200.0, INTRINSIC)
    assert "高估" in r.status
    assert r.mos_state == "expensive"
    assert r.score == 10


def test_cyclical_requires_half_discount():
    r = run_safety_margin(30.0, INTRINSIC, business_type="cyclical")
    assert r.required_discount == 0.5
    assert r.buy_price == pytest.approx(56.67 * 0.5, abs=0.01)


def test_assumption_overrides_required_discount():
    r = run_safety_margin(40.0, INTRINSIC, required_discount=0.1)
    assert r.required_discount == 0.1
    assert "买入区间" in r.status


def test_missing_data_neutral():
    r = run_safety_margin(None, {"low": None, "mid": None, "high": None})
    assert r.score == 50
    assert "数据不足" in r.status
    assert r.mos_state == "unavailable"


def test_sell_price_is_110pct_of_high():
    r = run_safety_margin(40.0, INTRINSIC)
    assert r.sell_price == pytest.approx(149.74 * 1.1, abs=0.01)  # 6.3：卖出区间收敛到上沿附近

def test_margin_adjustment_stacks_on_required_discount():
    """M7 市场情绪叠加：过热 +0.05 → 要求折扣 25%→30%，买入区间更保守。"""
    r = run_safety_margin(40.0, INTRINSIC, required_discount=0.25, margin_adjustment=0.05)
    assert r.required_discount == pytest.approx(0.30)
    assert r.buy_price == pytest.approx(56.67 * 0.70, abs=0.01)
    assert any("margin_adjustment" in e for e in r.evidence)


def test_margin_adjustment_cold_lowers_required_discount():
    """市场低估（−0.05）→ 要求折扣 25%→20%，买入区间放宽（机会更大时更积极）。"""
    r = run_safety_margin(40.0, INTRINSIC, margin_adjustment=-0.05)
    assert r.required_discount == pytest.approx(0.20)
    assert r.buy_price == pytest.approx(56.67 * 0.80, abs=0.01)


def test_margin_adjustment_default_zero_unchanged():
    r = run_safety_margin(40.0, INTRINSIC)
    assert r.required_discount == 0.25
    assert r.buy_price == pytest.approx(56.67 * 0.75, abs=0.01)


def test_above_high_emits_price_above_intrinsic_reason():
    """现价高于内在价值上沿 → 契约 reason_codes=[PRICE_ABOVE_INTRINSIC]（§4 M8）。"""
    r = run_safety_margin(200.0, INTRINSIC)
    assert r.mos_state == "expensive"
    assert r.reason_codes == ["PRICE_ABOVE_INTRINSIC"]


def test_normal_states_have_empty_reason_codes():
    """买入区间/合理区等正常态 reason_codes 为空（PRICE_ABOVE_INTRINSIC 只在高估态出现）。"""
    assert run_safety_margin(40.0, INTRINSIC).reason_codes == []
    assert run_safety_margin(130.0, INTRINSIC).reason_codes == []


def test_missing_data_reason_code_input_missing():
    r = run_safety_margin(None, {"low": None, "mid": None, "high": None})
    assert r.mos_state == "unavailable"
    assert r.reason_codes == ["INPUT_MISSING"]


def test_zero_intrinsic_low_degrades_instead_of_crashing():
    """下沿为 0 属于异常输入，M8 应降级为 unavailable，而不是除零失败。"""
    r = run_safety_margin(48.76, {"low": 0.0, "mid": 0.0, "high": 21.96})
    assert r.mos_state == "unavailable"
    assert r.discount is None
    assert r.reason_codes == ["OUT_OF_RANGE"]
    assert any("下沿" in e for e in r.evidence)


# ---------- backlog 6.x：确定性分级 / 分批建仓 / 卖出纪律 ----------

def test_certainty_discount_wide_moat_lowers_required():
    """6.1：宽护城河 → 要求折扣下调（25%×0.9），夹逼区间下限 20%。"""
    r = run_safety_margin(40.0, INTRINSIC, moat_width="wide", risk_level="low")
    assert r.required_discount == pytest.approx(0.25 * 0.90 * 0.95, abs=0.001)
    assert any("确定性分级" in e for e in r.evidence)


def test_certainty_discount_none_moat_high_risk_clamped():
    """6.1：无护城河 + 高风险 → 要求折扣上调，且被夹逼到 [0.2, 0.6] 上限内。"""
    r = run_safety_margin(40.0, INTRINSIC, moat_width="none", risk_level="high")
    assert r.required_discount == pytest.approx(min(0.6, 0.25 * 1.20 * 1.10), abs=0.001)
    assert 0.2 <= r.required_discount <= 0.6


def test_certainty_discount_evidence_shows_intermediate_before_margin():
    """8.9：确定性分级证据显示情绪调整前的中间值，算术不再误导（50%×1.00×1.10=55%，再 −5% → 净 50%）。"""
    r = run_safety_margin(
        40.0, INTRINSIC, business_type="cyclical",
        moat_width="medium", risk_level="high", margin_adjustment=-0.05,
    )
    assert r.required_discount == pytest.approx(0.50, abs=0.001)
    cert = next(e for e in r.evidence if "确定性分级要求折扣" in e)
    assert "= 55%" in cert  # 中间值（乘数链结果），而非被情绪调整污染后的净 50%
    adj = next(e for e in r.evidence if "市场情绪调整" in e)
    assert "margin_adjustment -5%" in adj
    assert "净要求折扣 50%" in adj


def test_buy_tranches_three_tiers():
    """6.2：分批建仓三档（1.0/0.85/0.7 × 买入价，各 1/3）。"""
    r = run_safety_margin(40.0, INTRINSIC)
    assert len(r.buy_tranches) == 3
    assert r.buy_tranches[0]["price"] == pytest.approx(r.buy_price, abs=0.01)
    assert r.buy_tranches[2]["price"] == pytest.approx(r.buy_price * 0.70, abs=0.01)
    assert all(t["weight"] == pytest.approx(1 / 3) for t in r.buy_tranches)
    assert all(t["price"] <= r.buy_price for t in r.buy_tranches)  # 档位不得高于买入价
    assert any("分批建仓" in e for e in r.evidence)


def test_buy_tranches_never_exceed_buy_price_for_cyclical():
    """生产稽核回归：周期股要求折扣 50% 时，档位不得高于买入价。

    此前档位锚在内在价值下沿（0.75/0.65/0.5 × low），而买入价 = low×(1−req)=low×0.5，
    第一档 0.75×low 反而比买入价高 50%（牧原 24.15 vs 16.1），M11 在买入区间外触发建仓。
    """
    r = run_safety_margin(
        40.0, INTRINSIC, business_type="cyclical",
        moat_width="narrow", risk_level="high",
    )
    assert r.buy_price < INTRINSIC["low"] * 0.75  # 复现原矛盾场景（要求折扣 > 25%）
    assert all(t["price"] <= r.buy_price for t in r.buy_tranches)


def test_sell_reference_on_high_valuation_percentile():
    """6.3：估值分位 > 90% → sell_reference=True 且进 evidence。"""
    r = run_safety_margin(40.0, INTRINSIC, valuation_percentile=0.95)
    assert r.sell_reference is True
    assert any("估值分位" in e for e in r.evidence)
    r2 = run_safety_margin(40.0, INTRINSIC, valuation_percentile=0.5)
    assert r2.sell_reference is False
