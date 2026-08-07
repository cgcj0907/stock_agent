"""S3 定性模块单元测试：M1 分类 / M5 护城河 / M6 治理（规则层）。"""

import pytest

from value_agent.business_model.engine import analyze_business_model, classify_business_type
from value_agent.governance.engine import assess_governance
from value_agent.moat.engine import assess_moat


def test_classify_by_industry_keywords():
    assert classify_business_type("股份制银行", 10, 30, 0.9) == "financial"
    assert classify_business_type("有色金属", 20, 20, 0.5) == "cyclical"
    assert classify_business_type("房地产", 10, 30, 0.7) == "cyclical"  # 周期先于资产匹配


def test_classify_by_profitability():
    assert classify_business_type("", 18, 45, 0.35) == "consumer_monopoly"
    assert classify_business_type("", 12, 30, 0.5) == "growth"
    assert classify_business_type("", 5, 20, 0.7) == "cyclical"  # 未知+低盈利保守


def test_m1_result_contains_routing_type():
    r = analyze_business_model(
        {"code": "600519", "name": "茅台", "industry": "白酒"},
        {"records": [{"period": "20261231", "roe": 30, "grossprofit_margin": 90, "debt_to_assets": 0.2}]},
    )
    assert r.business_type == "consumer_monopoly"
    assert "M4 估值方法将按此路由" in " ".join(r.evidence)


def test_moat_rule_proxy_tiers():
    """规则层 = 财务代理评级：极强/极弱两端的档位仍正确。"""
    strong = {"records": [{"period": f"{2026 - i}1231", "roe": 20, "grossprofit_margin": 60, "debt_to_assets": 0.2} for i in range(10)]}
    weak = {"records": [{"period": f"{2026 - i}1231", "roe": 5, "grossprofit_margin": 10, "debt_to_assets": 0.8} for i in range(10)]}
    assert assess_moat(strong).rule_tier == "宽"
    assert assess_moat(weak).rule_tier == "无"


def test_moat_peer_relative_not_absolute():
    """同行相对性：同一份高盈利财务数据，消费垄断基准下是「宽」，金融基准下不是。
    （修复旧版绝对阈值偏爱高毛利行业、低估银行的问题。）"""
    fin = {"records": [{"period": f"{2026 - i}1231", "roe": 20, "grossprofit_margin": 60,
                        "netprofit_margin": 30, "debt_to_assets": 0.2} for i in range(10)]}
    consumer = assess_moat(fin, industry="白酒", business_type="consumer_monopoly")
    bank = assess_moat(fin, industry="银行", business_type="financial")
    assert consumer.rule_tier == "宽"
    assert bank.rule_tier != "宽"          # 金融基准：毛利率维度不适用，不再被高毛利撑成「宽」
    assert bank.peer is not None
    assert bank.peer.margin_key == "netprofit_margin"  # 金融用净利率口径


def test_moat_peer_context_and_sources():
    """同行对比上下文 + 来源代理信号：高利润率→无形资产，低杠杆→成本/规模优势。"""
    fin = {"records": [{"period": f"{2026 - i}1231", "roe": 20, "grossprofit_margin": 60,
                        "debt_to_assets": 0.2} for i in range(10)]}
    r = assess_moat(fin, industry="白酒", business_type="consumer_monopoly")
    assert r.peer is not None
    assert r.peer.roe_company == 20.0
    assert r.peer.roe_median == 18.0
    srcs = {s.source for s in r.sources}
    assert "无形资产" in srcs
    assert "成本/规模优势" in srcs
    assert any(s.strength == "strong" for s in r.sources)


def test_ship_building_classified_cyclical():
    """船舶/造船是典型强周期行业：显式命中周期关键词，不再依赖低盈利兜底。"""
    assert classify_business_type("船舶制造", 20.0, 30.0, 0.5) == "cyclical"
    assert classify_business_type("造船", 20.0, 30.0, 0.5) == "cyclical"


