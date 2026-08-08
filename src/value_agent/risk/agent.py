"""M9 风险与否决智能体：聚合风险 + 一票否决 + 可选 LLM 红队批判。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.data.references import CompanyReferences, format_reference_list, select_references
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_risk

_LLM_SYSTEM = (
    "你是投资红队：找出这笔投资最可能出错的三个假设与永久损失路径。"
    + LLM_JSON_RULE
)


def _clean_red_team(parsed: dict) -> dict:
    """8.6：红队输出白名单清洗——permanent_loss_paths 结构化（path/veto_candidate/confidence）。"""
    out: dict = {}
    assumptions = parsed.get("key_assumptions")
    if isinstance(assumptions, list):
        cleaned = [str(x).strip() for x in assumptions if isinstance(x, str) and str(x).strip()]
        if cleaned:
            out["key_assumptions"] = cleaned[:3]
    paths = parsed.get("permanent_loss_paths")
    if isinstance(paths, list):
        cleaned_paths: list[dict] = []
        for p_ in paths:
            if isinstance(p_, str) and p_.strip():
                cleaned_paths.append({"path": p_.strip(), "veto_candidate": False, "confidence": "medium"})
            elif isinstance(p_, dict) and str(p_.get("path") or "").strip():
                conf = str(p_.get("confidence") or "medium")
                conf = conf if conf in ("high", "medium", "low") else "medium"
                cleaned_paths.append({
                    "path": str(p_["path"]).strip()[:200],
                    "veto_candidate": bool(p_.get("veto_candidate", False)),
                    "confidence": conf,
                })
        if cleaned_paths:
            out["permanent_loss_paths"] = cleaned_paths[:3]
    verdict = parsed.get("verdict")
    if isinstance(verdict, str) and verdict.strip():
        out["verdict"] = verdict.strip()[:200]
    return out


class M9RiskAgent(Agent):
    spec = AgentSpec(
        id="M9_risk",
        name="风险与否决智能体",
        description="风险清单 + 一票否决 + 红队批判",
        # 8.5：压力情景接入 M4 内在价值区间（intrinsic_range + current_price）
        inputs=["M2_financial_quality", "M3_growth", "M4_valuation", "M5_moat",
                "M6_governance", "M7_market", "M8_safety_margin"],
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        result = assess_risk(ctx.inputs, ctx.assumptions)
        outputs = {
            "risk_items": result.risk_items,          # Risk Registry（对象数组）
            "vetoes": result.vetoes,                   # 否决对象数组
            "veto": result.veto,                       # 兼容：否决 reason 列表（旧 M10 消费）
            "monitor_candidates": result.monitor_candidates,  # 供 M11 直接转规则
            "max_loss_scenario": result.max_loss_scenario,   # 压力测试（景气腰斩+估值腰斩）
            # 契约 handoff（docs/09-module-contracts.md §4 M9）：M10 用 veto_flags/max_severity
            "handoff": {
                "veto_flags": result.veto_flags,
                "max_severity": result.max_severity,
                "monitor_candidates": result.monitor_candidates,
            },
        }
        evidence = list(result.evidence)

        if ctx.llm is not None:
            try:
                refs = CompanyReferences().fetch(ctx.session.company_code, slot=3)  # 先抓真实链接供 LLM 筛选
                user_prompt = (
                    f"公司：{ctx.session.company_name or ctx.session.company_code}；"
                    f"规则风险清单：{result.risk_items}。\n"
                )
                ref_block = format_reference_list(refs)
                if ref_block:
                    user_prompt += ref_block + "\n"
                user_prompt += (
                    "请按以下结构输出 JSON：\n"
                    '{"key_assumptions": ["假设1", "假设2", "假设3"], '
                    '"permanent_loss_paths": [{"path": "永久损失路径描述", '
                    '"veto_candidate": false, "confidence": "high|medium|low"}], '
                    '"verdict": "一句话反方结论", '
                    '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
                    "permanent_loss_paths 每条必须带 veto_candidate（是否建议一票否决）与 "
                    "confidence（证据置信度）；只有当你非常确定该路径可能导致永久性资本损失"
                    "时才把 veto_candidate 设为 true。\n"
                    "reference_indices：从参考资料清单中筛选与「风险/红队批判」最相关的文章编号"
                    "（1 基），没有就输出空数组；不得编造标题或链接。"
                    "优先选择较新的资料（新闻/研报以最近 1-2 年内为主），不要把几年前的旧资讯当作当前事实；引用时以清单中标注的日期为准。"
                )
                text = ctx.stream_llm(_LLM_SYSTEM, user_prompt)
                parsed = parse_llm_json(text)
                if parsed is not None:
                    red = _clean_red_team(parsed)
                    selected = select_references(refs, parsed.get("reference_indices"))
                    if selected:
                        red["references"] = selected
                    outputs["llm_red_team"] = red
                    evidence.append("LLM 红队：已接入（结构化 JSON）")
                    # 8.6：高置信永久损失路径（veto_candidate=true + confidence=high）
                    # 不自动否决（防幻觉），但进 monitor_candidates 长期跟踪，并在 handoff 标注
                    high_conf = [
                        p_["path"] for p_ in red.get("permanent_loss_paths", [])
                        if isinstance(p_, dict) and p_.get("veto_candidate") and p_.get("confidence") == "high"
                    ]
                    if high_conf:
                        outputs["handoff"]["red_team_veto_candidates"] = high_conf
                        outputs["handoff"]["monitor_candidates"] = list(
                            dict.fromkeys(result.monitor_candidates + [f"red_team:{i}" for i in range(len(high_conf))])
                        )
                        evidence.append(
                            "⚠️ 红队高置信永久损失路径（veto_candidate 建议，待人工确认）："
                            + "；".join(high_conf)
                        )
                else:
                    outputs["llm_red_team"] = text[:2000]  # 3.2：raw 截断防 payload 膨胀
                    evidence.append("LLM 红队：已接入（输出解析失败，按原文展示）")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），红队定性待接入")

        calib: dict = {}
        score = llm_score(
            ctx, self.spec.id,
            facts={"风险项数": len(result.risk_items), "否决项数": len(result.vetoes)},
            evidence=evidence, default=result.score, trace=calib,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score, calibration=calib or None,
            outputs=outputs, evidence=evidence,
        )
