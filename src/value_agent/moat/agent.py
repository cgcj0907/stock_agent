"""M5 护城河智能体：规则层财务代理评级 + LLM 定性 → 两层合成最终护城河宽度。

修复点（相对旧版）：
1. 规则层不再自称「护城河结论」，只输出 rule_proxy（财务代理评级）；
2. LLM 定性结果真正回填 handoff：moat_durability / erosion_risks（供 M9 消费）；
3. LLM 的 width 与规则层做冲突处理（width_source + width_conflict），不静默并存；
4. 下游（M4/M9/M10）消费的 handoff.moat_width = 两层合成后的最终宽度。
"""
from __future__ import annotations

import logging

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.data.references import CompanyReferences, format_reference_list, select_references
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import MoatResult, assess_moat

logger = logging.getLogger(__name__)


_MOAT_WIDTH_CODE = {"宽": "wide", "中": "medium", "窄": "narrow", "无": "none"}
_ALLOWED_SOURCES = {"无形资产", "转换成本", "网络效应", "成本优势", "规模/渠道优势"}
_ALLOWED_WIDTH = {"宽", "中", "窄", "无"}
_ALLOWED_DURABILITY = {"high", "medium", "low"}
_ALLOWED_TREND = {"widening", "stable", "eroding"}

_LLM_SYSTEM = (
    "你是价值投资分析师，负责护城河定性判断。规则层已给出「财务代理评级」"
    "（相对行业基准，不完整），你的任务是结合财务信号、同行对比与参考资料，"
    "判断护城河来源（五类）、持久性、趋势与侵蚀风险，并给出独立的宽度判断"
    "（可修正规则层）。"
    + LLM_JSON_RULE
)


def _moat_width_code(width: str) -> str:
    """护城河宽度 → 契约枚举（wide/medium/narrow/none），供 M4/M10 消费。"""
    return _MOAT_WIDTH_CODE.get(width, "none")


def _moat_durability(width: str) -> str:
    """规则层持久性映射（LLM 定性给出合法 durability 时会被覆盖）。"""
    return {"宽": "high", "中": "medium", "窄": "low", "无": "low"}.get(width, "low")


def _clean_qualitative(parsed: dict) -> dict:
    """只保留合法字段的 LLM 定性结果：枚举白名单 + 列表元素清洗（防幻觉字段污染下游）。"""
    out: dict = {}
    srcs = parsed.get("moat_sources")
    if isinstance(srcs, list):
        cleaned = [s for s in srcs if isinstance(s, str) and s in _ALLOWED_SOURCES][:6]
        if cleaned:
            out["moat_sources"] = cleaned
    width = parsed.get("width")
    if isinstance(width, str) and width in _ALLOWED_WIDTH:
        out["width"] = width
    durability = parsed.get("durability")
    if isinstance(durability, str) and durability in _ALLOWED_DURABILITY:
        out["durability"] = durability
    trend = parsed.get("trend")
    if isinstance(trend, str) and trend in _ALLOWED_TREND:
        out["trend"] = trend
    erosion = parsed.get("erosion_risks")
    if isinstance(erosion, list):
        cleaned = [str(x).strip() for x in erosion if isinstance(x, str) and str(x).strip()]
        if cleaned:
            out["erosion_risks"] = cleaned[:6]
    evidence = parsed.get("evidence")
    if isinstance(evidence, list):
        cleaned = [str(x).strip() for x in evidence if isinstance(x, str) and str(x).strip()][:8]
        if cleaned:
            out["evidence"] = cleaned
    return out


def _synthesize_width(rule_tier: str, llm_width: str | None) -> tuple[str, str, bool]:
    """两层合成最终宽度：LLM 给出合法宽度则采用（带冲突标记），否则用规则代理档位。

    返回 (final_width, width_source, conflict)；width_source ∈ rule_proxy | llm。
    """
    if llm_width is None:
        return rule_tier, "rule_proxy", False
    return llm_width, "llm", llm_width != rule_tier


