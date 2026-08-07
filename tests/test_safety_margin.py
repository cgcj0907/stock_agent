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


def test_sell_price_is_120pct_of_high():
    r = run_safety_margin(40.0, INTRINSIC)
    assert r.sell_price == pytest.approx(149.74 * 1.2, abs=0.01)

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
