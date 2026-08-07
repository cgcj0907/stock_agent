"""M4 估值引擎单元测试：方法级 + 引擎级（路由/区间/覆盖率）。"""
import pytest

import value_agent.agents  # noqa: F401  先加载 agents（builtin→valuation 链），避免循环导入
from value_agent.valuation.engine import run_valuation
from value_agent.valuation.methods import (
    dcf,
    ddm,
    graham_formula,
    graham_number,
    relative_median_pe,
    tang,
)


def test_dcf_has_sensitivity_range():
    r = dcf(4.5, 0.10, 0.10, 0.03)
    assert r.value is not None
    assert r.low < r.value < r.high


def test_tang_buy_sell():
    r = tang(4.5, 0.10, 0.04)
    assert r.params["fair_pe"] == pytest.approx(25, abs=0.1)
    assert r.params["buy"] == pytest.approx(r.value * 0.5)
    assert r.params["sell"] == min(r.value * 1.5, 4.5 * 50)


def test_ddm_requires_r_gt_g():
    assert ddm(2.2, 0.10, 0.10).value is None
    assert ddm(2.2, 0.05, 0.10).value is not None


def test_graham_number():
    r = graham_number(4.5, 31.7)
    assert r.value == pytest.approx(56.67, abs=0.1)


def test_graham_formula():
    assert graham_formula(4.5, 0.10, 0.04).value is not None


def test_relative_median_pe():
    r = relative_median_pe(4.5, [21.0, 21.3])
    assert r.value == pytest.approx(4.5 * 21.15, abs=0.01)


def test_engine_intrinsic_range_and_score():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2)
    assert r.intrinsic["low"] < r.intrinsic["mid"] < r.intrinsic["high"]
    assert r.coverage_score > 0
    assert r.methods["ddm"].value is None  # r<=g 跳过


def test_cyclical_routing_excludes_dcf_tang():
    r = run_valuation(eps=4.5, bvps=30, pe_history=[10, 12, 15], dividend=None, business_type="cyclical")
    assert "dcf" not in r.methods
    assert "tang" not in r.methods
    assert "relative_median_pe" in r.methods


# ---------- M4 智能体：数据源细粒度容错 ----------
def _m4_ctx(data, business_type: str | None = None, inputs: dict | None = None,
            assumptions: dict | None = None, llm=None) -> object:
    from value_agent.agents.base import AgentContext  # 供下方构造 ctx
    from value_agent.sessions.models import Session, SessionStatus

    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    base_assumptions = {"business_type": business_type} if business_type else {}
    if assumptions:
        base_assumptions.update(assumptions)
    return AgentContext(
        session=session, assumptions=base_assumptions, inputs=inputs or {}, data=data, llm=llm
    )


def test_m4_partial_data_failure_still_values():
    """某个数据集失败（如分红）时，M4 仍用其余数据完成估值并标记降级，而不是整模块空白。"""
    from tests.conftest import StubData
    from value_agent.valuation.agent import M4ValuationAgent

    class _NoDividend(StubData):
        def dividends(self, code):
            raise ConnectionError("RemoteDisconnected")

    res = M4ValuationAgent().run(_m4_ctx(_NoDividend()))
    assert res.status.value == "done"
    assert res.outputs["intrinsic_value"] is not None, "部分数据失败也应给出估值"
    assert any("分红数据获取失败" in e for e in res.evidence)
    assert res.meta.get("degraded") is True


