"""用户通知渠道：user_webhooks 存储 + 按用户推送 + 规则归属物化。"""
from __future__ import annotations

import json
import os

from value_agent.monitor.runner import MonitorEvent, notify_webhooks
from value_agent.monitor.user_webhooks import (
    InMemoryUserWebhookStore,
    SqliteUserWebhookStore,
)


def test_user_webhook_store_sqlite_roundtrip(tmp_path):
    store = SqliteUserWebhookStore(str(tmp_path / "sessions.db"))
    try:
        assert store.get_webhooks("u-1") == {}
        store.set_webhook("u-1", "feishu", "https://feishu.example/hook")
        store.set_webhook("u-1", "wechat", "https://wechat.example/hook")
        store.set_webhook("u-2", "feishu", "https://other.example/hook")
        assert store.get_webhooks("u-1") == {
            "feishu": "https://feishu.example/hook",
            "wechat": "https://wechat.example/hook",
        }
        # 覆盖更新
        store.set_webhook("u-1", "feishu", "https://feishu.example/new")
        assert store.get_webhooks("u-1")["feishu"] == "https://feishu.example/new"
        # 删除
        store.delete_webhook("u-1", "feishu")
        assert "feishu" not in store.get_webhooks("u-1")
        assert store.get_webhooks("u-2")["feishu"] == "https://other.example/hook"
    finally:
        store.close()


def _mock_httpx(handler):
    import httpx

    transport = httpx.MockTransport(handler)
    orig = httpx.post
    httpx.post = lambda url, **kw: transport.handle_request(
        httpx.Request("POST", url, json=kw.get("json"), headers={"content-type": "application/json"})
    )
    return orig


def test_notify_webhooks_per_user():
    """按用户推送：归属用户推该用户渠道；未配置用户跳过；全局事件走环境变量。"""
    import httpx

    seen: list[tuple[str, str]] = []

    def handler(request):
        seen.append((request.url.host, json.loads(request.content or b"{}").get("msgtype", "text")))
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    orig = _mock_httpx(handler)
    old_feishu = os.environ.get("FEISHU_WEBHOOK")
    try:
        store = InMemoryUserWebhookStore()
        store.set_webhook("u-1", "feishu", "https://feishu.example/hook")
        store.set_webhook("u-1", "wechat", "https://wechat.example/hook")
        events = [
            MonitorEvent("600519", "茅台", "price_buy", "跌破买入区间", "info", user_id="u-1"),
            MonitorEvent("600519", "茅台", "price_sell", "达到卖出区间", "warn", user_id="u-2"),  # 未配置 → 跳过
            MonitorEvent("000333", "美的", "risk_watch", "风险提示", "critical"),  # 全局 → 环境变量
        ]
        os.environ["FEISHU_WEBHOOK"] = "https://global.example/hook"
        sent = notify_webhooks(events, webhook_store=store)
        # u-1 飞书+企微 成功；全局环境变量成功；u-2 跳过
        assert "飞书" in sent and "企业微信" in sent
        hosts = {h for h, _ in seen}
        assert hosts == {"feishu.example", "wechat.example", "global.example"}
    finally:
        httpx.post = orig
        if old_feishu is None:
            os.environ.pop("FEISHU_WEBHOOK", None)
        else:
            os.environ["FEISHU_WEBHOOK"] = old_feishu


def test_persist_materializes_rules_with_user_id(tmp_path):
    """会话带 user_id → M11 规则物化时带上归属，供按用户推送。"""
    from value_agent.monitor.rules_store import SqliteRuleStore
    from value_agent.sessions import SessionManager
    from value_agent.sessions.models import ModuleResult, ModuleStatus, SessionStatus
    from value_agent.sessions.store import SqliteStore

    db = str(tmp_path / "sessions.db")
    store = SqliteStore(db)
    rules_store = SqliteRuleStore(db)
    manager = SessionManager(store, rules_store=rules_store)
    try:
        session = manager.create_session("600519", "贵州茅台", user_id="u-1")
        session.status = SessionStatus.COMPLETED
        session.module_results["M11_monitor"] = ModuleResult(
            module="M11_monitor", status=ModuleStatus.DONE, score=50.0,
            outputs={"monitor_rules": [
                {"rule_type": "price_buy", "message": "跌破买入区间", "severity": "info",
                 "source_module": "M8_safety_margin", "action": "action", "params": {"price": 42.5}},
            ]},
        )
        manager.persist(session)
        rows = rules_store.list_by_session(session.id)
        assert len(rows) == 1
        assert rows[0]["user_id"] == "u-1"
        assert session.user_id == "u-1"
    finally:
        rules_store.close()
