"""M10 决策智能体：汇总全模块评分 → 结论 + 仓位建议。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import run_decision


class M10DecisionAgent(Agent):
    spec = AgentSpec(
        id="M10_decision",
        name="决策输出智能体",
        description="五维评分卡 + 结论档位 + 仓位建议",
        inputs=["M4_valuation", "M7_market", "M8_safety_margin", "M9_risk"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        result = run_decision(ctx.session.module_results)
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=result.total,
            outputs={
                "dimensions": result.dimensions,
                "total": result.total,
                "conclusion": result.conclusion,
                "position": result.position,
                "vetoed": result.vetoed,
            },
            evidence=result.evidence,
        )