def test_m4_all_data_failure_degrades_with_reasons():
    """全部数据集失败时，M4 降级为 DONE（空估值），evidence 说明各失败原因。"""
    from value_agent.valuation.agent import M4ValuationAgent

    class _NoData:
        def financials(self, code, years=10):
            raise ConnectionError("x")

        def valuation_history(self, code):
            raise ConnectionError("x")

        def daily_prices(self, code):
            raise ConnectionError("x")

        def dividends(self, code):
            raise ConnectionError("x")

    res = M4ValuationAgent().run(_m4_ctx(_NoData()))
    assert res.status.value == "done"
    iv = res.outputs["intrinsic_value"]
    assert iv is None or iv.get("mid") is None  # 无有效估值
    assert res.outputs["methods"], "methods 列表仍应存在（applicable=false）"
    assert all(not m["applicable"] for m in res.outputs["methods"])
    assert any("财务数据获取失败" in e for e in res.evidence)
    assert any("估值历史获取失败" in e for e in res.evidence)
    assert any("日线价格获取失败" in e for e in res.evidence)
    assert any("分红数据获取失败" in e for e in res.evidence)
    assert res.meta.get("degraded") is True


# ---------- v2：路由一致性 / 加权汇总 / 质量乘数 / kill switch / PEG / 现金化代理 ----------
def test_routing_yaml_consistent_with_code():
    """路由唯一事实来源 = YAML；DEFAULT_ROUTING 兜底与 YAML 一致，防止漂移。"""
    from value_agent.valuation.engine import DEFAULT_ROUTING, load_routing

    routing = load_routing()
    assert set(routing) == set(DEFAULT_ROUTING)
    for bt in DEFAULT_ROUTING:
        assert sorted(routing[bt]) == sorted(DEFAULT_ROUTING[bt]), f"{bt} 路由不一致"


def test_routing_only_implemented_methods():
    """路由表里不允许出现未实现的方法（避免「理念正确但取不到数」）。"""
    from value_agent.valuation.engine import IMPLEMENTED_METHODS, load_routing

    for methods in load_routing().values():
        assert set(methods) <= IMPLEMENTED_METHODS


def test_intrinsic_is_weighted_median_not_min_max():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2)
    vals = sorted(m.value for m in r.methods.values() if m.value is not None)
    assert len(vals) >= 3
    # 新汇总不再是 min~max 包络
    assert r.intrinsic["low"] > vals[0]
    assert r.intrinsic["high"] < vals[-1]
    assert r.intrinsic["std"] is not None
    assert 0 <= r.intrinsic["method_agreement"] <= 1


def test_valuation_confidence_range_and_coverage_boost():
    full = run_valuation(eps=4.5, bvps=31.7, pe_history=list(range(10, 40)), dividend=2.2)
    thin = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0], dividend=2.2)
    assert 0 <= full.valuation_confidence <= 1
    assert full.valuation_confidence >= thin.valuation_confidence  # 覆盖度更高 → 置信度更高


def test_quality_multiplier_tiers():
    from value_agent.valuation.engine import quality_multiplier

    assert quality_multiplier({"m2": 90, "m5": 85, "m3": 80, "m6": 75})[0] == 1.1
    assert quality_multiplier({"m2": 70, "m5": 65, "m3": 60, "m6": 55})[0] == 1.0
    assert quality_multiplier({"m2": 50, "m5": 45, "m3": 40, "m6": 35})[0] == 0.9
    assert quality_multiplier({"m2": 30, "m5": 20, "m3": 25, "m6": 15})[0] == 0.85


def test_quality_multiplier_fallback_neutral():
    from value_agent.valuation.engine import quality_multiplier

    assert quality_multiplier(None)[0] == 1.0
    assert quality_multiplier({})[0] == 1.0
    assert quality_multiplier({"m2": 90})[0] == 1.1  # 只有 M2 时按单源归一


def test_quality_multiplier_applies_to_intrinsic():
    r_neutral = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2)
    r_good = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2,
                           quality={"m2": 92, "m5": 88, "m3": 80, "m6": 85})
    assert r_good.quality_multiplier == 1.1
    assert r_good.intrinsic["mid"] == pytest.approx(round(r_neutral.intrinsic["mid"] * 1.1, 2))


def test_kill_switch_loss_year_removes_earnings_methods():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2,
                      m2_signals=["LOSS_YEAR"])
    assert "LOSS_YEAR" in r.kill_switches
    assert "dcf" not in r.methods
    assert "tang" not in r.methods
    assert "peg" not in r.methods


