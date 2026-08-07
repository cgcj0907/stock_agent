"""M2 财务质量智能体：取财报数据 → 规则引擎打分 → 输出 ModuleResult。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.scoring import llm_score
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
        try:
            fin = ctx.data.financials(code, years=10)
            result = analyze_financial_quality(fin["records"])
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"财务数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "metrics": {},
                    "signals": [],
                    "summary": {"说明": "财务数据不可用"},
                },
            )
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "ROE 最新": result.metrics.get("roe_latest"),
                "净利率": result.metrics.get("net_margin"),
                "现金流/净利最低": result.metrics.get("ocf_to_np_min"),
                "资产负债率": result.metrics.get("debt_to_assets_latest"),
                "造假信号数": len(result.signals),
            },
            evidence=result.evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=score,
            outputs={
                "metrics": result.metrics,
                "signals": [sig.to_dict() for sig in result.signals],
                "summary": result.details,
            },
            evidence=result.evidence,
        )
