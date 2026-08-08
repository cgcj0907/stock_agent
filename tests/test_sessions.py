"""会话管理单元测试：状态机、依赖链重算、断点续跑。

执行走 WorkflowEngine（run_pipeline 已移除）；这里用全 stub 智能体，
不依赖数据源，专注会话语义。
"""
import pytest

from tests.helpers import StubAgent
from value_agent.agents import Agent, AgentContext, AgentRegistry, AgentSpec
from value_agent.sessions import (
    PIPELINE_ORDER,
    InMemoryStore,
    InvalidTransitionError,
    ModuleName,
    ModuleResult,
    ModuleStatus,
    Session,
    SessionManager,
    SessionStatus,
    transition,
)
from value_agent.sessions.manager import _affected_modules
from value_agent.workflow import Workflow, WorkflowEngine, WorkflowStep, default_workflow


def _stub_registry(overrides: list[Agent] | None = None) -> AgentRegistry:
    """全 11 模块 stub 智能体（M2 也用 stub，避免依赖数据源）。"""
    reg = AgentRegistry()
    for m in PIPELINE_ORDER:
        spec = AgentSpec(id=m.value, name=m.label)
        reg.register(StubAgent(spec, placeholder="test stub"))
    for agent in overrides or []:
        reg.register(agent, overwrite=True)
    return reg


def _engine(manager: SessionManager, overrides: list[Agent] | None = None) -> WorkflowEngine:
    return WorkflowEngine(_stub_registry(overrides), manager)


@pytest.fixture
def manager() -> SessionManager:
    return SessionManager(InMemoryStore())


@pytest.fixture
def session(manager: SessionManager) -> Session:
    return manager.create_session("600519", "贵州茅台")


def test_create_session_status(session):
    assert session.status == SessionStatus.CREATED
    assert len(session.module_results) == len(PIPELINE_ORDER)
    assert all(isinstance(k, str) for k in session.module_results)  # key=agent id


def test_illegal_transition_raises(session):
    with pytest.raises(InvalidTransitionError):
        transition(session, SessionStatus.COMPLETED)  # created 不能直接 completed


def test_rerun_affected_closure():
    affected = _affected_modules([ModuleName.M3])
    assert affected == {ModuleName.M3, ModuleName.M4,
                        ModuleName.M8, ModuleName.M9,
                        ModuleName.M10, ModuleName.M11}
    assert ModuleName.M2 not in affected       # 上游（M2）结果仍有效，只作输入
    assert ModuleName.M1 not in affected       # 与 M3 无关


def test_rerun_returns_pipeline_order(manager, session):
    _engine(manager).run(session, default_workflow())
    ordered = manager.rerun(session, [ModuleName.M3], assumptions={"growth": 0.18})
    assert ordered == [ModuleName.M3, ModuleName.M4,
                       ModuleName.M8, ModuleName.M9,
                       ModuleName.M10, ModuleName.M11]
    assert session.assumptions["growth"] == 0.18
    assert session.module_results[ModuleName.M3.value].status == ModuleStatus.PENDING
    assert session.module_results[ModuleName.M1.value].status == ModuleStatus.DONE  # 未受影响


def test_failed_module_sets_session_failed(manager, session):
    class BoomAgent(Agent):
        spec = AgentSpec(id="M1_business_model", name="boom")

        def run(self, ctx: AgentContext) -> ModuleResult:
            raise RuntimeError("数据缺失")

    flow = Workflow(
        id="f",
        name="失败流",
        steps=[WorkflowStep(id="M1", agent_id="M1_business_model")],
    )
    _engine(manager, overrides=[BoomAgent()]).run(session, flow)
    assert session.status == SessionStatus.FAILED
    assert session.module_results["M1_business_model"].status == ModuleStatus.FAILED


def test_resume_after_failure(manager, session):
    class BoomAgent(Agent):
        spec = AgentSpec(id="M1_business_model", name="boom")

        def run(self, ctx: AgentContext) -> ModuleResult:
            raise RuntimeError("boom")

    flow = Workflow(
        id="f",
        name="失败流",
        steps=[WorkflowStep(id="M1", agent_id="M1_business_model")],
    )
    engine = _engine(manager, overrides=[BoomAgent()])
    engine.run(session, flow)
    assert session.status == SessionStatus.FAILED
    manager.resume(session)
    assert session.status == SessionStatus.IN_PROGRESS


def test_save_memo_version_keeps_status(manager, session):
    manager.save_memo_version(session, "memo v1")
    manager.save_memo_version(session, "memo v2")
    assert session.memo_versions == ["memo v1", "memo v2"]
    assert session.status == SessionStatus.CREATED  # 不改变状态


def test_delete_session(manager, session):
    sid = session.id
    manager._store.delete(sid)
    with pytest.raises(KeyError):
        manager.load(sid)


def test_workflow_id_default_and_custom(manager):
    s1 = manager.create_session("600519")
    assert s1.workflow_id == "default"
    s2 = manager.create_session("600519", workflow_id="quick")
    assert s2.workflow_id == "quick"


def test_add_message_updates_session_object(manager, session):
    """add_message 应同时更新传入的 session（供 API 返回最新消息）。"""
    manager.add_message(session, "user", "追问")
    manager.add_message(session, "assistant", "回复")
    assert len(session.messages) == 2
    assert session.messages[-1].role == "assistant"
    # 重新加载也应一致（已持久化）
    reloaded = manager.load(session.id)
    assert len(reloaded.messages) == 2


# ---------- I-2 跨会话监控记忆继承 ----------

