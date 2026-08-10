"""M11 监控测试：规则生成 + 每日运行器触发。"""

from value_agent.monitor.engine import build_monitor_plan
from value_agent.monitor.runner import MonitorEvent, notify_webhooks, run_daily_monitor
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
        "M2_financial_quality": _mod("M2_financial_quality", {"signals": [
            {"code": "ROE_SPIKE", "severity": "high", "metric": "roe", "message": "ROE 突变"},
        ]}),
        "M9_risk": _mod("M9_risk", {
            "risk_items": [
                {"id": "R-001", "trigger": "width=narrow", "impact": "护城河不足",
                 "severity": "high", "source_module": "M5_moat"},
            ],
            "monitor_candidates": ["R-001"],
        }),
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
    assert risk.source_module == "M5_moat"  # 风险项真实来源模块


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
    rules_store = _store_rules(session, [
        {"rule_type": "price_buy", "company_code": session.company_code, "company_name": "测试",
         "message": "跌破买入区间", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 42.5}},
    ])
    events = run_daily_monitor([session], _CheapSource(), rules_store=rules_store)
    assert len(events) == 1
    assert session.monitor_hits
    hit = session.monitor_hits[0]
    assert hit["rule_type"] == "price_buy"
    assert hit["severity"] == "info"
    assert "occurred_at" in hit



def test_monitor_plan_consumes_monitor_candidates():
    """契约：M11 只把 M9 的 monitor_candidates（high/critical）转成 risk_watch，medium 不转。"""
    results = {
        "M9_risk": _mod("M9_risk", {
            "risk_items": [
                {"id": "R-001", "trigger": "t_high", "impact": "高严重度风险", "severity": "high",
                 "source_module": "M5_moat"},
                {"id": "R-002", "trigger": "t_medium", "impact": "中严重度风险", "severity": "medium",
                 "source_module": "M3_growth"},
            ],
            "monitor_candidates": ["R-001"],
        }),
    }
    plan = build_monitor_plan(results)
    risk_watch = [r for r in plan.rules if r.rule_type == "risk_watch"]
    assert [r.trigger for r in risk_watch] == ["t_high"]


def test_monitor_plan_falls_back_to_all_items_without_candidates():
    """无 monitor_candidates → 回退全量**结构化** risk_items；字符串形态不再兼容（9.6 收口）。"""
    results = {
        "M9_risk": _mod("M9_risk", {
            "risk_items": [
                {"id": "R-001", "trigger": "t1", "impact": "护城河不足", "severity": "high",
                 "source_module": "M5_moat"},
                "旧字符串形态",  # 9.6：忽略非对象
            ],
        }),
    }
    plan = build_monitor_plan(results)
    risk_watch = [r for r in plan.rules if r.rule_type == "risk_watch"]
    assert len(risk_watch) == 1 and risk_watch[0].source_module == "M5_moat"


def test_monitor_plan_dedup_m2_sourced_risk_items():
    """M2 信号已由 M2 直接转 fundamental_watch，M9 聚合的同源 risk_item 不再重复转 risk_watch。"""
    results = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "signals": [{"code": "LOSS_YEAR", "severity": "high", "metric": "roe",
                         "message": "存在亏损年份"}],
        }),
        "M9_risk": _mod("M9_risk", {
            "risk_items": [
                {"id": "R-001", "trigger": "LOSS_YEAR", "impact": "存在亏损年份", "severity": "high",
                 "source_module": "M2_financial_quality"},
                {"id": "R-002", "trigger": "erosion_risk", "impact": "护城河被侵蚀", "severity": "high",
                 "source_module": "M5_moat"},
            ],
            "monitor_candidates": ["R-001", "R-002"],
        }),
    }
    plan = build_monitor_plan(results)
    fundamental = [r for r in plan.rules if r.rule_type == "fundamental_watch"]
    risk_watch = [r for r in plan.rules if r.rule_type == "risk_watch"]
    assert len(fundamental) == 1
    assert [r.trigger for r in risk_watch] == ["erosion_risk"]


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
    rules_store = _store_rules(session, [
        {"rule_type": "price_buy", "company_code": session.company_code, "company_name": "测试",
         "message": "跌破买入区间", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 42.5}},
    ])
    events = run_daily_monitor([session], _CheapSource(), rules_store=rules_store)
    assert len(events) == 1
    assert events[0].rule_type == "price_buy"
    assert "15.0" in events[0].message


