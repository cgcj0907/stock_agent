"""SSE 实时进度长链接测试：事件顺序 started → step(running/终态) → done。"""

from __future__ import annotations

import json
import os
import threading
import time

# 必须在导入 value_agent.main 前设置：用内存会话库，避免测试污染 data/sessions.db
os.environ["SESSION_STORE"] = "memory"

import pytest
from fastapi.testclient import TestClient

from tests.conftest import StubData
from value_agent.main import _engine, app


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # 数据源用桩、LLM 置空，保证离线、可复现、快速
    monkeypatch.setattr(_engine, "_data", StubData())
    monkeypatch.setattr(_engine, "_llm", None)
    return TestClient(app)


def _events(resp):
    for line in resp.iter_lines():
        if line.startswith("data:"):
            yield json.loads(line[5:].strip())


def test_sse_streams_real_time_step_progress(client: TestClient) -> None:
    r = client.post(
        "/api/sessions",
        json={
            "company_code": "600519",
            "company_name": "贵州茅台",
            "workflow_id": "default",
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    with client.stream("GET", f"/api/sessions/{sid}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("cache-control") == "no-cache"
        events = list(_events(resp))

    types = [e["type"] for e in events]
    assert types[0] == "started", "连接建立应先推送 started 事件"
    assert types[-1] in ("done", "error"), "应以 done/error 收尾"

    steps = [e for e in events if e["type"] == "step"]
    assert steps, "应至少推送一个步骤事件"
    # 每个步骤：先 running（实时开始），再终态 done/failed/skipped
    by_step: dict[str, list[str]] = {}
    for e in steps:
        by_step.setdefault(str(e["step"]), []).append(str(e["status"]))
    for step_id, statuses in by_step.items():
        assert statuses[0] == "running", f"{step_id} 应先推送 running，实际: {statuses}"
        assert statuses[-1] != "running", f"{step_id} 终态不应是 running"


def test_sse_heartbeat_keeps_long_connection_alive(client: TestClient, monkeypatch) -> None:
    """长步骤执行期间，SSE 定期发送 `: keep-alive` 注释防止连接被切断。"""
    import time

    from value_agent.agents import Agent, AgentContext, AgentSpec
    from value_agent.sessions import ModuleResult, ModuleStatus

    class SlowAgent(Agent):
        spec = AgentSpec(id="T_slow", name="慢速步骤")

        def run(self, ctx: AgentContext) -> ModuleResult:
            time.sleep(0.4)  # 模拟长 LLM/数据步骤
            return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE)

    # 把慢速 agent 临时注册进全局注册表（monkeypatch 自动还原）
    from value_agent.main import _registry

    monkeypatch.setitem(_registry._agents, "T_slow", SlowAgent())

    r = client.post(
        "/api/sessions",
        json={
            "company_code": "600519",
            "company_name": "贵州茅台",
            "workflow_steps": [{"id": "slow", "agent": "T_slow"}],
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    monkeypatch.setenv("SSE_HEARTBEAT_SECONDS", "0.05")
    with client.stream("GET", f"/api/sessions/{sid}/events") as resp:
        assert resp.status_code == 200
        raw = list(resp.iter_lines())

    assert any(line == ": keep-alive" for line in raw), "长步骤期间应发送心跳注释"
    assert any(line.startswith("data:") for line in raw), "心跳之外还应推送数据事件"


def test_watch_sse_observes_existing_run_without_restart(client: TestClient, monkeypatch) -> None:
    """watch 端点只观察已有运行中的会话，不主动触发一次新的执行。"""
    from value_agent.agents import Agent, AgentContext, AgentSpec
    from value_agent.sessions import ModuleResult, ModuleStatus

    class SlowWatchAgent(Agent):
        spec = AgentSpec(id="T_watch", name="观察步骤")

        def run(self, ctx: AgentContext) -> ModuleResult:
            time.sleep(0.2)
            return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE)

    from value_agent.main import _registry

    monkeypatch.setitem(_registry._agents, "T_watch", SlowWatchAgent())

    r = client.post(
        "/api/sessions",
        json={
            "company_code": "600519",
            "company_name": "贵州茅台",
            "workflow_steps": [{"id": "watch", "agent": "T_watch"}],
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    run_events: list[dict] = []

    def _run() -> None:
        with TestClient(app).stream("GET", f"/api/sessions/{sid}/events") as resp:
            run_events.extend(list(_events(resp)))

    runner = threading.Thread(target=_run, daemon=True)
    runner.start()
    time.sleep(0.05)

    with TestClient(app).stream("GET", f"/api/sessions/{sid}/watch") as resp:
        assert resp.status_code == 200
        watch_events = list(_events(resp))

    runner.join(timeout=2)
    assert not runner.is_alive()
    assert run_events, "基准执行流应实际跑完"
    assert watch_events, "watch 应观察到已有执行中的事件"
    assert watch_events[0]["type"] == "started"
    assert any(e["type"] == "step" and e["status"] == "running" for e in watch_events)
    assert watch_events[-1]["type"] == "done"


def test_watch_sse_ends_when_created_session_never_starts(client: TestClient, monkeypatch) -> None:
    """created 会话从未开始执行时，watch 观察超时后主动结束，不悬挂、不触发执行。"""
    r = client.post(
        "/api/sessions",
        json={
            "company_code": "600519",
            "company_name": "贵州茅台",
            "workflow_id": "quick",
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    monkeypatch.setenv("SSE_WATCH_IDLE_SECONDS", "0.2")
    monkeypatch.setenv("SSE_WATCH_POLL_SECONDS", "0.05")
    with client.stream("GET", f"/api/sessions/{sid}/watch") as resp:
        assert resp.status_code == 200
        events = list(_events(resp))

    assert events[0]["type"] == "started"
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "created"
    # 未被触发执行：没有 step 事件，状态仍停留在 created
    assert all(e["type"] != "step" for e in events)
