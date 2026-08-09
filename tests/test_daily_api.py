"""FC 定时触发器事件入口（POST /）测试。"""
from __future__ import annotations

import os

# 必须在导入 value_agent.main 前设置：内存会话库 + 无 DB，避免污染/联网
os.environ["SESSION_STORE"] = "memory"
os.environ["DATABASE_URL"] = ""

from fastapi.testclient import TestClient

import value_agent.main as m


def _fake_daily(**kw):
    return {
        "updated": {"daily_price": 0, "valuation_history": 0, "skipped": 0},
        "session_count": 0,
        "monitor_events": 0,
        "events": [],
        "pushed_channels": [],
        "errors": [],
    }


def test_fc_timer_event_runs_daily(monkeypatch):
    monkeypatch.setenv("DAILY_TOKEN", "secret123")
    calls: list[str] = []

    def fake_daily(**kw):
        calls.append("hit")
        return _fake_daily(**kw)

    monkeypatch.setattr(m, "run_daily_job", fake_daily)
    client = TestClient(m.app)

    # 未知事件 → 404
    assert client.post("/", json={"action": "unknown"}).status_code == 404
    # token 不匹配 → 401
    assert client.post("/", json={"action": "daily", "token": "wrong"}).status_code == 401
    # 正确 token → 200 并执行
    r = client.post("/", json={"action": "daily", "token": "secret123"})
    assert r.status_code == 200
    assert r.json()["monitor_events"] == 0
    assert calls == ["hit"]
    # 未设 DAILY_TOKEN 时：不带 token 也放行（个人项目开关）
    monkeypatch.delenv("DAILY_TOKEN", raising=False)
    calls.clear()
    assert client.post("/", json={"action": "daily"}).status_code == 200
    assert calls == ["hit"]