def test_daily_runner_fires_sell_event_when_price_above_sell():
    class _ExpensiveSource(_CheapSource):
        def daily_prices(self, code, start=None, end=None):
            return {"records": [{"trade_date": "20260804", "close": 200.0}]}

    session = _session_with_m8(buy=42.5, sell=179.69)
    rules_store = _store_rules(session, [
        {"rule_type": "price_sell", "company_code": session.company_code, "company_name": "测试",
         "message": "达到卖出区间", "severity": "warn", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 179.69}},
    ])
    events = run_daily_monitor([session], _ExpensiveSource(), rules_store=rules_store)
    assert len(events) == 1
    assert events[0].rule_type == "price_sell"


def test_daily_runner_skips_pending_sessions():
    session = _session_with_m8(buy=42.5, sell=179.69)
    session.status = SessionStatus.CREATED
    assert run_daily_monitor([session], _CheapSource()) == []


# ---------- M11 消费 M10 决策（契约 §4 M11：依赖 M10_decision） ----------

def test_monitor_plan_consumes_m10_buy_decision():
    """M10 决策=buy → 生成 decision_watch 规则（来源 M10_decision）。"""
    results = {
        "M10_decision": _mod("M10_decision", {
            "decision_code": "buy",
            "blocked_by_veto": False,
            "position": 0.1,
            "handoff": {"decision_code": "buy", "blocked_by_veto": False, "position": 0.1},
        }),
    }
    plan = build_monitor_plan(results)
    dec = [r for r in plan.rules if r.rule_type == "decision_watch"]
    assert len(dec) == 1
    assert dec[0].source_module == "M10_decision"
    assert "buy" in dec[0].trigger
    assert dec[0].action == "watch"


def test_monitor_plan_m10_veto_adds_avoid_watch():
    """M10 一票否决/avoid → decision_watch 规则标记解除前不建仓。"""
    results = {
        "M10_decision": _mod("M10_decision", {
            "decision_code": "avoid",
            "blocked_by_veto": True,
            "handoff": {"decision_code": "avoid", "blocked_by_veto": True, "position": 0.0},
        }),
    }
    plan = build_monitor_plan(results)
    dec = [r for r in plan.rules if r.rule_type == "decision_watch"]
    assert len(dec) == 1
    assert "avoid" in dec[0].trigger
    assert dec[0].severity == "warn"


def test_monitor_plan_ignores_missing_m10():
    """M10 未运行（如监控历史会话缺 M10）→ 不生成 decision_watch，不报错。"""
    results = {"M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 10, "sell_price": 100})}
    plan = build_monitor_plan(results)
    assert not any(r.rule_type == "decision_watch" for r in plan.rules)
    assert any(r.rule_type == "price_buy" for r in plan.rules)


def test_daily_runner_hits_persist_roundtrip(tmp_path):
    """I-2 记忆闭环：cmd_monitor 必须把命中写回存储；重载后仍在（此前只改内存即丢）。"""
    from value_agent.monitor.rules_store import SqliteRuleStore
    from value_agent.sessions.store import SqliteStore

    db = str(tmp_path / "sessions.db")
    store = SqliteStore(db)
    rules_store = SqliteRuleStore(db)
    session = _session_with_m8(buy=42.5, sell=179.69)
    store.save(session)
    rules_store.replace_for_session(session.id, [
        {"rule_type": "price_buy", "company_code": session.company_code, "company_name": "测试",
         "message": "跌破买入区间", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 42.5}},
    ])

    loaded = store.list()
    assert not loaded[0].monitor_hits
    events = run_daily_monitor(loaded, _CheapSource(), rules_store=rules_store)
    assert len(events) == 1
    for s in loaded:  # cmd_monitor 的写回行为：复用同一份列表
        if s.monitor_hits:
            store.save(s)

    again = store.list()
    assert len(again[0].monitor_hits) == 1
    assert again[0].monitor_hits[0]["rule_type"] == "price_buy"
    rules_store.close()


