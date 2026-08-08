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


def test_sse_streams_llm_chunks(client: TestClient, monkeypatch) -> None:
    """运行期间 LLM 流式增量应以 llm_chunk 事件实时推送（打字机数据源）。"""
    from value_agent.agents import Agent, AgentContext, AgentSpec
    from value_agent.sessions import ModuleResult, ModuleStatus

    class StreamLLM:
        def stream_chat(self, system: str, user: str):
            yield "thinking", "先看生意类型"
            yield "content", '{"business_model": "测试"}'

    class TStreamAgent(Agent):
        spec = AgentSpec(id="T_stream", name="流式步骤")

        def run(self, ctx: AgentContext) -> ModuleResult:
            text = ctx.stream_llm("sys", "usr")
            assert text == '{"business_model": "测试"}'
            return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE)

    from value_agent.main import _engine, _registry

    monkeypatch.setitem(_registry._agents, "T_stream", TStreamAgent())
    monkeypatch.setattr(_engine, "_llm", StreamLLM())

    r = client.post(
        "/api/sessions",
        json={
            "company_code": "600519",
            "company_name": "贵州茅台",
            "workflow_steps": [{"id": "stream", "agent": "T_stream"}],
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    with client.stream("GET", f"/api/sessions/{sid}/events") as resp:
        assert resp.status_code == 200
        events = list(_events(resp))

    chunks = [e for e in events if e["type"] == "llm_chunk"]
    assert chunks, "应推送 llm_chunk 增量事件"
    content = "".join(str(e["chunk"]) for e in chunks if e["kind"] == "content")
    thinking = "".join(str(e["chunk"]) for e in chunks if e["kind"] == "thinking")
    assert content == '{"business_model": "测试"}'
    assert thinking == "先看生意类型"
    assert all(e["step"] == "stream" for e in chunks)
    assert all(e["agent"] == "T_stream" for e in chunks)
    # 顺序：thinking 先于 content
    assert [e["kind"] for e in chunks] == ["thinking", "content"]
    # 事件顺序：步骤 running → LLM 增量 → 步骤 done
    types = [e["type"] for e in events]
    assert types.index("step") < types.index("llm_chunk") < types.index("done")


def test_chat_stream_streams_reply_and_persists(client: TestClient, monkeypatch) -> None:
    """追问对话流式端点：实时推送 chat_chunk（thinking/content），结束落库 assistant 消息。"""
    from value_agent.main import _engine

    class StreamChatLLM:
        def stream_chat(self, system: str, user: str):
            yield "thinking", "让我想想"
            yield "content", "茅台"
            yield "content", "值得关注"

    monkeypatch.setattr(_engine, "_llm", StreamChatLLM())

    r = client.post(
        "/api/sessions",
        json={"company_code": "600519", "company_name": "贵州茅台", "workflow_id": "quick"},
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/chat/stream",
        json={"content": "怎么看茅台？"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = list(_events(resp))

    chunks = [e for e in events if e["type"] == "chat_chunk"]
    assert [e["kind"] for e in chunks] == ["thinking", "content", "content"]
    assert "".join(str(e["chunk"]) for e in chunks if e["kind"] == "content") == "茅台值得关注"

    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["content"] == "茅台值得关注"

    # user + assistant 消息均已落库
    sess = client.get(f"/api/sessions/{sid}").json()
    msgs = sess.get("messages", [])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[-1]["content"] == "茅台值得关注"


def test_chat_stream_falls_back_without_llm(client: TestClient) -> None:
    """未配置 LLM 时流式对话返回兜底文案并正常结束。"""
    r = client.post(
        "/api/sessions",
        json={"company_code": "600519", "workflow_id": "quick"},
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/chat/stream",
        json={"content": "hi"},
    ) as resp:
        assert resp.status_code == 200
        events = list(_events(resp))

    done = [e for e in events if e["type"] == "done"]
    assert done and "未配置可用的 LLM" in done[0]["content"]
    assert events[-1]["type"] == "done"


def test_create_session_sets_snapshot_and_validates_code(client: TestClient) -> None:
    """API 创建会话：绑定 PIT 快照标识；非法代码返回 400；响应不含 api_key。"""
    # 合法代码：响应带 data_snapshot_id，且 llm_config 无密钥（即便注入了 llm_config）
    r = client.post(
        "/api/sessions",
        json={
            "company_code": "600519",
            "company_name": "贵州茅台",
            "llm_config": {"provider": "deepseek", "base_url": "https://x/v1",
                           "model": "deepseek-chat", "api_key": "sk-secret"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["data_snapshot_id"] and body["data_snapshot_id"].startswith("snap_600519_")
    assert "api_key" not in (body.get("llm_config") or {})

    # 非法代码（7 位）：400 + 明确错误，不再产生垃圾会话
    bad = client.post(
        "/api/sessions",
        json={"company_code": "6002579", "company_name": "中京电子"},
    )
    assert bad.status_code == 400
    assert "6002579" in bad.json()["detail"]
