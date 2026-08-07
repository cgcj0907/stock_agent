"""M5 护城河智能体：规则层财务代理评级 + LLM 定性 → 两层合成最终护城河宽度。

修复点（相对旧版）：
1. 规则层不再自称「护城河结论」，只输出 rule_proxy（财务代理评级）；
2. LLM 定性结果真正回填 handoff：moat_durability / erosion_risks（供 M9 消费）；
3. LLM 的 width 与规则层做冲突处理（width_source + width_conflict），不静默并存；
4. 下游（M4/M9/M10）消费的 handoff.moat_width = 两层合成后的最终宽度。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

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

# 市场情绪/资金面新闻标题特征：这类资料不能作为护城河（竞争优势）证据，
# 从 M5 参考池中直接剔除，防止 LLM 把「资金热度/股价动量」当成护城河。
_SENTIMENT_TITLE_RE = re.compile(
    r"(净流入|特大单|主力资金|主力净|涨停|涨停潮|连板|龙虎榜|两融|融资余额|融券|"
    r"成交额|换手率|北向资金|游资|跌停|封板|获资金|资金流入|蹭概念|吸筹|拉升|"
    r"异动|出货|洗盘|妖股|题材|炒作|情绪|人气)"
)

# 5.10：竞争优势证据类别关键词（LLM 给的竞争证据必须落在这些类别内，
# 否则视为「股价/情绪凑数」剔除）——与 _SENTIMENT_TITLE_RE 互补。
_COMPETITION_CATEGORY_RE = re.compile(
    r"(订单|份额|市占|成本|技术|专利|牌照|客户|转换成本|网络效应|产能|交付|"
    r"渠道|品牌|规模|壁垒|资质|市占率|市占份额)"
)


def _validate_competition_evidence(items: list) -> list[str]:
    """5.10：竞争证据内容校验——只保留带类别标签（订单/份额/成本/技术/客户/其他）且
    不命中市场情绪词表的证据，防止 LLM 用「股价上涨/机构看好」凑数。"""
    out: list[str] = []
    for x in items:
        if not isinstance(x, str):
            continue
        t = x.strip()
        if not t:
            continue
        if _SENTIMENT_TITLE_RE.search(t):
            continue  # 资金面/情绪表述不是护城河证据
        if not _COMPETITION_CATEGORY_RE.search(t):
            continue  # 无竞争优势类别关键词 → 剔除
        out.append(t[:120])
    return out[:4]


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
    comp = parsed.get("competition_evidence")
    if isinstance(comp, list):
        # 5.10：内容校验（类别标签 + 情绪词过滤）
        cleaned = _validate_competition_evidence(comp)
        if cleaned:
            out["competition_evidence"] = cleaned
    return out


def _load_moat_config() -> dict:
    """5.5：宽度合成门槛进 config/scoring.yaml（moat 段），缺失回退默认。"""
    default = {
        "min_competition_evidence": 1,   # LLM 冲突升级需至少 N 条竞争优势证据
        "downgrade_requires_evidence": False,  # 降级是否同样要求证据
        "allow_without_refs": True,      # 无参考资料时是否放行 LLM 宽度
    }
    for path in (Path("config/scoring.yaml"),
                 Path(__file__).resolve().parents[3] / "config" / "scoring.yaml"):
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cfg = raw.get("moat") or {}
            return {k: cfg.get(k, v) for k, v in default.items()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("scoring.yaml(moat) 读取失败：%s", type(exc).__name__)
            continue
    return default


def _synthesize_width(
    rule_tier: str, llm_width: str | None, has_competitive_evidence: bool = False
) -> tuple[str, str, bool, str]:
    """两层合成最终宽度：LLM 给出合法宽度则采用（带冲突标记），否则用规则代理档位。

    升级门槛（5.5，可配置）：LLM 宽度与规则层**冲突**时，升级必须附带至少
    min_competition_evidence 条竞争优势类证据（订单/份额/成本/技术/客户/牌照/专利等），
    否则不采纳 LLM 宽度、回退规则层——防止 LLM 用「资金面/价格/情绪」等非护城河证据
    把宽度改高/改低。

    返回 (final_width, width_source, conflict, note)；width_source ∈ rule_proxy | llm。
    """
    cfg = _load_moat_config()
    downgrade_requires = bool(cfg.get("downgrade_requires_evidence", False))
    if llm_width is None:
        return rule_tier, "rule_proxy", False, ""
    if llm_width != rule_tier:
        needs_evidence = llm_width in ("宽", "中") or downgrade_requires  # 升级必验；降级按配置
        if needs_evidence and not has_competitive_evidence:
            return (
            rule_tier,
            "rule_proxy",
            False,
            (
                f"LLM 宽度({llm_width})与规则层({rule_tier})冲突，"
                "但未给出竞争优势类证据（订单/份额/成本/技术/客户等），"
                "宽度未采纳，按规则层"
            ),
        )
    return llm_width, "llm", llm_width != rule_tier, ""


class M5MoatAgent(Agent):
    spec = AgentSpec(
        id="M5_moat",
        name="护城河智能体",
        description="护城河宽度/来源/侵蚀（规则代理评级 + LLM 定性两层合成）",
        inputs=["M1_business_model"],  # 5.8：显式声明依赖 M1（business_type 口径统一）
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
                # 参考池过滤：剔除市场情绪/资金面新闻（不能作为护城河证据）
                refs = _filter_competitive_refs(CompanyReferences().fetch(code, slot=1))
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

        # 两层合成：最终宽度（LLM 冲突升级必须附竞争优势证据）+ 回填 handoff
        has_comp_evidence = bool(qual.get("competition_evidence"))
        width, width_source, width_conflict, width_note = _synthesize_width(
            result.rule_tier, qual.get("width"), has_comp_evidence
        )
        if qual.get("durability"):
            handoff["moat_durability"] = qual["durability"]
        if qual.get("erosion_risks"):
            handoff["erosion_risks"] = qual["erosion_risks"]
        handoff["moat_width"] = _moat_width_code(width)
        if width_note:
            evidence.append(f"⚠️ {width_note}")
        if width_conflict:
            evidence.append(
                f"⚠️ 宽度冲突：规则代理={result.rule_tier}，LLM 定性={qual.get('width')}，"
                f"最终采用 LLM（width_source=llm，已附竞争优势证据）"
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
                "cycle_notes": result.cycle_notes,
            },
            "signals": result.signals,
            # 下游契约（docs/09-module-contracts.md §4 M5）：
            # M4/M10 用 moat_width；M9 用 moat_durability + erosion_risks
            "handoff": handoff,
        }
        if qual:
            outputs["llm_qualitative"] = qual
        if llm_raw is not None:
            # 3.2：raw 仅调试用，截断防 API payload 膨胀
            outputs["llm_qualitative"] = llm_raw[:2000]

        score = llm_score(
            ctx, self.spec.id,
            facts={
                "规则代理档位": result.rule_tier,
                "代理评分": result.score,
                "最终宽度": width,
                "来源信号数": len(result.sources),
                "侵蚀风险数": len(handoff["erosion_risks"]),
                "竞争优势证据数": len(qual.get("competition_evidence") or []),
            },
            evidence=evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score,
            outputs=outputs, evidence=evidence,
        )


def _filter_competitive_refs(refs: list[dict]) -> list[dict]:
    """参考池过滤：剔除市场情绪/资金面类新闻（标题命中 _SENTIMENT_TITLE_RE）。

    护城河证据只能是竞争优势类（订单/份额/成本/技术/客户/牌照等）；
    资金流入、涨停、换手、龙虎榜等标题与护城河无关，直接不放给 LLM。
    """
    return [r for r in refs if not _SENTIMENT_TITLE_RE.search(str(r.get("title") or ""))]


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
        '"competition_evidence": ["1-3 条竞争优势证据"], '
        '"evidence": ["关键证据1", "关键证据2"], '
        '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
        "moat_sources 只从五类中选择确有依据的，不要为了凑数乱填；"
        "width 可修正规则层（规则层只是财务代理）；"
        "erosion_risks 给 0-3 条具体、可跟踪的侵蚀风险（没有就空数组）。\n"
        "competition_evidence（竞争优势证据）：只有当你给出的 width 与规则层不一致"
        "（修正/升级/降级）时才必须给出；内容**只能**是竞争优势类事实，例如："
        "订单能见度/在手订单份额、产能与交付能力、市场份额、成本曲线位置、"
        "技术/船型/专利/牌照壁垒、客户结构与转换成本、网络效应。\n"
        "严禁把以下内容当作竞争优势证据：资金流向/净流入、涨跌幅、成交量/换手率、"
        "新闻热度、股价动量、机构评级等市场情绪类信息——它们不是护城河。\n"
        "evidence（证据链）：同样不要包含资金面/价格/情绪类表述，只写竞争优势与行业格局证据；"
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
        "debt_note": peer.debt_note,
    }
