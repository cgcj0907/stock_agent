"""M8 安全边际智能体：读 M4 估值结果 → 计算折扣/买卖区间。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.contracts import ReasonCode, build_meta
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import run_safety_margin


class M8SafetyMarginAgent(Agent):
    spec = AgentSpec(
        id="M8_safety_margin",
        name="安全边际智能体",
        description="折扣率/要求折扣/买卖区间（格雷厄姆核心）",
        inputs=["M4_valuation", "M7_market"],
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
                    "reason_codes": [ReasonCode.INPUT_MISSING.value],
                },
                evidence=["依赖 M4_valuation 未产出内在价值区间，安全边际按数据不足处理"],
                meta=build_meta(0.0, "low", degraded=True,
                                reason_codes=[ReasonCode.INPUT_MISSING.value]),
            )
        intrinsic = m4.outputs["intrinsic_value"]
        price = m4.outputs.get("current_price")
        business_type = m4.outputs.get("business_type", "consumer_monopoly")
        required_discount = ctx.assumptions.get("required_discount")

        result = run_safety_margin(
            price=price, intrinsic=intrinsic,
            business_type=business_type, required_discount=required_discount,
        )
        evidence = list(result.evidence)
        m7 = ctx.inputs.get("M7_market")
        if m7 and m7.outputs.get("position") in ("高估", "泡沫"):
            evidence.append(f"M7 估值位置：{m7.outputs['position']}（卖出参考触发）")
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=result.score,
            outputs={
                "price": price,
                "discount": result.discount,
                "required_discount": result.required_discount,
                "buy_price": result.buy_price,
                "sell_price": result.sell_price,
                "status": result.status,
                "mos_state": result.mos_state,
            },
            evidence=evidence,
        )