class M5MoatAgent(Agent):
    spec = AgentSpec(
        id="M5_moat",
        name="护城河智能体",
        description="护城河宽度/来源/侵蚀（规则代理评级 + LLM 定性两层合成）",
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M5 需要数据访问（ctx.data）")
        code = ctx.session.company_code

        try:
            fin = ctx.data.financials(code)
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"财务数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "width": "无",
                    "width_source": "degraded",
                    "width_conflict": False,
                    "rule_proxy": {
                        "tier": "无", "score": 0.0, "signals": [],
                        "sources": [], "peer": None, "erosion_signals": [],
                    },
                    "signals": [],
                    "handoff": {
                        "moat_width": "none",
                        "moat_durability": "low",
                        "erosion_risks": [],
                    },
                },
            )

        # 行业/生意类型：优先软读 M1 已产出的 business_type（不声明依赖，避免改工作流）；
        # 否则直接从公司信息 + 财务数据分类（与 M1 共用 classify_business_type，口径一致）。
        industry, business_type = "", None
        try:
            info = ctx.data.company_info(code)
            industry = str(info.get("industry") or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("M5 公司信息获取失败（%s），继续用财务数据", type(exc).__name__)
        m1 = ctx.inputs.get("M1_business_model")
        if m1 and m1.outputs and m1.outputs.get("business_type"):
            business_type = m1.outputs["business_type"]

        try:
            result: MoatResult = assess_moat(fin, industry=industry, business_type=business_type)
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"规则引擎执行失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "width": "无",
                    "width_source": "degraded",
                    "width_conflict": False,
                    "rule_proxy": {
                        "tier": "无", "score": 0.0, "signals": [],
                        "sources": [], "peer": None, "erosion_signals": [],
                    },
                    "signals": [],
                    "handoff": {
                        "moat_width": "none",
                        "moat_durability": "low",
                        "erosion_risks": [],
                    },
                },
            )

        evidence = list(result.evidence)
        qual: dict = {}          # 清洗后的 LLM 定性（合法字段）
        llm_raw: str | None = None  # 解析失败时的原文

        # 初始 handoff：规则层代理评级（LLM 有合法输出时覆盖 durability/erosion）
        handoff = {
            "moat_width": _moat_width_code(result.rule_tier),
            "moat_durability": _moat_durability(result.rule_tier),
            "erosion_risks": list(result.erosion_signals),
        }

        if ctx.llm is not None:
            try:
                refs = CompanyReferences().fetch(code, slot=1)  # 真实链接供 LLM 筛选
                user_prompt = _build_llm_prompt(ctx, result, refs)
                text = ctx.stream_llm(_LLM_SYSTEM, user_prompt)
                if not text:
                    evidence.append("LLM 调用无返回，使用规则结果")
                else:
                    parsed = parse_llm_json(text)
                    if parsed is None:
                        llm_raw = text
                        evidence.append("LLM 定性：已接入（输出解析失败，按原文展示）")
                    else:
                        qual = _clean_qualitative(parsed)
                        selected = select_references(refs, parsed.get("reference_indices"))
                        if selected:
                            qual["references"] = selected
                        if qual:
                            evidence.append("LLM 定性：已接入（结构化 JSON）")
                        else:
                            evidence.append("LLM 定性：已接入但字段全部非法，按规则结果")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），当前为规则引擎结果")

        # 两层合成：最终宽度 + 回填 handoff
        width, width_source, width_conflict = _synthesize_width(
            result.rule_tier, qual.get("width")
        )
        if qual.get("durability"):
            handoff["moat_durability"] = qual["durability"]
        if qual.get("erosion_risks"):
            handoff["erosion_risks"] = qual["erosion_risks"]
        handoff["moat_width"] = _moat_width_code(width)
        if width_conflict:
            evidence.append(
                f"⚠️ 宽度冲突：规则代理={result.rule_tier}，LLM 定性={qual.get('width')}，"
                f"最终采用 LLM（width_source=llm）"
            )

        outputs: dict = {
            "width": width,
            "width_source": width_source,
            "width_conflict": width_conflict,
            "rule_proxy": {
                "tier": result.rule_tier,
                "score": result.score,
                "signals": result.signals,
                "sources": [_s.__dict__ for _s in result.sources],
                "peer": _peer_to_dict(result.peer),
                "erosion_signals": result.erosion_signals,
            },
            "signals": result.signals,
            # 下游契约（docs/09-module-contracts.md §4 M5）：
            # M4/M10 用 moat_width；M9 用 moat_durability + erosion_risks
            "handoff": handoff,
        }
        if qual:
            outputs["llm_qualitative"] = qual
        if llm_raw is not None:
            outputs["llm_qualitative"] = llm_raw

        score = llm_score(
            ctx, self.spec.id,
            facts={
                "规则代理档位": result.rule_tier,
                "代理评分": result.score,
                "最终宽度": width,
                "来源信号数": len(result.sources),
                "侵蚀风险数": len(handoff["erosion_risks"]),
            },
            evidence=evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score,
            outputs=outputs, evidence=evidence,
        )


