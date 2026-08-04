"""M6 治理与资本配置智能体：分红代理评分 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_governance

_LLM_SYSTEM = "你是公司治理分析师。基于公开信息评估管理层诚信、资本配置与治理风险。"


class M6GovernanceAgent(Agent):
    spec = AgentSpec(
        id="M6_governance",
        name="治理与资本配置智能体",
        description="回报股东/分红持续性 + 治理评级",
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M6 需要数据访问（ctx.data）")
        code = ctx.session.company_code
        div = ctx.data.dividends(code)
        result = assess_governance(div)

        outputs = {
            "dividend_years": result.dividend_years,
            "payout_latest": result.payout_latest,
            "note": result.note,
        }
        evidence = list(result.evidence)

        if ctx.llm is not None:
            try:
                text = ctx.llm.chat(
                    _LLM_SYSTEM,
                    f"公司：{ctx.session.company_name or code}，分红信号：{result.note}。"
                    f"请评估治理与资本配置，指出风险点。",
                )
                outputs["llm_qualitative"] = text
                evidence.append("LLM 定性：已接入")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），当前为规则引擎结果")

        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=result.score,
            outputs=outputs, evidence=evidence,
        )
