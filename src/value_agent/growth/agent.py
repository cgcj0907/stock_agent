"""M3 成长与再投资智能体。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_growth


class M3GrowthAgent(Agent):
    spec = AgentSpec(
        id="M3_growth",
        name="成长与再投资智能体",
        description="历史增速 + 再投资质量 + 景气度评级（供 M4 DCF）",
        inputs=["M2_financial_quality"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M3 需要数据访问（ctx.data）")
        fin = ctx.data.financials(ctx.session.company_code)
        result = assess_growth(fin, default_growth=ctx.assumptions.get("growth_rate", 0.10))
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=result.score,
            outputs={
                "growth_estimate": result.growth_estimate,
                "prosperity": result.prosperity,
            },
            evidence=result.evidence,
        )
