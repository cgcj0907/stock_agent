"""M5 护城河智能体：标准面代理评级 + 可选 LLM 定性。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.data.references import CompanyReferences, format_reference_list, select_references
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
        try:
            fin = ctx.data.financials(code)
            result = assess_moat(fin)
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"财务数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "width": "无",
                    "signals": [],
                    "handoff": {
                        "moat_width": "none",
                        "moat_durability": "low",
                        "erosion_risks": [],
                    },
                },
            )

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
                refs = CompanyReferences().fetch(code, slot=1)  # 先抓真实链接供 LLM 筛选
                user_prompt = f"公司：{ctx.session.company_name or code}，财务信号：{result.signals}。\n"
                ref_block = format_reference_list(refs)
                if ref_block:
                    user_prompt += ref_block + "\n"
                user_prompt += (
                    "请按以下结构输出 JSON：\n"
                    '{"moat_sources": ["无形资产", "转换成本"], '
                    '"width": "宽|中|窄|无", '
                    '"evidence": ["关键证据1", "关键证据2"], '
                    '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
                    "reference_indices：从参考资料清单中筛选与「护城河/竞争优势判断」最相关的文章编号"
                    "（1 基），没有就输出空数组；不得编造标题或链接。"
                    "优先选择较新的资料（新闻/研报以最近 1-2 年内为主），不要把几年前的旧资讯当作当前事实；引用时以清单中标注的日期为准。"
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
            facts={"护城河宽度": result.width, "信号数": len(result.signals)},
            evidence=evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score,
            outputs=outputs, evidence=evidence,
        )
