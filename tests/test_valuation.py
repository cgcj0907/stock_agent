"""M4 估值引擎单元测试：方法级 + 引擎级（路由/区间/覆盖率）。"""
import pytest

import value_agent.agents  # noqa: F401  先加载 agents（builtin→valuation 链），避免循环导入
from value_agent.valuation.engine import run_valuation
from value_agent.valuation.methods import (
    dcf,
    ddm,
    graham_formula,
    graham_number,
    relative_median_pe,
    tang,
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


# ---------- M4 智能体：数据源细粒度容错 ----------
def _m4_ctx(data, business_type: str | None = None) -> object:
    from value_agent.agents.base import AgentContext  # 供下方构造 ctx
    from value_agent.sessions.models import Session, SessionStatus

    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    assumptions = {"business_type": business_type} if business_type else {}
    return AgentContext(
        session=session, assumptions=assumptions, inputs={}, data=data, llm=None
    )


def test_m4_partial_data_failure_still_values():
    """某个数据集失败（如分红）时，M4 仍用其余数据完成估值并标记降级，而不是整模块空白。"""
    from tests.conftest import StubData
    from value_agent.valuation.agent import M4ValuationAgent

    class _NoDividend(StubData):
        def dividends(self, code):
            raise ConnectionError("RemoteDisconnected")

    res = M4ValuationAgent().run(_m4_ctx(_NoDividend()))
    assert res.status.value == "done"
    assert res.outputs["intrinsic_value"] is not None, "部分数据失败也应给出估值"
    assert any("分红数据获取失败" in e for e in res.evidence)
    assert res.meta.get("degraded") is True


def test_m4_all_data_failure_degrades_with_reasons():
    """全部数据集失败时，M4 降级为 DONE（空估值），evidence 说明各失败原因。"""
    from value_agent.valuation.agent import M4ValuationAgent

    class _NoData:
        def financials(self, code, years=10):
            raise ConnectionError("x")

        def valuation_history(self, code):
            raise ConnectionError("x")

        def daily_prices(self, code):
            raise ConnectionError("x")

        def dividends(self, code):
            raise ConnectionError("x")

    res = M4ValuationAgent().run(_m4_ctx(_NoData()))
    assert res.status.value == "done"
    iv = res.outputs["intrinsic_value"]
    assert iv is None or iv.get("mid") is None  # 无有效估值
    assert res.outputs["methods"], "methods 列表仍应存在（applicable=false）"
    assert all(not m["applicable"] for m in res.outputs["methods"])
    assert any("财务数据获取失败" in e for e in res.evidence)
    assert any("估值历史获取失败" in e for e in res.evidence)
    assert any("日线价格获取失败" in e for e in res.evidence)
    assert any("分红数据获取失败" in e for e in res.evidence)
    assert res.meta.get("degraded") is True
