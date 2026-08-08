"""函数注册表测试（docs/12-v2-upgrade.md §5）：注册 / 输入输出 schema 校验 / plan-then-execute。"""
from __future__ import annotations

import pytest

from value_agent.tools import ToolError, ToolRegistry, build_tool_registry


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        "math.add", lambda a, b: {"sum": a + b},
        description="加法",
        input_schema={"a": float, "b": float},
        output_schema={"sum": float},
    )
    return reg


def test_builtin_registry_registers_all_tools():
    reg = build_tool_registry()
    assert len(reg.names()) == 14
    assert reg.has("valuation.dcf")
    assert reg.has("valuation.nav")
    assert reg.has("financials.quality")
    assert reg.has("market.percentile")
    assert reg.get("valuation.graham_number") is not None


def test_execute_valid_tool(registry):
    assert registry.execute("math.add", {"a": 1.0, "b": 2.0}) == {"sum": 3.0}


def test_execute_missing_required_param(registry):
    with pytest.raises(ToolError, match="缺少必填参数"):
        registry.execute("math.add", {"a": 1.0})


def test_execute_type_mismatch(registry):
    with pytest.raises(ToolError, match="类型错误"):
        registry.execute("math.add", {"a": 1.0, "b": "x"})


def test_execute_unknown_tool(registry):
    with pytest.raises(ToolError, match="未知工具"):
        registry.execute("nope", {})


def test_execute_plan_runs_sequence(registry):
    out = registry.execute_plan([
        {"tool": "math.add", "params": {"a": 1.0, "b": 2.0}},
        {"tool": "math.add", "params": {"a": 10.0, "b": 20.0}},
    ])
    assert [o["result"]["sum"] for o in out] == [3.0, 30.0]


def test_execute_plan_stops_on_error(registry):
    with pytest.raises(ToolError):
        registry.execute_plan([
            {"tool": "math.add", "params": {"a": 1.0}},
            {"tool": "math.add", "params": {"a": 1.0, "b": 2.0}},
        ])


def test_duplicate_register_rejected():
    reg = ToolRegistry()
    reg.register("x", lambda: {"v": 1}, description="d", input_schema={}, output_schema={"v": int})
    with pytest.raises(ToolError, match="重复注册"):
        reg.register("x", lambda: {"v": 2}, description="d", input_schema={}, output_schema={"v": int})


def test_output_schema_validation_rejects_wrong_type():
    reg = ToolRegistry()
    reg.register("bad", lambda: {"v": "not-int"}, description="d",
                 input_schema={}, output_schema={"v": int})
    with pytest.raises(ToolError, match="类型错误"):
        reg.execute("bad", {})


def test_valuation_method_tool_end_to_end():
    """M4 估值方法经注册表执行：输入校验 + MethodResult → dict + 输出校验。"""
    reg = build_tool_registry()
    res = reg.execute("valuation.graham_number", {"eps": 4.5, "bvps": 31.7})
    assert res["name"] == "graham_number"
    assert res["value"] > 50
    # 可选参数缺省走默认：nav discount 默认 0.80
    res2 = reg.execute("valuation.nav", {"bvps": 10.0})
    assert res2["value"] == pytest.approx(8.0, abs=0.01)


def test_financials_quality_tool_end_to_end():
    """M2 财务质量经注册表执行：records 输入 + 契约输出（score/metrics/signals）。"""
    reg = build_tool_registry()
    out = reg.execute("financials.quality", {"records": [
        {"period": "20241231", "roe": 20, "grossprofit_margin": 40,
         "netprofit_margin": 15, "debt_to_assets": 0.4, "ocf_to_np": 1.0},
    ]})
    assert out["score"] > 70
    assert isinstance(out["metrics"], dict)
    assert isinstance(out["signals"], list)
    assert isinstance(out["evidence"], list)


def test_financials_quality_requires_records():
    reg = build_tool_registry()
    with pytest.raises(ToolError, match="缺少必填参数"):
        reg.execute("financials.quality", {})


def test_market_percentile_tool_end_to_end():
    """M7 价格分位经注册表执行：valuation_history 输入 + position 输出。"""
    reg = build_tool_registry()
    out = reg.execute("market.percentile", {"valuation_history": {"records": [
        {"trade_date": "20250101", "pe_ttm": 20, "pb": 5},
        {"trade_date": "20250102", "pe_ttm": 15, "pb": 4},
        {"trade_date": "20250103", "pe_ttm": 18, "pb": 4.5},
    ]}})
    assert "样本不足" in out["position"] or out["position"] in ("极低估", "低估", "合理", "高估", "泡沫")
    assert isinstance(out["score"], (int, float))
