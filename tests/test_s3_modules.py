"""S3 定性模块单元测试：M1 分类 / M5 护城河 / M6 治理（规则层）。"""
from tests.conftest import StubData
from value_agent.agents.base import AgentContext  # 先加载 agents，避免 builtin 注册触发循环导入
from value_agent.business_model.agent import M1BusinessModelAgent
from value_agent.business_model.engine import analyze_business_model, classify_business_type
from value_agent.governance.engine import assess_governance
from value_agent.moat.engine import assess_moat
from value_agent.sessions.models import Session, SessionStatus


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


def test_moat_width_bands():
    strong = {"records": [{"period": f"{2026 - i}1231", "roe": 20, "grossprofit_margin": 60, "debt_to_assets": 0.2} for i in range(10)]}
    weak = {"records": [{"period": f"{2026 - i}1231", "roe": 5, "grossprofit_margin": 10, "debt_to_assets": 0.8} for i in range(10)]}
    assert assess_moat(strong).width == "宽"
    assert assess_moat(weak).width == "无"


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


class _FakeLLM:
    """最小 LLM 桩：返回预设文本。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def chat(self, system: str, user: str) -> str:
        return self._text


def _run_m1_with_llm(llm_text: str):
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    ctx = AgentContext(
        session=session, assumptions={}, inputs={},
        data=StubData(), llm=_FakeLLM(llm_text),
    )
    return M1BusinessModelAgent().run(ctx)


def test_m1_filters_invalid_reference_links(monkeypatch):
    """LLM 给的参考链接经校验后只保留真实可访问的。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.validate_reference_links",
        lambda refs: [r for r in refs if "annual" in r["url"]],
    )
    res = _run_m1_with_llm(
        '{"business_model": "运货赚钱", "understandability": "可理解", '
        '"reasons": ["r1"], '
        '"references": [{"title": "假链接", "url": "https://example.com/fake"}, '
        '{"title": "真年报", "url": "https://example.com/annual.pdf"}]}'
    )
    quals = res.outputs["llm_qualitative"]
    assert quals["references"] == [{"title": "真年报", "url": "https://example.com/annual.pdf"}]


def test_m1_drops_all_invalid_references(monkeypatch):
    """参考链接全部无效时，直接移除 references 字段。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.validate_reference_links",
        lambda refs: [],
    )
    res = _run_m1_with_llm(
        '{"business_model": "运货赚钱", "understandability": "可理解", '
        '"reasons": ["r1"], "references": [{"title": "x", "url": "https://example.com/x"}]}'
    )
    assert "references" not in res.outputs["llm_qualitative"]
