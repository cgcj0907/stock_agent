"""M1 商业模式智能体：规则分类 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.links import validate_reference_links
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import analyze_business_model


def _understandability_level(label: str) -> str:
    """可理解性 → 契约枚举（high/medium/low），供 M4 保守度使用。"""
    if "能力圈内" in label:
        return "high"
    if "边缘" in label:
        return "medium"
    return "low"



_LLM_SYSTEM = (
    "你是价值投资分析师。基于给定公司信息判断其商业模式与能力圈可理解性。"
    + LLM_JSON_RULE
)


class M1BusinessModelAgent(Agent):
    spec = AgentSpec(
        id="M1_business_model",
        name="商业模式认知智能体",
        description="生意类型分类 + 能力圈评级（M4 路由依据）",
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M1 需要数据访问（ctx.data）")
        code = ctx.session.company_code
        try:
            info = ctx.data.company_info(code)
            fin = ctx.data.financials(code)
            result = analyze_business_model(info, fin)
        except Exception as exc:  # noqa: BLE001
            # 数据源瞬时故障：降级为 DONE（保守按周期），不阻塞下游估值
            return ModuleResult(
                module=self.spec.id,
                status=ModuleStatus.DONE,
                score=50.0,
                outputs={
                    "business_type": "cyclical",
                    "one_liner": f"数据获取失败（{type(exc).__name__}），保守按周期处理",
                    "understandability": "边缘（需行业周期专识）",
                    "industry": "",
                    "handoff": {
                        "valuation_route": "cyclical",
                        "understandability_level": "medium",
                    },
                },
                evidence=[f"数据源异常：{type(exc).__name__}（{str(exc)[:80]}），已降级为周期分类"],
            )

        outputs = {
            "business_type": result.business_type,
            "one_liner": result.one_liner,
            "understandability": result.understandability,
            "industry": result.industry,
            # 下游契约（§4 M1）：M4 直接读 handoff.valuation_route，不再猜
            "handoff": {
                "valuation_route": result.business_type,
                "understandability_level": _understandability_level(result.understandability),
            },
        }
        evidence = list(result.evidence)

        if ctx.llm is not None:  # LLM 定性层（可选）
            try:
                text = ctx.llm.chat(
                    _LLM_SYSTEM,
                    f"公司：{info.get('name')}（{code}），行业：{result.industry}，"
                    f"规则判定类型：{result.business_type}。\n"
                    "请按以下结构输出 JSON：\n"
                    '{"business_model": "一句话描述其生意本质", '
                    '"understandability": "可理解|基本可理解|难以理解", '
                    '"reasons": ["判断理由1", "判断理由2"], '
                    '"references": [{"title": "参考文章标题", "url": "https://..."}]}\n'
                    "references 给出 1-3 条你参考的来源文章链接"
                    "（优先公司财报/公告/行业报告，链接必须真实存在、可访问，无法确定则为空数组 []）。",
                )
                parsed = parse_llm_json(text)
                if parsed is not None:
                    refs = validate_reference_links(parsed.get("references"))
                    if refs:
                        parsed["references"] = refs
                    else:
                        parsed.pop("references", None)
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
