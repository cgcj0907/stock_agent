"""M11 跟踪监控智能体：生成监控规则（每日由 monitor --daily 执行）。

消费 M2/M3/M7/M8/M9 信号 + M10 决策（decision_watch 规则），走 ctx.inputs。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import build_monitor_plan


class M11MonitorAgent(Agent):
    spec = AgentSpec(
        id="M11_monitor",
        name="跟踪监控智能体",
        description="生成监控规则：卖出触发 + 验证点 + 风险项",
        # 实际消费：M2/M3/M7/M8/M9 输出 + M10 上下文；与 MODULE_DEPENDENCIES[M11] 对齐
        inputs=["M2_financial_quality", "M3_growth", "M7_market", "M8_safety_margin",
                "M9_risk", "M10_decision"],
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        prior_hits = list(getattr(ctx.session, "monitor_hits", []) or [])
        # 只消费 spec.inputs 声明的模块（含 M10_decision），不直接读全量 session 结果
        inputs = {aid: ctx.inputs[aid] for aid in self.spec.inputs if aid in ctx.inputs}
        plan = build_monitor_plan(inputs, prior_hits=prior_hits)
        evidence = list(plan.evidence)
        if prior_hits:
            evidence.append(f"跨会话记忆：历史监控命中 {len(prior_hits)} 次（warn/critical 回放为回顾规则）")
        calib: dict = {}
        score = llm_score(
            ctx, self.spec.id,
            facts={"规则数": len(plan.rules), "规则类型": [r.rule_type for r in plan.rules]},
            evidence=evidence, default=plan.score, trace=calib,
        )
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score, calibration=calib or None,
            outputs={
                "monitor_rules": [r.__dict__ for r in plan.rules],
                "rule_count": len(plan.rules),
                "prior_hits": prior_hits,
            },
            evidence=evidence,
        )