def test_moat_cyclical_uses_through_cycle_roe():
    """5.6：周期行业 ROE 用近 8 年跨周期均值去周期位置；波动/下滑进 cycle_notes 而非侵蚀信号。"""
    # 最新期(2026)=1（周期低谷），历史最高 18 → 近 8 年跨周期均值 7.1（固定窗口，不随总年数漂移）
    roes = [1, 2, 4, 6, 8, 10, 12, 14, 16, 18]
    recs = [{"period": f"{2026 - i}1231", "roe": r, "grossprofit_margin": 18,
             "debt_to_assets": 0.6} for i, r in enumerate(roes)]
    r = assess_moat({"records": recs}, industry="船舶制造", business_type="cyclical")
    assert r.peer is not None
    assert round(r.peer.roe_company, 1) == 7.1          # 近 8 年跨周期均值而非最新 1.0
    assert any("跨周期均值" in s for s in r.signals)
    assert r.cycle_notes, "周期行业 ROE 波动/下滑应记入周期属性备注"
    assert not r.erosion_signals, "周期行业 ROE 波动不应进侵蚀信号（避免污染 M9）"
    assert r.peer.debt_note, "杠杆口径应注明 debt_to_assets 含合同负债"
    assert any("周期属性备注" in e for e in r.evidence)


def test_moat_missing_data_degrades():
    """无数据 → 代理档位「无」、0 分、明确证据。"""
    r = assess_moat({"records": []})
    assert r.rule_tier == "无"
    assert r.score == 0.0
    assert any("无财务数据" in e for e in r.evidence)


def test_moat_erosion_signals_on_decline():
    """ROE 下滑 → 规则层侵蚀信号非空，且评分被扣减。"""
    # 最新期(2026) ROE 最低（6.5），越往历史越高（20）→ 持续下滑
    recs = [{"period": f"{2026 - i}1231", "roe": 6.5 + i * 1.5, "grossprofit_margin": 50,
             "debt_to_assets": 0.3} for i in range(10)]
    r = assess_moat({"records": recs}, industry="白酒", business_type="consumer_monopoly")
    assert r.erosion_signals, "ROE 持续下滑应触发侵蚀信号"
    assert any("ROE 下滑" in s for s in r.erosion_signals)


def test_governance_no_data_neutral():
    r = assess_governance({"records": []})
    assert r.score == 50.0
    assert "中性" in r.note


def test_governance_increasing_payouts_scores_higher():
    r = assess_governance({"records": [
        {"period": "20251231", "cash_div_tax": 2.2},
        {"period": "20241231", "cash_div_tax": 2.0},
    ]})
    assert r.dividend_years == 2
    assert r.score >= 60
    assert "递增" in r.note


def test_governance_rule_events_lower_score_and_emit_risk_codes():
    """规则层非分红证据：监管处罚/质押/减持等治理事件扣分，并映射结构化风险码（M9 消费）。"""
    div = {"records": [
        {"period": "20251231", "cash_div_tax": 2.2},
        {"period": "20241231", "cash_div_tax": 2.0},
    ]}
    events = {
        "regulatory": [{"kind": "处罚", "date": "2025-06", "reason": "信披违规"}],
        "pledges": [{"holder": "控股股东", "ratio": 0.3}],
        "buybacks": [],
    }
    r = assess_governance(div, events=events)
    # 基础 65（40+10+15）- 监管15 - 质押15 = 35
    assert r.score == 35.0
    codes = {c["code"] for c in r.risk_codes}
    assert "REGULATORY_PENALTY" in codes and "SHARE_PLEDGE" in codes
    reg = next(c for c in r.risk_codes if c["code"] == "REGULATORY_PENALTY")
    assert reg["severity"] == "high" and "信披违规" in reg["description"]
    assert any("治理事件" in e for e in r.evidence)


