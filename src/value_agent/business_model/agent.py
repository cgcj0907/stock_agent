"""M1 商业模式智能体：规则分类 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.data.references import CompanyReferences, format_reference_list, select_references
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import analyze_business_model, normalize_business_type


def _understandability_level(label: str) -> str:
    """可理解性 → 契约枚举（high/medium/low），供 M4 保守度使用。"""
    if "能力圈内" in label:
        return "high"
    if "边缘" in label:
        return "medium"
    return "low"



_LLM_SYSTEM = (
    "你是价值投资分析师。基于给定公司信息判断其商业模式与能力圈可理解性。"
    "你必须先做排他判断：公司最终只能归入一个主导生意类型。"
    "判断时优先看盈利模式、需求驱动、周期属性、资产特征、竞争结构与财务特征，"
    "不要把“高增长”直接等同于“成长型”，也不要把“重资产”直接等同于“资产型”。"
    "如果行业强依赖景气、商品价格、运价、地产周期或产能周期，应优先考虑周期型；"
    "如果增长主要来自长期渗透率提升、产品迭代、再投资效率和竞争优势，才更接近成长型。"
    "你必须先判断该公司更接近哪一类生意类型，再给出一句话商业模式描述。"
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
        # 公司信息与财务数据分开容错：东财接口瞬时故障（如 JSONDecodeError）时，
        # 公司信息失败仍可用财务数据（ROE/毛利率/负债率）完成分类，不整模块降级。
        info: dict = {}
        data_issues: list[str] = []
        try:
            info = ctx.data.company_info(code)
        except Exception as exc:  # noqa: BLE001
            data_issues.append(f"公司信息获取失败（{type(exc).__name__}），仅用财务数据分类")
        try:
            fin = ctx.data.financials(code)
        except Exception as exc:  # noqa: BLE001
            if not info:
                # 公司信息和财务都失败：只能整体降级
                return ModuleResult(
                    module=self.spec.id,
                    status=ModuleStatus.DONE,
                    score=50.0,
                    outputs={
                        "business_type": "cyclical",
                        "business_model": f"数据获取失败（{type(exc).__name__}），保守按周期处理",
                        "understandability": "边缘（需行业周期专识）",
                        "industry": "",
                        "handoff": {
                            "valuation_route": "cyclical",
                            "understandability_level": "medium",
                        },
                    },
                    evidence=[f"数据源异常：{type(exc).__name__}（{str(exc)[:80]}），已降级为周期分类"],
                )
            data_issues.append(f"财务数据获取失败（{type(exc).__name__}），仅用公司信息与 LLM 判断")
            fin = {"records": [], "source": "fallback(empty_financials)"}
        rule_result = analyze_business_model(info, fin)
        result = rule_result
        evidence = data_issues + list(rule_result.evidence)
        llm_qualitative = None

        if ctx.llm is not None:  # LLM 定性层（可选）
            try:
                refs = CompanyReferences().fetch(code, slot=0)  # 先抓真实链接供 LLM 筛选
                user_prompt = (
                    f"公司：{info.get('name')}（{code}），行业：{result.industry}，"
                    f"财务摘要：{rule_result.evidence[0]}。\n"
                    f"规则参考类型：{rule_result.business_type}。\n"
                )
                ref_block = format_reference_list(refs)
                if ref_block:
                    user_prompt += ref_block + "\n"
                user_prompt += (
                    "请按以下结构输出 JSON：\n"
                    '{"business_type": "consumer_monopoly|growth|cyclical|financial|asset_based|stable_dividend 之一", '
                    '"business_model": "一句话描述其生意本质", '
                    '"understandability": "可理解|基本可理解|难以理解", '
                    '"reasons": ["判断理由1", "判断理由2"], '
                    '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
                    "business_type 必须从给定枚举中选择一个，优先依据行业属性、盈利模式、周期性、"
                    "资产特征与财务表现综合判断，不要机械跟随规则参考类型。\n"
                    "reasons 至少覆盖两点：为什么是该类型；为什么不是另一个最相近的类型。\n"
                    "reference_indices：从参考资料清单中筛选与「商业模式/可理解性判断」最相关的文章编号"
                    "（1 基），没有相关文章就输出空数组；不得编造标题或链接。"
                )
                text = ctx.stream_llm(_LLM_SYSTEM, user_prompt)
                parsed = parse_llm_json(text)
                if parsed is not None:
                    llm_business_type = normalize_business_type(parsed.get("business_type"))
                    if llm_business_type is not None:
                        result = analyze_business_model(info, fin, business_type=llm_business_type)
                        evidence = data_issues + list(result.evidence)
                        evidence.append(f"LLM 主判生意类型：{llm_business_type}")
                    else:
                        evidence.append("LLM 未给出合法 business_type，已回退规则分类")
                    selected = select_references(refs, parsed.get("reference_indices"))
                    if selected:
                        parsed["references"] = selected
                    else:
                        parsed.pop("references", None)
                    parsed.pop("reference_indices", None)
                    llm_qualitative = parsed
                    evidence.append("LLM 定性：已接入（结构化 JSON）")
                else:
                    llm_qualitative = {"business_model": text}
                    evidence.append("LLM 定性：已接入（输出解析失败，按原文展示）")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，business_type 使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），当前 business_type 使用规则结果")

        outputs = {
            "business_type": result.business_type,
            "business_model": llm_qualitative.get("business_model") if isinstance(llm_qualitative, dict) else result.one_liner,
            "understandability": llm_qualitative.get("understandability") if isinstance(llm_qualitative, dict) and llm_qualitative.get("understandability") else result.understandability,
            "reasons": llm_qualitative.get("reasons") if isinstance(llm_qualitative, dict) else [],
            "industry": result.industry,
            "references": llm_qualitative.get("references") if isinstance(llm_qualitative, dict) else None,
            # 下游契约（§4 M1）：M4 直接读 handoff.valuation_route，不再猜
            "handoff": {
                "valuation_route": result.business_type,
                "understandability_level": _understandability_level(result.understandability),
            },
        }
        # 移除空 references
        if not outputs.get("references"):
            outputs.pop("references", None)

        score = llm_score(
            ctx, self.spec.id,
            facts={
                "行业": outputs.get("industry"),
                "生意类型": outputs.get("business_type"),
                "可理解性": outputs.get("understandability"),
            },
            evidence=evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score,
            outputs=outputs, evidence=evidence,
        )
