"""M1 数据容错测试：公司信息失败仍用财务数据分类；全失败才降级。"""
from __future__ import annotations

from tests.conftest import StubData
from value_agent.agents.base import AgentContext  # 先加载 agents，避免循环导入
from value_agent.business_model.agent import M1BusinessModelAgent
from value_agent.sessions.models import Session, SessionStatus


def _run_m1(data) -> object:
    session = Session(id="s1", company_code="000333", status=SessionStatus.CREATED)
    ctx = AgentContext(session=session, assumptions={}, inputs={}, data=data, llm=None)
    return M1BusinessModelAgent().run(ctx)


def test_m1_continues_when_company_info_fails():
    """东财 company_info 瞬时故障（如 JSONDecodeError）→ 仍用财务数据分类，不降级。"""
    class _NoInfo(StubData):
        def company_info(self, code: str) -> dict:
            raise RuntimeError("JSONDecodeError")

    res = _run_m1(_NoInfo())
    assert res.status.value == "done"
    assert res.outputs["business_type"] == "consumer_monopoly"  # 财务 ROE/毛利率分类
    assert any("公司信息获取失败" in e for e in res.evidence)


def test_m1_continues_when_financials_fail_but_company_info_exists():
    class _NoFin(StubData):
        def financials(self, code: str, years: int = 10) -> dict:
            raise RuntimeError("JSONDecodeError")

    res = _run_m1(_NoFin())
    assert res.status.value == "done"
    assert res.outputs["industry"] == "白酒"
    assert "数据获取失败" not in res.outputs["business_model"]
    assert any("财务数据获取失败" in e for e in res.evidence)


def test_m1_degrades_only_when_financials_also_fail():
    class _NoData(StubData):
        def company_info(self, code: str) -> dict:
            raise RuntimeError("x")

        def financials(self, code: str, years: int = 10) -> dict:
            raise RuntimeError("y")

    res = _run_m1(_NoData())
    assert res.status.value == "done"
    assert res.outputs["business_type"] == "cyclical"  # 保守按周期
    assert "数据获取失败" in res.outputs["business_model"]


def test_m6_degrades_on_dividend_failure_not_failed():
    """分红数据源失败时，M6 应降级为 DONE（带原因 + meta.degraded），而不是 FAILED 连锁阻塞下游。"""
    from value_agent.governance.agent import M6GovernanceAgent

    class _NoDiv(StubData):
        def dividends(self, code):
            raise ConnectionError("RemoteDisconnected")

    session = Session(id="s1", company_code="000333", status=SessionStatus.CREATED)
    ctx = AgentContext(session=session, assumptions={}, inputs={}, data=_NoDiv(), llm=None)
    res = M6GovernanceAgent().run(ctx)
    assert res.status.value == "done"
    assert res.meta.get("degraded") is True
    assert any("分红数据获取失败" in e for e in res.evidence)
    # 降级输出仍满足下游契约（M9/M10 消费）
    assert res.outputs["handoff"]["governance_score"] == 0
    assert res.outputs["handoff"]["capital_allocation_flag"] == "neutral"
