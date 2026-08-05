"""FastAPI 应用入口（部署到 Render，见 docs/07-deployment-guide.md）。

- GET  /health                        Render 健康检查
- 会话 API：创建 / 查询 / 运行 / 追问 / 重算 / 备忘录 / 归档
- SSE 进度：GET /api/sessions/{id}/events
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from value_agent.agents import AgentRegistry
from value_agent.core.config import _load_dotenv
from value_agent.core.llm import get_llm
from value_agent.data.manager import DataManager
from value_agent.agents.builtin import register_builtin_agents
from value_agent.report.memo import build_memo
from value_agent.sessions import (
    ModuleName,
    Session,
    SessionManager,
    SessionStatus,
    create_session_store,
)
from value_agent.workflow import (
    Workflow,
    WorkflowEngine,
    WorkflowStep,
    WorkflowValidationError,
    default_workflow,
    load_workflow_from_yaml,
)

logger = logging.getLogger(__name__)

# ---- 全局单例（SESSION_STORE=sqlite|supabase|memory，见 store.create_session_store） ----
_load_dotenv()  # 确保 DATABASE_URL / SESSION_STORE 等环境变量已从 .env 加载
_store = create_session_store()
_manager = SessionManager(_store)
_registry = register_builtin_agents(AgentRegistry())
_engine = WorkflowEngine(_registry, _manager, data=DataManager(), llm=get_llm())

# ---- 应用 ----
app = FastAPI(title="Value Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Pydantic 请求模型 ----
class CreateSessionRequest(BaseModel):
    company_code: str
    company_name: str = ""
    workflow_id: str = "default"
    workflow_steps: list[dict] | None = Field(
        default=None, description="内联自定义工作流步骤（[{id, agent, deps}]），优先于 workflow_id"
    )


class MessageRequest(BaseModel):
    content: str
    action: str | None = None


class RerunRequest(BaseModel):
    modules: list[str] = Field(description="要重算的模块（如 M3_growth），自动级联下游")
    assumptions: dict | None = None


# ---- 基础 ----
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/agents")
def list_agents() -> dict:
    return {"agents": [spec.__dict__ for spec in _registry.specs()]}


@app.get("/api/workflows")
def list_workflows() -> dict:
    flows = [{"id": "default", "name": "标准价值投资分析"}]
    for name in ("quick",):
        try:
            wf = load_workflow_from_yaml(f"config/workflows/{name}.yaml")
            flows.append({"id": wf.id, "name": wf.name, "steps": wf.step_ids()})
        except Exception:  # noqa: BLE001
            continue
    return {"workflows": flows}


# ---- 会话 ----
def _load_session(session_id: str):
    try:
        return _manager.load(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在") from None


def _load_workflow(session: Session) -> Workflow:
    """按会话加载工作流：优先内联 workflow_steps（自定义工作流），其次按 workflow_id。"""
    if session.workflow_steps:
        steps = [
            WorkflowStep(
                id=str(st["id"]),
                agent_id=str(st["agent"]),
                deps=[str(d) for d in st.get("deps", [])],
            )
            for st in session.workflow_steps
        ]
        return Workflow(
            id=session.workflow_id or "custom",
            name="自定义工作流",
            description="用户拖拽编排的自定义分析流",
            steps=steps,
        )
    if session.workflow_id == "default":
        return default_workflow()
    try:
        return load_workflow_from_yaml(f"config/workflows/{session.workflow_id}.yaml")
    except (FileNotFoundError, ImportError):
        raise HTTPException(status_code=400, detail=f"工作流不存在: {session.workflow_id}") from None


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest) -> dict:
    session = _manager.create_session(
        req.company_code,
        company_name=req.company_name,
        workflow_id=req.workflow_id,
        workflow_steps=req.workflow_steps,
    )
    return session.to_dict()


@app.get("/api/sessions")
def list_sessions(status: str | None = None) -> dict:
    sessions = _store.list(status=status)
    return {"sessions": [s.to_dict() for s in sessions]}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    return _load_session(session_id).to_dict()


@app.post("/api/sessions/{session_id}/run")
def run_session(session_id: str) -> dict:
    session = _load_session(session_id)
    flow = _load_workflow(session)
    _engine.run(session, flow)
    return session.to_dict()


@app.post("/api/sessions/{session_id}/messages")
def post_message(session_id: str, req: MessageRequest) -> dict:
    session = _load_session(session_id)
    _manager.add_message(session, "user", req.content, action=req.action)
    return session.to_dict()


@app.post("/api/sessions/{session_id}/rerun")
def rerun_session(session_id: str, req: RerunRequest) -> dict:
    session = _load_session(session_id)
    try:
        modules = [ModuleName(m) for m in req.modules]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"未知模块: {req.modules}") from exc
    ordered = _manager.rerun(session, modules, assumptions=req.assumptions)
    return {"rerun_order": [m.value for m in ordered], "session": session.to_dict()}


@app.post("/api/sessions/{session_id}/memo")
def save_memo(session_id: str) -> dict:
    """生成并保存一份备忘录版本（版本化：每次调用 +1 版）。"""
    session = _load_session(session_id)
    memo = build_memo(session)
    _manager.save_memo_version(session, memo)
    return {"session_id": session_id, "version": len(session.memo_versions), "memo": memo}


@app.post("/api/sessions/{session_id}/resume")
def resume_session(session_id: str) -> dict:
    """恢复 failed / awaiting_input 会话（断点续跑）。"""
    session = _load_session(session_id)
    if session.status not in (SessionStatus.FAILED, SessionStatus.AWAITING_INPUT):
        raise HTTPException(
            status_code=400,
            detail=f"只有 failed/awaiting_input 可恢复，当前 {session.status.value}",
        )
    _manager.resume(session)
    return session.to_dict()


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """删除会话。"""
    _load_session(session_id)  # 不存在则 404
    _store.delete(session_id)
    return {"deleted": session_id}


@app.get("/api/sessions/{session_id}/memo")
def get_memo(session_id: str) -> dict:
    session = _load_session(session_id)
    if session.memo_versions:
        memo = session.memo_versions[-1]
    else:
        memo = build_memo(session)
    return {"session_id": session_id, "memo": memo}


@app.post("/api/sessions/{session_id}/archive")
def archive_session(session_id: str) -> dict:
    session = _load_session(session_id)
    _manager.archive(session)
    return session.to_dict()


@app.get("/api/sessions/{session_id}/events")
def stream_events(session_id: str):
    """SSE：运行工作流并推送每个模块的完成事件（浏览器直连）。"""
    session = _load_session(session_id)
    flow = _load_workflow(session)
    q: "queue.Queue[dict | None]" = queue.Queue()

    def on_step(sess, step, result) -> None:  # type: ignore[no-untyped-def]
        q.put(
            {
                "type": "step",
                "step": step.id,
                "agent": step.agent_id,
                "status": result.status.value,
            }
        )

    def worker() -> None:
        try:
            _engine.run(session, flow, on_step=on_step)
            q.put({"type": "done", "status": session.status.value})
        except WorkflowValidationError as exc:
            q.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("工作流执行失败")
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
