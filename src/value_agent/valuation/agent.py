"""M4 估值智能体：取数据 → 估值引擎 → 输出 ModuleResult。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import run_valuation


class M4ValuationAgent(Agent):
    spec = AgentSpec(
        id="M4_valuation",
        name="估值引擎智能体",
        description="方法路由(按生意类型) + 多模型交叉估值",
        inputs=["M1_business_model"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M4 需要数据访问（ctx.data），请注入 DataManager")
        code = ctx.session.company_code
        fin = ctx.data.financials(code)
        val = ctx.data.valuation_history(code)
        price = ctx.data.daily_prices(code)
        div = ctx.data.dividends(code)

        # 输入抽取
        fin_recs = [r for r in fin["records"] if r.get("eps")]
        eps = fin_recs[0]["eps"] if fin_recs else None
        # 按 trade_date 降序取最新
        val_recs = sorted(val["records"], key=lambda r: r.get("trade_date") or "", reverse=True)
        price_recs = sorted(price["records"], key=lambda r: r.get("trade_date") or "", reverse=True)
        close = price_recs[0].get("close") if price_recs else None
        pb = next((r["pb"] for r in val_recs if r.get("pb")), None)
        bvps = close / pb if (close and pb) else None
        pe_history = [r["pe_ttm"] for r in val_recs if r.get("pe_ttm")]
        dividend = next((r["cash_div_tax"] for r in div["records"] if r.get("cash_div_tax")), None)

        # 业务类型：优先 M1 输出，其次 assumptions
        m1 = ctx.inputs.get("M1_business_model")
        business_type = (
            (m1.outputs.get("business_type") if m1 and m1.outputs else None)
            or ctx.assumptions.get("business_type")
            or "consumer_monopoly"
        )
        params = {k: ctx.assumptions[k] for k in
                  ("growth_rate", "discount_rate", "terminal_growth", "risk_free_rate")
                  if k in ctx.assumptions}
        # M3 提供的增速估计优先（用户 assumptions 显式覆盖除外）
        m3 = ctx.inputs.get("M3_growth")
        if m3 and m3.outputs.get("growth_estimate") is not None and "growth_rate" not in ctx.assumptions:
            params["growth_rate"] = m3.outputs["growth_estimate"]

        result = run_valuation(
            eps=eps, bvps=bvps, pe_history=pe_history, dividend=dividend,
            business_type=business_type, params=params,
        )
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=result.coverage_score,
            outputs={
                "business_type": result.business_type,
                "methods": {k: {"value": m.value, "low": m.low, "high": m.high, "note": m.note}
                            for k, m in result.methods.items()},
                "intrinsic_value": result.intrinsic,
                "current_price": close,
                "params": result.params,
            },
            evidence=result.evidence,
        )
