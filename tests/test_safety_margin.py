"""M8 安全边际引擎单元测试：状态判定/折扣率/买卖区间/要求折扣分级。"""
import pytest

from value_agent.safety_margin.engine import run_safety_margin

INTRINSIC = {"low": 56.67, "mid": 111.21, "high": 149.74}


def test_below_buy_price_is_buy_zone():
    r = run_safety_margin(40.0, INTRINSIC)
    assert "买入区间" in r.status
    assert r.score == 95
    assert r.buy_price == pytest.approx(56.67 * 0.75, abs=0.01)


def test_between_mid_and_high_is_fair():
    r = run_safety_margin(130.0, INTRINSIC)
    assert "合理偏上" in r.status
    assert r.score == 30


def test_above_high_is_overvalued():
    r = run_safety_margin(200.0, INTRINSIC)
    assert "高估" in r.status
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


def test_sell_price_is_120pct_of_high():
    r = run_safety_margin(40.0, INTRINSIC)
    assert r.sell_price == pytest.approx(149.74 * 1.2, abs=0.01)