def _build_llm_prompt(ctx: AgentContext, rule: MoatResult, refs: list[dict]) -> str:
    """组装 LLM 定性提示词：规则层代理评级 + 同行对比 + 参考资料。"""
    code = ctx.session.company_code
    lines = [
        f"公司：{ctx.session.company_name or code}（{code}）。",
        f"规则层财务代理评级：{rule.rule_tier}（{rule.score:.0f}/100）。",
    ]
    if rule.peer:
        p = rule.peer
        lines.append(
            f"同行基准（{p.label}）：ROE {p.roe_company}% vs 中位 {p.roe_median}%；"
            f"利润率 {p.margin_company}% vs 中位 {p.margin_median}%；"
            f"杠杆 {p.debt_company} vs 中位 {p.debt_median}"
        )
    if rule.signals:
        lines.append(f"财务信号：{'；'.join(rule.signals)}")
    if rule.sources:
        lines.append(f"规则层来源线索：{'；'.join(s.source for s in rule.sources)}")
    if rule.erosion_signals:
        lines.append(f"规则层侵蚀信号：{'；'.join(rule.erosion_signals)}")
    ref_block = format_reference_list(refs)
    if ref_block:
        lines.append(ref_block)
    lines.append(
        "请按以下结构输出 JSON：\n"
        '{"moat_sources": ["无形资产", "转换成本", "网络效应", "成本优势", "规模/渠道优势"], '
        '"width": "宽|中|窄|无", '
        '"durability": "high|medium|low", '
        '"trend": "widening|stable|eroding", '
        '"erosion_risks": ["具体侵蚀风险1", "具体侵蚀风险2"], '
        '"evidence": ["关键证据1", "关键证据2"], '
        '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
        "moat_sources 只从五类中选择确有依据的，不要为了凑数乱填；"
        "width 可修正规则层（规则层只是财务代理）；"
        "erosion_risks 给 0-3 条具体、可跟踪的侵蚀风险（没有就空数组）；"
        "reference_indices：从参考资料清单中筛选与「护城河/竞争优势判断」最相关的文章编号"
        "（1 基），没有就输出空数组；不得编造标题或链接。"
        "优先选择较新的资料（新闻/研报以最近 1-2 年内为主），不要把几年前的旧资讯当作当前事实；"
        "引用时以清单中标注的日期为准。"
    )
    return "\n".join(lines)


def _peer_to_dict(peer) -> dict | None:
    if peer is None:
        return None
    return {
        "benchmark": peer.benchmark,
        "label": peer.label,
        "roe_company": peer.roe_company,
        "roe_median": peer.roe_median,
        "margin_key": peer.margin_key,
        "margin_company": peer.margin_company,
        "margin_median": peer.margin_median,
        "debt_company": peer.debt_company,
        "debt_median": peer.debt_median,
    }
