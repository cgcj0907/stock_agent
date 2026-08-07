"""M6 治理与资本配置智能体：分红代理评分 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.data.references import CompanyReferences, format_reference_list, select_references
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
        try:
            div = ctx.data.dividends(code)
            result = assess_governance(div)
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"分红数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "dividend_years": 0,
                    "payout_latest": None,
                    "note": "分红数据不可用",
                    "handoff": {
                        "governance_score": 0,
                        "capital_allocation_flag": "neutral",
                        "governance_risk_codes": [],
                    },
                },
            )

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
                refs = CompanyReferences().fetch(code, slot=2)  # 先抓真实链接供 LLM 筛选
                user_prompt = f"公司：{ctx.session.company_name or code}，分红信号：{result.note}。\n"
                ref_block = format_reference_list(refs)
                if ref_block:
                    user_prompt += ref_block + "\n"
                user_prompt += (
                    "请按以下结构输出 JSON：\n"
                    '{"governance_assessment": "治理评估", '
                    '"capital_allocation": "资本配置评估", '
                    '"risks": ["风险1", "风险2"], '
                    '"conclusion": "一句话结论", '
                    '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
                    "reference_indices：从参考资料清单中筛选与「治理/资本配置判断」最相关的文章编号"
                    "（1 基），没有就输出空数组；不得编造标题或链接。"
                )
                text = ctx.stream_llm(_LLM_SYSTEM, user_prompt)
                parsed = parse_llm_json(text)
                if parsed is not None:
                    selected = select_references(refs, parsed.get("reference_indices"))
                    if selected:
                        parsed["references"] = selected
                    else:
                        parsed.pop("references", None)
                    parsed.pop("reference_indices", None)
                    outputs["llm_qualitative"] = parsed
                    evidence.append("LLM 定性：已接入（结构化 JSON）")
                else:
                    outputs["llm_qualitative"] = text
                    evidence.append("LLM 定性：已接入（输出解析失败，按原文展示）")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），当前为规则引擎结果")

        score = llm_score(
            ctx, self.spec.id,
            facts={
                "连续分红年数": result.dividend_years,
                "最新分红率": result.payout_latest,
                "治理说明": result.note,
            },
            evidence=evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score,
            outputs=outputs, evidence=evidence,
        )
