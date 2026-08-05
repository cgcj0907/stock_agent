"""S4 模块单元测试：M3 成长 / M7 价格情绪 / M9 风险。"""
import pytest

from value_agent.growth.engine import assess_growth
from value_agent.market.engine import assess_market
from value_agent.risk.engine import assess_risk
from value_agent.sessions.models import ModuleResult, ModuleStatus


# ---- M3 ----
def test_growth_estimate_from_eps_cagr():
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0 * (1.1 ** (9 - i)), "roe": 20, "debt_to_assets": 0.3} for i in range(10)]
    r = assess_growth({"records": recs})
    assert r.growth_estimate == pytest.approx(0.10, abs=0.02)
    assert r.prosperity in ("上行", "平稳")


def test_growth_decline_prosperity_down():
    # 最新期(2026) EPS 低于最早期(2017) → 增速为负 → 下行
    recs = [{"period": f"{2026 - i}1231", "eps": 2.3 + i * 0.3, "roe": 12, "debt_to_assets": 0.4} for i in range(10)]
    r = assess_growth({"records": recs})
    assert r.prosperity == "下行"
    assert r.growth_estimate < 0.05


def test_growth_caps_at_20pct():
    recs = [{"period": f"{2026 - i}1231", "eps": 1.0 * (1.5 ** (9 - i)), "roe": 30, "debt_to_assets": 0.2} for i in range(10)]
    assert assess_growth({"records": recs}).growth_estimate <= 0.20


# ---- M7 ----
def test_market_insufficient_samples():
    r = assess_market({"records": [{"trade_date": "20260731", "pe_ttm": 20, "pb": 3}, {"trade_date": "20260803", "pe_ttm": 21, "pb": 3.1}]})
    assert r.position == "样本不足（<10 期）"
    assert r.score == 50.0


def test_market_percentile_position():
    import random
    random.seed(1)
    recs = [
        {"trade_date": f"202501{i:02d}", "pe_ttm": random.uniform(10, 40), "pb": random.uniform(2, 5)}
        for i in range(1, 100)
    ]
    recs[-1]["pe_ttm"] = 15.0   # 当前低分位
    recs[-1]["pb"] = 2.2
    r = assess_market({"records": recs})
    assert r.pe_percentile is not None
    assert r.position in ("极低估", "低估")


def test_market_overvalued_high_percentile():
    recs = [
        {"trade_date": f"202501{i:02d}", "pe_ttm": 10 + i * 0.1, "pb": 2 + i * 0.02}
        for i in range(1, 101)
    ]
    r = assess_market({"records": recs})
    assert r.position in ("高估", "泡沫")


# ---- M9 ----
def _mod(agent_id: str, outputs: dict, score: float | None = 50.0) -> ModuleResult:
    return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)


def test_risk_aggregates_and_veto():
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {"signals": ["ROE 单年突变"], "score": 100}, 100),
        "M3_growth": _mod("M3_growth", {"prosperity": "下行", "growth_estimate": 0.0}),
        "M5_moat": _mod("M5_moat", {"width": "无"}),
        "M6_governance": _mod("M6_governance", {"score": 60}, 60),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": -0.3}, 10),
    }
    r = assess_risk(inputs)
    assert any("财务信号" in x for x in r.risk_items)
    assert any("护城河" in x for x in r.risk_items)
    assert any("泡沫" in x for x in r.risk_items)
    assert r.veto == []


def test_risk_veto_on_bad_financials():
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {"score": 20}, 20),
    }
    r = assess_risk(inputs)
    assert any("财务质量极差" in v for v in r.veto)


def test_risk_assumption_veto():
    r = assess_risk({}, assumptions={"veto_reasons": ["pledge_ratio_gt_80"]})
    assert r.veto == ["pledge_ratio_gt_80"]
    assert r.score < 100


def test_shipping_classified_cyclical():
    """航运港口/水运/运输按周期分类（中远海控场景），避免误判资产/成长。"""
    from value_agent.business_model.engine import classify_business_type

    assert classify_business_type("航运港口", 13.0, 15.0, 0.4) == "cyclical"
    assert classify_business_type("水运", 13.0, 15.0, 0.4) == "cyclical"
    assert classify_business_type("高速公路", 15.0, 50.0, 0.4) == "asset_based"
