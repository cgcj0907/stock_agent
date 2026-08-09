"""内置 M1–M11 智能体（全部为真实实现，见各模块 agent.py）。"""
from __future__ import annotations

from value_agent.business_model.agent import M1BusinessModelAgent
from value_agent.decision.agent import M10DecisionAgent
from value_agent.financials.agent import M2FinancialQualityAgent
from value_agent.governance.agent import M6GovernanceAgent
from value_agent.growth.agent import M3GrowthAgent
from value_agent.market.agent import M7MarketAgent
from value_agent.moat.agent import M5MoatAgent
from value_agent.monitor.agent import M11MonitorAgent
from value_agent.profile.agent import M0InvestorProfileAgent
from value_agent.risk.agent import M9RiskAgent
from value_agent.safety_margin.agent import M8SafetyMarginAgent
from value_agent.valuation.agent import M4ValuationAgent

from .registry import AgentRegistry


def register_builtin_agents(registry: AgentRegistry) -> AgentRegistry:
    """注册 M0–M11 内置智能体（M0 为可选投资者画像，不进默认流）。"""
    agents = [
        M0InvestorProfileAgent(),
        M1BusinessModelAgent(),
        M2FinancialQualityAgent(),
        M3GrowthAgent(),
        M4ValuationAgent(),
        M5MoatAgent(),
        M6GovernanceAgent(),
        M7MarketAgent(),
        M8SafetyMarginAgent(),
        M9RiskAgent(),
        M10DecisionAgent(),
        M11MonitorAgent(),
    ]
    for agent in agents:
        registry.register(agent)
    return registry
