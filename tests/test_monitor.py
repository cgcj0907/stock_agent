"""M11 监控测试：规则生成 + 每日运行器触发。"""

from value_agent.monitor.engine import build_monitor_plan
from value_agent.monitor.runner import run_daily_monitor
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


def _mod(agent_id: str, outputs: dict) -> ModuleResult:
    return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=50.0, outputs=outputs)


def test_monitor_plan_generates_rules():
    results = {
        "M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 42.5, "sell_price": 179.69}),
        "M7_market": _mod("M7_market", {"position": "合理"}),
        "M3_growth": _mod("M3_growth", {
            "prosperity": "下行",
            "handoff": {"prosperity_code": "down"},
        }),
        "M2_financial_quality": _mod("M2_financial_quality", {"signals": ["ROE 突变"]}),
        "M9_risk": _mod("M9_risk", {"risk_items": ["护城河不足"]}),
    }
    plan = build_monitor_plan(results)
    types = [r.rule_type for r in plan.rules]
    assert "price_buy" in types and "price_sell" in types
    assert "prosperity_watch" in types and "risk_watch" in types
    assert plan.score > 0
    # 契约：每条规则带 source_module 与 action 分层（§4 M11）
    for rule in plan.rules:
        assert rule.source_module
        assert rule.action in ("watch", "alert", "action")
    buy = next(r for r in plan.rules if r.rule_type == "price_buy")
    assert buy.source_module == "M8_safety_margin"
    assert buy.action == "action"
    risk = next(r for r in plan.rules if r.rule_type == "risk_watch")
    assert risk.source_module == "M9_risk"


def test_monitor_plan_high_valuation_adds_sell():
    results = {
        "M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 10, "sell_price": 100}),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
    }
    plan = build_monitor_plan(results)
    assert any(r.rule_type == "valuation_sell" for r in plan.rules)


class _CheapSource:
    def daily_prices(self, code, start=None, end=None):
        return {"records": [{"trade_date": "20260804", "close": 15.0}]}  # 低于买入 42.5


def _session_with_m8(buy: float, sell: float, code="600519") -> Session:
    s = Session(company_code=code, company_name="测试")
    s.status = SessionStatus.COMPLETED
    s.module_results["M8_safety_margin"] = _mod("M8_safety_margin", {"buy_price": buy, "sell_price": sell})
    return s


def test_daily_runner_records_monitor_hits():
    """I-2：触发事件写入 session.monitor_hits（跨会话记忆输入）。"""
    session = _session_with_m8(buy=42.5, sell=179.69)
    events = run_daily_monitor([session], _CheapSource())
    assert len(events) == 1
    assert session.monitor_hits
    hit = session.monitor_hits[0]
    assert hit["rule_type"] == "price_buy"
    assert hit["severity"] == "info"
    assert "occurred_at" in hit


def test_monitor_plan_replays_prior_warn_hits():
    """I-2：历史 warn/critical 命中回放为回顾规则；info 不回放。"""
    results = {
        "M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 42.5, "sell_price": 179.69}),
    }
    plan = build_monitor_plan(results, prior_hits=[
        {"rule_type": "valuation_sell", "message": "估值过热", "severity": "warn"},
        {"rule_type": "price_buy", "message": "现价低", "severity": "info"},
    ])
    reviews = [r for r in plan.rules if r.rule_type == "prior_hit_review"]
    assert len(reviews) == 1  # 只回放 warn
    assert "估值过热" in reviews[0].trigger
    assert reviews[0].action == "watch"


def test_daily_runner_fires_buy_event_when_price_below_buy():
    session = _session_with_m8(buy=42.5, sell=179.69)
    events = run_daily_monitor([session], _CheapSource())
    assert len(events) == 1
    assert events[0].rule_type == "price_buy"
    assert "15.0" in events[0].message


def test_daily_runner_fires_sell_event_when_price_above_sell():
    class _ExpensiveSource(_CheapSource):
        def daily_prices(self, code, start=None, end=None):
            return {"records": [{"trade_date": "20260804", "close": 200.0}]}

    session = _session_with_m8(buy=42.5, sell=179.69)
    events = run_daily_monitor([session], _ExpensiveSource())
    assert len(events) == 1
    assert events[0].rule_type == "price_sell"


def test_daily_runner_skips_pending_sessions():
    session = _session_with_m8(buy=42.5, sell=179.69)
    session.status = SessionStatus.CREATED
    assert run_daily_monitor([session], _CheapSource()) == []