def test_kill_switch_ocf_divergence_discounts_dcf():
    r_plain = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2, ocf_to_np=1.2)
    r_risk = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2, ocf_to_np=1.2,
                           m2_signals=["OCF_NP_DIVERGENCE"])
    assert "OCF_NP_DIVERGENCE" in r_risk.kill_switches
    assert r_risk.methods["dcf"].value == pytest.approx(round(r_plain.methods["dcf"].value * 0.85, 2))
    assert r_risk.methods["dcf"].params.get("kill_discount") == 0.85


def test_kill_switch_high_leverage_discounts_overall():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2, debt_to_assets=0.75)
    assert "HIGH_LEVERAGE" in r.kill_switches
    assert r.risk_multiplier == pytest.approx(0.85)


def test_kill_switch_cyclical_down_keeps_relative_asset():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2,
                      m3_cyclicality_flag=True, m3_prosperity_code="down")
    assert "CYCLICAL_DOWN" in r.kill_switches
    assert set(r.methods) <= {"relative_median_pe", "graham_number", "graham_formula", "ddm"}


def test_peg_method():
    from value_agent.valuation.methods import peg

    r = peg(4.5, 0.15, [15.0, 16.0, 14.0])
    assert r.value == pytest.approx(4.5 * 15)  # 增速 15% → PE 15
    assert peg(4.5, 0.0, [15.0]).value is None
    assert peg(4.5, 0.15, []).value is None


def test_dcf_cash_proxy():
    from value_agent.valuation.methods import cash_earnings_proxy, dcf

    r = dcf(4.5, 0.10, 0.10, 0.03, cash_eps=5.4)
    assert r.params["profit_base"] == "cash_proxy"
    assert r.params["cash_eps"] == 5.4
    # ocf_to_np 夹逼到 [0.5, 1.5]，防一次性损益失真
    assert cash_earnings_proxy(4.5, ocf_to_np=3.0) == pytest.approx(4.5 * 1.5)
    assert cash_earnings_proxy(4.5, ocf_to_np=0.2) == pytest.approx(4.5 * 0.5)
    # ocfps 兜底；无现金流字段 → EPS
    assert cash_earnings_proxy(4.5, ocfps=6.0) == pytest.approx(6.0)
    assert cash_earnings_proxy(4.5) == pytest.approx(4.5)
    # 现金化代理 ≤0 → DCF 跳过
    assert dcf(4.5, 0.10, 0.10, 0.03, cash_eps=-1.0).value is None


def test_growth_routing_includes_peg():
    r = run_valuation(eps=4.5, bvps=30, pe_history=[20.0, 22.0, 25.0], dividend=None,
                      business_type="growth", params={"growth_rate": 0.15})
    assert "peg" in r.methods
    assert r.methods["peg"].value == pytest.approx(4.5 * 15)


def test_m4_agent_uses_upstream_quality_and_handoff():
    """M4 消费 M2/M3/M5/M6 输出 → 质量乘数 + kill switch + handoff 契约字段。"""
    from tests.conftest import StubData
    from value_agent.sessions.models import ModuleResult, ModuleStatus
    from value_agent.valuation.agent import M4ValuationAgent

    def _mod(agent_id, outputs, score):
        return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)

    inputs = {
        "M1_business_model": _mod("M1_business_model", {"business_type": "consumer_monopoly"}, 80),
        "M2_financial_quality": _mod("M2_financial_quality", {"signals": [{"code": "LOSS_YEAR"}]}, 30),
        "M3_growth": _mod("M3_growth", {
            "growth_estimate": 0.08,
            "handoff": {"recommended_growth_rate": 0.08, "growth_confidence": "high",
                        "cyclicality_flag": False, "prosperity_code": "up"},
        }, 40),
        "M5_moat": _mod("M5_moat", {"width": "无", "handoff": {"moat_width": "none"}}, 10),
        "M6_governance": _mod("M6_governance", {"handoff": {"governance_score": 30}}, 30),
    }
    res = M4ValuationAgent().run(_m4_ctx(StubData(), inputs=inputs))
    assert res.status.value == "done"
    assert "LOSS_YEAR" in res.outputs["kill_switches"]
    assert res.outputs["quality_multiplier"] is not None
    assert res.outputs["handoff"]["intrinsic_range"]["low"] is not None
    assert 0 <= res.outputs["handoff"]["valuation_confidence"] <= 1
    assert res.outputs["handoff"]["methods_used"]
    assert res.outputs["handoff"]["coverage"] in ("high", "medium", "low")


