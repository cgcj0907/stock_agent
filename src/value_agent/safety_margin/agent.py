"""M8 安全边际智能体：读 M4 估值结果 → 计算折扣/买卖区间（含确定性分级）。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.contracts import ReasonCode, build_meta
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import run_safety_margin


def _risk_level(m2_score: float | None, m3_cyclical: bool | None) -> str:
    """上游风险代理（6.1）：M2 财务质量低或 M3 周期特征 → high；否则 medium。

    不消费 M9（M9 聚合依赖 M8，避免成环），确定性输入取 M5/M2/M3 上游信号。
    """
    if m2_score is not None and m2_score < 60:
        return "high"
    if m3_cyclical:
        return "high"
    return "medium"


class M8SafetyMarginAgent(Agent):
    spec = AgentSpec(
        id="M8_safety_margin",
        name="安全边际智能体",
        description="折扣率/要求折扣/买卖区间（格雷厄姆核心，确定性分级）",
        # 确定性分级（6.1）消费 M5 moat_width + M2 财务风险 + M3 周期/景气（均为上游，无环）
        inputs=["M2_financial_quality", "M3_growth", "M4_valuation", "M5_moat", "M7_market"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        m4 = ctx.inputs.get("M4_valuation")
        if m4 is None or not m4.outputs.get("intrinsic_value"):
            # 降级为 DONE（数据不足）而非 SKIPPED，避免阻断下游 M9/M10/M11
            return ModuleResult(
                module=self.spec.id,
                status=ModuleStatus.DONE,
                score=0.0,
                outputs={
                    "price": None,
                    "buy_price": None,
                    "sell_price": None,
                    "status": "数据不足（依赖 M4 估值结果缺失）",
                    "mos_state": "unavailable",
                    "buy_tranches": [],
                    "reason_codes": [ReasonCode.INPUT_MISSING.value],
                    "handoff": {
                        "mos_state": "unavailable",
                        "buy_zone": None,
                        "sell_zone": None,
                        "buy_tranches": [],
                        "reason_codes": [ReasonCode.INPUT_MISSING.value],
                    },
                },
                evidence=["依赖 M4_valuation 未产出内在价值区间，安全边际按数据不足处理"],
                meta=build_meta(0.0, "low", degraded=True,
                                reason_codes=[ReasonCode.INPUT_MISSING.value]),
            )
        intrinsic = m4.outputs["intrinsic_value"]
        price = m4.outputs.get("current_price")
        business_type = m4.outputs.get("business_type", "consumer_monopoly")
        required_discount = ctx.assumptions.get("required_discount")

        # M7 契约：margin_adjustment 直接叠加到要求折扣（过热更保守 / 低估更宽松）
        m7 = ctx.inputs.get("M7_market")
        margin_adjustment = 0.0
        valuation_percentile = None
        if m7:
            handoff = m7.outputs.get("handoff") or {}
            margin_adjustment = handoff.get("margin_adjustment", 0.0) or 0.0
            valuation_percentile = handoff.get("valuation_percentile")

        # 确定性分级（6.1）：M5 moat_width + M2/M3 风险代理
        moat_width = None
        m5 = ctx.inputs.get("M5_moat")
        if m5:
            moat_width = (m5.outputs.get("handoff") or {}).get("moat_width")
        m2 = ctx.inputs.get("M2_financial_quality")
        m2_score = None
        if m2:
            m2_score = (m2.outputs.get("handoff") or {}).get("quality_score")
            if m2_score is None:
                m2_score = m2.score
        m3 = ctx.inputs.get("M3_growth")
        m3_cyclical = None
        if m3:
            m3_cyclical = bool((m3.outputs.get("handoff") or {}).get("cyclicality_flag", False))
        risk_level = _risk_level(m2_score, m3_cyclical)

        result = run_safety_margin(
            price=price, intrinsic=intrinsic,
            business_type=business_type, required_discount=required_discount,
            margin_adjustment=margin_adjustment,
            moat_width=moat_width, risk_level=risk_level,
            valuation_percentile=valuation_percentile,
        )
        evidence = list(result.evidence)
        if m7 and m7.outputs.get("position") in ("高估", "泡沫"):
            evidence.append(f"M7 估值位置：{m7.outputs['position']}（卖出参考触发）")
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "折扣率": result.discount,
                "要求折扣": result.required_discount,
                "安全边际状态": result.mos_state,
                "状态": result.status,
            },
            evidence=evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=score,
            outputs={
                "price": price,
                "discount": result.discount,
                "required_discount": result.required_discount,
                "buy_price": result.buy_price,
                "sell_price": result.sell_price,
                "buy_tranches": result.buy_tranches,
                "sell_reference": result.sell_reference,
                "status": result.status,
                "mos_state": result.mos_state,
                # 下游契约（§4 M8）：mos_state 供 M10/M11，买卖区间供监控
                "handoff": {
                    "mos_state": result.mos_state,
                    "buy_zone": result.buy_price,
                    "sell_zone": result.sell_price,
                    "buy_tranches": result.buy_tranches,
                    "sell_reference": result.sell_reference,
                    "reason_codes": result.reason_codes,
                },
            },
            evidence=evidence,
            # 6.6：正常态也带 meta.reason_codes（前端按 meta 判断质量/降级）
            meta=build_meta(
                round(score / 100.0, 3),
                "high" if result.mos_state in ("attractive", "fair") else "medium",
                degraded=False,
                reason_codes=result.reason_codes,
            ),
        )
