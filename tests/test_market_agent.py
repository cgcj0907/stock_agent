"""M7 智能体测试：消费 M1 生意类型 + 换手率情绪 + 降级边界。"""
from __future__ import annotations

from value_agent.agents.base import AgentContext
from value_agent.market.agent import M7MarketAgent
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


class _FakeData:
    """可控假数据：估值历史 + 带换手率的日线。"""

    def __init__(self, daily_ok: bool = True) -> None:
        self._daily_ok = daily_ok

    def valuation_history(self, code: str) -> dict:
        return {
            "records": [
                {"trade_date": f"2025{i:02d}01", "pe_ttm": 20.0, "pb": 4.0}
                for i in range(1, 13)
            ]
        }

    def daily_prices(self, code: str) -> dict:
        if not self._daily_ok:
            raise ConnectionError("RemoteDisconnected")
        return {
            "records": [
                {"trade_date": f"20250{i:02d}01", "turnover": 5.0 - i * 0.1, "close": 10.0}
                for i in range(1, 31)
            ]
        }


def _run(data, m1_outputs: dict | None = None):
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    inputs = {}
    if m1_outputs is not None:
        inputs["M1_business_model"] = ModuleResult(
            module="M1_business_model", status=ModuleStatus.DONE, score=60.0,
            outputs=m1_outputs,
        )
    ctx = AgentContext(session=session, assumptions={}, inputs=inputs, data=data, llm=None)
    return M7MarketAgent().run(ctx)


def test_m7_agent_wires_turnover_sentiment_and_business_type():
    """换手率情绪 + M1 生意类型都进入结论：情绪热度输出 + 主指标证据。"""
    res = _run(_FakeData(), m1_outputs={"business_type": "cyclical", "financial_subtype": "other"})
    assert res.status.value == "done"
    assert res.outputs["sentiment_heat"] is not None
    assert res.outputs["sentiment_signals"], "应有换手率情绪信号"
    assert any("换手率" in e for e in res.outputs["sentiment_signals"])
    assert res.outputs["handoff"]["sentiment_heat"] == res.outputs["sentiment_heat"]
    assert any("主指标 PB" in e for e in res.evidence)


def test_m7_agent_daily_prices_failure_keeps_module_done():
    """日线（情绪）失败 → 只丢情绪，不降级模块，契约 handoff 仍完整。"""
    res = _run(_FakeData(daily_ok=False), m1_outputs={"business_type": "consumer_monopoly"})
    assert res.status.value == "done"
    assert res.outputs["sentiment_heat"] is None
    assert res.outputs["handoff"]["market_state"] in ("overheated", "normal", "cold", "insufficient")
    assert "margin_adjustment" in res.outputs["handoff"]
    assert any("情绪指标未接入" in e for e in res.evidence)


def test_m7_agent_without_m1_falls_back_to_max():
    """M1 缺失（如 quick 流）→ 退化为 max(PE,PB) 保守口径，不报错。"""
    res = _run(_FakeData(daily_ok=False))
    assert res.status.value == "done"
    assert res.outputs["position"] in ("高估", "泡沫")
    assert "margin_adjustment" in res.outputs["handoff"]
