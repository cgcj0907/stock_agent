"""M5 护城河智能体 LLM 集成测试：两层合成 / handoff 回填 / 宽度冲突 / 无 LLM 退化。

重点回归（对应 docs/09-module-contracts.md §4 M5 两层制）：
- LLM 定性结果真正回填 handoff.moat_durability / erosion_risks（M9 消费）；
- LLM width 与规则层冲突时显式标记（width_source / width_conflict），不静默并存；
- 未配置 LLM 时完全退化为规则代理评级（字段集合一致）。
"""
from __future__ import annotations

from tests.conftest import StubData
from value_agent.agents.base import AgentContext
from value_agent.moat.agent import M5MoatAgent
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


class _FakeLLM:
    """流式 + 阻塞双实现：qualitative 为 LLM 定性 JSON，score 为 llm_score 的评分 JSON。"""

    def __init__(self, qualitative: str, score: str = '{"score": 70, "reason": "ok"}'):
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


def _run(monkeypatch, llm, *, business_type=None):
    monkeypatch.setattr("value_agent.moat.agent.CompanyReferences", _NoRefs)
    session = Session(id="s1", company_code="600519", company_name="贵州茅台", status=SessionStatus.CREATED)
    inputs = {}
    if business_type:
        inputs["M1_business_model"] = ModuleResult(
            module="M1_business_model", status=ModuleStatus.DONE, score=60.0,
            outputs={"business_type": business_type},
        )
    ctx = AgentContext(
        session=session, assumptions={}, inputs=inputs,
        data=StubData(), llm=llm,
    )
    return M5MoatAgent().run(ctx)


def test_llm_qualitative_backfills_handoff(monkeypatch):
    """LLM 合法输出 → 回填 durability/erosion_risks，width 采用 LLM 并标记冲突。"""
    llm = _FakeLLM(
        '{"moat_sources": ["无形资产", "网络效应"], "width": "宽", "durability": "high", '
        '"trend": "stable", "erosion_risks": ["新进入者低价竞争"], '
        '"evidence": ["品牌力强，提价能力强"], "reference_indices": []}'
    )
    res = _run(monkeypatch, llm)
    assert res.status.value == "done"
    # 两层合成：StubData(ROE18/GM45/杠杆0.35, 白酒) 规则代理=中；LLM=宽 → 采用 LLM + 冲突标记
    assert res.outputs["width"] == "宽"
    assert res.outputs["width_source"] == "llm"
    assert res.outputs["width_conflict"] is True
    assert res.outputs["rule_proxy"]["tier"] == "中"
    # handoff 真正回填（M9 消费）
    assert res.outputs["handoff"]["moat_width"] == "wide"
    assert res.outputs["handoff"]["moat_durability"] == "high"
    assert res.outputs["handoff"]["erosion_risks"] == ["新进入者低价竞争"]
    # LLM 定性字段清洗保留
    assert res.outputs["llm_qualitative"]["moat_sources"] == ["无形资产", "网络效应"]
    assert any("宽度冲突" in e for e in res.evidence)


def test_llm_invalid_fields_fall_back_to_rule(monkeypatch):
    """LLM 字段越界/非法 → 全部丢弃，回退规则代理评级与规则映射的 handoff。"""
    llm = _FakeLLM(
        '{"moat_sources": ["胡诌来源"], "width": "超级宽", "durability": "very_high", '
        '"erosion_risks": "not a list", "evidence": 123}'
    )
    res = _run(monkeypatch, llm)
    assert res.outputs["width"] == "中"          # 规则代理档位
    assert res.outputs["width_source"] == "rule_proxy"
    assert res.outputs["width_conflict"] is False
    assert res.outputs["handoff"]["moat_durability"] == "medium"  # 规则映射：中→medium
    assert res.outputs["handoff"]["erosion_risks"] == []          # Stub 数据稳定，规则无侵蚀信号
    assert "llm_qualitative" not in res.outputs                  # 字段全非法 → 不写入
    assert any("字段全部非法" in e for e in res.evidence)


def test_llm_width_match_no_conflict(monkeypatch):
    """LLM 宽度与规则一致 → 采用 LLM 但无冲突标记。"""
    llm = _FakeLLM('{"width": "中", "durability": "medium", "erosion_risks": []}')
    res = _run(monkeypatch, llm)
    assert res.outputs["width"] == "中"
    assert res.outputs["width_source"] == "llm"
    assert res.outputs["width_conflict"] is False


def test_no_llm_uses_rule_proxy_only(monkeypatch):
    """未配置 LLM → 完全退化为规则代理评级，字段集合与正常态一致。"""
    res = _run(monkeypatch, None)
    assert res.outputs["width"] == "中"
    assert res.outputs["width_source"] == "rule_proxy"
    assert res.outputs["width_conflict"] is False
    assert res.outputs["handoff"]["moat_width"] == "medium"
    assert res.outputs["handoff"]["moat_durability"] == "medium"
    assert res.outputs["handoff"]["erosion_risks"] == []
    assert res.outputs["rule_proxy"]["peer"]["benchmark"] == "consumer_monopoly"  # 白酒→消费垄断基准
    assert any("未配置 LLM" in e for e in res.evidence)


def test_m1_business_type_soft_read(monkeypatch):
    """M1 已运行（business_type=financial）→ 规则层改用金融基准（净利率口径）。"""
    res = _run(monkeypatch, None, business_type="financial")
    assert res.outputs["rule_proxy"]["peer"]["benchmark"] == "financial"
    assert res.outputs["rule_proxy"]["peer"]["margin_key"] == "netprofit_margin"
