"""M7 价格与情绪智能体。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_market


class M7MarketAgent(Agent):
    spec = AgentSpec(
        id="M7_market",
        name="价格与情绪智能体",
        description="估值历史分位 + 股债性价比 + 价格位置",
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M7 需要数据访问（ctx.data）")
        val = ctx.data.valuation_history(ctx.session.company_code)
        risk_free = ctx.assumptions.get("risk_free_rate", 0.04)
        result = assess_market(val, risk_free=risk_free)
        evidence = list(result.evidence)
        if val.get("url"):
            evidence.append(f"数据来源：百度股市通估值 {val['url']}")
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=result.score,
            outputs={
                "pe_percentile": result.pe_percentile,
                "pb_percentile": result.pb_percentile,
                "position": result.position,
            },
            evidence=evidence,
        )