def test_memory_loop_end_to_end(tmp_path):
    """I-2 端到端：每日命中 → 持久化 → 新会话继承 → M11 回放为回顾规则。"""
    from value_agent.sessions import SessionManager
    from value_agent.sessions.store import SqliteStore

    class _ExpensiveSource:
        def daily_prices(self, code, start=None, end=None):
            return {"records": [{"trade_date": "20260804", "close": 200.0}]}

    from value_agent.monitor.rules_store import SqliteRuleStore

    db = str(tmp_path / "sessions.db")
    store = SqliteStore(db)
    rules_store = SqliteRuleStore(db)
    session = _session_with_m8(buy=42.5, sell=179.69)
    store.save(session)
    rules_store.replace_for_session(session.id, [
        {"rule_type": "price_sell", "company_code": session.company_code, "company_name": "测试",
         "message": "达到卖出区间", "severity": "warn", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 179.69}},
    ])

    # 第 1 天：price_sell（warn）命中并持久化
    loaded = store.list()
    events = run_daily_monitor(loaded, _ExpensiveSource(), rules_store=rules_store)
    assert len(events) == 1 and events[0].rule_type == "price_sell"
    for s in loaded:
        if s.monitor_hits:
            store.save(s)

    # 第 2 天：新分析会话继承命中（cmd_analyze 行为）
    manager = SessionManager(store)
    fresh = manager.create_session("600519", "测试", monitor_hits=manager.prior_monitor_hits("600519"))
    assert len(fresh.monitor_hits) == 1 and fresh.monitor_hits[0]["severity"] == "warn"

    # M11 把 warn 命中回放为 prior_hit_review 回顾规则
    plan = build_monitor_plan(
        {"M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 42.5, "sell_price": 179.69})},
        prior_hits=fresh.monitor_hits,
    )
    reviews = [r for r in plan.rules if r.rule_type == "prior_hit_review"]
    assert len(reviews) == 1
    assert "price_sell" in reviews[0].trigger


# ---------- 9.x：message 字段 / severity 透传 / 质量加权评分 / runner 消费规则 ----------

def _m11_outputs(rules: list[dict]) -> dict:
    return {"monitor_rules": rules, "rule_count": len(rules)}


def test_monitor_rule_uses_message_field():
    """9.4：契约字段 message（替代旧 description），并带结构化 params。"""
    results = {
        "M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 42.5, "sell_price": 179.69}),
    }
    plan = build_monitor_plan(results)
    buy = next(r for r in plan.rules if r.rule_type == "price_buy")
    assert buy.message == "跌破买入区间，可分批建仓"
    assert not hasattr(buy, "description")
    assert buy.params.get("price") == 42.5  # runner 消费的结构化阈值


def test_monitor_plan_m2_severity_passthrough():
    """9.7：M2 critical 信号不再被拍平成 warn。"""
    results = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "signals": [
                {"code": "FRAUD", "severity": "critical", "metric": "roe", "message": "造假信号"},
                {"code": "LOW", "severity": "medium", "metric": "roe", "message": "一般信号"},
            ],
        }),
    }
    plan = build_monitor_plan(results)
    fundamental = [r for r in plan.rules if r.rule_type == "fundamental_watch"]
    sev_by_msg = {r.message: r.severity for r in fundamental}
    assert sev_by_msg["造假信号"] == "critical"
    assert sev_by_msg["一般信号"] == "warn"


def test_monitor_plan_quality_weighted_score():
    """9.8：评分按覆盖维度 + severity 权重，而非规则条数计数。"""
    results = {
        "M8_safety_margin": _mod("M8_safety_margin", {"buy_price": 10, "sell_price": 100}),
        "M7_market": _mod("M7_market", {"position": "合理"}),
        "M3_growth": _mod("M3_growth", {"handoff": {"prosperity_code": "down"}}),
        "M2_financial_quality": _mod("M2_financial_quality", {"signals": [
            {"code": "X", "severity": "high", "metric": "m", "message": "m"},
        ]}),
    }
    plan = build_monitor_plan(results)
    # 覆盖 price + prosperity + fundamental 三维 → 40 + 30 + warn 加成
    assert plan.score >= 70 and plan.score <= 100
    assert any("覆盖维度" in e for e in plan.evidence)


