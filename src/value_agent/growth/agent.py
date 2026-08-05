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
        inputs=[],  # 实际只读 ctx.data；M2 顺序依赖由 MODULE_DEPENDENCIES 保证
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
                # 下游契约（§4 M3）：M4 用 recommended_growth_rate，M9/M11 用 prosperity_code
                "handoff": {
                    "recommended_growth_rate": result.growth_estimate,
                    "growth_confidence": result.growth_confidence,
                    "cyclicality_flag": result.cyclicality_flag,
                    "prosperity_code": result.prosperity_code,
                },
            },
            evidence=result.evidence,
        )
