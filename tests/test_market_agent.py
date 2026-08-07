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


# ---------- backlog 7.1/7.2/7.5/7.12：多情绪指标合成 ----------

class _MultiSentimentData(_FakeData):
    """日线 + 北向 + 两融 + 大盘情绪全部可用。"""

    def northbound(self, code: str) -> dict:
        return {
            "records": [
                {"trade_date": f"20250{i:02d}01", "hold_shares": 1e6 + i * 1e4,
                 "hold_ratio": 0.03 + i * 0.002}
                for i in range(1, 31)
            ]
        }

    def margin(self, code: str) -> dict:
        return {
            "records": [
                {"trade_date": f"20250{i:02d}01", "margin_balance": 5e8 + i * 1e6,
                 "fin_balance": 4.8e8, "sec_balance": 2e7}
                for i in range(1, 31)
            ]
        }

    def market_activity(self) -> dict:
        return {"records": [{"trade_date": "20260807", "up_count": 2100,
                             "down_count": 2900, "breadth": 0.42}]}


def test_m7_aggregates_multi_sentiment_metrics():
    """7.12：换手率 + 北向 + 两融 + 大盘涨跌家数合成情绪热度。"""
    res = _run(_MultiSentimentData(), m1_outputs={"business_type": "consumer_monopoly", "financial_subtype": "other"})
    assert res.outputs["sentiment_heat"] is not None
    signals = "；".join(res.outputs["sentiment_signals"])
    assert "北向持股比例" in signals
    assert "融资融券余额" in signals
    assert "全市场上涨家数占比" in signals
    assert res.outputs["handoff"]["sentiment_heat"] == res.outputs["sentiment_heat"]


def test_m7_handles_missing_sentiment_sources():
    """7.1/7.2/7.5 缺失（如 StubData 无接口）→ 只丢对应指标，不降级模块。"""
    res = _run(_FakeData(daily_ok=False))
    assert res.status.value == "done"
    assert res.outputs["sentiment_heat"] is None
