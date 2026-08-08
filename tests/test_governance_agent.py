"""M6 治理与资本配置智能体测试：LLM 风险回填 handoff / 分数口径统一 / 治理事件贯通。

重点回归（对应 docs/09-module-contracts.md §4 M6 修复）：
- LLM 合法 governance_risks 回填 handoff.governance_risk_codes（M9 消费闭环），
  非法风险码/严重度被清洗丢弃；
- handoff.governance_score = 最终分数（含 llm_score 校准），与 ModuleResult.score 一致，
  M4/M9/M10 读同一个数；
- 治理事件（非分红证据）从数据源贯通到评分与 risk_codes。
"""
from __future__ import annotations

from tests.conftest import StubData
from value_agent.agents.base import AgentContext
from value_agent.governance.agent import M6GovernanceAgent
from value_agent.sessions.models import Session, SessionStatus


class _FakeLLM:
    """流式 + 阻塞双实现：qualitative 为 LLM 定性 JSON，score 为 llm_score 的评分 JSON。"""

    def __init__(self, qualitative: str, score: str = '{"delta": 0, "reasons": ["ok"]}'):
        self._qualitative = qualitative
        self._score = score

    def chat(self, system, user):
        return self._score

    def stream_chat(self, system, user):
        yield "content", self._qualitative


class _NoRefs:
    """不联网的 CompanyReferences 替身（单测里 references.fetch 不应触发网络）。"""

    def fetch(self, code, slot=0):
        return []


class _EventData(StubData):
    """带治理事件的数据桩：监管处罚 + 控股股东减持。"""

    def governance_events(self, code):
        return {
            "records": [
                {"kind": "regulatory", "date": "2025-06", "reason": "信披违规被处罚"},
                {"kind": "reductions", "holder": "控股股东", "date": "2025-03", "ratio": 0.03},
            ],
        }


def _run(monkeypatch, llm, *, data=None):
    monkeypatch.setattr("value_agent.governance.agent.CompanyReferences", _NoRefs)
    session = Session(id="s1", company_code="600519", company_name="贵州茅台", status=SessionStatus.CREATED)
    ctx = AgentContext(
        session=session, assumptions={}, inputs={},
        data=data or StubData(), llm=llm,
    )
    return M6GovernanceAgent().run(ctx)


def test_llm_qualitative_backfills_governance_risk_codes(monkeypatch):
    """LLM 合法 governance_risks → 回填 handoff.governance_risk_codes + signals（M9 消费）。"""
    llm = _FakeLLM(
        '{"shareholder_alignment": "实控人与小股东利益一致", '
        '"capital_allocation": "分红回购审慎", '
        '"governance_risks": ['
        '  {"code": "REGULATORY_PENALTY", "severity": "high", "description": "信披违规被处罚"}, '
        '  {"code": "SHARE_REDUCTION", "severity": "medium", "description": "控股股东计划减持"}'
        '], '
        '"disclosure_quality": "一般", '
        '"conclusion": "治理中性偏弱", "reference_indices": []}'
    )
    res = _run(monkeypatch, llm)
    assert res.status.value == "done"
    # handoff 真正回填（M9 消费闭环）
    codes = res.outputs["handoff"]["governance_risk_codes"]
    assert {c["code"] for c in codes} == {"REGULATORY_PENALTY", "SHARE_REDUCTION"}
    reg = next(c for c in codes if c["code"] == "REGULATORY_PENALTY")
    assert reg["severity"] == "high" and "信披违规" in reg["description"]
    # signals 契约字段（RiskSignal 兼容）
    signals = res.outputs["signals"]
    assert any(s["code"] == "SHARE_REDUCTION" and s["severity"] == "medium" for s in signals)
    # 定性字段清洗保留
    qual = res.outputs["llm_qualitative"]
    assert qual["shareholder_alignment"] == "实控人与小股东利益一致"
    assert any("已回填 handoff" in e for e in res.evidence)


def test_llm_invalid_risk_codes_fall_back_to_rule(monkeypatch):
    """LLM 风险码/严重度非法 → 全部丢弃，回退规则层（handoff 保留规则 risk_codes）。"""
    llm = _FakeLLM(
        '{"governance_risks": ['
        '  {"code": "FAKE_CODE", "severity": "high", "description": "非法码"}, '
        '  {"code": "SHARE_PLEDGE", "severity": "critical", "description": "严重度越界"}'
        ']}'
    )
    res = _run(monkeypatch, llm)
    # 规则层无事件 → risk_codes 为空；LLM 非法风险被丢弃
    assert res.outputs["handoff"]["governance_risk_codes"] == []
    assert res.outputs["signals"] == []
    assert "llm_qualitative" not in res.outputs  # 字段全非法 → 不写入
    assert any("字段全部非法" in e for e in res.evidence)


def test_no_llm_uses_rule_only(monkeypatch):
    """未配置 LLM → 完全退化为规则引擎结果，handoff 字段集合与正常态一致。"""
    res = _run(monkeypatch, None)
    assert res.outputs["handoff"]["governance_risk_codes"] == []
    assert res.outputs["handoff"]["capital_allocation_flag"] in ("good", "neutral", "poor")
    assert res.outputs["handoff"]["governance_score"] == res.score  # 口径统一
    assert any("未配置 LLM" in e for e in res.evidence)


def test_dividend_yield_computed_in_outputs(monkeypatch):
    """M6 outputs 携带股息率：StubData 现价 101.65，TTM 每股派息 2.0 → 1.97%。"""
    res = _run(monkeypatch, None)
    assert res.outputs["dividend_yield"] == round(2.0 / 101.65, 4)
    assert any("股息率" in e for e in res.evidence)


def test_llm_score_unifies_handoff_governance_score(monkeypatch):
    """llm_score 校准后，handoff.governance_score 与最终分数一致（M4/M9/M10 同口径）。"""
    llm = _FakeLLM('{"shareholder_alignment": "x"}', score='{"delta": 1, "reasons": ["好"], "evidence_refs": [0]}')
    res = _run(monkeypatch, llm)
    assert res.score == 79.0  # 规则 78 + delta 1
    assert res.outputs["handoff"]["governance_score"] == 79.0
    assert res.outputs["handoff"]["capital_allocation_flag"] == "good"


def test_governance_events_flow_through_agent(monkeypatch):
    """数据源治理事件（非分红证据）贯通：扣分 + risk_codes 进 handoff。"""
    res = _run(monkeypatch, None, data=_EventData())
    # StubData 分红 10 期恒定 → 规则 78；监管-15 + 减持-15 = 48
    assert res.outputs["handoff"]["governance_score"] == 48.0
    codes = {c["code"] for c in res.outputs["handoff"]["governance_risk_codes"]}
    assert {"REGULATORY_PENALTY", "SHARE_REDUCTION"} <= codes
    assert res.outputs["handoff"]["capital_allocation_flag"] == "poor"
    assert any("治理事件" in e for e in res.evidence)
