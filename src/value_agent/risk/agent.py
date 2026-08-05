"""M9 风险与否决智能体：聚合风险 + 一票否决 + 可选 LLM 红队批判。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_risk

_LLM_SYSTEM = (
    "你是投资红队：找出这笔投资最可能出错的三个假设与永久损失路径。"
    + LLM_JSON_RULE
)


class M9RiskAgent(Agent):
    spec = AgentSpec(
        id="M9_risk",
        name="风险与否决智能体",
        description="风险清单 + 一票否决 + 红队批判",
        inputs=["M2_financial_quality", "M3_growth", "M5_moat", "M6_governance", "M7_market", "M8_safety_margin"],
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        result = assess_risk(ctx.inputs, ctx.assumptions)
        outputs = {"risk_items": result.risk_items, "veto": result.veto}
        evidence = list(result.evidence)

        if ctx.llm is not None:
            try:
                text = ctx.llm.chat(
                    _LLM_SYSTEM,
                    f"公司：{ctx.session.company_name or ctx.session.company_code}；"
                    f"规则风险清单：{result.risk_items}。\n"
                    "请按以下结构输出 JSON：\n"
                    '{"key_assumptions": ["假设1", "假设2", "假设3"], '
                    '"permanent_loss_paths": ["路径1", "路径2"], '
                    '"verdict": "一句话反方结论"}',
                )
                parsed = parse_llm_json(text)
                if parsed is not None:
                    outputs["llm_red_team"] = parsed
                    evidence.append("LLM 红队：已接入（结构化 JSON）")
                else:
                    outputs["llm_red_team"] = text
                    evidence.append("LLM 红队：已接入（输出解析失败，按原文展示）")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），红队定性待接入")

        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=result.score,
            outputs=outputs, evidence=evidence,
        )