def test_monitor_plan_mos_expensive_adds_watch():
    """M8-6.4：mos_state=expensive → 补「估值偏高，暂停买入」watch 规则。"""
    results = {
        "M8_safety_margin": _mod("M8_safety_margin", {
            "buy_price": 42.5, "sell_price": 179.69,
            "handoff": {"mos_state": "expensive"},
        }),
    }
    plan = build_monitor_plan(results)
    mos = [r for r in plan.rules if r.rule_type == "mos_watch"]
    assert len(mos) == 1 and mos[0].severity == "warn"
    assert "暂停买入" in mos[0].message


def test_monitor_plan_sentiment_watch():
    """7.14：情绪热度过热 → sentiment_watch 规则。"""
    results = {
        "M7_market": _mod("M7_market", {"position": "合理", "sentiment_heat": 0.85}),
    }
    plan = build_monitor_plan(results)
    senti = [r for r in plan.rules if r.rule_type == "sentiment_watch"]
    assert len(senti) == 1 and senti[0].severity == "warn"
    assert "过热" in senti[0].message


class _RulesSource:
    """最新价 15.0。"""

    def daily_prices(self, code, start=None, end=None):
        return {"records": [{"trade_date": "20260804", "close": 15.0}]}


def _session_with_rules(rules: list[dict], code="600519") -> Session:
    s = Session(company_code=code, company_name="测试")
    s.status = SessionStatus.COMPLETED
    s.module_results["M11_monitor"] = _mod("M11_monitor", _m11_outputs(rules))
    return s


def _store_rules(session: Session, rules: list[dict]):
    """把规则写入 InMemoryRuleStore（模拟 monitor_rules 表），供 runner 读取。"""
    from value_agent.monitor.rules_store import InMemoryRuleStore

    rs = InMemoryRuleStore()
    rs.replace_for_session(session.id, rules)
    return rs


def test_daily_runner_consumes_monitor_rules():
    """9.1：runner 消费 M11 生成的 monitor_rules（price_buy 用 params.price 阈值）。"""
    session = _session_with_rules([])
    rules_store = _store_rules(session, [
        {"rule_type": "price_buy", "company_code": session.company_code, "company_name": "测试",
         "trigger": "现价 ≤ 42.5 元", "message": "跌破买入区间",
         "severity": "info", "source_module": "M8_safety_margin", "action": "action",
         "params": {"price": 42.5}},
    ])
    events = run_daily_monitor([session], _RulesSource(), rules_store=rules_store)
    assert len(events) == 1
    assert events[0].rule_type == "price_buy"
    assert "15.0" in events[0].message


def test_daily_runner_decision_watch_veto_event():
    """8.4：decision_watch（blocked_by_veto）进 runner 事件 → 「解除前不建仓」提醒。"""
    session = _session_with_rules([])
    rules_store = _store_rules(session, [
        {"rule_type": "decision_watch", "trigger": "M10 决策=avoid", "message": "决策回避：一票否决生效，解除前不建仓",
         "severity": "warn", "source_module": "M10_decision", "action": "watch",
         "params": {"blocked_by_veto": True}},
    ])
    events = run_daily_monitor([session], _RulesSource(), rules_store=rules_store)
    assert len(events) == 1
    assert events[0].rule_type == "decision_watch"
    assert "解除前不建仓" in events[0].message


def test_daily_runner_critical_watch_alert():
    """9.2：非价格 critical 级 watch → 独立告警事件（可执行路径）。"""
    session = _session_with_rules([])
    rules_store = _store_rules(session, [
        {"rule_type": "risk_watch", "trigger": "erosion_risk", "message": "护城河被侵蚀",
         "severity": "critical", "source_module": "M5_moat", "action": "watch"},
    ])
    events = run_daily_monitor([session], _RulesSource(), rules_store=rules_store)
    assert len(events) == 1
    assert events[0].rule_type == "risk_watch"
    assert events[0].severity == "critical"


