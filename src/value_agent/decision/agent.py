"""M10 决策智能体：汇总全模块评分 → 结论 + 仓位建议。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import apply_band, run_decision


class M10DecisionAgent(Agent):
    spec = AgentSpec(
        id="M10_decision",
        name="决策输出智能体",
        description="五维评分卡 + 结论档位 + 仓位建议",
        # 实际消费：维度评分用 M1/M2/M3/M5/M6 score + M4/M7/M8/M9；与 MODULE_DEPENDENCIES[M10] 对齐
        inputs=["M1_business_model", "M2_financial_quality", "M3_growth", "M4_valuation",
                "M5_moat", "M6_governance", "M7_market", "M8_safety_margin", "M9_risk"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        result = run_decision(ctx.session.module_results)
        total = result.total
        if not result.vetoed:  # 一票否决时保持回避，不让 LLM 覆盖
            total = llm_score(
                ctx, self.spec.id,
                facts={
                    "五维评分": result.dimensions,
                    "加权总分": result.total,
                    "结论": result.conclusion,
                    "否决项": result.vetoed,
                },
                evidence=result.evidence, default=result.total,
            )
        _, position, conclusion, decision_code = apply_band(total, result.vetoed)
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=total,
            outputs={
                "dimensions": result.dimensions,
                "total": total,
                "conclusion": conclusion,
                "position": position,
                "vetoed": result.vetoed,
                "decision_code": decision_code,
                "blocked_by_veto": result.blocked_by_veto,
            },
            evidence=result.evidence,
        )