# ---------- v3：LLM 行业校准（可选层） ----------
from tests.conftest import StubData  # 本文件其他用例在函数内导入


class _FakeLLM:
    """最小 LLM 桩：chat() 返回固定文本（AgentContext.stream_llm 无 stream_chat 时退化用 chat）。"""

    def __init__(self, response: str):
        self._response = response
        self.last_prompt = ""

    def chat(self, system: str, user: str) -> str:
        self.last_prompt = user
        return self._response


def _quality_inputs():
    from value_agent.sessions.models import ModuleResult, ModuleStatus

    def _mod(agent_id, outputs, score):
        return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)

    return {
        "M1_business_model": _mod("M1_business_model", {"business_type": "consumer_monopoly", "industry": "白酒"}, 80),
        "M2_financial_quality": _mod("M2_financial_quality", {"signals": []}, 92),
        "M3_growth": _mod("M3_growth", {
            "growth_estimate": 0.08,
            "handoff": {"recommended_growth_rate": 0.08, "growth_confidence": "high",
                        "cyclicality_flag": False, "prosperity_code": "up"},
        }, 60),
        "M5_moat": _mod("M5_moat", {"width": "宽", "handoff": {"moat_width": "wide"}}, 88),
        "M6_governance": _mod("M6_governance", {"handoff": {"governance_score": 70}}, 70),
    }


def test_llm_parse_calibration_clamps():
    from value_agent.valuation.llm import parse_calibration

    text = ('{"business_type_override": "growth", "route_confidence": 0.9, '
            '"parameter_adjustments": {"growth_rate": 0.99, "discount_rate": 0.05, "terminal_growth": 0.1, "risk_free_rate": 0.0}, '
            '"method_weight_adjustments": {"dcf": 2.0, "peg": 0.1}, '
            '"valuation_confidence_delta": 0.5, '
            '"industry_notes": ["成长股宜用 PEG"], "risk_notes": ["增速回落风险"], "reasons": ["行业惯例"]}')
    calib = parse_calibration(text)
    assert calib["business_type_override"] == "growth"
    assert calib["parameter_adjustments"]["growth_rate"] == 0.20   # clamp 上限
    assert calib["parameter_adjustments"]["discount_rate"] == 0.07  # clamp 下限
    assert calib["parameter_adjustments"]["terminal_growth"] == 0.03
    assert calib["parameter_adjustments"]["risk_free_rate"] == 0.01
    assert calib["method_weight_adjustments"]["dcf"] == 0.5  # clamp 上限
    assert calib["method_weight_adjustments"]["peg"] == 0.1
    assert calib["valuation_confidence_delta"] == 0.1  # clamp 上限


def test_llm_parse_calibration_ignores_invalid_route():
    from value_agent.valuation.llm import parse_calibration

    # 非法生意类型 / 低 route_confidence → 无任何有效校准 → None（保持规则结果）
    assert parse_calibration('{"business_type_override": "科技", "route_confidence": 0.5}') is None
    assert parse_calibration('{"business_type_override": "growth", "route_confidence": 0.3}') is None
    assert parse_calibration("不是 JSON") is None
    assert parse_calibration("{}") is None