def test_daily_runner_ignores_m8_without_table_rules():
    """规则只读 monitor_rules 表：会话 M8 buy/sell 不再回退（删表规则后即不触发）。"""
    from value_agent.monitor.rules_store import InMemoryRuleStore

    session = _session_with_m8(buy=42.5, sell=179.69)
    events = run_daily_monitor([session], _RulesSource(), rules_store=InMemoryRuleStore())
    assert events == []


def _mock_httpx_post(handler):
    """把 httpx.post 替换为 MockTransport 处理器，返回还原函数。"""
    import httpx

    transport = httpx.MockTransport(handler)
    orig_post = httpx.post
    httpx.post = lambda url, **kw: transport.handle_request(
        httpx.Request("POST", url, json=kw.get("json"), headers={"content-type": "application/json"})
    )
    return orig_post


def test_notify_webhooks_pushes_events():
    """9.10：notify_webhooks 推送飞书/企微（httpx MockTransport），失败兜底不抛错。"""
    import os

    import httpx

    seen: list[str] = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "feishu.example":
            return httpx.Response(200, json={"code": 0, "msg": "success"})
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    orig_post = _mock_httpx_post(handler)
    old_feishu, old_wechat = os.environ.get("FEISHU_WEBHOOK"), os.environ.get("WECHAT_WEBHOOK")
    os.environ["FEISHU_WEBHOOK"] = "https://feishu.example/hook"
    os.environ["WECHAT_WEBHOOK"] = "https://wechat.example/hook"
    try:
        ev = MonitorEvent("600519", "测试", "price_buy", "现价低", "info")
        sent = notify_webhooks([ev])  # 不应抛错
        assert set(sent) == {"飞书", "企业微信"}
        assert seen == ["feishu.example", "wechat.example"]
        assert notify_webhooks([]) == []  # 空事件不推送
    finally:
        httpx.post = orig_post
        if old_feishu is None:
            os.environ.pop("FEISHU_WEBHOOK", None)
        else:
            os.environ["FEISHU_WEBHOOK"] = old_feishu
        if old_wechat is None:
            os.environ.pop("WECHAT_WEBHOOK", None)
        else:
            os.environ["WECHAT_WEBHOOK"] = old_wechat


def test_notify_webhooks_reports_business_failure():
    """平台返回 code/errcode≠0（如关键词不匹配、签名错误）→ 渠道不计入成功，不抛错。"""
    import os

    import httpx

    def handler(request):
        return httpx.Response(200, json={"errcode": 93000, "errmsg": "invalid webhook url"})

    orig_post = _mock_httpx_post(handler)
    old_wechat = os.environ.get("WECHAT_WEBHOOK")
    os.environ["WECHAT_WEBHOOK"] = "https://wechat.example/hook"
    try:
        sent = notify_webhooks([MonitorEvent("600519", "测试", "price_buy", "现价低", "info")])
        assert sent == []  # 业务失败不计入成功渠道
    finally:
        httpx.post = orig_post
        if old_wechat is None:
            os.environ.pop("WECHAT_WEBHOOK", None)
        else:
            os.environ["WECHAT_WEBHOOK"] = old_wechat


def test_send_webhook_text_no_channels():
    """未配置任何 Webhook → 不推送、返回空列表。"""
    import os

    old_feishu, old_wechat = os.environ.get("FEISHU_WEBHOOK"), os.environ.get("WECHAT_WEBHOOK")
    os.environ.pop("FEISHU_WEBHOOK", None)
    os.environ.pop("WECHAT_WEBHOOK", None)
    try:
        from value_agent.monitor.runner import send_webhook_text

        assert send_webhook_text("测试") == []
    finally:
        if old_feishu is None:
            os.environ.pop("FEISHU_WEBHOOK", None)
        else:
            os.environ["FEISHU_WEBHOOK"] = old_feishu
        if old_wechat is None:
            os.environ.pop("WECHAT_WEBHOOK", None)
        else:
            os.environ["WECHAT_WEBHOOK"] = old_wechat