def _complete(session: Session) -> Session:
    transition(session, SessionStatus.IN_PROGRESS)
    transition(session, SessionStatus.COMPLETED)
    return session


def test_prior_monitor_hits_inherits_latest_completed(manager):
    """只继承同标的最远一次已完成会话，并按 (rule_type, severity) 收敛。"""
    older = manager.create_session("600519")
    older.monitor_hits = [{"rule_type": "price_buy", "message": "旧命中", "severity": "info"}]
    _complete(older)

    latest = manager.create_session("600519")
    latest.monitor_hits = [
        {"rule_type": "price_sell", "message": "新命中", "severity": "warn"},
        {"rule_type": "price_buy", "message": "重复买点", "severity": "info"},
        {"rule_type": "price_buy", "message": "重复买点2", "severity": "info"},
    ]
    _complete(latest)

    inherited = manager.prior_monitor_hits("600519")
    keys = {(h["rule_type"], h["severity"]) for h in inherited}
    assert keys == {("price_sell", "warn"), ("price_buy", "info")}
    buy_hits = [h for h in inherited if h["rule_type"] == "price_buy"]
    assert len(buy_hits) == 1
    assert buy_hits[0]["message"] == "重复买点2"  # 收敛后保留最后一次命中

    fresh = manager.create_session("600519", monitor_hits=manager.prior_monitor_hits("600519"))
    assert {h["rule_type"] for h in fresh.monitor_hits} == {"price_buy", "price_sell"}


def test_prior_monitor_hits_ignores_non_completed(manager):
    pending = manager.create_session("600519")
    pending.monitor_hits = [{"rule_type": "price_buy", "message": "x", "severity": "info"}]
    assert manager.prior_monitor_hits("600519") == []  # created 未完成，不作为继承来源


def test_prior_monitor_hits_caps_items(manager):
    s = manager.create_session("600519")
    s.monitor_hits = [
        {"rule_type": f"t{i}", "message": f"m{i}", "severity": "info"} for i in range(30)
    ]
    _complete(s)
    assert len(manager.prior_monitor_hits("600519")) == 20          # 默认上限
    assert len(manager.prior_monitor_hits("600519", max_items=5)) == 5


# ---------- 生产数据暴露的问题修复（2026-08-08 Supabase sessions 稽核） ----------

def test_to_dict_never_persists_api_key(manager):
    """安全：llm_config.api_key 明文不得进入序列化 payload（曾全部落库泄漏）。"""
    session = manager.create_session(
        "600519",
        llm_config={"provider": "deepseek", "base_url": "https://x/v1",
                    "model": "deepseek-chat", "api_key": "sk-secret-123456"},
    )
    d = session.to_dict()
    assert d["llm_config"]["provider"] == "deepseek"
    assert d["llm_config"]["base_url"] == "https://x/v1"
    assert "api_key" not in d["llm_config"]

    # 无配置时 llm_config 序列化为 None
    assert manager.create_session("600519").to_dict()["llm_config"] is None


def _sqlite_manager(tmp_path) -> tuple[SessionManager, Session]:
    """用 SqliteStore 建真实持久化管理器（InMemoryStore 存对象不序列化，无法验证落库脱敏）。"""
    from value_agent.sessions.store import SqliteStore

    manager = SessionManager(SqliteStore(str(tmp_path / "sessions.db")))
    session = manager.create_session(
        "600519",
        llm_config={"provider": "deepseek", "base_url": "https://x/v1",
                    "model": "deepseek-chat", "api_key": "sk-secret-123456"},
    )
    return manager, session


def test_load_restores_cached_llm_config(tmp_path):
    """运行期密钥来自进程内缓存：create 后同进程 load 仍可用（创建→立即运行流）。"""
    manager, session = _sqlite_manager(tmp_path)
    # 存储层 round-trip 后 payload 不含密钥
    stored = manager._store.load(session.id)
    assert "api_key" not in (stored.llm_config or {})
    # manager.load 从缓存补回密钥
    reloaded = manager.load(session.id)
    assert (reloaded.llm_config or {}).get("api_key") == "sk-secret-123456"


def test_load_without_cache_has_no_api_key(tmp_path):
    """进程重启/缓存过期：load 到的会话不含 api_key，回退全局 LLM（不报错）。"""
    from value_agent.sessions.store import SqliteStore

    _, session = _sqlite_manager(tmp_path)
    fresh = SessionManager(SqliteStore(str(tmp_path / "sessions.db")))  # 无缓存的新管理器
    reloaded = fresh.load(session.id)
    assert "api_key" not in (reloaded.llm_config or {})


def test_create_session_rejects_invalid_company_code(manager):
    """公司代码必须为 6 位数字：拦截 6002579 这类脏代码产生的垃圾会话。"""
    with pytest.raises(ValueError):
        manager.create_session("6002579")
    with pytest.raises(ValueError):
        manager.create_session("abc123")
    with pytest.raises(ValueError):
        manager.create_session("")


def test_create_session_normalizes_company_code(manager):
    """容忍 sh/sz 前缀、点号与空白，统一归一化为 6 位代码。"""
    for raw, expect in (
        ("SH600519", "600519"),
        ("600519.SH", "600519"),
        (" sz000333 ", "000333"),
    ):
        s = manager.create_session(raw)
        assert s.company_code == expect


def test_persist_bumps_updated_at(manager, session):
    """步骤推进落库应刷新 updated_at（此前整段运行 updated_at 不变）。"""
    before = session.updated_at
    manager.persist(session)
    assert session.updated_at >= before
