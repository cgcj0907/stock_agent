"""M4 估值智能体：取数据 → 估值引擎 → 输出 ModuleResult。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.contracts import ReasonCode, build_meta
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import run_valuation

# 方法名 → 一句话说明（methods[].reason 用；note 用于跳过原因）
_METHOD_REASON = {
    "dcf": "两阶段 DCF（含敏感性：增速±2pct / 折现率∓1pct）",
    "tang": "唐朝估值法（三年后合理估值，买点 50% / 卖点 150%）",
    "graham_number": "格雷厄姆数 √(22.5×EPS×每股净资产)",
    "graham_formula": "格雷厄姆公式 EPS×(8.5+2g)×4.4/Y",
    "ddm": "股利折现（D₁/(r−g)）",
    "relative_median_pe": "历史中位 PE × EPS 相对估值",
}


def methods_to_list(methods: dict) -> list[dict]:
    """methods dict → 统一方法数组（docs/09-module-contracts.md §4 M4）。"""
    return [
        {
            "method": name,
            "applicable": m.value is not None,
            "value": m.value,
            "low": m.low,
            "high": m.high,
            "reason": (m.note or _METHOD_REASON.get(name, "")),
            "confidence": 0.8 if m.value is not None else 0.0,
        }
        for name, m in methods.items()
    ]




class M4ValuationAgent(Agent):
    spec = AgentSpec(
        id="M4_valuation",
        name="估值引擎智能体",
        description="方法路由(按生意类型) + 多模型交叉估值",
        inputs=["M1_business_model", "M3_growth"],  # 实际读取：M1 路由 + M3 增速
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M4 需要数据访问（ctx.data），请注入 DataManager")
        code = ctx.session.company_code
        try:
            return self._run_impl(ctx, code)
        except Exception as exc:  # noqa: BLE001
            # 数据源瞬时故障：降级为 DONE（带说明），不阻塞下游 M8/M9/M10/M11
            return ModuleResult(
                module=self.spec.id,
                status=ModuleStatus.DONE,
                score=0.0,
                # 降级态字段集合与正常态一致（§3）：缺值置 None/空，meta 标记 degraded
                outputs={
                    "business_type": "cyclical",
                    "methods": [],
                    "intrinsic_value": None,
                    "current_price": None,
                    "params": {},
                },
                evidence=[f"数据源异常：{type(exc).__name__}（{str(exc)[:80]}），估值降级"],
                meta=build_meta(0.0, "low", degraded=True,
                                reason_codes=[ReasonCode.DATA_UNAVAILABLE.value]),
            )

    def _run_impl(self, ctx: AgentContext, code: str) -> ModuleResult:
        fin = ctx.data.financials(code)
        val = ctx.data.valuation_history(code)
        price = ctx.data.daily_prices(code)
        div = ctx.data.dividends(code)

        # 输入抽取：优先最新年报 EPS（季度记录按 period 倒序，避免取到最旧/亏损期）
        fin_recs = [r for r in fin["records"] if r.get("eps")]
        fin_recs_sorted = sorted(
            fin_recs, key=lambda r: str(r.get("period") or ""), reverse=True
        )
        annual_eps = next(
            (
                r["eps"]
                for r in fin_recs_sorted
                if str(r.get("period", "")).endswith("1231")
            ),
            None,
        )
        eps = annual_eps if annual_eps is not None else (
            fin_recs_sorted[0]["eps"] if fin_recs_sorted else None
        )
        # 按 trade_date 降序取最新
        val_recs = sorted(val["records"], key=lambda r: r.get("trade_date") or "", reverse=True)
        price_recs = sorted(price["records"], key=lambda r: r.get("trade_date") or "", reverse=True)
        close = price_recs[0].get("close") if price_recs else None
        pb = next((r["pb"] for r in val_recs if r.get("pb")), None)
        bvps = close / pb if (close and pb) else None
        # 仅取正 PE：亏损期 PE 为负，会让中位数失真（相对估值无意义）
        pe_history = [
            r["pe_ttm"] for r in val_recs if r.get("pe_ttm") and r["pe_ttm"] > 0
        ]
        dividend = next((r["cash_div_tax"] for r in div["records"] if r.get("cash_div_tax")), None)

        # 业务类型：优先 M1 输出，其次 assumptions
        m1 = ctx.inputs.get("M1_business_model")
        business_type = (
            (m1.outputs.get("business_type") if m1 and m1.outputs else None)
            or ctx.assumptions.get("business_type")
            or "cyclical"  # 未知类型保守按周期（禁 DCF/唐朝，避免增长假设拉宽区间）
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
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "生意类型": business_type,
                "EPS": eps,
                "现价": close,
                "方法覆盖分": result.coverage_score,
            },
            evidence=result.evidence, default=result.coverage_score,
        )
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=score,
            outputs={
                "business_type": result.business_type,
                "methods": methods_to_list(result.methods),
                "intrinsic_value": result.intrinsic,
                "current_price": close,
                "params": result.params,
            },
            evidence=result.evidence,
        )
