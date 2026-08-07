"""默认工作流：与理论模块顺序一致的标准分析流。"""
from __future__ import annotations

from value_agent.sessions.manager import MODULE_DEPENDENCIES, PIPELINE_ORDER

from .models import Workflow, WorkflowStep

_STEP_NAMES = {
    "M1_business_model": "商业模式认知",
    "M2_financial_quality": "财务质量分析",
    "M3_growth": "成长与再投资",
    "M4_valuation": "估值引擎",
    "M5_moat": "护城河分析",
    "M6_governance": "治理与资本配置",
    "M7_market": "价格与情绪",
    "M8_safety_margin": "安全边际",
    "M9_risk": "风险与否决",
    "M10_decision": "决策输出",
    "M11_monitor": "跟踪监控",
}


def default_workflow() -> Workflow:
    """由 PIPELINE_ORDER + MODULE_DEPENDENCIES 生成标准工作流。

    步骤 id 用短编号（M1/M2/…，与 config/workflows/default.yaml 及前端目录一致），
    agent_id 用模块全名；SSE step 事件与前端状态映射都依赖短 id。
    """
    steps: list[WorkflowStep] = []
    for module in PIPELINE_ORDER:
        agent_id = module.value
        short_id = agent_id.split("_", 1)[0]
        deps = sorted(d.value.split("_", 1)[0] for d in MODULE_DEPENDENCIES.get(module, set()))
        steps.append(
            WorkflowStep(
                id=short_id,
                agent_id=agent_id,
                deps=deps,
            )
        )
    return Workflow(
        id="default",
        name="标准价值投资分析",
        description="M1–M11 全模块标准分析流",
        steps=steps,
    )
