"""M2 财务质量智能体：取财报数据 → 规则引擎打分 → 输出 ModuleResult。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .quality import analyze_financial_quality


class M2FinancialQualityAgent(Agent):
    spec = AgentSpec(
        id="M2_financial_quality",
        name="财务质量智能体",
        description="盈利能力(ROE+杜邦)/稳定性/现金流/杠杆/造假信号",
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M2 需要数据访问（ctx.data），请注入 DataManager")
        code = ctx.session.company_code
        fin = ctx.data.financials(code, years=10)
        result = analyze_financial_quality(fin["records"])
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=result.score,
            outputs={
                "metrics": result.metrics,
                "signals": result.signals,
                "summary": result.details,
            },
            evidence=result.evidence,
        )
