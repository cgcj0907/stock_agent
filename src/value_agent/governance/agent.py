"""M6 治理与资本配置智能体：分红代理评分 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_governance


def _capital_allocation_flag(result) -> str:
    """资本配置代理（规则层）：评分高分红持续 → good；一般 → neutral；弱 → poor。"""
    if result.score >= 70:
        return "good"
    if result.score >= 55:
        return "neutral"
    return "poor"



_LLM_SYSTEM = (
    "你是公司治理分析师。基于公开信息评估管理层诚信、资本配置与治理风险。"
    + LLM_JSON_RULE
)


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
            # 下游契约（§4 M6）：M9/M10 消费 governance_score / capital_allocation_flag
            "handoff": {
                "governance_score": result.score,
                "capital_allocation_flag": _capital_allocation_flag(result),
                "governance_risk_codes": [],
            },
        }
        evidence = list(result.evidence)

        if ctx.llm is not None:
            try:
                text = ctx.llm.chat(
                    _LLM_SYSTEM,
                    f"公司：{ctx.session.company_name or code}，分红信号：{result.note}。\n"
                    "请按以下结构输出 JSON：\n"
                    '{"governance_assessment": "治理评估", '
                    '"capital_allocation": "资本配置评估", '
                    '"risks": ["风险1", "风险2"], '
                    '"conclusion": "一句话结论", '
                    '"references": [{"title": "参考文章标题", "url": "https://..."}]}\n'
                    "references 给出 1-3 条你参考的来源文章链接"
                    "（优先公司财报/公告/行业报告，无法确定则为空数组 []）。",
                )
                parsed = parse_llm_json(text)
                if parsed is not None:
                    outputs["llm_qualitative"] = parsed
                    evidence.append("LLM 定性：已接入（结构化 JSON）")
                else:
                    outputs["llm_qualitative"] = text
                    evidence.append("LLM 定性：已接入（输出解析失败，按原文展示）")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），当前为规则引擎结果")

        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=result.score,
            outputs=outputs, evidence=evidence,
        )
