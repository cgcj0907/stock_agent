"""M3 成长与再投资智能体。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.scoring import llm_score
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
        try:
            fin = ctx.data.financials(ctx.session.company_code)
            result = assess_growth(
                fin,
                default_growth=ctx.assumptions.get("growth_rate", 0.10),
                wacc=float(ctx.assumptions.get("wacc", 0.10)),  # 4.6：WACC 参数化
            )
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"财务数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "growth_estimate": None,
                    "prosperity": "未知",
                    "handoff": {
                        "recommended_growth_rate": None,
                        "growth_confidence": "low",
                        "cyclicality_flag": False,
                        "prosperity_code": "flat",
                        "growth_scenarios": {"conservative": None, "neutral": None, "optimistic": None},
                    },
                },
            )
        calib: dict = {}
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "增速估计": result.growth_estimate,
                "景气度": result.prosperity,
                "增长信心": result.growth_confidence,
                "周期行业": result.cyclicality_flag,
            },
            evidence=result.evidence, default=result.score, trace=calib,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score, calibration=calib or None,
            outputs={
                "growth_estimate": result.growth_estimate,
                "prosperity": result.prosperity,
                # 下游契约（§4 M3）：M4 用 recommended_growth_rate，M9/M11 用 prosperity_code
                "handoff": {
                    "recommended_growth_rate": result.growth_estimate,
                    "growth_confidence": result.growth_confidence,
                    "cyclicality_flag": result.cyclicality_flag,
                    "prosperity_code": result.prosperity_code,
                    # 4.4：增速情景区间（M4 DCF 用保守档）
                    "growth_scenarios": result.scenarios,
                },
            },
            evidence=result.evidence,
        )
