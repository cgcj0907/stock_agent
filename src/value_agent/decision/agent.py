"""M10 决策智能体：汇总全模块评分 → 结论 + 仓位建议。

修复点（对齐 docs/09-module-contracts.md §4 M10）：
1. 只消费 spec.inputs 声明的模块（走 ctx.inputs，不直接读全量 session.module_results），
   局部重跑 / 分支工作流下不混入无关结果，模块边界干净；
2. LLM 评分校准后的最终总分仍走 run_decision(total_override=...) 同一决策函数，
   一票否决 / M8 安全边际门禁（expensive → 禁止 buy）不会被 agent 层重算冲掉；
3. 补齐契约字段：qualitative.decision_reasons[] + handoff.decision_code/blocked_by_veto/position；
4. 8.3 LLM 定性理由：LLM 对（维度分, 总分, 档位）给 1–2 条赞成/反对理由，白名单后并入 decision_reasons；
5. 8.7 core_facts 契约分组：{decision, position, dimension_scores, total} 别名与顶层同值。
"""
from __future__ import annotations

import logging

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import run_decision

logger = logging.getLogger(__name__)

_LLM_REASONS_SYSTEM = (
    "你是价值投资决策复核员。基于五维评分与结论档位，给出 1-2 条赞成或反对的定性理由。"
    + LLM_JSON_RULE
)


def _clean_reasons(parsed: dict) -> list[str]:
    """8.3：LLM 理由白名单清洗——只取字符串数组，每条 ≤80 字，最多 3 条。"""
    reasons = parsed.get("reasons")
    if not isinstance(reasons, list):
        return []
    cleaned = []
    for r in reasons:
        if isinstance(r, str) and r.strip():
            cleaned.append(r.strip()[:80])
        if len(cleaned) >= 3:
            break
    return cleaned


class M10DecisionAgent(Agent):
    spec = AgentSpec(
        id="M10_decision",
        name="决策输出智能体",
        description="五维评分卡 + 结论档位 + 仓位建议",
        # 实际消费：维度评分用 M1/M2/M3/M5/M6 score + M4/M7/M8/M9；与 MODULE_DEPENDENCIES[M10] 对齐
        inputs=["M1_business_model", "M2_financial_quality", "M3_growth", "M4_valuation",
                "M5_moat", "M6_governance", "M7_market", "M8_safety_margin", "M9_risk"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        inputs = {aid: ctx.inputs[aid] for aid in self.spec.inputs if aid in ctx.inputs}
        # M0 投资者画像：个人仓位上限（可选，默认 None 不限制）
        m0 = ctx.inputs.get("M0_investor_profile")
        position_cap = None
        if m0 is not None:
            cap = ((m0.outputs or {}).get("handoff") or {}).get("position_cap")
            if cap is not None:
                position_cap = float(cap)
        result = run_decision(inputs, position_cap=position_cap)
        total = result.total
        calib_trace: dict = {}
        if not result.vetoed:  # 一票否决时保持回避，不让 LLM 覆盖
            total = llm_score(
                ctx, self.spec.id,
                facts={
                    "五维评分": result.dimensions,
                    "加权总分": result.total,
                    "结论": result.conclusion,
                    "否决项": result.vetoed,
                },
                evidence=result.evidence, default=result.total,
                trace=calib_trace,
            )
        # 用最终总分（含 LLM 校准）走同一决策函数：否决/M8 门禁/个人仓位上限统一生效
        final = run_decision(inputs, total_override=total, position_cap=position_cap)

        # 8.3：LLM 定性理由（可选增强；失败/无 LLM 时保持纯规则理由）
        reasons = list(final.decision_reasons)
        if ctx.llm is not None and not final.vetoed:
            try:
                prompt = (
                    f"五维评分（0-100，**分数越高越好**；governance_risk 实为治理质量分，"
                    f"85 分代表治理优秀而非高风险）：{final.dimensions}\n"
                    f"加权总分：{final.total}"
                    f"（决策码 {final.decision_code}，建议仓位 {final.position:.0%}）。\n"
                    "请只输出 JSON：{\"reasons\": [\"赞成/反对理由1\", \"理由2\"]}。"
                    "理由必须是基于上述评分的定性解释（如估值保护是否充分、治理/风险是否被充分定价），"
                    "不得编造素材之外的数字或事实，也不得把高分维度解读为负面信号。"
                )
                text = ctx.stream_llm(_LLM_REASONS_SYSTEM, prompt)
                parsed = parse_llm_json(text)
                if parsed is not None:
                    llm_reasons = _clean_reasons(parsed)
                    if llm_reasons:
                        reasons.extend(f"LLM 复核：{r}" for r in llm_reasons)
            except Exception as exc:  # noqa: BLE001
                logger.warning("M10 LLM 定性理由失败，保持规则理由：%s", type(exc).__name__)

        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=final.total,
            calibration=calib_trace or None,
            outputs={
                # 顶层字段（memo/快照/前端向后兼容）
                "dimensions": final.dimensions,
                "total": final.total,
                "conclusion": final.conclusion,
                "position": final.position,
                "vetoed": final.vetoed,
                "decision_code": final.decision_code,
                "blocked_by_veto": final.blocked_by_veto,
                # 契约 §4 M10：定性理由 + 结构化 handoff（M11/审计消费）
                "qualitative": {"decision_reasons": reasons},
                "handoff": {
                    "decision_code": final.decision_code,
                    "blocked_by_veto": final.blocked_by_veto,
                    "position": final.position,
                },
                # 8.7：core_facts 契约分组（与顶层同值，消费方逐步迁移）
                "core_facts": {
                    "decision": final.decision_code,
                    "position": final.position,
                    "dimension_scores": final.dimensions,
                    "total": final.total,
                },
            },
            evidence=list(final.evidence) + [f"LLM 校准：{n}" for n in calib_trace.get("notes", [])],
        )
