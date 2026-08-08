"""LLM 评分层测试：解析 / 回退 / 模块接入（不依赖外网）。"""
from __future__ import annotations

import pytest

from tests.conftest import StubData
from tests.test_decision import _results
from value_agent.agents.base import AgentContext  # 先加载 agents，避免循环导入
from value_agent.core.scoring import (
    CalibrationProposal,
    calibrate_score,
    llm_score,
    parse_llm_calibration,
)
from value_agent.decision.agent import M10DecisionAgent
from value_agent.sessions import ModuleName
from value_agent.sessions.models import Session, SessionStatus


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def chat(self, system: str, user: str) -> str:
        return self._text


class _QueuedLLM:
    """按调用顺序返回预设文本（模拟同一模块的定性 + 评分两次调用）。"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    def chat(self, system: str, user: str) -> str:
        return self._texts.pop(0)


class _RecordingLLM:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._text


class _RecordingQueuedLLM:
    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._texts.pop(0)


def _ctx(llm=None) -> AgentContext:
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    return AgentContext(
        session=session, assumptions={}, inputs={}, data=StubData(), llm=llm
    )


# ---------- parse_llm_calibration（v2 delta 制） ----------
def test_parse_calibration_valid():
    p = parse_llm_calibration({
        "delta": 5, "reasons": ["r1"], "evidence_refs": [0, 2], "new_facts": ["f"],
    })
    assert p is not None
    assert p.delta == 5
    assert p.reasons == ["r1"]
    assert p.evidence_refs == [0, 2]
    assert p.new_facts == ["f"]


def test_parse_calibration_invalid_returns_none():
    assert parse_llm_calibration(None) is None
    assert parse_llm_calibration({}) is None
    assert parse_llm_calibration({"delta": "abc"}) is None
    assert parse_llm_calibration({"delta": None}) is None
    assert parse_llm_calibration({"delta": float("nan")}) is None
    # 旧绝对分格式不再接受（v2 起只认 delta）
    assert parse_llm_calibration({"score": 82}) is None


def test_parse_calibration_cleans_lists():
    p = parse_llm_calibration({
        "delta": 3, "reasons": ["  短理由  ", 1, "长" * 50],
        "evidence_refs": ["1", "x", 3], "new_facts": ["n"],
    })
    assert p.reasons[0] == "短理由"
    assert len(p.reasons) <= 3
    assert p.evidence_refs == [1, 3]


# ---------- llm_score 辅助（v2 delta 制） ----------
def test_llm_score_applies_delta_when_valid():
    ctx = _ctx(llm=_FakeLLM('{"delta": 5, "reasons": ["好"], "evidence_refs": [0]}'))
    assert llm_score(ctx, "M1_business_model", facts={"行业": "白酒"}, evidence=["品牌强"], default=50) == 55


def test_llm_score_up_without_evidence_rejected():
    """v2 规则 3：抬分无证据 → 拒绝，回退规则分。"""
    ctx = _ctx(llm=_FakeLLM('{"delta": 8, "reasons": ["好"]}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_down_with_reason_applied():
    """v2 规则 4：压分只需理由（审慎原则）。"""
    ctx = _ctx(llm=_FakeLLM('{"delta": -5, "reasons": ["结构缺陷"]}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 45


def test_llm_score_down_without_reason_rejected():
    ctx = _ctx(llm=_FakeLLM('{"delta": -5}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_delta_capped():
    """v2 规则 1：超模块上限 → 截断（M1 cap ±15）。"""
    ctx = _ctx(llm=_FakeLLM('{"delta": 30, "reasons": ["好"], "evidence_refs": [0]}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=["e"], default=50) == 65


def test_llm_score_cap_tightened_by_confidence():
    """v2 规则 2：置信度高 → 上限收紧（M5 cap 15 → confidence=high → ±5）。"""
    ctx = _ctx(llm=_FakeLLM('{"delta": 12, "reasons": ["好"], "evidence_refs": [0]}'))
    assert llm_score(ctx, "M5_moat", facts={}, evidence=["e"], default=50, confidence="high") == 55


def test_llm_score_disabled_module_skips_llm():
    """v2 规则 6/§6.4：纯数值模块禁用校准，且不发起 LLM 调用。"""
    llm = _RecordingLLM('{"delta": 5, "reasons": ["好"], "evidence_refs": [0]}')
    ctx = _ctx(llm=llm)
    assert llm_score(ctx, "M2_financial_quality", facts={}, evidence=["e"], default=50) == 50
    assert llm.calls == []


def test_llm_score_falls_back_on_invalid():
    ctx = _ctx(llm=_FakeLLM('{"reasons": ["没有 delta"]}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_falls_back_without_llm():
    ctx = _ctx(llm=None)
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_falls_back_when_disabled(monkeypatch):
    monkeypatch.setattr("value_agent.core.scoring.scoring_enabled", lambda: False)
    ctx = _ctx(llm=_FakeLLM('{"delta": 5, "reasons": ["好"]}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_fills_trace_dict():
    ctx = _ctx(llm=_FakeLLM('{"delta": 5, "reasons": ["好"], "evidence_refs": [0]}'))
    trace: dict = {}
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=["e"], default=50, trace=trace) == 55
    assert trace["module_id"] == "M1_business_model"
    assert trace["base"] == 50 and trace["final"] == 55
    assert trace["outcome"] == "applied"
    assert trace["delta"] == 5


def test_llm_score_uses_value_investing_prompt():
    llm = _RecordingLLM('{"delta": 0, "reasons": ["合理"]}')
    ctx = _ctx(llm=llm)

    assert llm_score(ctx, "M1_business_model", facts={"行业": "白酒"}, evidence=["品牌强"], default=50) == 50

    system, user = llm.calls[0]
    assert "格雷厄姆" in system
    assert "费雪" in system
    assert "巴菲特" in system
    assert "芒格" in system
    assert "安全边际" in system
    assert "护城河" in system
    assert "不能因为措辞华丽或叙事动人而给高分" in system
    assert "不得脱离素材臆测" in user
    assert "delta" in user
    assert "规则评分" in user


# ---------- M1 接入 ----------
def test_m1_uses_llm_score_and_strips_score_from_qualitative(monkeypatch):
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        '{"business_type": "growth", "confidence": "high", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"], "references": []}',
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.score == 95  # 规则 100 + delta -5（画像 high completeness → 校准上限 ±5）
    assert res.outputs["business_type"] == "growth"
    assert res.outputs["handoff"]["valuation_route"] == "growth"
    assert "score" not in res.outputs


def test_m1_drops_references_when_tool_empty(monkeypatch):
    """工具拿不到真实链接时，直接移除 references，不展示 LLM 编造的内容。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "high", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"], '
         '"references": [{"title": "编造的假链接", "url": "https://example.com/fake"}]}'),
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert "references" not in res.outputs