def test_daily_runner_quarterly_review_emits_watch_alerts():
    """9.3：财报季模式对 warn/critical 非价格 watch 补发复查提醒。"""
    session = _session_with_rules([])
    rules_store = _store_rules(session, [
        {"rule_type": "prosperity_watch", "trigger": "景气评级=下行", "message": "行业景气下行",
         "severity": "warn", "source_module": "M3_growth", "action": "watch"},
        {"rule_type": "price_buy", "trigger": "现价 ≤ 42.5 元", "message": "跌破买入区间",
         "severity": "info", "source_module": "M8_safety_margin", "action": "action",
         "params": {"price": 42.5}},
    ])
    events = run_daily_monitor([session], _RulesSource(), quarterly_review=True, rules_store=rules_store)
    # price_buy 触发 + prosperity_watch 财报季复查提醒
    assert any("财报季复查" in e.message for e in events)
    assert any(e.rule_type == "price_buy" for e in events)
    # 非财报季模式不产生复查提醒
    events2 = run_daily_monitor([session], _RulesSource(), rules_store=rules_store)
    assert not any("财报季复查" in e.message for e in events2)


# ---------- 9.11：monitor_rules 表（规则源物化 + runner 从表读） ----------

def test_rules_store_sqlite_roundtrip(tmp_path):
    """monitor_rules 表：写读回环；重物化保留用户自定义行（user_id 非空）。"""
    from value_agent.monitor.rules_store import SqliteRuleStore

    store = SqliteRuleStore(str(tmp_path / "sessions.db"))
    try:
        store.replace_for_session("s1", [
            {"rule_type": "price_buy", "company_code": "600519", "company_name": "贵州茅台",
             "message": "跌破买入区间", "severity": "info", "params": {"price": 42.5}},
        ])
        rows = store.list_by_session("s1")
        assert len(rows) == 1
        assert rows[0]["company_code"] == "600519"
        assert rows[0]["params"]["price"] == 42.5
        assert rows[0]["active"] is True
        # 用户自定义行（user_id 非空）在重物化时保留
        store.replace_for_session("s1", [
            {"rule_type": "price_buy", "company_code": "600519",
             "user_id": "u-1", "params": {"price": 30.0}},
        ])
        kept = store.replace_for_session("s1", [
            {"rule_type": "price_sell", "company_code": "600519", "params": {"price": 100.0}},
        ])
        assert kept == 1
        types = {r["rule_type"] for r in store.list_by_session("s1")}
        assert types == {"price_sell", "price_buy"}  # 系统规则替换 + 用户行保留
        user_rows = [r for r in store.list_by_session("s1") if r.get("user_id") == "u-1"]
        assert len(user_rows) == 1 and user_rows[0]["params"]["price"] == 30.0
        assert store.list_by_company("600519")
    finally:
        store.close()


def test_run_daily_monitor_reads_rules_from_store():
    """runner 以 monitor_rules 表为规则源：会话无 JSONB 规则时用表规则（用户可改阈值）。"""
    from value_agent.monitor.rules_store import InMemoryRuleStore

    session = _session_with_rules([])  # M11 存在但规则为空
    rules_store = InMemoryRuleStore()
    rules_store.replace_for_session(session.id, [
        {"rule_type": "price_buy", "company_code": "600519", "company_name": "测试",
         "message": "跌破用户买入线", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 50.0}},
    ])
    events = run_daily_monitor([session], _RulesSource(), rules_store=rules_store)
    assert len(events) == 1
    assert events[0].rule_type == "price_buy"
    assert "50.0" in events[0].message


def test_daily_runner_ignores_jsonb_when_table_empty():
    """规则只读 monitor_rules 表：表里没有该会话规则时，不回退会话 JSONB 的 M11 规则。"""
    from value_agent.monitor.rules_store import InMemoryRuleStore

    session = _session_with_rules([
        {"rule_type": "price_buy", "trigger": "现价 ≤ 42.5 元", "message": "跌破买入区间",
         "severity": "info", "source_module": "M8_safety_margin", "action": "action",
         "params": {"price": 42.5}},
    ])
    events = run_daily_monitor([session], _RulesSource(), rules_store=InMemoryRuleStore())
    assert events == []


