"""M5 护城河智能体：标准面代理评级 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.links import validate_reference_links
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_moat


def _moat_width_code(width: str) -> str:
    """护城河宽度 → 契约枚举（wide/medium/narrow/none），供 M10 消费。"""
    return {"宽": "wide", "中": "medium", "窄": "narrow", "无": "none"}.get(width, "none")


def _moat_durability(width: str) -> str:
    """持久性代理（规则层）：宽→high / 中→medium / 窄或无→low（LLM 定性后续补充）。"""
    return {"宽": "high", "中": "medium", "窄": "low", "无": "low"}.get(width, "low")



_LLM_SYSTEM = (
    "你是价值投资分析师。基于财务特征判断公司护城河来源"
    "（无形资产/转换成本/网络效应/成本优势/规模）并评级。"
    + LLM_JSON_RULE
)


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

        outputs = {
            "width": result.width,
            "signals": result.signals,
            # 下游契约（§4 M5）：M10 用 moat_width；M9 用 erosion_risks（LLM 定性后填充）
            "handoff": {
                "moat_width": _moat_width_code(result.width),
                "moat_durability": _moat_durability(result.width),
                "erosion_risks": [],
            },
        }
        evidence = list(result.evidence)

        if ctx.llm is not None:
            try:
                text = ctx.llm.chat(
                    _LLM_SYSTEM,
                    f"公司：{ctx.session.company_name or code}，财务信号：{result.signals}。\n"
                    "请按以下结构输出 JSON：\n"
                    '{"moat_sources": ["无形资产", "转换成本"], '
                    '"width": "宽|中|窄|无", '
                    '"evidence": ["关键证据1", "关键证据2"], '
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
