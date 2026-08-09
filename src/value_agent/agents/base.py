"""Agent 抽象：统一输入输出契约，是自由编排的基础。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from value_agent.sessions.models import ModuleResult, ModuleStatus

if TYPE_CHECKING:
    from value_agent.sessions.models import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentManifest:
    """输出自描述（docs/13 §12 试点）：静态、每 agent 一份，引导下游/LLM 消费本模块输出。

    与 handoff 契约互补：handoff 规定「字段叫什么」，manifest 说明「字段什么意思、
    下游该怎么处理」——尤其对自定义 agent 互操作（来源可枚举，语义靠 manifest 解释）。
    """

    agent: str  # 产出的 agent id
    summary: str  # 一句话：这个模块产出什么
    output_fields: dict[str, str]  # 字段路径（如 handoff.competence_level）→ 含义/取值说明
    how_to_consume: str  # 下游怎么用：读哪些字段、缺失/None 时怎么兜底


@dataclass(frozen=True)
class AgentSpec:
    """智能体的静态描述（注册表索引用）。"""

    id: str
    name: str
    description: str = ""
    inputs: list[str] = field(default_factory=list)  # 依赖的 agent id
    requires_llm: bool = False
    version: str = "0.1.0"
    manifest: AgentManifest | None = None  # 输出自描述（可选，docs/13 §12）
    # P1（docs/13 §13）：缺失会导致「结果降级/硬约束失效」的关键上游。
    # 工作流 validate 后据此给出连接覆盖警告（提示不拦截，语义自由度保留）。
    required_inputs: list[str] = field(default_factory=list)


@dataclass
class AgentContext:
    """Agent 运行时上下文：只读输入 + 会话 + 数据/LLM 访问入口。"""

    session: Session
    assumptions: dict
    inputs: dict[str, ModuleResult]  # 依赖 agent 的结果（按 agent id 索引）
    data: Any = None  # 数据访问层（后续接入 data/）
    llm: Any = None  # LLM client（requires_llm=True 时提供）
    params: dict = field(default_factory=dict)  # 工作流步骤透传参数
    step_id: str | None = None  # 当前工作流步骤 id（SSE llm_chunk 事件定位用）
    # 实时流式回调：每产出增量触发一次 (step_id, kind, chunk)，kind ∈ content|thinking
    on_llm_chunk: Callable[[str, str, str], None] | None = None

    def stream_llm(self, system: str, user: str) -> str | None:
        """流式 LLM 定性调用：边生成边回调 on_llm_chunk，返回完整正文文本。

        - 正文增量（content）会累加进返回值；思考增量（thinking）只转发回调，
          不混入正文（由前端单独渲染成灰字思考区）。
        - 未配置 LLM 返回 None；回调失败只记日志，绝不阻断分析主流程。
        """
        if self.llm is None:
            return None
        # 兼容只实现了阻塞 chat() 的注入对象：退化为一次性整段返回
        stream = getattr(self.llm, "stream_chat", None)
        if stream is None:
            return self.llm.chat(system, user)
        parts: list[str] = []
        for item in stream(system, user):
            # 兼容旧式纯字符串增量：视为正文
            if isinstance(item, tuple):
                kind, delta = item
            else:
                kind, delta = "content", item
            if self.on_llm_chunk is not None:
                try:
                    self.on_llm_chunk(self.step_id or "", kind, delta)
                except Exception:
                    logger.warning("llm chunk 回调失败（不影响分析）", exc_info=True)
            if kind == "content":
                parts.append(delta)
        return "".join(parts)


def format_inputs_for_llm(inputs: dict[str, ModuleResult]) -> str:
    """把 ctx.inputs 整理成「来源 + 一句话自描述」文本，供下游 LLM 提示词引用。

    每个模块的 outputs 里可带 summary（产出的一句话说明，docs/13 §12），
    缺失时退化为 agent id。用于让下游 LLM 知道收到的数据来自哪些 agent、分别是什么，
    从而正确解读任意（含自定义）上游输入。
    """
    lines: list[str] = []
    for aid in sorted(inputs):
        result = inputs[aid]
        outputs = getattr(result, "outputs", None) or {}
        summary = outputs.get("summary")
        summary = str(summary).strip() if summary else ""
        lines.append(f"- {aid}" + (f"：{summary}" if summary else ""))
    return "\n".join(lines) if lines else "（无上游输入）"


# 数据源拉取失败时的可操作提示（Render 海外 IP 常被 A 股数据源拦截）
DATA_SOURCE_HINT = (
    "提示：数据未命中缓存且当前环境（如 Render 海外 IP）常被 A 股数据源拦截；"
    "可在本地执行 value-agent data fetch <股票代码> 预取到 Supabase 后重试。"
)


def degraded_module_result(
    module_id: str,
    reason: str,
    outputs: dict | None = None,
    evidence: list[str] | None = None,
    score: float = 0.0,
) -> ModuleResult:
    """数据源失败时的统一降级结果：DONE + 空/保守 outputs + 明确原因 + meta.degraded。

    避免单个模块因数据源瞬时异常直接 FAILED，连锁阻塞依赖它的下游模块
    （如 M6 分红失败曾把 M4 堵成「依赖步骤失败」）。
    """
    from value_agent.core.contracts import ReasonCode, build_meta

    return ModuleResult(
        module=module_id,
        status=ModuleStatus.DONE,
        score=score,
        outputs=outputs or {},
        evidence=[reason] + list(evidence or []) + [DATA_SOURCE_HINT],
        meta=build_meta(
            0.0,
            "low",
            degraded=True,
            reason_codes=[ReasonCode.DATA_UNAVAILABLE.value],
        ),
    )


class Agent(ABC):
    """分析能力单元。子类必须定义 spec 并实现 run。"""

    spec: AgentSpec

    @abstractmethod
    def run(self, ctx: AgentContext) -> ModuleResult:
        """执行分析，返回统一 ModuleResult。"""
        raise NotImplementedError
