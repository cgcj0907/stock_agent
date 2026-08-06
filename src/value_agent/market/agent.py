"""M7 价格与情绪智能体。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_market


def _valuation_percentile(result) -> float | None:
    """估值分位 = max(PE 分位, PB 分位)，供 M8/M10 消费。"""
    vals = [p for p in (result.pe_percentile, result.pb_percentile) if p is not None]
    return max(vals) if vals else None


def _market_state(position: str) -> str:
    """价格位置 → 契约枚举（overheated/normal/cold/insufficient）。"""
    if position in ("极低估", "低估"):
        return "cold"
    if position == "合理":
        return "normal"
    if position in ("高估", "泡沫"):
        return "overheated"
    return "insufficient"


def _margin_adjustment(position: str) -> float:
    """安全边际折扣调整量：过热 +5pct、样本不足 +10pct（保守）、正常 0、低估 −5pct。"""
    return {
        "极低估": -0.05,
        "低估": -0.05,
        "合理": 0.0,
        "高估": 0.05,
        "泡沫": 0.05,
        "样本不足（<10 期）": 0.10,
    }.get(position, 0.0)




class M7MarketAgent(Agent):
    spec = AgentSpec(
        id="M7_market",
        name="价格与情绪智能体",
        description="估值历史分位 + 股债性价比 + 价格位置",
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M7 需要数据访问（ctx.data）")
        val = ctx.data.valuation_history(ctx.session.company_code)
        risk_free = ctx.assumptions.get("risk_free_rate", 0.04)
        result = assess_market(val, risk_free=risk_free)
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "PE 分位": result.pe_percentile,
                "PB 分位": result.pb_percentile,
                "价格位置": result.position,
            },
            evidence=result.evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score,
            outputs={
                "pe_percentile": result.pe_percentile,
                "pb_percentile": result.pb_percentile,
                "position": result.position,
                # 下游契约（§4 M7）：M8 消费 margin_adjustment，M10 消费 market_state
                "handoff": {
                    "valuation_percentile": _valuation_percentile(result),
                    "market_state": _market_state(result.position),
                    "margin_adjustment": _margin_adjustment(result.position),
                },
            },
            evidence=result.evidence,
        )
