"""会话数据模型（dataclass，起步零依赖；生产可换 ORM）。"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SessionStatus(str, enum.Enum):
    """会话生命周期状态，合法迁移见 state_machine.VALID_TRANSITIONS。"""

    CREATED = "created"
    IN_PROGRESS = "in_progress"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class ModuleStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ModuleName(str, enum.Enum):
    """内置 11 大模块的常量（理论模块见 docs/01-design.md §2）。

    注意：module_results 以**字符串 agent id** 为键（str），
    允许自由注册自定义智能体（如 "M12_esg_rating"），不受本枚举限制。
    """

    M1 = "M1_business_model"
    M2 = "M2_financial_quality"
    M3 = "M3_growth"
    M4 = "M4_valuation"
    M5 = "M5_moat"
    M6 = "M6_governance"
    M7 = "M7_market"
    M8 = "M8_safety_margin"
    M9 = "M9_risk"
    M10 = "M10_decision"
    M11 = "M11_monitor"

    @property
    def label(self) -> str:
        return self.value.split("_", 1)[1]


@dataclass
class ModuleResult:
    """单个智能体的运行结果，是会话与工作流之间的统一契约。"""

    module: str  # agent id（如 "M2_financial_quality" 或自定义 "M12_esg_rating"）
    status: ModuleStatus = ModuleStatus.PENDING
    score: float | None = None  # 0-100 子评分（供 M10 加权），None=不适用
    outputs: dict = field(default_factory=dict)  # 结构化结果（指标表/估值区间/信号…）
    evidence: list[str] = field(default_factory=list)  # 数据来源/引用（强制溯源）
    llm_explanation: str | None = None
    # 质量元数据（方案 1 强约束，见 docs/09-module-contracts.md §2/§3）：
    # {"confidence": 0.0, "completeness": "high|medium|low", "degraded": false, "reason_codes": []}
    # 构造/校验见 value_agent.core.contracts（build_meta / validate_meta）。
    meta: dict = field(default_factory=dict)
    # v2 LLM 校准轨迹（docs/12-v2-upgrade.md §8.3，P2 落库）：
    # {"module_id", "base", "final", "outcome", "notes", "delta", "reasons", "evidence_refs", "new_facts"}
    calibration: dict | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "status": self.status.value,
            "score": self.score,
            "outputs": self.outputs,
            "evidence": self.evidence,
            "llm_explanation": self.llm_explanation,
            "meta": self.meta,
            "calibration": self.calibration,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ModuleResult:
        return cls(
            module=d["module"],
            status=ModuleStatus(d.get("status", "pending")),
            score=d.get("score"),
            outputs=d.get("outputs", {}),
            evidence=d.get("evidence", []),
            llm_explanation=d.get("llm_explanation"),
            meta=d.get("meta", {}),
            calibration=d.get("calibration"),
            started_at=_parse_dt(d.get("started_at")),
            finished_at=_parse_dt(d.get("finished_at")),
        )


@dataclass
class Message:
    role: str  # user | assistant | system
    content: str
    action: str | None = None  # 如 "rerun_M3"、"update_assumption"
    id: str = field(default_factory=lambda: _new_id("msg"))
    created_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "action": self.action,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Message:
        return cls(
            role=d["role"],
            content=d["content"],
            action=d.get("action"),
            id=d.get("id", _new_id("msg")),
            created_at=_parse_dt(d.get("created_at")) or _now(),
        )


@dataclass
class Session:
    company_code: str
    company_name: str = ""
    user_id: str | None = None  # 归属用户（Supabase auth.users id）；None = 系统/全局
    id: str = field(default_factory=lambda: _new_id("sess"))
    status: SessionStatus = SessionStatus.CREATED
    current_module: str | None = None  # 正在执行的 agent id
    module_results: dict[str, ModuleResult] = field(default_factory=dict)  # key=agent id
    assumptions: dict = field(default_factory=dict)  # 用户覆盖的假设（增速/折现率/折扣率…）
    data_snapshot_id: str | None = None  # point-in-time 数据快照绑定
    workflow_id: str = "default"  # 使用的工作流定义 id（见 workflow/）
    workflow_steps: list[dict] | None = None  # 内联自定义工作流步骤（[{id, agent, deps}]），优先于 workflow_id
    llm_config: dict | None = None  # 按会话注入的 LLM 配置（{provider, base_url, model, api_key}），优先于全局
    investor_profile: dict | None = None  # M0 投资者画像快照（创建会话时附加，已剥离 PII；见 docs/13）
    model_version: str = "0.1.0"
    memo_versions: list[str] = field(default_factory=list)
    # 批次 E 增强：M10 决策快照审计（O-3）+ 跨会话监控命中历史（I-2）
    decision_snapshots: list[dict] = field(default_factory=list)
    monitor_hits: list[dict] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    archived_at: datetime | None = None

    def to_dict(self) -> dict:
        # 安全：llm_config.api_key 属敏感凭据，序列化（落库/对外返回）时一律剔除，
        # 绝不持久化明文 Key；运行期密钥仅存在于进程内 SessionManager 缓存。
        llm_config = dict(self.llm_config) if self.llm_config else None
        if llm_config:
            llm_config.pop("api_key", None)
            if not llm_config:
                llm_config = None
        return {
            "id": self.id,
            "company_code": self.company_code,
            "company_name": self.company_name,
            "user_id": self.user_id,
            "status": self.status.value,
            "current_module": self.current_module,
            "module_results": {k: v.to_dict() for k, v in self.module_results.items()},
            "assumptions": self.assumptions,
            "data_snapshot_id": self.data_snapshot_id,
            "workflow_id": self.workflow_id,
            "workflow_steps": self.workflow_steps,
            "llm_config": llm_config,
            "investor_profile": self.investor_profile,
            "model_version": self.model_version,
            "memo_versions": self.memo_versions,
            "decision_snapshots": self.decision_snapshots,
            "monitor_hits": self.monitor_hits,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        session = cls(
            company_code=d["company_code"],
            company_name=d.get("company_name", ""),
            user_id=d.get("user_id"),
            id=d.get("id", _new_id("sess")),
            status=SessionStatus(d.get("status", "created")),
            current_module=d.get("current_module"),
            assumptions=d.get("assumptions", {}),
            data_snapshot_id=d.get("data_snapshot_id"),
            workflow_id=d.get("workflow_id", "default"),
            workflow_steps=d.get("workflow_steps"),
            llm_config=d.get("llm_config"),
            investor_profile=d.get("investor_profile"),
            model_version=d.get("model_version", "0.1.0"),
            memo_versions=list(d.get("memo_versions", [])),
            decision_snapshots=list(d.get("decision_snapshots", [])),
            monitor_hits=list(d.get("monitor_hits", [])),
            created_at=_parse_dt(d.get("created_at")) or _now(),
            updated_at=_parse_dt(d.get("updated_at")) or _now(),
            archived_at=_parse_dt(d.get("archived_at")),
        )
        session.module_results = {
            k: ModuleResult.from_dict(v)
            for k, v in (d.get("module_results") or {}).items()
        }
        session.messages = [Message.from_dict(m) for m in (d.get("messages") or [])]
        return session
