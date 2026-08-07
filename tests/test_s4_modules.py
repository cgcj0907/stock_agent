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


def test_growth_no_eps_uses_default_not_crash():
    # 回归：无 EPS 时走默认增速，不再抛 UnboundLocalError（原实现 cagr 未初始化）
    r = assess_growth({"records": [{"period": "20251231", "eps": None, "roe": 15, "debt_to_assets": 0.3}]})
    assert r.growth_estimate == pytest.approx(0.10)
    assert r.growth_confidence == "low"
    assert r.prosperity == "平稳" and r.prosperity_code == "flat"


def test_growth_empty_records_uses_default():
    r = assess_growth({"records": []})
    assert r.growth_estimate == pytest.approx(0.10)
    assert r.growth_confidence == "low"
    assert r.prosperity_code in ("up", "flat", "down")


def test_growth_flat_eps_stable_roe_is_flat_not_down():
    # 成熟稳定公司：EPS 持平、ROE 稳定 → 平稳，而非"下行"（避免 M9/M11 假警报）
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0, "roe": 18, "debt_to_assets": 0.3} for i in range(8)]
    r = assess_growth({"records": recs})
    assert r.prosperity == "平稳"
    assert r.prosperity_code == "flat"


def test_growth_roe_deterioration_down():
    # ROE 同比下滑 ≥5pp（即使 EPS 持平）→ 下行
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0, "roe": 18, "debt_to_assets": 0.3} for i in range(8)]
    recs[0]["roe"] = 10  # 最新一年 18 → 10
    r = assess_growth({"records": recs})
    assert r.prosperity == "下行"
    assert r.prosperity_code == "down"


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


def test_market_pb_only_fallback_when_pe_insufficient():
    """银行/资产型：PE 样本不足但 PB 完整 → 用 PB 分位，不再误判"样本不足"。"""
    recs = [
        {"trade_date": f"202501{i:02d}", "pb": 0.5 + i * 0.02}
        for i in range(1, 51)
    ]
    r = assess_market({"records": recs})
    assert r.pe_percentile is None
    assert r.pb_percentile is not None
    assert r.position in ("高估", "泡沫")  # 最新 PB 分位最高
    assert any("PB 分位" in e for e in r.evidence)


def test_market_pb_only_low_percentile_is_cheap():
    recs = [
        {"trade_date": f"202501{i:02d}", "pb": 3.0 - i * 0.01}
        for i in range(1, 51)
    ]
    r = assess_market({"records": recs})
    assert r.pe_percentile is None
    assert r.pb_percentile is not None
    assert r.position in ("极低估", "低估")


def test_market_pe_only_when_pb_missing():
    """PB 缺失但 PE 完整 → 仍用 PE 分位（现状保持）。"""
    recs = [
        {"trade_date": f"202501{i:02d}", "pe_ttm": 10 + i * 0.1}
        for i in range(1, 51)
    ]
    r = assess_market({"records": recs})
    assert r.pe_percentile is not None
    assert r.pb_percentile is None
    assert r.position in ("高估", "泡沫")


# ---- M9 ----
def _mod(agent_id: str, outputs: dict, score: float | None = 50.0) -> ModuleResult:
    return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)


def test_risk_aggregates_and_veto():
    inputs = {
        "M2_financial_quality": _mod(
            "M2_financial_quality",
            {"signals": [
                {"code": "ROE_SPIKE", "severity": "medium", "metric": "roe", "message": "ROE 单年突变"},
            ], "score": 100},
            100,
        ),
        "M3_growth": _mod("M3_growth", {
            "prosperity": "下行", "growth_estimate": 0.0,
            "handoff": {"prosperity_code": "down"},
        }),
        "M5_moat": _mod("M5_moat", {"width": "无"}),
        "M6_governance": _mod("M6_governance", {"score": 60}, 60),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": -0.3}, 10),
    }
    r = assess_risk(inputs)
    # Risk Registry：对象化（id/category/severity/source_module/trigger/impact）
    assert all({"id", "category", "severity", "source_module", "trigger", "impact"} <= set(x) for x in r.risk_items)
    assert any("ROE 单年突变" in x["impact"] for x in r.risk_items)  # 结构化信号按 message 消费
    assert any("护城河" in x["impact"] for x in r.risk_items)
    assert any("泡沫" in x["impact"] for x in r.risk_items)
    assert any(x["category"] == "景气" and x["trigger"] == "prosperity_code=down" for x in r.risk_items)
    assert r.veto == []  # 兼容列表
    assert r.vetoes == []
    assert sorted(r.monitor_candidates) == ["R-004", "R-005"]  # 泡沫(high) + 安全边际(high) 进入监控候选


def test_risk_veto_on_bad_financials():
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {"score": 20}, 20),
    }
    r = assess_risk(inputs)
    assert any("财务质量极差" in v for v in r.veto)


def test_risk_consumes_moat_erosion_risks():
    """M9 真正消费 M5 handoff 的 erosion_risks/moat_durability（契约闭环，不再只看 width）。"""
    inputs = {
        "M5_moat": _mod("M5_moat", {
            "width": "中",
            "handoff": {
                "moat_width": "medium",
                "moat_durability": "low",
                "erosion_risks": ["新进入者低价竞争", "技术路线被替代"],
            },
        }),
    }
    r = assess_risk(inputs)
    erosion_items = [
        it for it in r.risk_items
        if it["category"] == "护城河" and it["trigger"] == "erosion_risk"
    ]
    assert len(erosion_items) == 2
    assert any("低价竞争" in it["impact"] for it in erosion_items)
    # durability=low → 侵蚀风险升级为 high → 自动进入 M11 监控候选
    assert all(it["severity"] == "high" for it in erosion_items)
    assert all(it["id"] in r.monitor_candidates for it in erosion_items)


def test_risk_moat_erosion_medium_when_durable():
    """durability=high 时侵蚀风险为 medium，不进入监控候选。"""
    inputs = {
        "M5_moat": _mod("M5_moat", {
            "width": "宽",
            "handoff": {
                "moat_width": "wide",
                "moat_durability": "high",
                "erosion_risks": ["新进入者低价竞争"],
            },
        }),
    }
    r = assess_risk(inputs)
    erosion_items = [it for it in r.risk_items if it["trigger"] == "erosion_risk"]
    assert len(erosion_items) == 1
    assert erosion_items[0]["severity"] == "medium"
    assert erosion_items[0]["id"] not in r.monitor_candidates


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