def test_governance_buybacks_raise_score():
    """持续回购是正面非分红证据：加分且不产生风险码。"""
    div = {"records": [
        {"period": "20251231", "cash_div_tax": 2.2},
        {"period": "20241231", "cash_div_tax": 2.0},
    ]}
    events = {"buybacks": [
        {"period": "20241231", "amount": 10.0},
        {"period": "20251231", "amount": 12.0},
    ]}
    r = assess_governance(div, events=events)
    assert r.score == 75.0  # 65 + 10
    assert r.risk_codes == []
    assert any("持续回购" in e for e in r.evidence)


def test_governance_events_wired_but_empty_is_neutral():
    """事件数据源已接入但无事件 → 中性处理，不再标「待接入」。"""
    div = {"records": [
        {"period": "20251231", "cash_div_tax": 2.2},
        {"period": "20241231", "cash_div_tax": 2.0},
    ]}
    r = assess_governance(div, events={})
    assert r.score == 65.0
    assert r.risk_codes == []
    assert any("暂无治理事件数据" in e for e in r.evidence)
    assert not any("待接入" in e for e in r.evidence)


def test_governance_no_event_source_marks_pending():
    """事件数据源未接入（events=None）→ 保留「待接入」标注，评分不变。"""
    div = {"records": [
        {"period": "20251231", "cash_div_tax": 2.2},
        {"period": "20241231", "cash_div_tax": 2.0},
    ]}
    r = assess_governance(div, events=None)
    assert r.score == 65.0
    assert any("待接入" in e for e in r.evidence)


def test_utility_classified_as_stable_dividend():
    """公用事业（长江电力这类）应归 stable_dividend，避免被误分消费垄断用 DCF/唐朝 25 倍。"""
    from value_agent.business_model.engine import classify_business_type

    assert classify_business_type("电力", 15.0, 60.0, 0.5) == "stable_dividend"
    assert classify_business_type("燃气", 12.0, 30.0, 0.6) == "stable_dividend"


def test_financial_subtype_detection():
    from value_agent.business_model.engine import analyze_business_model, financial_subtype_of

    assert financial_subtype_of("股份制银行") == "bank"
    assert financial_subtype_of("证券") == "broker"
    assert financial_subtype_of("保险") == "insurance"
    assert financial_subtype_of("白酒") == "other"

    r = analyze_business_model(
        {"code": "600036", "name": "招商银行", "industry": "股份制银行"},
        {"records": [{"period": "20251231", "roe": 15.0}]},
    )
    assert r.business_type == "financial"
    assert r.financial_subtype == "bank"


# ---------- backlog 5.2 / 5.4：有息负债率 + 研发强度 ----------

def test_moat_prefers_interest_debt_ratio():
    """5.2：有 interest_debt_ratio 时用它做杠杆对比（不含合同负债）；高合同负债给口径注记。"""
    from value_agent.moat.engine import assess_moat

    recs = [{"period": f"{2026 - i}1231", "roe": 15.0, "grossprofit_margin": 40.0,
             "debt_to_assets": 0.7, "interest_debt_ratio": 0.2,
             "contract_liability_ratio": 0.35} for i in range(6)]
    r = assess_moat({"records": recs}, industry="白酒", business_type="consumer_monopoly")
    assert r.peer is not None
    assert r.peer.debt_company == pytest.approx(0.2)  # 用有息口径 0.2 而非报表 0.7
    assert r.peer.debt_note and "合同负债占比 35%" in r.peer.debt_note


def test_moat_rd_ratio_adds_tech_source():
    """5.4：研发费用率 ≥5% → 无形资产来源（技术壁垒代理）。"""
    from value_agent.moat.engine import assess_moat

    recs = [{"period": f"{2026 - i}1231", "roe": 14.0, "grossprofit_margin": 35.0,
             "debt_to_assets": 0.3, "rd_ratio": 0.08} for i in range(6)]
    r = assess_moat({"records": recs}, industry="软件", business_type="growth")
    assert any(s.source == "无形资产" and "研发费用率" in s.basis for s in r.sources)
