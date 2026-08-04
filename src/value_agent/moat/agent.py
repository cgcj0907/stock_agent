"""M5 护城河智能体：标准面代理评级 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_moat

_LLM_SYSTEM = "你是价值投资分析师。基于财务特征判断公司护城河来源（无形资产/转换成本/网络效应/成本优势/规模）并评级。"


class M5MoatAgent(Agent):
    spec = AgentSpec(
        id="M5_moat",
        name="护城河智能体",
        description="护城河类型/宽度评级（标准面代理 + LLM 定性）",
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M5 需要数据访问（ctx.data）")
        code = ctx.session.company_code
        fin = ctx.data.financials(code)
        result = assess_moat(fin)

        outputs = {"width": result.width, "signals": result.signals}
        evidence = list(result.evidence)

        if ctx.llm is not None:
            try:
                text = ctx.llm.chat(
                    _LLM_SYSTEM,
                    f"公司：{ctx.session.company_name or code}，财务信号：{result.signals}。"
                    f"请判断护城河来源与宽度（宽/中/窄/无）。",
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
