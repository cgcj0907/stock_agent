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
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from value_agent.agents import AgentRegistry
from value_agent.agents.builtin import register_builtin_agents
from value_agent.core.auth import enabled as verify_supabase_jwt_enabled
from value_agent.core.auth import verify_supabase_jwt
from value_agent.core.config import _load_dotenv
from value_agent.core.llm import get_llm, llm_from_config
from value_agent.daily import run_daily_job
from value_agent.data.manager import DataManager
from value_agent.monitor.rules_store import create_rule_store
from value_agent.monitor.runner import send_webhook_to_channels
from value_agent.monitor.user_webhooks import create_user_webhook_store
from value_agent.profile.models import strip_pii
from value_agent.report.memo import build_memo
from value_agent.sessions import (
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
_rules_store = create_rule_store()
_webhook_store = create_user_webhook_store()
_manager = SessionManager(_store, rules_store=_rules_store)
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

# 全局鉴权：所有 /api/* 只接受前端登录用户（Supabase JWT），
# 例外：/health（探活）、/api/daily（FC 定时触发器，用 DAILY_TOKEN）
@app.middleware("http")
async def _require_frontend_auth(request: Request, call_next):
    # 生产（配置了 SUPABASE_URL）才强制鉴权；本地开发未配置时放行
    if (
        verify_supabase_jwt_enabled()
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/daily"
    ):
        auth = request.headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return JSONResponse(
                status_code=401,
                content={"detail": "未登录：需要 Authorization: Bearer <supabase token>"},
            )
        try:
            request.state.user = verify_supabase_jwt(token.strip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("鉴权失败：%s", exc)
            return JSONResponse(status_code=401, content={"detail": f"登录态无效：{exc}"})
    return await call_next(request)


# ---- Pydantic 请求模型 ----
class CreateSessionRequest(BaseModel):
    company_code: str
    company_name: str = ""
    workflow_id: str = "default"
    workflow_steps: list[dict] | None = Field(
        default=None, description="内联自定义工作流步骤（[{id, agent, deps}]），优先于 workflow_id"
    )
    llm_config: dict | None = Field(
        default=None, description="按会话注入的 LLM 配置（{provider, base_url, model, api_key}）"
    )
    investor_profile: dict | None = Field(
        default=None, description="投资者画像快照（M0 消费；仅当工作流含 M0 时由前端附加，已剔除 PII）"
    )


class MessageRequest(BaseModel):
    content: str
    action: str | None = None


class RerunRequest(BaseModel):
    modules: list[str] = Field(description="要重算的模块（如 M3_growth），自动级联下游")
    assumptions: dict | None = None


class ChatRequest(BaseModel):
    content: str
    llm_config: dict | None = Field(
        default=None, description="本次对话使用的 LLM 配置（{provider, base_url, model, api_key}）"
    )


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
        except Exception as exc:  # noqa: BLE001
            logger.warning("工作流 %s 加载失败：%s", name, type(exc).__name__)
            continue
    return {"workflows": flows}


# ---- 会话 ----
def _mask_key(key: str) -> str:
    """API 返回时对 llm_config.api_key 脱敏（数据库 payload 仍存完整 Key）。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:3]}••••••{key[-4:]}"


def _public_session(session: Session) -> dict:
    """API 响应用：会话脱敏（llm_config 不暴露完整 api_key）。"""
    d = session.to_dict()
    cfg = d.get("llm_config")
    if cfg and cfg.get("api_key"):
        d["llm_config"] = {**cfg, "api_key": _mask_key(cfg["api_key"])}
    return d


def _load_session(session_id: str):
    try:
        return _manager.load(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在") from None


def _step_status_events(
    session: Session,
    workflow: Workflow,
    previous: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[dict]]:
    """把会话 module_results 映射成前端可消费的 step 事件。"""
    current: dict[str, str] = {}
    events: list[dict] = []
    for step in workflow.steps:
        result = session.module_results.get(step.agent_id)
        status = result.status.value if result is not None else "pending"
        current[step.agent_id] = status
        if previous is None:
            if status == "pending":
                continue
        elif previous.get(step.agent_id) == status:
            continue
        events.append(
            {
                "type": "step",
                "step": step.id,
                "agent": step.agent_id,
                "status": status,
            }
        )
    return current, events


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
def create_session(req: CreateSessionRequest, request: Request) -> dict:
    # 从已验签的 JWT 绑定归属用户（前端登录用户）；鉴权关闭/CLI 时为空 → 全局
    user_id = getattr(request.state, "user", None) or {}
    try:
        session = _manager.create_session(
            req.company_code,
            company_name=req.company_name,
            user_id=user_id.get("sub"),
            workflow_id=req.workflow_id,
            workflow_steps=req.workflow_steps,
            llm_config=req.llm_config,
            investor_profile=strip_pii(req.investor_profile),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    # 与 CLI 对齐：继承同标的最近已完成会话的监控命中（I-2）+ 绑定 PIT 快照标识
    session.monitor_hits = _manager.prior_monitor_hits(session.company_code)
    session.data_snapshot_id = f"snap_{session.company_code}_{session.created_at:%Y%m%d%H%M%S}"
    _manager.persist(session)
    return _public_session(session)


@app.get("/api/sessions")
def list_sessions(status: str | None = None) -> dict:
    sessions = _store.list(status=status)
    return {"sessions": [_public_session(s) for s in sessions]}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    return _public_session(_load_session(session_id))


@app.post("/api/sessions/{session_id}/run")
def run_session(session_id: str) -> dict:
    session = _load_session(session_id)
    flow = _load_workflow(session)
    _engine.run(session, flow)
    return _public_session(session)


@app.post("/api/sessions/{session_id}/messages")
def post_message(session_id: str, req: MessageRequest) -> dict:
    session = _load_session(session_id)
    _manager.add_message(session, "user", req.content, action=req.action)
    return _public_session(session)


def _chat_llm(session: Session, req: ChatRequest):
    """追问对话的 LLM 解析：请求级 > 会话级 > 全局。"""
    cfg = req.llm_config or getattr(session, "llm_config", None)
    if cfg and cfg.get("api_key"):
        client = llm_from_config(cfg)
        if client is not None:
            return client
    return _engine._resolve_llm(session)


def _chat_prompt(session: Session, content: str) -> tuple[str, str]:
    """追问对话的 system/user 提示词（含分析摘要上下文）。"""
    results = session.module_results
    summary = "；".join(
        f"{k} {v.status.value}" + (f"（{v.score}分）" if v.score is not None else "")
        for k, v in sorted(results.items())
        if v.status.value != "pending"
    ) or "（无完成模块）"
    company = session.company_name or session.company_code
    system = (
        "你是 A 股价值投资分析助手：基于给定公司的分析结果，用简洁中文回答用户追问，"
        "数据不确定时明确说明，不构成投资建议。"
    )
    user = (
        f"公司：{company}（{session.company_code}）\n"
        f"工作流：{session.workflow_id}\n"
        f"分析摘要：{summary}\n\n"
        f"用户提问：{content}"
    )
    return system, user


@app.post("/api/sessions/{session_id}/chat")
def chat(session_id: str, req: ChatRequest) -> dict:
    """追问对话（阻塞版）：记录用户消息 → 用 LLM 回复 → 记录 assistant 消息。"""
    session = _load_session(session_id)
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")

    _manager.add_message(session, "user", content)

    llm = _chat_llm(session, req)
    system, user = _chat_prompt(session, content)
    if llm is not None:
        try:
            reply = llm.chat(system, user)
        except Exception as exc:
            logger.exception("对话 LLM 调用失败")
            reply = f"（LLM 调用失败：{type(exc).__name__}，请检查 LLM 配置后重试）"
    else:
        reply = "未配置可用的 LLM，暂时无法回答追问。请先在「LLM 配置」中添加服务商并设为默认。"

    _manager.add_message(session, "assistant", reply)
    return _public_session(session)


@app.post("/api/sessions/{session_id}/chat/stream")
def chat_stream(session_id: str, req: ChatRequest) -> StreamingResponse:
    """追问对话（流式版）：SSE 实时推送 chat_chunk（kind=content|thinking），结尾 done。

    事件流：
    - `chat_chunk`  LLM 流式增量 {kind, chunk}
    - `done`        生成结束 {content: 完整回复}（此时 assistant 消息已落库）
    - `error`       失败
    心跳：每 15s 发送 `: keep-alive` 注释，防止长链接被代理切断。
    """
    session = _load_session(session_id)
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")

    _manager.add_message(session, "user", content)
    llm = _chat_llm(session, req)
    system, user = _chat_prompt(session, content)

    q: queue.Queue[dict | None] = queue.Queue()

    def worker() -> None:
        try:
            parts: list[str] = []
            if llm is not None:
                try:
                    for kind, chunk in llm.stream_chat(system, user):
                        if kind == "content":
                            parts.append(chunk)
                        q.put({"type": "chat_chunk", "kind": kind, "chunk": chunk})
                except Exception as exc:
                    logger.exception("对话 LLM 流式调用失败")
                    parts.append(f"（LLM 调用失败：{type(exc).__name__}，请检查 LLM 配置后重试）")
            else:
                parts.append(
                    "未配置可用的 LLM，暂时无法回答追问。请先在「LLM 配置」中添加服务商并设为默认。"
                )
            reply = "".join(parts)
            _manager.add_message(session, "assistant", reply)
            q.put({"type": "done", "content": reply})
        except Exception as exc:
            logger.exception("对话流式执行失败")
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        heartbeat = max(0.1, float(os.getenv("SSE_HEARTBEAT_SECONDS", "15")))
        while True:
            try:
                item = q.get(timeout=heartbeat)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/sessions/{session_id}/rerun")
def rerun_session(session_id: str, req: RerunRequest) -> dict:
    session = _load_session(session_id)
    # 支持内置模块（ModuleName）与自定义智能体（任意 agent id，如 M0_investor_profile）
    ordered = _manager.rerun(session, req.modules, assumptions=req.assumptions)
    return {"rerun_order": ordered, "session": _public_session(session)}


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
    return _public_session(session)


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
    return _public_session(session)


@app.get("/api/sessions/{session_id}/events")
def stream_events(session_id: str):
    """SSE 长链接：运行工作流并实时推送每个步骤的进度（浏览器直连）。

    事件流：
    - `started`  连接建立、运行开始（前端据此确认长链接已建立）
    - `step`     步骤状态变化（running / done / failed / skipped）
    - `llm_chunk` LLM 流式增量文本（step 定位步骤，kind=content|thinking，chunk 为一段文本）
    - `done`     运行结束（含会话终态 completed/failed）
    - `error`    运行失败
    心跳：每 15s 发送 `: keep-alive` 注释，避免代理/平台（Render/Vercel）切断空闲长链接。
    """
    session = _load_session(session_id)
    flow = _load_workflow(session)
    q: queue.Queue[dict | None] = queue.Queue()

    def _push_step(sess, step, result) -> None:  # type: ignore[no-untyped-def]
        q.put(
            {
                "type": "step",
                "step": step.id,
                "agent": step.agent_id,
                "status": result.status.value,
            }
        )

    def _push_chunk(sess, step, kind, chunk) -> None:  # type: ignore[no-untyped-def]
        q.put(
            {
                "type": "llm_chunk",
                "step": step.id,
                "agent": step.agent_id,
                "kind": kind,
                "chunk": chunk,
            }
        )

    def worker() -> None:
        try:
            _engine.run(
                session,
                flow,
                on_step=_push_step,
                on_step_start=_push_step,
                on_llm_chunk=_push_chunk,
            )
            q.put({"type": "done", "status": session.status.value})
        except WorkflowValidationError as exc:
            q.put({"type": "error", "message": str(exc)})
        except Exception as exc:
            logger.exception("工作流执行失败")
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        yield (
            "data: "
            + json.dumps({"type": "started", "status": "in_progress"}, ensure_ascii=False)
            + "\n\n"
        )
        # 心跳间隔可配置（测试用短间隔，默认 15s）
        heartbeat = max(0.1, float(os.getenv("SSE_HEARTBEAT_SECONDS", "15")))
        while True:
            try:
                item = q.get(timeout=heartbeat)
            except queue.Empty:
                # 心跳：LLM/数据步骤可能长时间无事件，保持长链接不超时
                yield ": keep-alive\n\n"
                continue
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/sessions/{session_id}/watch")
def watch_events(session_id: str):
    """SSE 观察接口：仅订阅会话进度，不触发新的执行。"""
    session = _load_session(session_id)
    flow = _load_workflow(session)

    def gen():
        yield (
            "data: "
            + json.dumps({"type": "started", "status": session.status.value}, ensure_ascii=False)
            + "\n\n"
        )
        heartbeat = max(0.1, float(os.getenv("SSE_HEARTBEAT_SECONDS", "15")))
        poll = max(0.1, float(os.getenv("SSE_WATCH_POLL_SECONDS", "0.5")))
        # created 会话若一直未开始执行，观察超过该时长后主动结束，避免长链接悬挂
        idle = max(0.1, float(os.getenv("SSE_WATCH_IDLE_SECONDS", "60")))
        opened_at = time.monotonic()
        last_keepalive = opened_at
        previous: dict[str, str] | None = None

        while True:
            current_session = _load_session(session_id)
            previous, events = _step_status_events(current_session, flow, previous)
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_keepalive = time.monotonic()

            if current_session.status in (
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.ARCHIVED,
            ):
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "done", "status": current_session.status.value},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                break

            # 从未开始的 created 会话：观察超时即结束（不会自己触发执行）
            if (
                current_session.status == SessionStatus.CREATED
                and time.monotonic() - opened_at >= idle
            ):
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "done", "status": current_session.status.value},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                break

            if time.monotonic() - last_keepalive >= heartbeat:
                yield ": keep-alive\n\n"
                last_keepalive = time.monotonic()
            time.sleep(poll)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class DailyRunResult(BaseModel):
    """每日任务执行结果（FC 定时触发器调用后返回）。"""

    updated: dict
    session_count: int
    monitor_events: int
    events: list[dict]
    pushed_channels: list[str]
    errors: list[str] = []


@app.post("/api/daily")
def run_daily(x_daily_token: str | None = Header(default=None)) -> DailyRunResult:
    """每日定时任务：监控评估 + 命中落库（monitor_hits）+ Webhook 推送。

    供阿里云 FC 定时触发器调用（大陆 IP 拉 AkShare）；也可手动 curl 触发。
    可选鉴权：设置环境变量 DAILY_TOKEN 后，请求需带 `x-daily-token` 头。
    """
    token = os.getenv("DAILY_TOKEN", "")
    if token and x_daily_token != token:
        raise HTTPException(status_code=401, detail="x-daily-token 不匹配")
    return DailyRunResult(**run_daily_job())


class FCTimerEvent(BaseModel):
    """FC 定时触发器（异步事件模式）的 Event Payload。"""

    action: str = ""
    token: str | None = None


@app.post("/")
def fc_timer_event(
    event: FCTimerEvent | None = None,
    x_daily_token: str | None = Header(default=None),
) -> DailyRunResult:
    """FC 定时触发器（异步事件）入口：兼容直接把定时事件 POST 到函数根路径 /。

    控制台「触发消息」填：{"action": "daily", "token": "<DAILY_TOKEN>"}
    设了 DAILY_TOKEN 时校验 token（body.token 或 x-daily-token 头均可），防止公开入口被滥用。
    注意：阿里云 FC 定时触发器对 Web 函数的实际调用路径是 POST /invoke（见 fc_invoke_entry）。
    """
    return _run_daily_event(event, x_daily_token)


@app.post("/invoke")
async def fc_invoke_entry(request: Request) -> DailyRunResult:
    """FC 定时触发器（异步事件）对 Web 函数/自定义容器的实际调用入口：POST /invoke。

    阿里云 FC 定时触发器的事件调用走 /invoke（而非 /），body 为控制台「触发消息」原样 JSON；
    手动解析 body（兼容非 application/json 的 content-type），再复用根路径的校验与执行逻辑。
    """
    raw = (await request.body()).decode("utf-8", "ignore").strip()
    event: FCTimerEvent | None = None
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                event = FCTimerEvent(**data)
        except (TypeError, ValueError):
            event = None
    return _run_daily_event(event, request.headers.get("x-daily-token"))


def _run_daily_event(
    event: FCTimerEvent | None,
    x_daily_token: str | None,
) -> DailyRunResult:
    """解析并执行定时触发事件（/ 与 /invoke 共用）。"""
    action = event.action if event is not None else ""
    if action not in ("daily", "run_daily"):
        raise HTTPException(status_code=404, detail=f"未知事件：{action or '(空)'}")
    token = os.getenv("DAILY_TOKEN", "")
    provided = (event.token if event is not None else None) or x_daily_token
    if token and provided != token:
        raise HTTPException(status_code=401, detail="token 不匹配")
    return DailyRunResult(**run_daily_job())


class WebhookUpsertRequest(BaseModel):
    """保存用户通知渠道：channel ∈ {feishu, wechat}；webhook_url 为空 = 删除该渠道。"""

    channel: str
    webhook_url: str = ""


class WebhookTestRequest(BaseModel):
    """测试推送：可指定 channel+url 直接测试；都不填则测试已保存的渠道。"""

    channel: str | None = None
    webhook_url: str | None = None


def _current_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    uid = user.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="未登录")
    return uid


@app.get("/api/webhooks")
def get_webhooks(request: Request) -> dict:
    """当前登录用户配置的通知渠道（飞书/企微 webhook）。"""
    uid = _current_user_id(request)
    return {"webhooks": _webhook_store.get_webhooks(uid)}


@app.put("/api/webhooks")
def put_webhook(req: WebhookUpsertRequest, request: Request) -> dict:
    """保存/删除当前用户某个渠道的 webhook（RLS 按 user_id 隔离）。"""
    uid = _current_user_id(request)
    if req.channel not in ("feishu", "wechat"):
        raise HTTPException(status_code=400, detail="channel 只能是 feishu/wechat")
    url = req.webhook_url.strip()
    if url and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="webhook 地址必须以 https:// 开头")
    if url:
        _webhook_store.set_webhook(uid, req.channel, url)
    else:
        _webhook_store.delete_webhook(uid, req.channel)
    return {"webhooks": _webhook_store.get_webhooks(uid)}


@app.post("/api/webhooks/test")
def test_webhook(req: WebhookTestRequest, request: Request) -> dict:
    """给当前用户发送一条测试通知（用已保存渠道或临时指定的渠道）。"""
    uid = _current_user_id(request)
    text = "Value Agent 测试通知 ✅（通知渠道配置成功）"
    if req.channel and req.webhook_url:
        channels = {req.channel: req.webhook_url.strip()}
    else:
        channels = _webhook_store.get_webhooks(uid)
    if not channels:
        raise HTTPException(status_code=400, detail="还没有配置任何通知渠道")
    pushed = send_webhook_to_channels(channels, text)
    if not pushed:
        raise HTTPException(status_code=502, detail="推送失败（请检查 webhook 地址）")
    return {"pushed": pushed}
