"""M4 估值引擎单元测试：方法级 + 引擎级（路由/区间/覆盖率）。"""
import pytest

from value_agent.valuation.engine import run_valuation
from value_agent.valuation.methods import (
    dcf, ddm, graham_formula, graham_number, relative_median_pe, tang,
)


def test_dcf_has_sensitivity_range():
    r = dcf(4.5, 0.10, 0.10, 0.03)
    assert r.value is not None
    assert r.low < r.value < r.high


def test_tang_buy_sell():
    r = tang(4.5, 0.10, 0.04)
    assert r.params["fair_pe"] == pytest.approx(25, abs=0.1)
    assert r.params["buy"] == pytest.approx(r.value * 0.5)
    assert r.params["sell"] == min(r.value * 1.5, 4.5 * 50)


def test_ddm_requires_r_gt_g():
    assert ddm(2.2, 0.10, 0.10).value is None
    assert ddm(2.2, 0.05, 0.10).value is not None


def test_graham_number():
    r = graham_number(4.5, 31.7)
    assert r.value == pytest.approx(56.67, abs=0.1)


def test_graham_formula():
    assert graham_formula(4.5, 0.10, 0.04).value is not None


def test_relative_median_pe():
    r = relative_median_pe(4.5, [21.0, 21.3])
    assert r.value == pytest.approx(4.5 * 21.15, abs=0.01)


def test_engine_intrinsic_range_and_score():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2)
    assert r.intrinsic["low"] < r.intrinsic["mid"] < r.intrinsic["high"]
    assert r.coverage_score > 0
    assert r.methods["ddm"].value is None  # r<=g 跳过


def test_cyclical_routing_excludes_dcf_tang():
    r = run_valuation(eps=4.5, bvps=30, pe_history=[10, 12, 15], dividend=None, business_type="cyclical")
    assert "dcf" not in r.methods
    assert "tang" not in r.methods
    assert "relative_median_pe" in r.methods
