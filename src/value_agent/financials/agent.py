"""M2 财务质量智能体：取财报数据 → 规则引擎打分 → 输出 ModuleResult。

backlog 12.1：按 M1 的 business_type / financial_subtype 分行业口径（金融/保险/银行
走 lenient 现金流 + industry 杠杆），M1 缺失（如 quick 流）时回退通用口径。
"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .quality import analyze_financial_quality


class M2FinancialQualityAgent(Agent):
    spec = AgentSpec(
        id="M2_financial_quality",
        name="财务质量智能体",
        description="盈利能力(ROE+杜邦)/稳定性/现金流/杠杆/造假信号（按 M1 生意类型分行业口径）",
        inputs=["M1_business_model"],  # 12.1：生意类型/金融细类 → 行业财务口径（M1 缺失可回退）
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M2 需要数据访问（ctx.data），请注入 DataManager")
        code = ctx.session.company_code
        try:
            m1 = ctx.inputs.get("M1_business_model")
            business_type = m1.outputs.get("business_type") if m1 and m1.outputs else None
            financial_subtype = (
                (m1.outputs.get("handoff") or {}).get("financial_subtype")
                if m1 and m1.outputs else None
            )
            fin = ctx.data.financials(code, years=10)
            result = analyze_financial_quality(
                fin["records"],
                business_type=business_type,
                financial_subtype=financial_subtype,
            )
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"财务数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "metrics": {},
                    "signals": [],
                    "summary": {"说明": "财务数据不可用"},
                    "handoff": {"quality_score": None, "risk_signal_codes": []},
                },
            )
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "ROE 最新": result.metrics.get("roe_latest"),
                "净利率": result.metrics.get("net_margin"),
                "现金流/净利最低": result.metrics.get("ocf_to_np_min"),
                "资产负债率": result.metrics.get("debt_to_assets_latest"),
                "造假信号数": len(result.signals),
                "行业口径": (
                    f"{business_type}/{financial_subtype}"
                    if business_type else "通用（M1 缺失）"
                ),
            },
            evidence=result.evidence, default=result.score,
        )
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=score,
            outputs={
                "metrics": result.metrics,
                "signals": [sig.to_dict() for sig in result.signals],
                "summary": result.details,
                # 下游契约（docs/09-module-contracts.md §4 M2）：M9 用 handoff.quality_score /
                # risk_signal_codes，不再读不存在的 outputs["score"]（旧断点：生产恒不触发）
                "handoff": {
                    "quality_score": score,
                    "risk_signal_codes": [sig.code for sig in result.signals],
                },
            },
            evidence=result.evidence,
        )
