"""内置 M1–M11 智能体。

已实现：M2 财务质量（真实规则引擎，见 financials/quality.py）。
其余为骨架占位，逐个替换为真实逻辑；每个模块规格见 docs/templates/module-spec.md。
"""
from __future__ import annotations

from .base import Agent, AgentContext, AgentSpec
from .registry import AgentRegistry
from value_agent.financials.agent import M2FinancialQualityAgent
from value_agent.business_model.agent import M1BusinessModelAgent
from value_agent.decision.agent import M10DecisionAgent
from value_agent.governance.agent import M6GovernanceAgent
from value_agent.growth.agent import M3GrowthAgent
from value_agent.market.agent import M7MarketAgent
from value_agent.monitor.agent import M11MonitorAgent
from value_agent.risk.agent import M9RiskAgent
from value_agent.moat.agent import M5MoatAgent
from value_agent.safety_margin.agent import M8SafetyMarginAgent
from value_agent.valuation.agent import M4ValuationAgent
from value_agent.sessions.models import ModuleResult, ModuleStatus


def _stub(name: str, description: str) -> AgentSpec:
    return AgentSpec(
        id=name,
        name=description.split("：")[0] if "：" in description else name,
        description=description,
    )


class StubAgent(Agent):
    """占位实现：输出固定结果，保证默认工作流端到端可跑。"""

    spec = _stub("__stub__", "stub")

    def __init__(self, spec: AgentSpec, placeholder: str) -> None:
        self.spec = spec
        self._placeholder = placeholder

    def run(self, ctx: AgentContext) -> ModuleResult:
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=50.0,
            outputs={"placeholder": self._placeholder, "status": "stub"},
            evidence=["builtin stub: 待接入真实实现"],
        )


def register_builtin_agents(registry: AgentRegistry) -> AgentRegistry:
    """注册 M1–M11 内置智能体（骨架实现）。"""
    specs = [
        _stub("M1_business_model", "商业模式认知：生意类型标签 + 能力圈评级"),
        _stub("M2_financial_quality", "财务质量：盈利能力/现金流/造假信号"),
        _stub("M3_growth", "成长与再投资：行业景气 + 增速假设"),
        _stub("M4_valuation", "估值引擎：方法路由 + 多模型交叉"),
        _stub("M5_moat", "护城河：竞争优势类型/宽度 + 证据链"),
        _stub("M6_governance", "治理与资本配置：管理层 + 分红回购"),
        _stub("M7_market", "价格与情绪：估值分位 + 股债性价比"),
        _stub("M8_safety_margin", "安全边际：折扣率 + 买卖区间"),
        _stub("M9_risk", "风险与否决：风险清单 + 一票否决"),
        _stub("M10_decision", "决策输出：评分卡 + 结论 + 备忘录"),
        _stub("M11_monitor", "跟踪监控：持有逻辑验证 + 卖出触发"),
    ]
    for spec in specs:
        if spec.id == M1BusinessModelAgent.spec.id:
            registry.register(M1BusinessModelAgent())
        elif spec.id == M2FinancialQualityAgent.spec.id:
            registry.register(M2FinancialQualityAgent())
        elif spec.id == M3GrowthAgent.spec.id:
            registry.register(M3GrowthAgent())
        elif spec.id == M4ValuationAgent.spec.id:
            registry.register(M4ValuationAgent())
        elif spec.id == M5MoatAgent.spec.id:
            registry.register(M5MoatAgent())
        elif spec.id == M6GovernanceAgent.spec.id:
            registry.register(M6GovernanceAgent())
        elif spec.id == M7MarketAgent.spec.id:
            registry.register(M7MarketAgent())
        elif spec.id == M8SafetyMarginAgent.spec.id:
            registry.register(M8SafetyMarginAgent())
        elif spec.id == M9RiskAgent.spec.id:
            registry.register(M9RiskAgent())
        elif spec.id == M10DecisionAgent.spec.id:
            registry.register(M10DecisionAgent())
        elif spec.id == M11MonitorAgent.spec.id:
            registry.register(M11MonitorAgent())
        else:
            registry.register(StubAgent(spec, placeholder=f"{spec.id} stub"))
    return registry
