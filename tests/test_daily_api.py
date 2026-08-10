"""FC 定时触发器事件入口（POST /）测试。"""
from __future__ import annotations

import hashlib
import json
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


# ---------- 用户通知渠道 API（/api/webhooks，JWT 鉴权） ----------

def _b64url(b: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _es256_token(sk, payload: dict, kid: str = "test-kid"):
    import ecdsa

    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = sk.sign(f"{h}.{p}".encode(), hashfunc=hashlib.sha256, sigencode=ecdsa.util.sigencode_string)
    return f"{h}.{p}.{_b64url(sig)}"


def test_webhook_api_crud_and_test(monkeypatch):
    import time

    import ecdsa
    from fastapi.testclient import TestClient

    import value_agent.main as m
    from value_agent.core import auth
    from value_agent.monitor.user_webhooks import InMemoryUserWebhookStore

    monkeypatch.setenv("SESSION_STORE", "memory")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    sk = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p)
    vk = sk.get_verifying_key()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: {"keys": [{
        "kty": "EC", "crv": "P-256", "kid": "test-kid",
        "x": _b64url(vk.pubkey.point.x().to_bytes(32, "big")),
        "y": _b64url(vk.pubkey.point.y().to_bytes(32, "big")),
        "alg": "ES256", "use": "sig",
    }]})
    token = _es256_token(sk, {
        "sub": "user-abc", "aud": "authenticated",
        "exp": int(time.time()) + 3600, "iss": "https://testref.supabase.co/auth/v1",
    })
    monkeypatch.setattr(m, "_webhook_store", InMemoryUserWebhookStore())
    monkeypatch.setattr(m, "send_webhook_to_channels", lambda channels, text: list(channels.keys()))

    client = TestClient(m.app)
    auth_h = {"Authorization": f"Bearer {token}"}

    # 未登录 → 401
    assert client.get("/api/webhooks").status_code == 401
    # 保存飞书
    r = client.put("/api/webhooks", json={"channel": "feishu", "webhook_url": "https://open.feishu.cn/hook/x"}, headers=auth_h)
    assert r.status_code == 200 and r.json()["webhooks"] == {"feishu": "https://open.feishu.cn/hook/x"}
    # 非法渠道 / 非 https
    assert client.put("/api/webhooks", json={"channel": "slack", "webhook_url": "https://x"}, headers=auth_h).status_code == 400
    assert client.put("/api/webhooks", json={"channel": "wechat", "webhook_url": "http://x"}, headers=auth_h).status_code == 400
    # 测试已保存渠道
    r = client.post("/api/webhooks/test", json={}, headers=auth_h)
    assert r.status_code == 200 and r.json()["pushed"] == ["feishu"]
    # 空 url 删除
    r = client.put("/api/webhooks", json={"channel": "feishu", "webhook_url": ""}, headers=auth_h)
    assert r.status_code == 200 and r.json()["webhooks"] == {}


def test_fc_invoke_entry_runs_daily(monkeypatch):
    """FC 定时触发器实际调用路径 POST /invoke：与根路径 / 同逻辑。

    回归：此前 /invoke 未实现 → 定时触发器请求被 404 吃掉，daily 从不执行。
    """
    monkeypatch.setenv("DAILY_TOKEN", "secret123")
    calls: list[str] = []

    def fake_daily(**kw):
        calls.append("hit")
        return _fake_daily(**kw)

    monkeypatch.setattr(m, "run_daily_job", fake_daily)
    client = TestClient(m.app)

    # 未知事件 → 404
    assert client.post("/invoke", json={"action": "unknown"}).status_code == 404
    # token 不匹配 → 401
    assert client.post("/invoke", json={"action": "daily", "token": "wrong"}).status_code == 401
    # 正确 token（JSON body）→ 200 并执行
    r = client.post("/invoke", json={"action": "daily", "token": "secret123"})
    assert r.status_code == 200
    assert r.json()["monitor_events"] == 0
    assert calls == ["hit"]
    # 未设 DAILY_TOKEN 时：非 JSON content-type 的原始 body 也能解析并放行
    monkeypatch.delenv("DAILY_TOKEN", raising=False)
    calls.clear()
    r = client.post("/invoke", content='{"action": "daily"}', headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200
    assert calls == ["hit"]


def test_fc_invoke_entry_parses_payload_wrapped_event(monkeypatch):
    """FC 定时触发器事件：触发消息作为 event.payload（字符串）传入，action/token 在 payload 里。

    回归：此前只解析顶层 action，FC 事件结构（{"payload": "{\\"action\\":...}"}）拿不到 action → 404。
    """
    monkeypatch.setenv("DAILY_TOKEN", "secret123")
    calls: list[str] = []

    def fake_daily(**kw):
        calls.append("hit")
        return _fake_daily(**kw)

    monkeypatch.setattr(m, "run_daily_job", fake_daily)
    client = TestClient(m.app)

    # FC 定时触发器事件：payload 是触发消息的 JSON 字符串
    body = json.dumps({
        "triggerTime": "2026-08-10T15:00:00Z",
        "triggerName": "daily-trigger",
        "payload": '{"action": "daily", "token": "secret123"}',
    })
    r = client.post("/invoke", content=body, headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200
    assert calls == ["hit"]

    # token 不匹配（payload 里）→ 401
    calls.clear()
    body = json.dumps({
        "triggerTime": "2026-08-10T15:00:00Z",
        "triggerName": "daily-trigger",
        "payload": '{"action": "daily", "token": "wrong"}',
    })
    assert client.post("/invoke", content=body, headers={"Content-Type": "application/octet-stream"}).status_code == 401

    # payload 不是 JSON（如纯文本触发消息）→ action 空 → 404
    calls.clear()
    body = json.dumps({"triggerTime": "2026-08-10T15:00:00Z", "triggerName": "t", "payload": "hello"})
    assert client.post("/invoke", content=body, headers={"Content-Type": "application/octet-stream"}).status_code == 404
    assert calls == []
