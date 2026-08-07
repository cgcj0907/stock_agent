"""M8 智能体对 M7 handoff（margin_adjustment）的真实消费测试。

契约（docs/09-module-contracts.md §4 M8）：M7 产出的 margin_adjustment
必须直接叠加到 M8 的要求折扣上，而不是只写进 evidence。
"""
import pytest

from value_agent.agents.base import AgentContext
from value_agent.safety_margin.agent import M8SafetyMarginAgent
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus

INTRINSIC = {"low": 56.67, "mid": 111.21, "high": 149.74}


def _mod(agent_id: str, outputs: dict, score: float = 50.0) -> ModuleResult:
    return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)


def _run(m7_outputs: dict, required_discount: float | None = None, price: float = 40.0):
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    inputs = {
        "M4_valuation": _mod("M4_valuation", {
            "intrinsic_value": INTRINSIC,
            "current_price": price,
            "business_type": "consumer_monopoly",
        }),
        "M7_market": _mod("M7_market", m7_outputs),
    }
    assumptions = {} if required_discount is None else {"required_discount": required_discount}
    ctx = AgentContext(session=session, assumptions=assumptions, inputs=inputs, data=None, llm=None)
    return M8SafetyMarginAgent().run(ctx)


def test_m8_applies_m7_margin_adjustment_to_buy_price():
    """M7 过热（margin_adjustment=+0.05）→ 要求折扣 25%→30%，买入区间收窄。"""
    res = _run({
        "position": "泡沫",
        "handoff": {"valuation_percentile": 0.95, "market_state": "overheated", "margin_adjustment": 0.05},
    })
    assert res.status.value == "done"
    assert res.outputs["required_discount"] == pytest.approx(0.30)
    assert res.outputs["buy_price"] == pytest.approx(56.67 * 0.70, abs=0.01)
    assert any("margin_adjustment" in e for e in res.evidence)


def test_m8_market_cold_relaxes_discount():
    """M7 低估（margin_adjustment=−0.05）→ 要求折扣 25%→20%。"""
    res = _run({
        "position": "低估",
        "handoff": {"valuation_percentile": 0.15, "market_state": "cold", "margin_adjustment": -0.05},
    })
    assert res.outputs["required_discount"] == pytest.approx(0.20)
    assert res.outputs["buy_price"] == pytest.approx(56.67 * 0.80, abs=0.01)


def test_m8_without_m7_keeps_base_discount():
    """M7 缺失/无调整量 → 沿用生意类型默认折扣，行为不变。"""
    res = _run({})
    assert res.outputs["required_discount"] == 0.25
    assert res.outputs["buy_price"] == pytest.approx(56.67 * 0.75, abs=0.01)


def test_m8_margin_adjustment_overrides_none_handoff():
    """handoff 缺失但 M7 有 position → 调整量按 0 处理，不崩溃。"""
    res = _run({"position": "高估"})
    assert res.outputs["required_discount"] == 0.25
    assert res.outputs["buy_price"] == pytest.approx(56.67 * 0.75, abs=0.01)


def test_m8_high_state_emits_price_above_intrinsic_reason():
    """现价高于内在价值上沿 → handoff.reason_codes=[PRICE_ABOVE_INTRINSIC]（契约 §4 M8）。"""
    res = _run({}, price=200.0)
    assert res.outputs["mos_state"] == "expensive"
    assert res.outputs["handoff"]["reason_codes"] == ["PRICE_ABOVE_INTRINSIC"]


def test_m8_buy_zone_reason_codes_empty():
    """正常买入区间态 reason_codes 为空数组（非降级、非高估）。"""
    res = _run({})
    assert res.outputs["mos_state"] == "attractive"
    assert res.outputs["handoff"]["reason_codes"] == []
