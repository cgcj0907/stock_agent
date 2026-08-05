"""M11 跟踪监控智能体：生成监控规则（每日由 monitor --daily 执行）。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import build_monitor_plan


class M11MonitorAgent(Agent):
    spec = AgentSpec(
        id="M11_monitor",
        name="跟踪监控智能体",
        description="生成监控规则：卖出触发 + 验证点 + 风险项",
        # 实际消费：M2/M3/M7/M8/M9 输出 + M10 上下文；与 MODULE_DEPENDENCIES[M11] 对齐
        inputs=["M2_financial_quality", "M3_growth", "M7_market", "M8_safety_margin",
                "M9_risk", "M10_decision"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        plan = build_monitor_plan(ctx.session.module_results)
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=plan.score,
            outputs={
                "monitor_rules": [r.__dict__ for r in plan.rules],
                "rule_count": len(plan.rules),
            },
            evidence=plan.evidence,
        )