def test_persist_materializes_rules_to_store(tmp_path):
    """SessionManager.persist 把 M11 规则物化进 monitor_rules 表，runner 从表读到。"""
    from value_agent.monitor.rules_store import SqliteRuleStore
    from value_agent.sessions import SessionManager
    from value_agent.sessions.store import SqliteStore

    db = str(tmp_path / "sessions.db")
    store = SqliteStore(db)
    rules_store = SqliteRuleStore(db)
    manager = SessionManager(store, rules_store=rules_store)
    try:
        session = manager.create_session("600519", "贵州茅台")
        session.status = SessionStatus.COMPLETED
        session.module_results["M11_monitor"] = _mod("M11_monitor", _m11_outputs([
            {"rule_type": "price_buy", "message": "跌破买入区间", "severity": "info",
             "source_module": "M8_safety_margin", "action": "action",
             "params": {"price": 42.5}},
        ]))
        manager.persist(session)

        rows = rules_store.list_by_session(session.id)
        assert len(rows) == 1
        assert rows[0]["company_code"] == "600519"
        assert rows[0]["params"]["price"] == 42.5
        # runner 从表读到该规则并触发
        loaded = store.list()
        events = run_daily_monitor(loaded, _RulesSource(), rules_store=rules_store)
        assert len(events) == 1 and events[0].rule_type == "price_buy"
    finally:
        rules_store.close()


# ---------- 9.12：每日任务 run_daily_job（数据更新 + 监控 + 推送，FC 定时同款） ----------

class _StubSource:
    """数据源替身：固定一条行情。"""

    name = "stub"

    def daily_prices(self, code, start=None, end=None):
        return {"records": [{"trade_date": "20260805", "close": 15.0}]}


def test_run_daily_job_reads_rules_and_pushes():
    """daily 只读模式：读表规则 → 实时拉价判断触发 → 不写行情/估值。"""
    from value_agent.daily import run_daily_job
    from value_agent.monitor.rules_store import InMemoryRuleStore
    from value_agent.sessions.store import InMemoryStore

    store = InMemoryStore()
    session = _session_with_rules([])  # JSONB 无规则，走表
    store.save(session)
    rules_store = InMemoryRuleStore()
    rules_store.replace_for_session(session.id, [
        {"rule_type": "price_buy", "company_code": "600519", "company_name": "测试",
         "message": "跌破买入区间", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 50.0}},
    ])

    summary = run_daily_job(
        source=_StubSource(), store=store, rules_store=rules_store,
    )
    assert summary["updated"] == {}             # 只读：不写行情/估值
    assert summary["session_count"] == 1
    assert summary["monitor_events"] == 1
    assert summary["events"][0]["rule_type"] == "price_buy"
    assert summary["events"][0]["message"].startswith("现价 15.0")
    assert summary["pushed_channels"] == []     # 未配置 webhook


def test_run_daily_job_degrades_on_data_source_failure():
    """数据源失败 → 不抛错，无最新价 → 规则跳过（只读模式无数据写入）。"""
    from value_agent.daily import run_daily_job
    from value_agent.monitor.rules_store import InMemoryRuleStore
    from value_agent.sessions.store import InMemoryStore

    class _FailSource:
        name = "fail"

        def daily_prices(self, code, start=None, end=None):
            raise ConnectionError("eastmoney blocked")

    store = InMemoryStore()
    store.save(_session_with_rules([
        {"rule_type": "price_buy", "message": "跌破买入区间", "severity": "info",
         "source_module": "M8_safety_margin", "action": "action", "params": {"price": 42.5}},
    ]))
    summary = run_daily_job(
        source=_FailSource(), store=store, rules_store=InMemoryRuleStore(),
    )
    assert summary["errors"] == []              # 价格获取失败被内部吞掉，不中断
    assert summary["monitor_events"] == 0       # 无最新价 → 规则跳过
    assert summary["updated"] == {}             # 只读：不写库