def test_llm_apply_calibration_merges():
    from value_agent.valuation.engine import METHOD_WEIGHTS, default_params
    from value_agent.valuation.llm import apply_calibration

    calib = {
        "parameter_adjustments": {"growth_rate": 0.05},
        "method_weight_adjustments": {"dcf": 0.45},
        "business_type_override": "growth",
        "valuation_confidence_delta": 0.05,
    }
    p, w, bt, delta = apply_calibration(default_params(), METHOD_WEIGHTS, calib)
    assert p["growth_rate"] == 0.05
    assert p["discount_rate"] == 0.10  # 未调整项保持
    assert w["dcf"] == 0.45
    assert w["relative_median_pe"] == 0.30  # 未调整项保持
    assert bt == "growth"
    assert delta == 0.05


def test_engine_confidence_delta():
    r = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2, confidence_delta=0.05)
    r0 = run_valuation(eps=4.5, bvps=31.7, pe_history=[21.0, 21.3], dividend=2.2)
    assert r.valuation_confidence == pytest.approx(min(1.0, r0.valuation_confidence + 0.05))


def test_m4_agent_llm_industry_calibration_applies():
    """LLM 行业校准：参数/权重/置信度增量被采用，llm_qualitative 落盘，evidence 有校准摘要。"""
    from value_agent.valuation.agent import M4ValuationAgent

    fake = _FakeLLM(
        '{"business_type_override": null, "route_confidence": 0.0, '
        '"parameter_adjustments": {"growth_rate": 0.05, "discount_rate": 0.08}, '
        '"method_weight_adjustments": {"dcf": 0.45}, '
        '"valuation_confidence_delta": 0.05, '
        '"industry_notes": ["白酒行业现金流好，DCF 权重可上调"], '
        '"risk_notes": ["消费复苏不确定"], "reasons": ["按白酒行业惯例校准"]}'
    )
    res = M4ValuationAgent().run(_m4_ctx(StubData(), inputs=_quality_inputs(), llm=fake))
    assert res.status.value == "done"
    assert res.outputs["params"]["growth_rate"] == 0.05
    assert res.outputs["params"]["discount_rate"] == 0.08
    assert res.outputs["weights"]["dcf"] == 0.45
    assert res.outputs["llm_qualitative"] is not None
    assert res.outputs["llm_qualitative"]["calibration"]["valuation_confidence_delta"] == 0.05
    assert any("行业校准" in e for e in res.evidence)
    assert any("白酒行业现金流好" in e for e in res.evidence)


def test_m4_agent_llm_route_override():
    """LLM 把误路由成 consumer_monopoly 的公司纠正为 financial → 路由切换（禁 DCF）。"""
    from value_agent.valuation.agent import M4ValuationAgent

    fake = _FakeLLM(
        '{"business_type_override": "financial", "route_confidence": 0.9, '
        '"parameter_adjustments": {}, "method_weight_adjustments": {}, '
        '"valuation_confidence_delta": 0.0, "reasons": ["银行/券商应走金融估值"]}'
    )
    res = M4ValuationAgent().run(_m4_ctx(StubData(), inputs=_quality_inputs(), llm=fake))
    assert res.status.value == "done"
    assert res.outputs["business_type"] == "financial"
    assert "dcf" not in res.outputs["methods"]  # financial 路由禁 DCF
    assert any(m["method"] == "ddm" for m in res.outputs["methods"])
    assert any("路由覆盖" in e for e in res.evidence)


def test_m4_agent_llm_parse_failure_keeps_rule_result():
    from value_agent.valuation.agent import M4ValuationAgent

    fake = _FakeLLM("抱歉，我无法给出 JSON。")
    res = M4ValuationAgent().run(_m4_ctx(StubData(), inputs=_quality_inputs(), llm=fake))
    assert res.status.value == "done"
    assert res.outputs["intrinsic_value"]["mid"] is not None
    assert res.outputs["llm_qualitative"] is None
    assert any("解析失败" in e for e in res.evidence)