def test_m1_references_use_tool_real_links(monkeypatch):
    """工具抓到的真实链接优先，覆盖 LLM 编造的链接。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    real_refs = [
        {"title": "2024年年度报告", "url": "https://www.cninfo.com.cn/new/disclosure/detail?a=1"},
    ]
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: real_refs,
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "high", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"], '
         '"references": [{"title": "编造的假链接", "url": "https://example.com/fake"}]}'),
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.outputs["references"] == real_refs


def test_m1_falls_back_to_rule_business_type_when_llm_missing_type(monkeypatch):
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        '{"business_model": "卖酒", "understandability": "可理解", "reasons": ["r"]}',
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.outputs["business_type"] == "consumer_monopoly"
    assert res.outputs["handoff"]["valuation_route"] == "consumer_monopoly"


def test_m1_prompt_requires_exclusive_type_judgment(monkeypatch):
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _RecordingQueuedLLM([
        '{"business_type": "growth", "confidence": "high", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"]}',
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    M1BusinessModelAgent().run(_ctx(llm=llm))
    system, user = llm.calls[0]
    assert "排他判断" in system
    assert "不要把“高增长”直接等同于“成长型”" in system
    assert "为什么是该类型" in user
    assert "为什么不是另一个最相近的类型" in user


# ---------- M10 接入 ----------
def _m10_inputs(results: dict) -> dict:
    """M10 只消费 spec.inputs 声明的模块（走 ctx.inputs，与契约一致）。"""
    return {aid: r for aid, r in results.items() if aid in M10DecisionAgent.spec.inputs}


def test_m10_llm_score_overrides_total_and_band():
    """LLM 校准在 ±15 分内生效：规则 50 → 校准 65 → 关注（watch）。"""
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    results = _results({ModuleName[f"M{i}"].value: 50.0 for i in range(1, 12)})
    session.module_results = results
    ctx = AgentContext(
        session=session, assumptions={}, inputs=_m10_inputs(results),
        llm=_FakeLLM('{"delta": 15, "reasons": ["综合较好"], "evidence_refs": [0]}'),
    )
    res = M10DecisionAgent().run(ctx)
    assert res.score == 65
    assert res.outputs["total"] == 65
    assert res.outputs["decision_code"] == "watch"
    assert "关注" in res.outputs["conclusion"]


def test_m10_llm_score_cap_over_15_capped_to_bound():
    """v2 规则 1 + 8.1 双层保护：LLM delta +40 超 ±15 → 截断至 +15 → 65（watch），并记 evidence。"""
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    results = _results({ModuleName[f"M{i}"].value: 50.0 for i in range(1, 12)})
    session.module_results = results
    ctx = AgentContext(
        session=session, assumptions={}, inputs=_m10_inputs(results),
        llm=_FakeLLM('{"delta": 40, "reasons": ["强行抬分"], "evidence_refs": [0]}'),
    )
    res = M10DecisionAgent().run(ctx)
    assert res.score == pytest.approx(65.0, abs=0.1)  # 截断至 +15，不再回退 50
    assert res.outputs["total"] == pytest.approx(65.0, abs=0.1)
    assert any("校准幅度" in e and "截断" in e for e in res.evidence)
    assert res.outputs["decision_code"] == "watch"


def test_m10_veto_not_overridden_by_llm():
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    results = _results(
        {f"M{i}": 90.0 for i in range(1, 12)}, veto=["fraud_signal_hit"]
    )
    session.module_results = results
    ctx = AgentContext(
        session=session, assumptions={}, inputs=_m10_inputs(results),
        llm=_FakeLLM('{"delta": 40, "reasons": ["x"], "evidence_refs": [0]}'),
    )
    res = M10DecisionAgent().run(ctx)
    assert res.outputs["blocked_by_veto"] is True
    assert res.outputs["decision_code"] == "avoid"
    assert res.outputs["conclusion"] == "回避（触发一票否决）"


def test_m1_filters_references_by_llm_indices(monkeypatch):
    """LLM 通过 reference_indices 筛选对 M1 有用的文章，系统按真实链接还原且不落 reference_indices。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    refs = [
        {"title": "2024年年度报告", "url": "https://www.cninfo.com.cn/a=1"},
        {"title": "茅台提价新闻", "url": "https://finance.eastmoney.com/a=2"},
        {"title": "白酒行业研报", "url": "https://pdf.dfcfw.com/pdf/H3.pdf"},
    ]
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: refs,
    )
    llm = _RecordingQueuedLLM([
        ('{"business_type": "growth", "confidence": "high", "business_model": "卖酒", "understandability": "可理解", '
         '"reasons": ["r"], "reference_indices": [2, 3]}'),
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    # 提示词里应包含参考资料清单
    user_prompt = llm.calls[0][1]
    assert "参考资料清单" in user_prompt
    assert "1. 2024年年度报告" in user_prompt
    # 过滤结果：只保留 2、3 号真实链接
    assert [r["title"] for r in res.outputs["references"]] == ["茅台提价新闻", "白酒行业研报"]
    assert "reference_indices" not in res.outputs


# ---------- calibrate_score（v2 核心：证据/截断/档位保护） ----------
def test_calibrate_zero_delta_is_noop():
    final, trace = calibrate_score(50.0, CalibrationProposal(delta=0, reasons=["合理"]), evidence=[], cap=15.0)
    assert final == 50.0
    assert trace.outcome == "applied"


def test_calibrate_applies_in_cap():
    final, trace = calibrate_score(50.0, CalibrationProposal(delta=5, reasons=["r"], evidence_refs=[0]),
                                   evidence=["e"], cap=15.0)
    assert final == 55.0
    assert trace.outcome == "applied"


def test_calibrate_caps_oversize_delta():
    final, trace = calibrate_score(50.0, CalibrationProposal(delta=30, reasons=["r"], evidence_refs=[0]),
                                   evidence=["e"], cap=15.0)
    assert final == 65.0
    assert trace.outcome == "capped"
    assert any("CALIBRATION_CAPPED" in n for n in trace.notes)


def test_calibrate_rejects_up_without_evidence():
    final, trace = calibrate_score(50.0, CalibrationProposal(delta=8, reasons=["r"]), evidence=[], cap=15.0)
    assert final == 50.0
    assert trace.outcome == "rejected_no_evidence"


def test_calibrate_rejects_down_without_reason():
    final, trace = calibrate_score(50.0, CalibrationProposal(delta=-8), evidence=["e"], cap=15.0)
    assert final == 50.0
    assert trace.outcome == "rejected_no_reason"


def test_calibrate_accepts_new_facts_as_evidence():
    final, trace = calibrate_score(50.0, CalibrationProposal(delta=8, reasons=["r"], new_facts=["行业景气回升"]),
                                   evidence=[], cap=15.0)
    assert final == 58.0
    assert trace.outcome == "applied"


def test_calibrate_clamps_to_0_100():
    final, _ = calibrate_score(98.0, CalibrationProposal(delta=10, reasons=["r"], evidence_refs=[0]),
                               evidence=["e"], cap=15.0)
    assert final == 100.0
    final, _ = calibrate_score(3.0, CalibrationProposal(delta=-10, reasons=["r"]), evidence=[], cap=15.0)
    assert final == 0.0


def test_calibrate_band_protection_blocks_borderline_cross():
    """v2 规则 5：base 78（watch，距 80 档位 2 分）→ 83 跨强档；new_facts 不足 2 → 封顶在档内。"""
    final, trace = calibrate_score(78.0, CalibrationProposal(delta=5, reasons=["r"], evidence_refs=[0],
                                                             new_facts=["f"]),
                                   evidence=["e"], cap=15.0)
    assert final == 78.0
    assert trace.outcome == "band_protected"


def test_calibrate_band_protection_allows_with_enough_new_facts():
    final, trace = calibrate_score(78.0, CalibrationProposal(delta=5, reasons=["r"], evidence_refs=[0],
                                                             new_facts=["f1", "f2"]),
                                   evidence=["e"], cap=15.0)
    assert final == 83.0
    assert trace.outcome == "applied"


def test_calibrate_band_protection_allows_clear_cross():
    """base 70（距 80 档位 10 分）→ 85 跨强档：未贴近阈值 → 放行。"""
    final, trace = calibrate_score(70.0, CalibrationProposal(delta=15, reasons=["r"], evidence_refs=[0]),
                                   evidence=["e"], cap=15.0)
    assert final == 85.0
    assert trace.outcome == "applied"


# ---------- v2 P2：配置一致性 + trace 落库 ----------
def test_llm_calibration_yaml_consistent_with_code():
    """llm_calibration.yaml 为唯一事实来源；只锁结构与字段，不锁数值（cap/enabled 是调参项）。

    数值允许 YAML ≠ 代码兜底常量（这正是配置的意义——校准值由 A/B 数据驱动回写）；
    结构必须完整：每个代码已知模块在 YAML 都有条目、字段齐全、数值类型合法，防漂移。
    """
    from value_agent.core.scoring import (
        BAND_MARGIN,
        CALIBRATION_POLICY,
        DEFAULT_CALIBRATION,
        MIN_NEW_FACTS_TO_CROSS,
        load_calibration_config,
    )

    policy, band = load_calibration_config()
    assert policy is not None and band is not None
    required = {"enabled", "cap", "require_evidence_for_up"}
    # 代码兜底的每个模块在 YAML 中都有条目，且字段齐全（结构一致，数值可调）
    for mid in CALIBRATION_POLICY:
        meta = policy[mid]
        assert required <= set(meta), f"{mid} 缺少字段：{required - set(meta)}"
        assert isinstance(meta["enabled"], bool), f"{mid} enabled 非布尔"
        assert isinstance(meta["cap"], (int, float)) and meta["cap"] >= 0, f"{mid} cap 非法"
        assert isinstance(meta["require_evidence_for_up"], bool), f"{mid} require_evidence_for_up 非布尔"
    default = policy["__default__"]
    assert required <= set(default)
    assert default["enabled"] in (True, False) and default["cap"] >= 0
    assert isinstance(band["margin"], (int, float)) and band["margin"] >= 0
    assert isinstance(band["min_new_facts_to_cross"], int) and band["min_new_facts_to_cross"] >= 1
    # 兜底常量仍可用（YAML 缺失时），确保 fallback 不会崩
    assert DEFAULT_CALIBRATION["enabled"] in (True, False)
    assert DEFAULT_CALIBRATION["cap"] >= 0
    assert BAND_MARGIN >= 0 and MIN_NEW_FACTS_TO_CROSS >= 1


def test_llm_score_disabled_module_records_trace():
    """禁用模块（M2）：不调用 LLM，trace 记 outcome=disabled（审计「为什么没校准」）。"""
    llm = _RecordingLLM('{"delta": 5, "reasons": ["好"], "evidence_refs": [0]}')
    ctx = _ctx(llm=llm)
    trace: dict = {}
    assert llm_score(ctx, "M2_financial_quality", facts={}, evidence=["e"], default=50, trace=trace) == 50
    assert trace["outcome"] == "disabled"
    assert trace["module_id"] == "M2_financial_quality"
    assert trace["final"] == 50
    assert llm.calls == []


def test_llm_score_no_llm_records_trace():
    ctx = _ctx(llm=None)
    trace: dict = {}
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50, trace=trace) == 50
    assert trace["outcome"] == "disabled"


def test_llm_score_parse_failure_records_trace():
    ctx = _ctx(llm=_FakeLLM('{"reasons": ["没有 delta"]}'))
    trace: dict = {}
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50, trace=trace) == 50
    assert trace["outcome"] == "fallback"
    assert any("解析失败" in n for n in trace["notes"])


def test_m1_attaches_calibration_trace(monkeypatch):
    """模块级 trace 挂到 ModuleResult.calibration（随快照/持久化落库）。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        '{"business_type": "growth", "confidence": "high", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"]}',
        '{"delta": -5, "reasons": ["模式清晰"]}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.score == 95  # 规则 100 + delta -5（high completeness → cap ±5）
    assert res.calibration is not None
    assert res.calibration["outcome"] == "applied"
    assert res.calibration["delta"] == -5
    assert res.calibration["final"] == 95


def test_confidence_from_completeness_mapping():
    """v2 P5 接线：completeness → 校准置信度（high→±5 / medium→±10 / low→±15）。"""
    from value_agent.core.scoring import CONFIDENCE_CAP, confidence_from_completeness

    assert confidence_from_completeness("high") == "high"
    assert confidence_from_completeness("medium") == "medium"
    assert confidence_from_completeness("low") == "low"
    assert confidence_from_completeness("bogus") == "medium"  # 非法回落
    assert CONFIDENCE_CAP["high"] == 5.0
    assert CONFIDENCE_CAP["low"] == 15.0