def test_daily_runner_dedupes_monitor_hits():
    """I-2 去重：同 (code, rule_type) 再次触发时覆盖而非追加。"""
    session = _session_with_m8(buy=42.5, sell=179.69)
    rules_store = _store_rules(session, [
        {"rule_type": "price_buy", "company_code": session.company_code, "company_name": "测试",
         "message": "跌破买入区间", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 42.5}},
    ])
    run_daily_monitor([session], _CheapSource(), rules_store=rules_store)
    run_daily_monitor([session], _CheapSource(), rules_store=rules_store)
    assert len(session.monitor_hits) == 1
    assert session.monitor_hits[0]["rule_type"] == "price_buy"
    assert "occurred_at" in session.monitor_hits[0]


def test_run_daily_job_persists_monitor_hits(tmp_path):
    """FC 定时任务（run_daily_job）命中后必须写回会话存储，前端监控中心可读。

    回归：此前 run_daily_job 只推送不落库，导致 monitor_hits 恒为空。
    """
    from value_agent.daily import run_daily_job
    from value_agent.monitor.rules_store import InMemoryRuleStore
    from value_agent.sessions.store import SqliteStore

    store = SqliteStore(str(tmp_path / "sessions.db"))
    store.save(_session_with_rules([]))
    rules_store = InMemoryRuleStore()
    session_id = store.list()[0].id
    rules_store.replace_for_session(session_id, [
        {"rule_type": "price_buy", "company_code": "600519", "company_name": "测试",
         "message": "跌破买入区间", "severity": "info", "action": "action",
         "source_module": "M8_safety_margin", "params": {"price": 50.0}},
    ])

    summary = run_daily_job(source=_StubSource(), store=store, rules_store=rules_store)
    assert summary["monitor_events"] == 1
    assert summary["updated"] == {}  # 不写行情/估值
    loaded = store.list()
    assert len(loaded[0].monitor_hits) == 1
    assert loaded[0].monitor_hits[0]["rule_type"] == "price_buy"

    # 第二次运行：同规则命中去重，不重复追加
    summary2 = run_daily_job(source=_StubSource(), store=store, rules_store=rules_store)
    assert summary2["monitor_events"] == 1
    loaded2 = store.list()
    assert len(loaded2[0].monitor_hits) == 1


def test_rules_store_replace_owner_dedupes(tmp_path):
    """防重复物化：同一归属用户重复 replace 不叠加；其他用户自定义行保留。"""
    from value_agent.monitor.rules_store import SqliteRuleStore

    store = SqliteRuleStore(str(tmp_path / "sessions.db"))
    try:
        base = {"company_code": "601318", "company_name": "中国平安",
                "severity": "info", "source_module": "M11_monitor", "action": "action"}
        # 第一次物化（归属 u-1）
        store.replace_for_session("s1", [
            {**base, "rule_type": "price_buy", "message": "第一档", "params": {"price": 56.76}, "user_id": "u-1"},
            {**base, "rule_type": "price_sell", "message": "卖出", "params": {"price": 95.1}, "user_id": "u-1"},
        ], owner_user_id="u-1")
        # 用户自定义行（其他用户 u-2）应保留
        store.replace_for_session("s1", [
            {**base, "rule_type": "price_buy", "message": "自定义", "params": {"price": 30.0}, "user_id": "u-2"},
        ])
        # 第二次物化（同一归属 u-1）：旧 u-1 行清理，不叠加
        store.replace_for_session("s1", [
            {**base, "rule_type": "price_buy", "message": "第一档", "params": {"price": 56.76}, "user_id": "u-1"},
            {**base, "rule_type": "price_sell", "message": "卖出", "params": {"price": 95.1}, "user_id": "u-1"},
        ], owner_user_id="u-1")

        rows = store.list_by_session("s1")
        assert len(rows) == 3  # u-1 两条（无重复） + u-2 一条保留
        types = {r["rule_type"] for r in rows}
        assert types == {"price_buy", "price_sell"}
        u2 = [r for r in rows if r.get("user_id") == "u-2"]
        assert len(u2) == 1 and u2[0]["params"]["price"] == 30.0
    finally:
        store.close()
