"""S3 定性模块单元测试：M1 分类 / M5 护城河 / M6 治理（规则层）。"""
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
